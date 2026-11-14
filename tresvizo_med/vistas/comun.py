"""Decorador común de las vistas de Med: rol, actor, bloqueo, errores de servicio y respuestas sin caché."""
from functools import wraps
from urllib.parse import quote

from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers, patch_cache_control
from tvplataforma.permisos import requiere_rol

from .. import navegacion
from ..servicios import Actor, NoEncontrado, PermisoDenegado

CLAVE_BLOQUEO = 'med_bloqueado'
TODOS = ('admin', 'medico')


def es_htmx(request):
    return request.headers.get('HX-Request') == 'true'


def redirigir(request, destino):
    """Redirección que HTMX sigue con la ventana completa."""
    if es_htmx(request):
        respuesta = HttpResponse(status=204)
        respuesta['HX-Redirect'] = destino
        return respuesta
    return redirect(destino)


def vista_med(*roles, metodos=('GET', 'HEAD'), bloqueable=True):
    """Aplica ``@requiere_rol("med", *roles)`` y deja ``request.actor``.

    * Sin sesión: redirección al acceso único; sin rol de Med: 404; con Med pero sin el rol: 403 (tvplataforma).
    * Con la sesión de Med bloqueada solo responden «Bloquear» y «Desbloquear».
    * Los errores de servicio se traducen: ``NoEncontrado`` → 404, ``PermisoDenegado`` → 403.
    * Nada se guarda en el navegador: ``Cache-Control: no-store`` (med-web.md §8).
    """
    def decorador(vista):
        @wraps(vista)
        def interna(request, *args, **kwargs):
            if request.method not in metodos:
                return HttpResponseNotAllowed(metodos)
            try:
                request.actor = Actor.de(request.user)
                request.tv_seccion = navegacion.seccion(request)
                if bloqueable and request.session.get(CLAVE_BLOQUEO):
                    if es_htmx(request):
                        return redirigir(request, reverse('med:desbloquear'))
                    return redirect(reverse('med:desbloquear')+'?siguiente='+quote(request.get_full_path()))
                respuesta = vista(request, *args, **kwargs)
            except NoEncontrado:
                raise Http404 from None
            except PermisoDenegado:
                raise PermissionDenied from None
            add_never_cache_headers(respuesta)
            patch_cache_control(respuesta, no_store=True, private=True)
            return respuesta
        return requiere_rol('med', *roles)(interna)
    return decorador


def pagina(request, plantilla, contexto=None, estado=200):
    return render(request, plantilla, contexto or {}, status=estado)
