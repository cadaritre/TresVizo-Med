"""Permisos con tvplataforma, módulo, enrutador de bases, apariencia e identidad."""
import io
import json

import pytest
from django.core.management import call_command
from django.db import connections

from tresvizo_med.dominio.errores import DataError
from tresvizo_med.dominio.themes import BUILTINS
from tresvizo_med.models import Clinica, Paciente, Profesional
from tresvizo_med.modulo import MODULO
from tresvizo_med.servicios import Actor, NoEncontrado, PermisoDenegado, apariencia, clinica, pacientes
from .conftest import datos_paciente


def test_modulo_declarado_y_descubierto():
    from tvplataforma.modulos import modulo, modulos_instalados
    assert [m.clave for m in modulos_instalados()] == ['med'] and modulo('med') is MODULO
    assert MODULO.url == '/med/' and MODULO.claves_de_roles == {'admin', 'medico'} and MODULO.rutas_publicas == ()
    call_command('check')


def test_las_migraciones_estan_al_dia():
    out = io.StringIO()
    call_command('makemigrations', 'med', check=True, dry_run=True, stdout=out)


def test_el_actor_sale_de_los_roles_del_portal(fabrica_actor):
    solo_medico = Actor.de(fabrica_actor('medico'))
    assert solo_medico.es_medico and not solo_medico.es_admin
    admin = Actor.de(fabrica_actor('admin'))
    assert admin.es_admin and not admin.es_medico
    ambos = Actor.de(fabrica_actor('admin', 'medico'))
    assert ambos.es_admin and ambos.es_medico
    dueno = Actor.de(fabrica_actor(superusuario=True))
    assert dueno.es_admin and dueno.es_medico


def test_sin_rol_de_med_todo_es_404(fabrica_actor, crear_usuario, roles):
    with pytest.raises(NoEncontrado):
        Actor.de(fabrica_actor())
    inactivo = crear_usuario('inactivo', activo=False)
    roles.conceder(inactivo, 'med', 'medico')
    with pytest.raises(NoEncontrado):
        Actor.de(inactivo)
    from django.contrib.auth.models import AnonymousUser
    with pytest.raises(NoEncontrado):
        Actor.de(AnonymousUser())


def test_suspender_a_un_medico_lo_saca_en_la_siguiente_peticion(fabrica_actor, roles):
    usuario = fabrica_actor('medico')
    assert Actor.de(usuario).es_medico
    roles.revocar(usuario, 'med')
    with pytest.raises(NoEncontrado):
        Actor.de(usuario)


def test_el_prefijo_de_med_responde_404_sin_rol_y_redirige_sin_sesion(client, cliente_con_rol):
    assert client.get('/med/pacientes/').status_code == 302
    assert 'entrar' in client.get('/med/pacientes/')['Location']
    sin_med = cliente_con_rol()
    assert sin_med.get('/med/pacientes/').status_code == 404


def test_tablas_de_med_solo_en_la_base_med():
    for alias, esperada in (('med', True), ('default', False)):
        with connections[alias].cursor() as cursor:
            assert (Paciente._meta.db_table in connections[alias].introspection.table_names(cursor)) is esperada
    assert Paciente.objects.db == 'med'


def test_personas_se_resuelven_por_id_con_tvplataforma(fabrica_actor):
    from tvplataforma import cuentas
    usuario = fabrica_actor('medico', nombre='Dra. Ana')
    assert cuentas.nombre(usuario.pk) == 'Dra. Ana'
    assert [p.id for p in cuentas.con_rol('med', 'medico')] == [usuario.pk]
    assert cuentas.nombre(999999) == 'Cuenta eliminada'


def tokens(**cambios):
    return {**BUILTINS['Clínico'], **cambios}


def test_temas_propios_nombres_unicos_y_permisos(medico, otro_medico, admin):
    tema = apariencia.guardar_tema(medico, 'Mi tema', tokens(primary='#123456'))
    assert str(tema.id) in apariencia.listar()
    for nombre in ('mi TEMA', 'Clínico', 'Personalizada'):
        with pytest.raises(DataError):
            apariencia.guardar_tema(otro_medico, nombre, tokens())
    with pytest.raises(PermisoDenegado):
        apariencia.renombrar(otro_medico, tema.id, 'Robado')
    assert apariencia.renombrar(admin, tema.id, 'Del admin').nombre == 'Del admin'
    with pytest.raises(DataError):
        apariencia.renombrar(medico, 'Clínico', 'Otro')
    with pytest.raises(DataError):
        apariencia.guardar_tema(medico, 'Malo', tokens(primary='rojo'))


def test_preferencia_por_persona_y_tema_general_de_la_clinica(medico, otro_medico, admin):
    tema = apariencia.guardar_tema(medico, 'Mi tema', tokens(primary='#123456'))
    assert apariencia.clave_activa(medico) == 'Clínico'
    apariencia.aplicar(medico, str(tema.id), hereda=False)
    assert apariencia.tokens_activos(medico)['primary'] == '#123456' and apariencia.clave_activa(otro_medico) == 'Clínico'
    with pytest.raises(PermisoDenegado):
        apariencia.aplicar(medico, 'TresVizo', clinica=True)
    apariencia.aplicar(admin, 'Verde suave', clinica=True)
    assert apariencia.clave_activa(otro_medico) == 'Verde suave' and apariencia.clave_activa(medico) == str(tema.id)
    apariencia.aplicar(medico, str(tema.id), hereda=True)
    assert apariencia.clave_activa(medico) == 'Verde suave'
    with pytest.raises(DataError):
        apariencia.aplicar(medico, 'Inventado')


def test_un_tema_en_uso_no_se_elimina(medico, admin):
    tema = apariencia.guardar_tema(medico, 'Mi tema', tokens())
    apariencia.aplicar(admin, str(tema.id), clinica=True)
    with pytest.raises(DataError, match='en uso'):
        apariencia.eliminar(medico, tema.id)
    apariencia.aplicar(admin, 'Clínico', clinica=True)
    apariencia.eliminar(medico, tema.id)
    assert str(tema.id) not in apariencia.listar()
    with pytest.raises(DataError):
        apariencia.eliminar(medico, 'TresVizo')


def test_importar_y_exportar_temas_v1(medico):
    exportado = apariencia.exportar('Neutro')
    assert exportado['schema_version'] == 1 and exportado['tokens'] == BUILTINS['Neutro']
    with pytest.raises(DataError, match='Ya existe'):
        apariencia.importar(medico, json.dumps(exportado))
    tema = apariencia.importar(medico, json.dumps({**exportado, 'name': 'Neutro propio'}).encode())
    assert tema.nombre == 'Neutro propio'
    with pytest.raises(DataError):
        apariencia.importar(medico, '{"schema_version": 1, "schema_version": 1}')
    with pytest.raises(DataError, match='64 KB'):
        apariencia.importar(medico, ' '*70_000)


def test_identidad_de_la_clinica_solo_admin_y_con_validacion(medico, admin):
    assert not Clinica.obtener().configurada and clinica.identidad()['clinic_name'] == 'Mi clínica'
    with pytest.raises(PermisoDenegado):
        clinica.guardar_identidad(medico, {'clinic_name': 'Mía'})
    fila = clinica.guardar_identidad(admin, {'clinic_name': 'Clínica Sur', 'contact': 'Tel. 555'})
    assert fila.configurada and clinica.identidad()['clinic_name'] == 'Clínica Sur' and fila.revision == 2
    with pytest.raises(DataError):
        clinica.guardar_identidad(admin, {'website': 'javascript:alert(1)'})
    from tresvizo_med.servicios import VersionConflict
    with pytest.raises(VersionConflict):
        clinica.guardar_identidad(admin, {'clinic_name': 'X'}, revision=1)
    assert Clinica.objects.count() == 1


def test_perfil_profesional_propio_o_de_admin(medico, otro_medico, admin):
    perfil = clinica.guardar_perfil(medico, medico.cuenta_id, cedula='123', especialidad='Medicina general')
    assert Profesional.para(medico.cuenta_id).cedula == '123' and perfil.activo
    with pytest.raises(PermisoDenegado):
        clinica.guardar_perfil(otro_medico, medico.cuenta_id, cedula='999')
    with pytest.raises(PermisoDenegado):
        clinica.guardar_perfil(medico, medico.cuenta_id, activo=False)
    assert not clinica.guardar_perfil(admin, medico.cuenta_id, activo=False).activo
    with pytest.raises(DataError):
        clinica.guardar_perfil(medico, medico.cuenta_id, cuenta_id_nueva=1)
    with pytest.raises(DataError):
        clinica.guardar_perfil(medico, medico.cuenta_id, cedula='x'*121)


def test_alta_de_pacientes_la_hacen_ambos_roles(medico, admin):
    assert pacientes.guardar(admin, datos_paciente('Del admin')).created_by == admin.cuenta_id
    assert pacientes.guardar(medico, datos_paciente('Del médico')).created_by == medico.cuenta_id
