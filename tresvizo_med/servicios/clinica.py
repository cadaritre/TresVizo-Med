"""Identidad de la clínica y perfil profesional."""
from django.utils import timezone

from ..db import atomico
from ..dominio import themes
from ..dominio.errores import DataError
from ..models import Clinica, Profesional
from .errores import VersionConflict


def identidad():
    return Clinica.obtener().valores()


def guardar_identidad(actor, valores, revision=None):
    """Identidad que usan los documentos. Solo ``med.admin``; el primer guardado marca la clínica como configurada."""
    actor.exigir_admin()
    with atomico():
        fila = Clinica.objects.select_for_update().get(pk=Clinica.obtener().pk)
        if revision is not None and fila.revision != revision:
            raise VersionConflict({'revision': fila.revision, 'identidad': fila.valores()})
        datos = {**fila.valores(), **valores}
        themes.validate_identity(datos)
        fila.identidad, fila.configurada = datos, True
        fila.revision += 1
        fila.updated_at, fila.updated_by = timezone.now(), actor.cuenta_id
        fila.save()
        return fila


def guardar_perfil(actor, cuenta_id, **valores):
    """Perfil profesional. Cada persona edita el suyo; ``med.admin`` edita cualquiera."""
    if cuenta_id != actor.cuenta_id:
        actor.exigir_admin()
    permitidos = {'nombre_visible', 'cedula', 'especialidad', 'avatar', 'reducir_movimiento', 'activo'}
    if set(valores) - permitidos:
        raise DataError('Campo de perfil no admitido.')
    if 'activo' in valores:
        actor.exigir_admin()
    for clave in ('nombre_visible', 'cedula', 'especialidad'):
        if len(str(valores.get(clave, ''))) > 120:
            raise DataError('Máximo 120 caracteres.')
    perfil = Profesional.para(cuenta_id)
    for clave, valor in valores.items():
        setattr(perfil, clave, valor)
    perfil.save()
    return perfil
