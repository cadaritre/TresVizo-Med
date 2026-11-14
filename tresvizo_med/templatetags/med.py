"""Etiquetas de plantilla propias de Med."""
from django import template
from django.urls import reverse

from ..formato import fecha_corta
from ..servicios import clinica as servicio_clinica

register = template.Library()


@register.filter
def get(diccionario, clave):
    """``{{ dic|get:clave }}`` (los diccionarios de las plantillas no admiten claves variables)."""
    try:
        return diccionario.get(clave, '')
    except AttributeError:
        return ''


ESTADOS_COLA = {'Pendiente de copia / reintento': 'Falta incorporar', 'Guardado': 'Incorporado'}
TIPOS_LEGIBLES = {'image/jpeg': 'Imagen JPEG', 'image/png': 'Imagen PNG', 'application/pdf': 'PDF',
                  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Documento de Word'}


@register.filter
def estado_cola(texto):
    """Estado de un archivo de la cola de documentos en palabras de uso."""
    return ESTADOS_COLA.get(texto, texto)


@register.filter
def tipo_legible(mime):
    """``image/jpeg`` → «Imagen JPEG»."""
    return TIPOS_LEGIBLES.get(mime, mime)


@register.filter
def fecha_iso(texto):
    """``{{ '2026-09-10'|fecha_iso }}`` → 10/09/2026."""
    return fecha_corta(texto)


@register.filter
def primera_linea(texto, largo=110):
    """Primera línea con contenido de un texto, recortada (vista previa de una sección plegada)."""
    linea = next((x.strip() for x in str(texto or '').splitlines() if x.strip()), '')
    return linea if len(linea) <= largo else linea[:largo-1].rstrip()+'…'


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
