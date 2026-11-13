"""Etiquetas de plantilla propias de Med."""
from django import template
from django.urls import reverse

from ..servicios import clinica as servicio_clinica

register = template.Library()


@register.filter
def get(diccionario, clave):
    """``{{ dic|get:clave }}`` (los diccionarios de las plantillas no admiten claves variables)."""
    try:
        return diccionario.get(clave, '')
    except AttributeError:
        return ''


@register.simple_tag(takes_context=True)
def yo(context):
    """«Quién soy» de la cabecera: nombre visible y avatar de la persona con sesión."""
    from tvplataforma import cuentas

    from ..models import Profesional
    usuario = context.get('user')
    if usuario is None or not getattr(usuario, 'is_authenticated', False):
        return {}
    perfil = Profesional.objects.filter(cuenta_id=usuario.pk).first()
    nombre = (perfil.nombre_visible if perfil and perfil.nombre_visible else '') or cuentas.nombre(usuario.pk)
    avatar = perfil.avatar if perfil and perfil.avatar else 'initials'
    return {'nombre': nombre, 'iniciales': ''.join(p[0] for p in nombre.split()[:2]).upper() or '?',
            'avatar': avatar, 'reducir': bool(perfil and perfil.reducir_movimiento), 'url': reverse('med:perfil_foto', args=[usuario.pk]) if avatar in ('photo',) or avatar in servicio_clinica.AVATARES else ''}
