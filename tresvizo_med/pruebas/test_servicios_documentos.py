"""Borradores de alta, documentos, catálogo y evolución."""
import hashlib
from pathlib import Path

import pytest
from django.conf import settings

from tresvizo_med.dominio.errores import DataError
from tresvizo_med.models import BorradorAlta, Documento, Paciente
from tresvizo_med.servicios import NoEncontrado, PermisoDenegado, VersionConflict, borradores, consultas, documentos, pacientes
from .conftest import datos_consulta, datos_paciente


@pytest.fixture
def paciente(medico):
    return pacientes.guardar(medico, datos_paciente('Ana Muñoz'))


def test_alta_con_borrador_privado_documentos_y_registro_idempotente(medico, otro_medico, imagen):
    borrador = borradores.guardar_borrador(medico, {'name': 'Luis Pérez', 'phone': '555'})
    assert [b.id for b in borradores.propios(medico)] == [borrador.id] and not borradores.propios(otro_medico).exists()
    with pytest.raises(NoEncontrado):
        borradores.guardar_borrador(otro_medico, {'name': 'x'}, identificador=borrador.id)
    with pytest.raises(NoEncontrado):
        documentos.listar(otro_medico, borrador=borrador.id)
    foto = documentos.agregar(medico, imagen('foto.png'), borrador=borrador.id, categoria='Fotografía clínica')
    assert foto.paciente_id is None and foto.borrador_id == borrador.id
    paciente = borradores.registrar(medico, borrador.id, {'name': 'Luis Pérez', 'phone': '555', 'photo_attachment_id': str(foto.id)})
    foto.refresh_from_db()
    assert foto.paciente_id == paciente.id and foto.borrador_id is None and paciente.foto_documento == foto.id
    assert paciente.datos['registration_draft'] == str(borrador.id) and paciente.revision == 1
    otra_vez = borradores.registrar(medico, borrador.id, {'name': 'Luis Pérez'})
    assert otra_vez.id == paciente.id and Paciente.objects.count() == 1
    assert not borradores.propios(medico).exists()


def test_descartar_borrador_y_ajeno(medico, otro_medico):
    borrador = borradores.guardar_borrador(medico, {'name': 'x'})
    with pytest.raises(NoEncontrado):
        borradores.descartar(otro_medico, borrador.id)
    borradores.descartar(medico, borrador.id)
    with pytest.raises(NoEncontrado):
        borradores.guardar_borrador(medico, {'name': 'y'}, identificador=borrador.id)
    with pytest.raises(DataError, match='descartado'):
        borradores.registrar(medico, borrador.id, {'name': 'x'})


def test_registro_con_nombre_invalido_no_deja_paciente_ni_mueve_documentos(medico, imagen):
    borrador = borradores.guardar_borrador(medico, {'name': ''})
    documento = documentos.agregar(medico, imagen(), borrador=borrador.id)
    with pytest.raises(DataError):
        borradores.registrar(medico, borrador.id, {'name': ' '})
    documento.refresh_from_db(), borrador.refresh_from_db()
    assert documento.borrador_id == borrador.id and borrador.estado == 'Borrador' and not Paciente.objects.exists()


def test_documento_guarda_original_con_sha_y_lo_verifica_al_leer(medico, paciente, imagen):
    origen = imagen('a.png')
    documento = documentos.agregar(medico, origen, paciente=paciente.id, categoria='Estudio', notas='Placa')
    esperado = hashlib.sha256(origen.read_bytes()).hexdigest()
    assert documento.sha256 == esperado and documento.mime == 'image/png' and documento.tamano == origen.stat().st_size
    ruta = documentos.ruta_verificada(medico, documento.id)
    assert ruta.read_bytes() == origen.read_bytes() and ruta.is_relative_to(Path(settings.TV_MED_ARCHIVOS))
    assert not list((documentos.raiz()/'preparacion').glob('*'))
    ruta.write_bytes(b'alterado')
    with pytest.raises(DataError, match='integridad'):
        documentos.ruta_verificada(medico, documento.id)
    ruta.unlink()
    with pytest.raises(DataError, match='ausente'):
        documentos.ruta_verificada(medico, documento.id)


def test_documentos_duplicados_versiones_y_operacion_idempotente(medico, paciente, imagen):
    origen = imagen('a.png')
    primero = documentos.agregar(medico, origen, paciente=paciente.id, operacion='op1')
    assert documentos.agregar(medico, origen, paciente=paciente.id, operacion='op1').id == primero.id
    with pytest.raises(DataError, match='idéntico'):
        documentos.agregar(medico, origen, paciente=paciente.id)
    version = documentos.agregar(medico, imagen('b.png', color='red'), paciente=paciente.id, reemplaza=primero.id)
    assert version.version_de_id == primero.id
    permitido = documentos.agregar(medico, origen, paciente=paciente.id, permitir_duplicado=True)
    assert Documento.objects.filter(paciente=paciente).count() == 3 and permitido.id != primero.id
    assert len(documentos.listar(medico, paciente.id)) == 3


def test_validaciones_de_archivo_y_categoria(medico, paciente, tmp_path, imagen):
    falso = tmp_path/'falso.png'
    falso.write_bytes(b'no es una imagen')
    with pytest.raises(DataError):
        documentos.agregar(medico, falso, paciente=paciente.id)
    with pytest.raises(DataError, match='categoría'):
        documentos.agregar(medico, imagen(), paciente=paciente.id, categoria='Inventada')
    assert not Documento.objects.exists() and not list(documentos.raiz().glob('originales/*'))


def test_destino_inexistente_cruzado_o_ajeno(medico, otro_medico, paciente, imagen):
    otro = pacientes.guardar(medico, datos_paciente('Otro'))
    borrador = consultas.guardar(medico, datos_consulta(paciente))
    with pytest.raises(DataError, match='no pertenece'):
        documentos.agregar(medico, imagen(), paciente=otro.id, consulta=borrador.id)
    with pytest.raises(NoEncontrado):
        documentos.agregar(otro_medico, imagen(), paciente=paciente.id, consulta=borrador.id)
    with pytest.raises(NoEncontrado):
        documentos.agregar(medico, imagen(), paciente='00000000-0000-0000-0000-000000000009')
    with pytest.raises(DataError):
        documentos.agregar(medico, imagen(), paciente=paciente.id, borrador=borrador.id)


def test_documento_de_consulta_ajena_en_borrador_no_se_lista(medico, otro_medico, paciente, imagen):
    borrador = consultas.guardar(medico, datos_consulta(paciente))
    documentos.agregar(medico, imagen(), paciente=paciente.id, consulta=borrador.id)
    assert len(documentos.listar(medico, paciente.id)) == 1
    assert documentos.listar(otro_medico, paciente.id) == []


def test_documento_en_consulta_finalizada_exige_motivo_y_deja_adenda(medico, paciente, imagen):
    final = consultas.guardar(medico, datos_consulta(paciente, 'Finalizada'))
    with pytest.raises(DataError, match='motivo'):
        documentos.agregar(medico, imagen(), paciente=paciente.id, consulta=final.id)
    assert not Documento.objects.exists()
    documento = documentos.agregar(medico, imagen(), paciente=paciente.id, consulta=final.id, motivo='Resultado tardío')
    adenda = final.adendas.get()
    assert adenda.documento_id == documento.id and 'Documento incorporado' in adenda.contenido
    anulada = consultas.anular(medico, final.id, 'Duplicada')
    with pytest.raises(DataError, match='anulada'):
        documentos.agregar(medico, imagen('c.png', color='blue'), paciente=paciente.id, consulta=anulada.id, motivo='x')


def test_actualizar_metadatos_con_conflicto_historial_y_permiso(medico, otro_medico, admin, paciente, imagen):
    documento = documentos.agregar(medico, imagen(), paciente=paciente.id)
    cambiado = documentos.actualizar(medico, documento.id, {'title': 'Placa', 'document_date': '2026-09-01', 'sha256': 'x'}, 1)
    assert cambiado.titulo == 'Placa' and cambiado.fecha_documento.isoformat() == '2026-09-01' and cambiado.revision == 2
    assert cambiado.sha256 == documento.sha256 and cambiado.historial[0]['previous']['title'] == documento.titulo
    with pytest.raises(VersionConflict):
        documentos.actualizar(medico, documento.id, {'title': 'Otro'}, 1)
    with pytest.raises(PermisoDenegado):
        documentos.actualizar(otro_medico, documento.id, {'title': 'Ajeno'}, 2)
    assert documentos.actualizar(admin, documento.id, {'archived': True}, 2).archivado
    assert documentos.listar(medico, paciente.id) == [] and len(documentos.listar(medico, paciente.id, archivados=True)) == 1
    with pytest.raises(DataError):
        documentos.actualizar(medico, documento.id, {'title': ' '}, 3)


def test_actualizar_en_consulta_finalizada_deja_adenda(medico, paciente, imagen):
    borrador = consultas.guardar(medico, datos_consulta(paciente))
    documento = documentos.agregar(medico, imagen(), paciente=paciente.id, consulta=borrador.id)
    consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', id=str(borrador.id)), 1)
    with pytest.raises(DataError, match='motivo'):
        documentos.actualizar(medico, documento.id, {'title': 'Nuevo'}, 1)
    documentos.actualizar(medico, documento.id, {'title': 'Nuevo'}, 1, motivo='Corrección')
    assert borrador.adendas.get().documento_id == documento.id


def test_miniatura_y_informe_de_integridad(medico, admin, paciente, imagen):
    documento = documentos.agregar(medico, imagen(tamano=(400, 200)), paciente=paciente.id)
    miniatura = documentos.miniatura(medico, documento.id, 160)
    assert miniatura.is_file() and miniatura.name == f'{documento.id}-160.png'
    informe = documentos.informe_integridad(admin)
    assert informe == {'documents': 1, 'missing': [], 'unreferenced': [], 'pending': []}
    documentos.ruta_absoluta(documento).unlink()
    (documentos.raiz()/'originales'/'suelto.png').write_bytes(b'x')
    informe = documentos.informe_integridad(admin)
    assert informe['missing'] == [str(documento.id)] and informe['unreferenced'] == ['suelto.png']
    with pytest.raises(PermisoDenegado):
        documentos.informe_integridad(medico)


def test_una_restriccion_de_base_exige_un_solo_destino(medico, paciente):
    from django.db import IntegrityError, transaction
    from django.utils import timezone
    ahora = timezone.now()
    with pytest.raises(IntegrityError), transaction.atomic(using='med'):
        Documento.objects.create(doctor_id=1, categoria='Otro documento', mime='image/png', tamano=1, sha256='0'*64,
                                 titulo='x', nombre_original='x', ruta='x', created_at=ahora, updated_at=ahora)


def test_catalogo_de_medicamentos_y_favoritos_por_medico(medico, otro_medico):
    primero = borradores.guardar_catalogo(medico, {'name': 'Paracetamol', 'strength': '500 mg'}, favorito=True)
    mismo = borradores.guardar_catalogo(otro_medico, {'name': ' paracetamol', 'strength': '500 mg'}, favorito=True)
    otro = borradores.guardar_catalogo(medico, {'name': 'Paracetamol', 'strength': '1 g'})
    assert primero.id == mismo.id != otro.id
    filas = {f['strength']: f for f in borradores.catalogo(medico, 'PARACETA')}
    assert set(filas['500 mg']['favorites']) == {medico.cuenta_id, otro_medico.cuenta_id} and filas['1 g']['favorites'] == []
    borradores.alternar_favorito(medico, primero.id, False)
    filas = {f['strength']: f for f in borradores.catalogo(medico, 'paracetamol')}
    assert filas['500 mg']['favorites'] == [otro_medico.cuenta_id]
    with pytest.raises(DataError):
        borradores.guardar_catalogo(medico, {'name': ' '})


def test_evolucion_solo_finalizadas_no_archivadas(medico, paciente):
    def toma(momento, sistolica):
        return [{'at': momento, 'values': {'systolic': {'value': sistolica, 'unit': 'mmHg'}}}]
    consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', vitals=toma('2026-09-02T10:00:00', '130')))
    consultas.guardar(medico, datos_consulta(paciente, 'Finalizada', vitals=toma('2026-09-01T10:00:00', '120')))
    consultas.guardar(medico, datos_consulta(paciente, vitals=toma('2026-09-03T10:00:00', '999')))
    puntos = borradores.evolucion(medico, paciente.id, 'systolic')
    assert [p['value'] for p in puntos] == [120, 130]
