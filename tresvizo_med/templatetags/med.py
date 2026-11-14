"""Etiquetas de plantilla propias de Med."""
from django import template
from django.templatetags.static import static
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


NOMBRES_AVATARES = {'arbol': 'Árbol', 'buho': 'Búho', 'montana': 'Montaña'}


def avatar_estatico(clave):
    """URL estática de un avatar de fábrica, archivo por archivo: con el almacén de producción sale con su hash, así un 404
    guardado en caché (Caddy marca todo /static como inmutable) nunca se queda pegado a la URL."""
    return static(f'med/img/avatares/{clave}.png')


def avatares_de_fabrica():
    return [{'clave': a, 'nombre': NOMBRES_AVATARES.get(a, a.capitalize()), 'url': avatar_estatico(a)} for a in servicio_clinica.AVATARES]


def version_foto(perfil):
    """Cambia con cada foto nueva: la URL de la foto no se queda con una versión vieja en caché."""
    import hashlib
    return hashlib.sha1(str(perfil.foto_ruta or '').encode()).hexdigest()[:10]


def iniciales_de(nombre):
    palabras = [p for p in str(nombre or '').replace('.', ' ').split() if p[:1].isalpha() and p.lower() not in ('dr', 'dra', 'de', 'del', 'la', 'los')]
    return ''.join(p[0] for p in palabras[:2]).upper() or '?'


@register.filter
def iniciales_med(nombre):
    """Iniciales para el círculo de una persona («Ana López Pérez» → «AL»)."""
    return iniciales_de(nombre)


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
    if avatar == 'photo' and perfil.foto_ruta:
        url = reverse('med:perfil_foto', args=[usuario.pk]) + '?v=' + version_foto(perfil)
    elif avatar in servicio_clinica.AVATARES:
        url = avatar_estatico(avatar)
    else:
        url = ''
    return {'nombre': nombre, 'iniciales': iniciales_de(nombre), 'avatar': avatar, 'reducir': bool(perfil and perfil.reducir_movimiento), 'url': url}



@register.filter
def tema_oscuro(tokens):
    """Un tema de Med con fondo oscuro: solo se ve con el modo oscuro de la cuenta."""
    from tvplataforma.temas import es_claro
    try:
        return not es_claro(tokens)
    except (KeyError, TypeError, ValueError):
        return False
