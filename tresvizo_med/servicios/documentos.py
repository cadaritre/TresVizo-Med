"""Documentos del expediente: archivos administrados, versiones, verificación de integridad y miniaturas.

Porta ``Attachments`` del escritorio. Los originales viven en ``TV_MED_ARCHIVOS/documentos/originales`` con el
nombre ``<id><extensión>``; la fila guarda su ruta relativa y su SHA-256, que se verifica al leer.
"""
import hashlib
import os
import shutil
import uuid
from datetime import date
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from ..db import atomico
from ..dominio import attachments as dominio
from ..dominio.errores import DataError
from ..formato import documento_a_dict
from ..models import BorradorAlta, Consulta, Documento, Paciente
from . import consultas as servicio_consultas
from .errores import NoEncontrado, VersionConflict

CATEGORIAS = dominio.CATEGORIES


def raiz():
    return Path(settings.TV_MED_ARCHIVOS)/'documentos'


def ruta_absoluta(documento):
    ruta = (Path(settings.TV_MED_ARCHIVOS)/documento.ruta).resolve()
    if not ruta.is_relative_to(Path(settings.TV_MED_ARCHIVOS).resolve()):
        raise DataError('Ruta de documento inválida.')
    return ruta


def autorizar(actor, paciente=None, consulta=None, borrador=None):
    """Comprueba que el destino existe y es visible para ``actor``. Devuelve ``(paciente, consulta, borrador)``."""
    try:
        if borrador:
            alta = BorradorAlta.objects.filter(pk=borrador).first()
            if paciente or consulta:
                raise DataError('Un documento pendiente de alta no puede vincularse simultáneamente a otro destino.')
            if not alta or alta.profesional_id != actor.cuenta_id or alta.estado != BorradorAlta.Estado.BORRADOR:
                raise NoEncontrado('Este borrador es privado o ya fue cerrado.')
            return None, None, alta
        persona = Paciente.objects.filter(pk=paciente).first() if paciente else None
        if not persona:
            raise NoEncontrado('No existe el paciente.')
        fila = None
        if consulta:
            fila = Consulta.objects.filter(pk=consulta).first()
            if not fila or fila.paciente_id != persona.id:
                raise DataError('La consulta no pertenece a este paciente.')
            if fila.estado == Consulta.Estado.BORRADOR and fila.doctor_id != actor.cuenta_id:
                raise NoEncontrado('No puedes consultar adjuntos de un borrador ajeno.')
        return persona, fila, None
    except DataError:
        raise
    except ValueError as exc:
        raise DataError('Identificador inválido.') from exc


def listar(actor, paciente=None, consulta=None, borrador=None, archivados=False):
    persona, fila, alta = autorizar(actor, paciente, consulta, borrador)
    filas = Documento.objects.filter(borrador=alta) if alta else Documento.objects.filter(paciente=persona, borrador=None)
    if fila:
        filas = filas.filter(consulta=fila)
    if not archivados:
        filas = filas.filter(archivado=False)
    visibles = []
    for documento in filas.select_related('consulta').order_by('-created_at'):
        # Un documento de un borrador ajeno de consulta no se ve aunque el paciente sea el mismo.
        if documento.consulta_id and documento.consulta.estado == Consulta.Estado.BORRADOR \
                and documento.consulta.doctor_id != actor.cuenta_id:
            continue
        visibles.append(documento)
    return visibles


def obtener(actor, identificador):
    try:
        documento = Documento.objects.get(pk=identificador)
    except (Documento.DoesNotExist, ValueError):
        raise NoEncontrado('No existe el documento.') from None
    autorizar(actor, documento.paciente_id, documento.consulta_id, documento.borrador_id)
    return documento


def ruta_verificada(actor, identificador):
    """Ruta del original tras comprobar que existe y que su SHA-256 coincide con el registrado."""
    documento = obtener(actor, identificador)
    ruta = ruta_absoluta(documento)
    if not ruta.is_file():
        raise DataError('El archivo está ausente. El registro se conserva para recuperación.')
    with ruta.open('rb') as flujo:
        if hashlib.file_digest(flujo, 'sha256').hexdigest() != documento.sha256:
            raise DataError('La integridad del documento no coincide. Restaura una copia verificada.')
    return ruta


def agregar(actor, origen, paciente=None, consulta=None, borrador=None, categoria='Otro documento', notas='',
            motivo='', permitir_duplicado=False, reemplaza=None, progreso=lambda fraccion: None, operacion=None,
            nombre_original=None):
    """Incorpora un archivo. Con ``operacion`` es idempotente: repetirlo devuelve el documento ya guardado.

    A una consulta finalizada solo se agrega con motivo, y deja una adenda.
    """
    actor.exigir_medico()
    if categoria not in CATEGORIAS:
        raise DataError('Elige una categoría de documento válida.')
    persona, fila, alta = autorizar(actor, paciente, consulta, borrador)
    destino = {'patient_id': str(persona.id) if persona else None, 'encounter_id': str(fila.id) if fila else None,
               'draft_id': str(alta.id) if alta else None}
    identificador = uuid.UUID(dominio.operation_identifier(actor.cuenta_id, destino, operacion)) if operacion else uuid.uuid4()
    previo = Documento.objects.filter(pk=identificador).first()
    if previo:
        return previo
    origen = Path(origen)
    nombre = nombre_original or origen.name
    mime = dominio.validate(origen)
    sufijo = origen.suffix.lower()
    relativa = f'documentos/originales/{identificador}{sufijo}'
    preparado = raiz()/'preparacion'/(str(uuid.uuid4())+sufijo)
    preparado.parent.mkdir(parents=True, exist_ok=True)
    sha, total, copiado = hashlib.sha256(), origen.stat().st_size, 0
    publicado = None
    try:
        with origen.open('rb') as entrada, preparado.open('xb') as salida:
            while trozo := entrada.read(1024*1024):
                salida.write(trozo)
                sha.update(trozo)
                copiado += len(trozo)
                progreso(copiado/total)
            salida.flush()
            os.fsync(salida.fileno())
        dominio.validate(preparado)  # el contenido se verifica sobre la copia que se publicará
        with preparado.open('rb') as flujo:
            if hashlib.file_digest(flujo, 'sha256').hexdigest() != sha.hexdigest():
                raise DataError('No se pudo verificar la copia del archivo.')
        with atomico():
            persona, fila, alta = autorizar(actor, paciente, consulta, borrador)
            previo = Documento.objects.filter(pk=identificador).first()
            if previo:
                return previo
            anterior = None
            if reemplaza:
                anterior = obtener(actor, reemplaza)
                if (anterior.paciente_id, anterior.consulta_id, anterior.borrador_id) != (
                        persona.id if persona else None, fila.id if fila else None, alta.id if alta else None):
                    raise DataError('La nueva versión debe pertenecer al mismo destino que la anterior.')
            if not permitir_duplicado and any(d.sha256 == sha.hexdigest() for d in listar(actor, paciente, None, borrador, True)):
                raise DataError('Ya existe un archivo idéntico en este expediente. Revisa la coincidencia o permite incorporarlo otra vez.')
            ahora = timezone.now()
            documento = Documento(
                id=identificador, paciente=persona, consulta=fila, borrador=alta, doctor_id=actor.cuenta_id,
                categoria=categoria, mime=mime, tamano=total, sha256=sha.hexdigest(), version_de=anterior,
                titulo=Path(nombre).stem, descripcion=notas, nombre_original=nombre, ruta=relativa,
                created_at=ahora, created_by=actor.cuenta_id, updated_at=ahora, updated_by=actor.cuenta_id)
            documento.save()
            if fila and fila.estado == Consulta.Estado.ANULADA:
                raise DataError('No se agregan documentos a una consulta anulada.')
            if fila and fila.estado != Consulta.Estado.BORRADOR:
                if not motivo.strip():
                    raise DataError('Indica el motivo para añadir un documento a una consulta finalizada.')
                servicio_consultas.agregar_adenda(actor, fila.id, motivo, 'Documento incorporado: '+nombre, documento.id)
            final = Path(settings.TV_MED_ARCHIVOS)/relativa
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(preparado, final)
            publicado = final
            return documento
    except BaseException:
        if publicado:
            publicado.unlink(missing_ok=True)
        raise
    finally:
        preparado.unlink(missing_ok=True)


def actualizar(actor, identificador, valores, revision, motivo=''):
    """Metadatos y archivo/restauración. Una consulta finalizada exige motivo y deja adenda."""
    valores = dominio.clean_update(valores)
    mapa = {'title': 'titulo', 'category': 'categoria', 'notes': 'descripcion', 'document_date': 'fecha_documento',
            'archived': 'archivado'}
    with atomico():
        documento = Documento.objects.select_for_update().filter(pk=identificador).first()
        if not documento:
            raise NoEncontrado('No existe el documento.')
        autorizar(actor, documento.paciente_id, documento.consulta_id, documento.borrador_id)
        if documento.doctor_id != actor.cuenta_id:
            actor.exigir_admin()
        if documento.revision != revision:
            raise VersionConflict(documento_a_dict(documento))
        if 'category' in valores and valores['category'] not in CATEGORIAS:
            raise DataError('Elige una categoría de documento válida.')
        if documento.consulta_id and documento.consulta.estado != Consulta.Estado.BORRADOR:
            if not motivo.strip():
                raise DataError('Indica el motivo del cambio documental.')
            servicio_consultas.agregar_adenda(actor, documento.consulta_id, motivo,
                                              'Metadatos/estado del documento actualizados: '+documento.titulo, documento.id)
        previo = {clave: getattr(documento, mapa[clave]) for clave in valores}
        previo = {k: (v.isoformat() if hasattr(v, 'isoformat') else v) for k, v in previo.items()}
        ahora = timezone.now()
        documento.historial = [*documento.historial, {'at': ahora.isoformat(timespec='seconds'), 'actor': actor.cuenta_id,
                                                      'reason': motivo, 'previous': previo}]
        for clave, valor in valores.items():
            setattr(documento, mapa[clave], (date.fromisoformat(valor) if valor else None) if clave == 'document_date' else valor)
        documento.revision += 1
        documento.updated_at, documento.updated_by = ahora, actor.cuenta_id
        documento.save()
        return documento


def miniatura(actor, identificador, tamano=160):
    documento = obtener(actor, identificador)
    if not documento.mime.startswith('image/'):
        return None
    destino = Path(settings.TV_MED_ARCHIVOS)/'documentos'/'miniaturas'/f'{documento.id}-{tamano}.png'
    if not destino.exists():
        dominio.make_thumbnail(ruta_verificada(actor, identificador), destino, tamano)
    return destino


def informe_integridad(actor):
    """Documentos sin archivo, archivos sin fila y preparaciones abandonadas (administrador)."""
    actor.exigir_admin()
    filas = list(Documento.objects.all())
    referencias = {d.ruta for d in filas}
    ausentes = [str(d.id) for d in filas if not ruta_absoluta(d).is_file()]
    originales = raiz()/'originales'
    huerfanos = [p.name for p in originales.glob('*') if p.is_file() and f'documentos/originales/{p.name}' not in referencias] \
        if originales.exists() else []
    preparacion = raiz()/'preparacion'
    pendientes = [p.name for p in preparacion.glob('*') if p.is_file()] if preparacion.exists() else []
    return {'documents': len(filas), 'missing': ausentes, 'unreferenced': huerfanos, 'pending': pendientes}
