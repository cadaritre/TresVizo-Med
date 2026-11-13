"""Consultas: borradores privados, finalización, adendas sin sobrescribir, anulación y conflictos."""
import pytest
from django.db import connections

from tresvizo_med.dominio.editing_state import merge_draft
from tresvizo_med.dominio.errores import DataError
from tresvizo_med.models import Adenda, ColaDocumentos, Consulta
from tresvizo_med.servicios import NoEncontrado, PermisoDenegado, VersionConflict, consultas, estadisticas, pacientes
from .conftest import datos_consulta, datos_paciente

MEDICAMENTO = {'name': 'Producto sintético', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral', 'frequency': '12',
               'frequency_kind': 'Cada N horas'}
SIGNOS = {'at': '2026-09-10T10:00:00', 'values': {'weight': {'value': '70', 'unit': 'kg'}}}


@pytest.fixture
def paciente(medico):
    return pacientes.guardar(medico, datos_paciente('Ana Muñoz', birth_date='1990-05-01', sex='Mujer'))


def finalizada(actor, paciente, **extra):
    return consultas.guardar(actor, datos_consulta(paciente, 'Finalizada', **extra))


def test_borrador_y_finalizacion_conservan_autoria_y_contenido(medico, paciente):
    borrador = consultas.guardar(medico, datos_consulta(paciente, subjective='Dolor de cabeza', vitals=[SIGNOS],
                                                        prescriptions=[MEDICAMENTO]))
    assert borrador.doctor_id == borrador.captured_by == medico.cuenta_id and borrador.revision == 1
    assert borrador.contenido['subjective'] == 'Dolor de cabeza' and borrador.contenido['vitals'][0]['values']['weight']['normalized_value'] == 70
    final = consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', id=str(borrador.id), subjective='Dolor de cabeza',
                                                     vitals=[SIGNOS], prescriptions=[MEDICAMENTO]), borrador.revision)
    assert final.estado == 'Finalizada' and final.revision == 2 and final.id == borrador.id
    assert final.atendida_iso == '2026-09-10T10:15:23-06:00' and final.atendida_en.utcoffset().total_seconds() == -6*3600


def test_finalizar_exige_motivo_diagnostico_y_plan(medico, paciente):
    for faltante in ('reason', 'assessment', 'plan'):
        datos = datos_consulta(paciente, 'Finalizada')
        datos[faltante] = ' '
        with pytest.raises(DataError):
            consultas.guardar(medico, datos)
    assert not Consulta.objects.exists()


def test_capturas_pendientes_y_archivos_sin_incorporar_bloquean_la_finalizacion(medico, paciente):
    borrador = consultas.guardar(medico, datos_consulta(paciente))
    with pytest.raises(DataError, match='capturas'):
        consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', id=str(borrador.id), editor_state={'pending': {'x': 1}}), 1)
    ColaDocumentos.objects.create(profesional_id=medico.cuenta_id, destino=f'consulta:{borrador.id}',
                                  filas=[{'status': 'Pendiente de copia / reintento'}], actualizado=borrador.updated_at)
    with pytest.raises(DataError, match='archivos'):
        consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', id=str(borrador.id)), 1)


def test_medicamentos_incompletos_no_se_finalizan(medico, paciente):
    with pytest.raises(DataError):
        finalizada(medico, paciente, prescriptions=[{'name': 'Producto', 'dose': '1'}])


def test_el_borrador_es_privado_de_su_responsable(medico, otro_medico, paciente):
    borrador = consultas.guardar(medico, datos_consulta(paciente))
    assert [c.id for c in consultas.visibles(medico)] == [borrador.id]
    assert not consultas.visibles(otro_medico).exists()
    with pytest.raises(NoEncontrado):
        consultas.obtener(otro_medico, borrador.id)
    with pytest.raises(DataError, match='responsable'):
        consultas.guardar(otro_medico, datos_consulta(paciente, id=str(borrador.id)), 1)
    consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', id=str(borrador.id)), 1)
    assert consultas.visibles(otro_medico).count() == 1


def test_consulta_finalizada_no_cambia_solo_admite_adendas(medico, paciente):
    final = finalizada(medico, paciente)
    with pytest.raises(DataError, match='adenda'):
        consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', id=str(final.id), reason='Otro motivo'), final.revision)
    with pytest.raises(DataError):
        consultas.guardar(medico, datos_consulta(paciente, 'Borrador', id=str(final.id)), final.revision)
    final.refresh_from_db()
    assert final.motivo == 'Dolor' and final.estado == 'Finalizada'


def test_un_registro_vinculado_no_cambia_de_paciente(medico, paciente):
    otro = pacientes.guardar(medico, datos_paciente('Otro'))
    borrador = consultas.guardar(medico, datos_consulta(paciente))
    with pytest.raises(DataError, match='paciente original'):
        consultas.guardar(medico, datos_consulta(otro, id=str(borrador.id)), 1)


def test_paciente_archivado_no_inicia_atencion(medico, admin, paciente):
    pacientes.archivar(admin, paciente.id, 'Duplicado')
    with pytest.raises(DataError, match='Reactiva'):
        consultas.guardar(medico, datos_consulta(paciente))


def test_conflicto_de_dos_pestanas_se_resuelve_sin_perdida(medico, paciente):
    base = consultas.guardar(medico, datos_consulta(paciente, reason='Base'))
    base_dict = consultas.como_dict(medico, base)
    remoto = consultas.guardar(medico, {**datos_consulta(paciente, id=str(base.id)), 'reason': 'Remoto', 'plan': 'Plan remoto'}, 1)
    local = {**base_dict, 'reason': 'Local', 'subjective': 'Nota local'}
    with pytest.raises(VersionConflict) as error:
        consultas.guardar(medico, local, 1)
    fusion, conflictos = merge_draft(base_dict, local, error.value.current)
    assert set(conflictos) == {'reason'} and fusion['plan'] == 'Plan remoto' and fusion['subjective'] == 'Nota local'
    fusion['reason'] = conflictos['reason']['local']
    guardada = consultas.guardar(medico, {**fusion, 'status': 'Borrador'}, remoto.revision)
    assert guardada.motivo == 'Local' and guardada.plan == 'Plan remoto' and guardada.atendida_iso == base_dict['attended_at']


def test_adendas_se_agregan_sin_sobrescribir(medico, otro_medico, paciente):
    final = finalizada(medico, paciente)
    primera = consultas.agregar_adenda(otro_medico, final.id, 'Aclaración', 'Texto uno')
    segunda = consultas.agregar_adenda(medico, final.id, 'Resultado', 'Texto dos')
    final.refresh_from_db()
    assert final.revision == 3 and final.motivo == 'Dolor'
    d = consultas.como_dict(medico, final)
    assert [a['content'] for a in d['addenda']] == ['Texto uno', 'Texto dos']
    assert d['addenda'][0]['actor'] == otro_medico.cuenta_id and primera.id != segunda.id
    with pytest.raises(DataError):
        consultas.agregar_adenda(medico, final.id, ' ', 'x')
    borrador = consultas.guardar(medico, datos_consulta(paciente))
    with pytest.raises(DataError, match='finalizadas'):
        consultas.agregar_adenda(medico, borrador.id, 'm', 'c')


def test_las_adendas_son_inmutables_en_orm_y_en_la_base(medico, paciente):
    final = finalizada(medico, paciente)
    adenda = consultas.agregar_adenda(medico, final.id, 'Aclaración', 'Texto')
    adenda.contenido = 'Alterado'
    with pytest.raises(PermissionError):
        adenda.save()
    with pytest.raises(PermissionError):
        adenda.delete()
    with pytest.raises(PermissionError):
        Adenda.objects.all().update(contenido='x')
    with pytest.raises(PermissionError):
        Adenda.objects.all().delete()
    from django.db import DatabaseError, transaction
    with connections['med'].cursor() as cursor:
        for sql in ("UPDATE med_adenda SET contenido = 'x'", 'DELETE FROM med_adenda'):
            with pytest.raises(DatabaseError, match='solo se agregan'), transaction.atomic(using='med'):
                cursor.execute(sql)
    assert Adenda.objects.get(pk=adenda.pk).contenido == 'Texto'


def test_anular_y_restaurar_con_permisos_y_estadisticas(medico, otro_medico, admin, paciente):
    final = finalizada(medico, paciente)
    rango = ('2026-09-01', '2026-09-30')
    assert estadisticas.calcular(medico, *rango)['consultations'] == 1
    with pytest.raises(PermisoDenegado):
        consultas.anular(otro_medico, final.id, 'Duplicada')
    with pytest.raises(DataError):
        consultas.anular(medico, final.id, ' ')
    anulada = consultas.anular(medico, final.id, 'Duplicada')
    assert anulada.estado == 'Anulada' and anulada.adendas.get().tipo == 'anulacion'
    assert estadisticas.calcular(medico, *rango)['consultations'] == 0
    with pytest.raises(DataError):
        consultas.anular(medico, final.id, 'otra vez')
    with pytest.raises(PermisoDenegado):
        consultas.restaurar(otro_medico, final.id, 'Error')
    restaurada = consultas.restaurar(admin, final.id, 'Error de captura')  # el administrador puede con cualquiera
    assert restaurada.estado == 'Finalizada' and [a.tipo for a in restaurada.adendas.all()] == ['anulacion', 'restauracion']
    assert estadisticas.calcular(medico, *rango)['consultations'] == 1
    assert consultas.anular(admin, final.id, 'Revisión').estado == 'Anulada'
    with pytest.raises(DataError, match='finalizadas'):
        consultas.anular(medico, consultas.guardar(medico, datos_consulta(paciente)).id, 'x')


def test_anulada_tampoco_cambia_de_contenido(medico, paciente):
    final = finalizada(medico, paciente)
    anulada = consultas.anular(medico, final.id, 'Duplicada')
    with pytest.raises(DataError):
        consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', id=str(final.id)), anulada.revision)


def test_atender_nunca_crea_dos_borradores(medico, otro_medico, paciente):
    primero, nuevo = consultas.iniciar(medico, paciente.id)
    segundo, creado = consultas.iniciar(medico, paciente.id)
    assert nuevo and not creado and primero.id == segundo.id
    ajeno, creado = consultas.iniciar(otro_medico, paciente.id)
    assert creado and ajeno.id != primero.id
    consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', id=str(primero.id)), 1)
    assert consultas.iniciar(medico, paciente.id)[1]


def test_papelera_privada_de_borradores(medico, otro_medico, paciente):
    borrador = consultas.guardar(medico, datos_consulta(paciente))
    with pytest.raises(DataError):
        consultas.papelera(otro_medico, borrador.id, 'x')
    retirado = consultas.papelera(medico, borrador.id, 'Duplicado')
    assert retirado.archivada and not consultas.visibles(medico).exists() and consultas.visibles(medico, True).exists()
    with pytest.raises(DataError, match='Restaura'):
        consultas.guardar(medico, datos_consulta(paciente, id=str(borrador.id)), retirado.revision)
    recuperado = consultas.papelera(medico, borrador.id, 'Error', restaurar_borrador=True)
    assert not recuperado.archivada and [e['action'] for e in recuperado.lifecycle] == ['archivar', 'restaurar']
    final = finalizada(medico, paciente)
    with pytest.raises(DataError):
        consultas.papelera(medico, final.id, 'x')


def test_solo_los_medicos_escriben_clinica(admin, medico, paciente):
    with pytest.raises(PermisoDenegado):
        consultas.guardar(admin, datos_consulta(paciente))
    final = finalizada(medico, paciente)
    with pytest.raises(PermisoDenegado):
        consultas.agregar_adenda(admin, final.id, 'm', 'c')


def test_estadisticas_por_rol(medico, otro_medico, admin, paciente):
    finalizada(medico, paciente)
    finalizada(otro_medico, paciente, attended_at='2026-09-12T10:00:00-06:00')
    rango = ('2026-09-01', '2026-09-30')
    assert estadisticas.calcular(medico, *rango)['consultations'] == 1
    assert estadisticas.calcular(admin, *rango, doctor='*')['consultations'] == 2
    assert estadisticas.calcular(admin, *rango, doctor=otro_medico.cuenta_id)['consultations'] == 1
    with pytest.raises(PermisoDenegado):
        estadisticas.calcular(medico, *rango, doctor='*')
    with pytest.raises(PermisoDenegado):
        estadisticas.calcular(medico, *rango, doctor=otro_medico.cuenta_id)
    resultado = estadisticas.calcular(medico, *rango, grupo='Nuevos')
    assert resultado['patients'] == 1 and resultado['sexes'] == {'Mujer': 1}
