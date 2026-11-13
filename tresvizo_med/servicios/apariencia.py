"""Temas de color: de fábrica, personalizados por médico, preferencia por persona y tema general de la clínica.

Porta ``Appearance`` del escritorio sobre las tablas ``Tema``, ``Profesional`` y ``Clinica``.
"""
import uuid
from copy import deepcopy

from django.utils import timezone

from ..db import atomico
from ..dominio import themes
from ..dominio.errores import DataError
from ..dominio.transfer import loads_strict
from ..models import Clinica, Profesional, Tema
from .errores import PermisoDenegado

LIMITE_IMPORTACION = 64_000


def listar():
    """``{clave: {'name', 'tokens', 'owner'?}}``: los de fábrica y los personalizados."""
    resultado = {k: {'name': k, 'tokens': deepcopy(v)} for k, v in themes.BUILTINS.items()}
    for tema in Tema.objects.all():
        resultado[str(tema.id)] = {'name': tema.nombre, 'tokens': tema.tokens, 'owner': tema.dueno_id}
    return resultado


def clave_activa(actor):
    perfil = Profesional.para(actor.cuenta_id)
    if perfil.hereda_tema or not perfil.tema:
        return Clinica.obtener().tema_clinica
    return perfil.tema


def tokens_activos(actor):
    disponibles = listar()
    clave = clave_activa(actor)
    return deepcopy(disponibles.get(clave, disponibles['Clínico'])['tokens'])


def guardar_tema(actor, nombre, tokens):
    datos = themes.validate_theme({'schema_version': 1, 'name': nombre, 'tokens': tokens})
    if datos['name'].casefold() == 'personalizada':
        raise DataError('Elige un nombre propio para distinguir el tema del editor Personalizada.')
    if any(t['name'].casefold() == datos['name'].casefold() for t in listar().values()):
        raise DataError('Ya existe un tema con ese nombre.')
    return Tema.objects.create(dueno_id=actor.cuenta_id, nombre=datos['name'], tokens=datos['tokens'])


def _tema_propio(actor, clave):
    try:
        tema = Tema.objects.select_for_update().get(pk=uuid.UUID(str(clave)))
    except (Tema.DoesNotExist, ValueError):
        raise DataError('Las paletas prediseñadas no se pueden modificar.') from None
    if not actor.es_admin and tema.dueno_id != actor.cuenta_id:
        raise PermisoDenegado('Solo puedes modificar tus temas personalizados.')
    return tema


def renombrar(actor, clave, nombre):
    with atomico():
        tema = _tema_propio(actor, clave)
        datos = themes.validate_theme({'schema_version': 1, 'name': nombre, 'tokens': tema.tokens})
        if any(k != str(tema.id) and t['name'].casefold() == datos['name'].casefold() for k, t in listar().items()):
            raise DataError('Ya existe un tema con ese nombre.')
        tema.nombre = datos['name']
        tema.save(update_fields=['nombre'])
        return tema


def eliminar(actor, clave):
    with atomico():
        tema = _tema_propio(actor, clave)
        if Clinica.obtener().tema_clinica == str(tema.id) or Profesional.objects.filter(tema=str(tema.id), hereda_tema=False).exists():
            raise DataError('El tema está en uso. Cambia primero las preferencias que lo utilizan.')
        tema.delete()


def aplicar(actor, clave, hereda=False, clinica=False):
    """Preferencia propia, o tema general de la clínica (administrador)."""
    if clave not in listar():
        raise DataError('No existe el tema.')
    with atomico():
        if clinica:
            actor.exigir_admin()
            fila = Clinica.obtener()
            fila.tema_clinica = clave
            fila.updated_at, fila.updated_by, fila.revision = timezone.now(), actor.cuenta_id, fila.revision+1
            fila.save()
        else:
            perfil = Profesional.para(actor.cuenta_id)
            perfil.tema, perfil.hereda_tema = clave, bool(hereda)
            perfil.save(update_fields=['tema', 'hereda_tema'])


def importar(actor, contenido):
    """Importa un tema v1 (JSON de hasta 64 KB)."""
    if len(contenido) > LIMITE_IMPORTACION:
        raise DataError('El tema excede el máximo de 64 KB.')
    datos = themes.validate_theme(loads_strict(contenido))
    return guardar_tema(actor, datos['name'], datos['tokens'])


def exportar(clave):
    disponible = listar()[clave]
    return themes.validate_theme({'schema_version': 1, 'name': disponible['name'], 'tokens': disponible['tokens']})
