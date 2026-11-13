"""Pacientes: folio, búsqueda, validaciones, conflictos y archivo."""
import pytest

from tresvizo_med.dominio.errores import DataError
from tresvizo_med.models import Paciente
from tresvizo_med.servicios import PermisoDenegado, VersionConflict, pacientes
from .conftest import datos_paciente


def test_alta_asigna_folio_secuencial_y_autoria(medico):
    a = pacientes.guardar(medico, datos_paciente('Ana Muñoz', phone='5551234', email='ana@correo.mx'))
    b = pacientes.guardar(medico, datos_paciente('Luis Pérez'))
    assert (a.folio, b.folio) == ('RC-000001', 'RC-000002')
    assert a.created_by == a.updated_by == medico.cuenta_id and a.revision == 1
    assert a.datos['email'] == 'ana@correo.mx' and a.telefono == '5551234'


def test_busqueda_sin_acentos_ni_mayusculas_por_nombre_folio_y_telefono(medico):
    ana = pacientes.guardar(medico, datos_paciente('Ana Muñoz', phone='5551234'))
    pacientes.guardar(medico, datos_paciente('Luis Pérez', preferred_name='Lucho'))
    assert [p['name'] for p in pacientes.buscar(medico, 'MUNOZ')[0]] == ['Ana Muñoz']
    assert [p['name'] for p in pacientes.buscar(medico, 'lucho')[0]] == ['Luis Pérez']
    assert [p['name'] for p in pacientes.buscar(medico, '5551')[0]] == ['Ana Muñoz']
    assert [p['name'] for p in pacientes.buscar(medico, ana.folio.lower())[0]] == ['Ana Muñoz']
    assert [p['name'] for p in pacientes.buscar(medico, 'ana mun')[0]] == ['Ana Muñoz']
    assert pacientes.buscar(medico, 'nadie')[1] == 0
    assert len(pacientes.buscar(medico)[0]) == 2


def test_paginacion_de_cien_y_ajuste_de_pagina(medico):
    for n in range(103):
        pacientes.guardar(medico, datos_paciente(f'Paciente {n:03d}'))
    filas, total, pagina = pacientes.buscar(medico, '', 'Activos', 0)
    assert (len(filas), total, pagina) == (100, 103, 0)
    filas, total, pagina = pacientes.buscar(medico, '', 'Activos', 9)
    assert (len(filas), pagina) == (3, 1)
    assert filas[0]['name'] == 'Paciente 100'


def test_homonimos_se_distinguen_por_folio(medico):
    pacientes.guardar(medico, datos_paciente('Juan López', birth_date='1980-01-01'))
    pacientes.guardar(medico, datos_paciente('Juan López', birth_date='1990-02-02'))
    filas = pacientes.buscar(medico, 'juan lopez')[0]
    assert len(filas) == 2 and filas[0]['file_number'] != filas[1]['file_number']


@pytest.mark.parametrize('datos', [
    {'name': '  '}, {'name': 'X', 'birth_date': '2999-01-01'}, {'name': 'X', 'birth_date': 'mal'},
    {'name': 'X', 'birth_date': '2000-01-01', 'approx_age': {'value': 5}},
    {'name': 'X', 'allergy_records': [{'name': 'Penicilina'}], 'allergy_status': 'Sin alergias conocidas'},
    {'name': 'X', 'photo_attachment_id': '00000000-0000-0000-0000-000000000009'}, {'name': 'X', 'photo_attachment_id': 'mal'}])
def test_validaciones(medico, datos):
    with pytest.raises(DataError):
        pacientes.guardar(medico, datos)
    assert not Paciente.objects.exists()


def test_edicion_con_revision_y_conflicto_de_dos_pestanas(medico):
    paciente = pacientes.guardar(medico, datos_paciente('Ana', phone='1'))
    base = {'id': str(paciente.id), 'name': 'Ana', 'phone': '1'}
    pacientes.guardar(medico, {**base, 'phone': '2'}, paciente.revision)
    with pytest.raises(VersionConflict) as error:
        pacientes.guardar(medico, {**base, 'phone': '3'}, paciente.revision)
    assert error.value.current['phone'] == '2' and error.value.current['revision'] == 2
    paciente.refresh_from_db()
    assert paciente.telefono == '2' and paciente.folio == 'RC-000001'


def test_edicion_conserva_folio_y_archivo(medico, admin):
    paciente = pacientes.guardar(medico, datos_paciente('Ana'))
    pacientes.archivar(admin, paciente.id, 'Duplicado')
    editado = pacientes.guardar(medico, {'id': str(paciente.id), 'name': 'Ana María', 'archived': False}, 2)
    assert editado.archivado is True and editado.folio == paciente.folio and editado.nombre_norm == 'ana maria'


def test_archivar_y_restaurar_solo_administrador(medico, admin):
    paciente = pacientes.guardar(medico, datos_paciente('Ana'))
    with pytest.raises(PermisoDenegado):
        pacientes.archivar(medico, paciente.id, 'Duplicado')
    with pytest.raises(DataError):
        pacientes.archivar(admin, paciente.id, ' ')
    archivado = pacientes.archivar(admin, paciente.id, 'Duplicado')
    assert archivado.archivado and archivado.lifecycle[0]['action'] == 'archivar'
    assert pacientes.buscar(medico)[1] == 0 and pacientes.buscar(medico, '', 'Archivados')[1] == 1
    assert pacientes.buscar(medico, '', 'Todos')[1] == 1
    restaurado = pacientes.archivar(admin, paciente.id, 'Error', restaurar=True)
    assert not restaurado.archivado and [e['action'] for e in restaurado.lifecycle] == ['archivar', 'restaurar']
    with pytest.raises(DataError):
        pacientes.archivar(admin, paciente.id, 'x', revision=1)


def test_secuencia_de_folios_tras_importar(medico):
    pacientes.reiniciar_secuencia(500)
    assert pacientes.guardar(medico, datos_paciente('A')).folio == 'RC-000501'
    pacientes.reiniciar_secuencia(10)  # nunca retrocede
    assert pacientes.guardar(medico, datos_paciente('B')).folio == 'RC-000502'


def test_modo_invalido(medico):
    with pytest.raises(DataError):
        pacientes.buscar(medico, '', 'Nada')


def test_posibles_duplicados_por_nombre_o_telefono_sin_fusionar(medico):
    ana = pacientes.guardar(medico, datos_paciente('Ana Muñoz', phone='555 1234'))
    luis = pacientes.guardar(medico, datos_paciente('Luis Pérez', phone='555 9999'))
    assert [p.id for p in pacientes.posibles_duplicados({'name': 'ANA MUNOZ'})] == [ana.id]
    assert [p.id for p in pacientes.posibles_duplicados({'name': 'Otra', 'phone': '555 9999'})] == [luis.id]
    assert pacientes.posibles_duplicados({'name': 'Ana Muñoz'}, excluir=ana.id) == []
    assert pacientes.posibles_duplicados({'name': 'Nadie', 'phone': ''}) == []
    assert Paciente.objects.count() == 2
