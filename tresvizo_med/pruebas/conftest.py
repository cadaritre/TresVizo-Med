"""Datos sintéticos compartidos por las pruebas de dominio. Nada clínico real."""
import uuid

import pytest


def make_patient(name='Paciente sintético', number=1, **extra):
    return {'id': str(uuid.uuid4()), 'name': name, 'file_number': f'RC-{number:06d}', **extra}


def make_encounter(patient_id, doctor_id, attended_at='2026-09-10T10:00:00', status='Finalizada', **extra):
    return {'id': str(uuid.uuid4()), 'patient_id': patient_id, 'doctor_id': doctor_id, 'status': status,
            'attended_at': attended_at, 'reason': 'Motivo', 'assessment': 'Gastritis', 'plan': 'Reposo',
            'type': 'General', 'vitals': [], 'prescriptions': [], **extra}


@pytest.fixture
def doctor():
    return str(uuid.uuid4())


# --- Fixtures de la app Django (base ``med``) ------------------------------------------------------------------
from PIL import Image  # noqa: E402

from tresvizo_med.servicios import Actor  # noqa: E402


@pytest.fixture
def bases(db):
    """Todas las pruebas de servicios usan las dos bases (el contrato exige declararlo)."""


def pytest_collection_modifyitems(items):
    for item in items:
        if 'servicios' in item.nodeid or 'modelos' in item.nodeid or 'permisos' in item.nodeid:
            item.add_marker(pytest.mark.django_db(databases=['default', 'med']))


@pytest.fixture
def fabrica_actor(crear_usuario, roles):
    contador = {'n': 0}

    def crear(*concedidos, superusuario=False, nombre=''):
        contador['n'] += 1
        usuario = crear_usuario(f'persona{contador["n"]}', superusuario=superusuario, nombre=nombre or f'Persona {contador["n"]}')
        if concedidos:
            roles.conceder(usuario, 'med', *concedidos)
        return usuario
    return crear


@pytest.fixture
def medico(fabrica_actor):
    return Actor.de(fabrica_actor('medico', nombre='Dra. Ana'))


@pytest.fixture
def otro_medico(fabrica_actor):
    return Actor.de(fabrica_actor('medico', nombre='Dr. Beto'))


@pytest.fixture
def admin(fabrica_actor):
    return Actor.de(fabrica_actor('admin', nombre='Administración'))


@pytest.fixture
def imagen(tmp_path):
    def crear(nombre='foto.png', tamano=(40, 30), color='white'):
        ruta = tmp_path/nombre
        Image.new('RGB', tamano, color).save(ruta)
        return ruta
    return crear


def datos_paciente(nombre='Ana Muñoz', **extra):
    return {'name': nombre, **extra}


def datos_consulta(paciente, estado='Borrador', **extra):
    base = {'patient_id': str(paciente.id), 'status': estado, 'attended_at': '2026-09-10T10:15:23-06:00', 'type': 'General'}
    if estado == 'Finalizada':
        base.update(reason='Dolor', assessment='Gastritis', plan='Reposo')
    return {**base, **extra}


@pytest.fixture(autouse=True)
def _folios_desde_uno(request):
    """La secuencia de folios no se revierte con la transacción de la prueba: se reinicia al empezar."""
    if request.node.get_closest_marker('django_db') is None:
        yield
        return
    request.getfixturevalue('bases')
    from django.db import connections
    with connections['med'].cursor() as cursor:
        cursor.execute('ALTER SEQUENCE med_folio_seq RESTART WITH 1')
    yield


@pytest.fixture(autouse=True)
def _archivos_aislados(settings, tmp_path_factory):
    """Cada prueba escribe en su propia carpeta de archivos de Med."""
    settings.TV_MED_ARCHIVOS = tmp_path_factory.mktemp('med')


def reverse_med(nombre, args=None, kwargs=None):
    """``reverse`` con las URLs del host de Med (fuera de una petición se usa el «portal» de las pruebas)."""
    from django.urls import reverse
    from tvplataforma.middleware import urlconf_de
    return reverse(nombre, args=args, kwargs=kwargs, urlconf=urlconf_de('med'))


@pytest.fixture
def cliente_med(crear_usuario, roles):
    """Fábrica de clientes independientes (cada uno con su sesión) en el host de Med: ``cliente_med('medico', username='ana')``."""
    from django.test import Client
    from tvplataforma import hosts
    from tvplataforma.modulos import modulo

    contador = {'n': 0}

    def fabrica(*concedidos, username=None, superusuario=False):
        contador['n'] += 1
        usuario = crear_usuario(username or f'med{contador["n"]}', superusuario=superusuario)
        if concedidos:
            roles.conceder(usuario, 'med', *concedidos)
        cliente = Client(HTTP_HOST=hosts.host_de(modulo('med')))
        cliente.force_login(usuario)
        cliente.usuario = usuario
        return cliente
    return fabrica
