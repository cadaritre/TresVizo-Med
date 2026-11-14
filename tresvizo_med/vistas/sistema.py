"""Bloquear/desbloquear la sesión de Med y la hoja de tema."""
from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from tvplataforma.temas import es_claro, hoja_css

from ..servicios import apariencia
from .comun import CLAVE_BLOQUEO, TODOS, redirigir, vista_med

INTENTOS = 5
CLAVE_INTENTOS = 'med_intentos_desbloqueo'


@vista_med(*TODOS, metodos=('POST',), bloqueable=False)
def bloquear(request):
    """Oculta el contenido de Med hasta que la persona escriba su contraseña. Los borradores ya están guardados."""
    request.session[CLAVE_BLOQUEO] = True
    return redirigir(request, reverse('med:desbloquear'))


def _interno(destino):
    partes = urlsplit(destino or '')
    return destino if destino.startswith('/') and not destino.startswith('//') and not partes.netloc else reverse('med:pacientes')


@vista_med(*TODOS, metodos=('GET', 'POST'), bloqueable=False)
def desbloquear(request):
    siguiente = _interno(request.GET.get('siguiente') or request.POST.get('siguiente', ''))
    if not request.session.get(CLAVE_BLOQUEO):
        return redirect(siguiente)
    error = ''
    if request.method == 'POST':
        if request.user.check_password(request.POST.get('password', '')):
            request.session.pop(CLAVE_BLOQUEO, None)
            request.session.pop(CLAVE_INTENTOS, None)
            return redirect(siguiente)
        fallos = request.session.get(CLAVE_INTENTOS, 0)+1
        request.session[CLAVE_INTENTOS] = fallos
        if fallos >= INTENTOS:
            logout(request)  # demasiados intentos: la sesión se cierra y hay que entrar de nuevo por el portal
            return redirect(reverse('med:inicio'))
        error = 'La contraseña no coincide.'
    respuesta = render(request, 'med/bloqueo.html', {'siguiente': siguiente, 'error': error, 'bloqueado': True},
                       status=401 if error else 200)
    return respuesta


@vista_med(*TODOS, bloqueable=False)
def tema_css(request):
    """Hoja que redefine los tokens ``--tv-*`` con el tema de Med de la persona (nunca estilos en línea).

    El modo lo decide la cuenta (``<html data-tv-tema="claro|oscuro">``, claro por omisión, nunca el del sistema). Los temas de Med
    son paletas: un tema claro pinta el modo claro y deja el oscuro al grafito del armazón; un tema oscuro (Azul profundo o uno
    propio) pinta solo el modo oscuro y el claro queda en Clínico. Así nadie ve Med oscuro sin haberlo pedido, y la hoja no depende
    de la preferencia (cambiar de modo desde la paleta no necesita recargarla).
    """
    return HttpResponse(hoja_para_modos(apariencia.tokens_activos(request.actor)), content_type='text/css; charset=utf-8')


def hoja_para_modos(tokens):
    if es_claro(tokens):
        return hoja_css(tokens, ':root:not([data-tv-tema="oscuro"])')
    return hoja_css(apariencia.tokens_de_fabrica(), ':root:not([data-tv-tema="oscuro"])') + hoja_css(tokens, ':root[data-tv-tema="oscuro"]')
