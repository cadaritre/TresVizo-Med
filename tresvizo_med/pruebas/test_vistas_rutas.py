"""Cada ruta de Med: sin sesión redirige, sin rol de Med es 404, sin el rol exigido es 403, método incorrecto es 405."""
import re
import uuid

import pytest

from tresvizo_med import urls
from .conftest import reverse_med as reverse

pytestmark = pytest.mark.django_db(databases=['default', 'med'])
RUTAS = [(p.name, p.pattern._route, p.callback) for p in urls.urlpatterns]


def argumentos(ruta):
    return [str(uuid.uuid4()) if conv == 'uuid' else 'vitals' if nombre == 'tipo' else 'x'
            for conv, nombre in re.findall(r'<(\w+):(\w+)>', ruta)]


def url_de(nombre, ruta):
    return reverse(f'med:{nombre}', args=argumentos(ruta))


def test_todas_las_rutas_declaran_su_rol():
    assert len(RUTAS) >= 30
    for nombre, _, vista in RUTAS:
        modulo, roles = vista.tv_requiere
        assert modulo == 'med' and set(roles) <= {'admin', 'medico'}, nombre


@pytest.mark.parametrize('nombre,ruta,vista', RUTAS, ids=[r[0] for r in RUTAS])
def test_sin_sesion_redirige_al_acceso_unico(nombre, ruta, vista, cliente_med):
    from django.test import Client
    from tvplataforma import hosts
    from tvplataforma.modulos import modulo
    anonimo = Client(HTTP_HOST=hosts.host_de(modulo('med')))
    r = anonimo.get(url_de(nombre, ruta))
    assert r.status_code in (302, 204) and 'sso/entrar' in (r.get('Location') or r.get('HX-Redirect', 'sso/entrar'))


@pytest.mark.parametrize('nombre,ruta,vista', RUTAS, ids=[r[0] for r in RUTAS])
def test_sin_rol_de_med_es_404_con_cualquier_metodo(nombre, ruta, vista, cliente_med):
    ajeno = cliente_med(username=f'ajeno-{nombre}')
    for metodo in (ajeno.get, ajeno.post):
        assert metodo(url_de(nombre, ruta)).status_code == 404


@pytest.mark.parametrize('nombre,ruta,vista', RUTAS, ids=[r[0] for r in RUTAS])
def test_sin_el_rol_exigido_es_403(nombre, ruta, vista, cliente_med):
    _, roles = vista.tv_requiere
    if set(roles) >= {'admin', 'medico'}:
        pytest.skip('la ruta admite ambos roles')
    solo_admin = cliente_med('admin', username=f'jefa-{nombre}')
    for metodo in (solo_admin.get, solo_admin.post):
        assert metodo(url_de(nombre, ruta)).status_code == 403


def test_metodo_incorrecto_es_405(cliente_med):
    medico = cliente_med('medico', username='dra')
    assert medico.get(reverse('med:bloquear')).status_code == 405
    assert medico.post(reverse('med:pacientes')).status_code == 405
    assert medico.get(reverse('med:atender', args=[uuid.uuid4()])).status_code == 405
    assert medico.get(reverse('med:finalizar', args=[uuid.uuid4()])).status_code == 405


def test_identificadores_inexistentes_son_404_para_quien_tiene_rol(cliente_med):
    medico = cliente_med('medico', username='dra')
    for nombre in ('expediente', 'evolucion'):
        assert medico.get(reverse(f'med:{nombre}', args=[uuid.uuid4()])).status_code == 404
    for nombre in ('consulta', 'revisar'):
        assert medico.get(reverse(f'med:{nombre}', args=[uuid.uuid4()])).status_code == 404
    assert medico.get(reverse('med:alta', args=[uuid.uuid4()])).status_code == 404
    assert medico.get(reverse('med:archivo', args=[uuid.uuid4()])).status_code == 404


def test_el_superadministrador_ve_todo(cliente_med):
    dueno = cliente_med(superusuario=True, username='dueno')
    assert dueno.get(reverse('med:pacientes')).status_code == 200
    assert dueno.get(reverse('med:en_curso')).status_code == 200


def test_el_inicio_lleva_a_pacientes(cliente_med):
    assert cliente_med('medico').get(reverse('med:inicio'))['Location'] == reverse('med:pacientes')
