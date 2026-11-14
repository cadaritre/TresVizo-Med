"""Filas de la base ↔ diccionarios con el esquema del escritorio (``schema_version: 2``).

Las reglas de ``dominio`` trabajan con diccionarios; los servicios convierten aquí en ambos sentidos.
"""
from datetime import date, datetime

from django.utils import timezone

from .dominio.texto import normalized

PACIENTE_COLUMNAS = {'id', 'name', 'birth_date', 'approx_age', 'sex', 'phone', 'file_number', 'archived', 'lifecycle',
                     'revision', 'created_at', 'created_by', 'updated_at', 'updated_by', 'photo_attachment_id',
                     'schema_version'}
CONSULTA_COLUMNAS = {'id', 'patient_id', 'doctor_id', 'captured_by', 'status', 'archived', 'attended_at', 'type', 'reason',
                     'assessment', 'plan', 'editor_state', 'revision', 'created_at', 'created_by', 'updated_at',
                     'updated_by', 'lifecycle', 'addenda', 'schema_version'}


def iso(momento):
    return momento.isoformat(timespec='seconds') if momento else None


def a_aware(texto):
    """Fecha ISO del escritorio → ``datetime`` con zona (las ingenuas se toman en la zona del proyecto)."""
    momento = datetime.fromisoformat(texto)
    return timezone.make_aware(momento) if timezone.is_naive(momento) else momento


def texto_busqueda(d):
    return normalized(' '.join(str(d.get(k) or '') for k in ('name', 'preferred_name', 'file_number', 'phone')))


def paciente_a_dict(p):
    d = dict(p.datos)
    d.update(id=str(p.id), name=p.nombre, file_number=p.folio, archived=p.archivado, revision=p.revision,
             schema_version=2, created_at=iso(p.created_at), created_by=p.created_by, updated_at=iso(p.updated_at),
             updated_by=p.updated_by)
    if p.nacimiento:
        d['birth_date'] = p.nacimiento.isoformat()
    if p.edad_aproximada:
        d['approx_age'] = p.edad_aproximada
    if p.sexo:
        d['sex'] = p.sexo
    if p.telefono:
        d['phone'] = p.telefono
    if p.foto_documento:
        d['photo_attachment_id'] = str(p.foto_documento)
    if p.lifecycle:
        d['lifecycle'] = p.lifecycle
    return d


def paciente_columnas(d):
    """Separa un diccionario de paciente en columnas y ``datos``."""
    nacimiento = date.fromisoformat(d['birth_date']) if d.get('birth_date') else None
    return {
        'nombre': d['name'], 'nacimiento': nacimiento,
        'edad_aproximada': d.get('approx_age') or {}, 'sexo': d.get('sex', ''), 'telefono': d.get('phone', ''),
        'datos': {k: v for k, v in d.items() if k not in PACIENTE_COLUMNAS},
    }


def alergias_texto(datos):
    """Sustancias de las alergias registradas, o el estado declarado cuando no hay ninguna."""
    sustancias = [r.get('substance', '') for r in datos.get('allergy_records', []) if r.get('substance')]
    return ', '.join(sustancias) or datos.get('allergies', '')


def paciente_resumen(p):
    d = {'id': str(p.id), 'name': p.nombre, 'file_number': p.folio, 'archived': p.archivado,
         'allergies': alergias_texto(p.datos)}
    if p.nacimiento:
        d['birth_date'] = p.nacimiento.isoformat()
    if p.edad_aproximada:
        d['approx_age'] = p.edad_aproximada
    if p.telefono:
        d['phone'] = p.telefono
    return d


def adenda_a_dict(a):
    d = {'id': str(a.id), 'actor': a.autor_id, 'at': iso(a.momento), 'reason': a.motivo, 'content': a.contenido,
         'kind': a.tipo}
    if a.documento_id:
        d['attachment_id'] = str(a.documento_id)
    return d


def consulta_a_dict(c, adendas=True):
    d = dict(c.contenido)
    d.update(id=str(c.id), patient_id=str(c.paciente_id), doctor_id=c.doctor_id, captured_by=c.captured_by,
             status=c.estado, archived=c.archivada, attended_at=c.atendida_iso, type=c.tipo, reason=c.motivo,
             assessment=c.diagnostico, plan=c.plan, revision=c.revision, schema_version=2,
             created_at=iso(c.created_at), created_by=c.created_by, updated_at=iso(c.updated_at), updated_by=c.updated_by)
    if c.editor_state:
        d['editor_state'] = c.editor_state
    if c.lifecycle:
        d['lifecycle'] = c.lifecycle
    if adendas:
        d['addenda'] = [adenda_a_dict(a) for a in c.adendas.all()]
    return d


def consulta_contenido(d):
    return {k: v for k, v in d.items() if k not in CONSULTA_COLUMNAS}


def documento_a_dict(x):
    d = {'id': str(x.id), 'patient_id': str(x.paciente_id) if x.paciente_id else None,
         'encounter_id': str(x.consulta_id) if x.consulta_id else None,
         'draft_id': str(x.borrador_id) if x.borrador_id else None, 'title': x.titulo, 'original_name': x.nombre_original,
         'path': x.ruta, 'mime': x.mime, 'size': x.tamano, 'sha256': x.sha256, 'category': x.categoria,
         'notes': x.descripcion, 'document_date': x.fecha_documento.isoformat() if x.fecha_documento else '',
         'doctor_id': x.doctor_id, 'created_at': iso(x.created_at), 'updated_at': iso(x.updated_at),
         'revision': x.revision, 'archived': x.archivado, 'replaces': str(x.version_de_id) if x.version_de_id else None,
         'provenance': x.origen, 'schema_version': 2}
    if x.historial:
        d['history'] = x.historial
    return d


def fecha_corta(texto):
    """``2026-09-10`` (o con hora) → ``10/09/2026``; lo que no es una fecha ISO se devuelve igual."""
    try:
        return date.fromisoformat(str(texto)[:10]).strftime('%d/%m/%Y')
    except ValueError:
        return str(texto)
