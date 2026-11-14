"""Pruebas de punta a punta de Med con Playwright (Chromium) contra un servidor en vivo y PostgreSQL.

Correr con ``e2e/ejecutar.sh e2e --ds=tresvizo_med.pruebas.ajustes_e2e`` (toma el turno de la Mac y levanta su PostgreSQL).
La sesión se crea con el cliente de Django y su cookie se pasa al navegador: el acceso único con ticket lo prueban las
pruebas de ``tvplataforma``; aquí se prueba Med.
"""
import os
import re

import pytest

# Playwright (API síncrona) deja un bucle de asyncio activo en el hilo de las pruebas; el ORM de Django lo rechaza sin esto.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
from django.test import Client

playwright = pytest.importorskip('playwright.sync_api')
from playwright.sync_api import sync_playwright  # noqa: E402

DESKTOP = {'width': 1280, 'height': 800}
TELEFONO = {'width': 360, 'height': 740}


@pytest.fixture(scope='session')
def navegador():
    """Chromium; ``MOTOR=webkit`` (o ``firefox``) corre las mismas pruebas en otro motor."""
    with sync_playwright() as p:
        motor = getattr(p, os.environ.get('MOTOR', 'chromium')).launch()
        yield motor
        motor.close()


@pytest.fixture
def servidor(live_server, settings):
    """El servidor en vivo atendiendo el host del módulo (``med.localhost:<puerto>``)."""
    puerto = live_server.thread.port
    settings.TV_HOSTS = {'med': f'med.localhost:{puerto}'}
    return f'http://med.localhost:{puerto}'


class Sesion:
    """Un navegador con sesión de una cuenta de Med."""

    def __init__(self, navegador, servidor, usuario, viewport, movil=False):
        from django.conf import settings
        cliente = Client()
        cliente.force_login(usuario)
        self.usuario = usuario
        self.servidor = servidor
        self.errores = []
        self.contexto = navegador.new_context(viewport=viewport, is_mobile=movil, has_touch=movil, locale='es-MX', accept_downloads=True,
                                              timezone_id='America/Mexico_City')
        self.contexto.add_cookies([{'name': settings.SESSION_COOKIE_NAME, 'value': cliente.cookies[settings.SESSION_COOKIE_NAME].value,
                                    'url': servidor}])
        self.contexto.on('page', self._vigilar)
        self.pagina = self.contexto.new_page()

    def _vigilar(self, pagina):
        pagina.on('pageerror', lambda e: self.errores.append(f'pageerror: {e}'))
        pagina.on('console', lambda m: self.errores.append(f'console: {m.text}') if m.type == 'error' and 'favicon' not in m.text
                  and 'status of 4' not in m.text else None)

    def ir(self, ruta, pagina=None):
        pagina = pagina or self.pagina
        pagina.goto(self.servidor+ruta)
        return pagina

    def nueva(self):
        pagina = self.contexto.new_page()
        return pagina

    def cerrar(self):
        self.contexto.close()


@pytest.fixture
def fabrica_sesion(navegador, servidor, crear_usuario, roles):
    sesiones = []

    def crear(*concedidos, username='dra', viewport=DESKTOP, movil=False, superusuario=False):
        usuario = crear_usuario(username, superusuario=superusuario, nombre=f'Persona {username}')
        if concedidos:
            roles.conceder(usuario, 'med', *concedidos)
        sesion = Sesion(navegador, servidor, usuario, viewport, movil)
        sesiones.append(sesion)
        return sesion
    yield crear
    errores = [e for s in sesiones for e in s.errores]
    for s in sesiones:
        s.cerrar()
    # La CSP no admite estilos ni scripts en línea: cualquier violación o error de JS es un fallo.
    assert not errores, 'Errores en el navegador:\n'+'\n'.join(errores)


@pytest.fixture
def medico(fabrica_sesion):
    return fabrica_sesion('medico', username='dra')


@pytest.fixture
def actor(medico):
    from tresvizo_med.servicios import Actor
    return Actor.de(medico.usuario)


def guardado(pagina, tiempo=8000):
    """Espera a que el indicador diga «Guardado hh:mm:ss» (guardado real del servidor)."""
    pagina.wait_for_function("() => /Guardado \\d/.test((document.getElementById('indicador')||{}).textContent||'')", timeout=tiempo)


def sin_scroll_horizontal(pagina):
    return pagina.evaluate("() => [document.documentElement.scrollWidth, document.body.scrollWidth, window.innerWidth]")


@pytest.fixture
def fabrica_actor(crear_usuario, roles):
    contador = {'n': 0}

    def crear(*concedidos, superusuario=False):
        contador['n'] += 1
        usuario = crear_usuario(f'persona{contador["n"]}', superusuario=superusuario, nombre=f'Persona {contador["n"]}')
        if concedidos:
            roles.conceder(usuario, 'med', *concedidos)
        return usuario
    return crear
