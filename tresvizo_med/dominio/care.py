"""Reglas puras de atención: migración conservadora v1→v2, evolución de signos y catálogo de medicamentos.

El escritorio las tenía dentro de ``Care`` y ``migrate(store)``, atadas a su almacén de archivos; aquí reciben y
devuelven filas.
"""
import uuid
from copy import deepcopy

from .errores import DataError
from .texto import normalized

SCHEMA_VERSION = 2
LEGACY_KEYS = ('allergies', 'problems', 'history', 'medications', 'objective')


def check_schema_version(version):
    """Rechaza datos escritos por una versión posterior a la que entiende este código."""
    if version > SCHEMA_VERSION:
        raise DataError('La carpeta requiere una versión posterior de la aplicación.')


def migrate_record(row):
    """Migración v1→v2 de un paciente o consulta: conserva el texto clínico en ``legacy`` sin interpretarlo.

    Idempotente: una fila ya migrada se devuelve igual. No modifica la fila recibida.
    """
    row = deepcopy(row)
    row.setdefault('legacy', {k: row[k] for k in LEGACY_KEYS if row.get(k)})
    row['schema_version'] = SCHEMA_VERSION
    row.setdefault('archived', False)
    return row


def evolution_points(encounters, patient_id, key):
    """Serie cronológica de una medición (``key`` de ``clinical_models.VITALS`` o ``bmi``).

    Solo cuentan consultas finalizadas y no archivadas del paciente.
    """
    points = []
    for row in encounters:
        if row['patient_id'] != patient_id or row['status'] != 'Finalizada' or row.get('archived'):
            continue
        for group in row.get('vitals', []):
            item = group.get('values', {}).get(key)
            if key == 'bmi' and group.get('bmi') is not None:
                item = {'normalized_value': group['bmi'], 'normalized_unit': 'kg/m²'}
            if item:
                points.append({'at': group['at'], 'value': item['normalized_value'], 'unit': item['normalized_unit'],
                               'context': group.get('context', ''), 'encounter_id': row['id'],
                               'doctor_id': row['doctor_id']})
    return sorted(points, key=lambda p: p['at'])


def filter_catalog(rows, query=''):
    needle = normalized(query)
    return [r for r in rows if needle in normalized(r['name'])]


def catalog_item(row, catalog, actor_id, favorite=False):
    """Fila del catálogo para guardar un medicamento: reutiliza el identificador del mismo nombre y concentración
    y acumula los favoritos por médico."""
    name = row.get('name', '').strip()
    if not name:
        raise DataError('Escribe el nombre del medicamento.')
    known = next((r for r in catalog if normalized(r['name']) == normalized(name)
                  and r.get('strength') == row.get('strength')), None)
    item = {k: row.get(k, '') for k in ('name', 'ingredient', 'presentation', 'strength')}
    item['id'] = known['id'] if known else str(uuid.uuid4())
    item['favorites'] = list(set((known or {}).get('favorites', []) + ([actor_id] if favorite else [])))
    return item
