"""Reglas puras de exportación, importación y verificación de respaldos.

El escritorio mezclaba estas reglas con su almacén de archivos (clase ``Transfer``). Aquí quedan solo las
funciones que no tocan base de datos ni carpeta clínica: reciben filas y archivos y devuelven resultados.
"""
import csv
import hashlib
import io
import json
import re
import zipfile
from datetime import date
from pathlib import Path

from .clinical_models import VITALS, medication_text
from .errores import DataError
from .texto import normalized

BACKUP_CATEGORIES = ('config', 'data', 'attachments', 'avatars')
IMPORT_FIELDS = ('name', 'birth_date', 'phone', 'email')
CSV_MAX_BYTES = 10_000_000
CSV_MAX_ROWS = 10000

PATIENT_EXPORT_FIELDS = ('id', 'file_number', 'name', 'birth_date', 'phone', 'email')
CONSULTATION_BASE_FIELDS = ('id', 'patient_id', 'patient_file_number', 'patient_name', 'doctor_id', 'doctor_name',
                            'attended_at', 'status', 'consultation_type', 'reason', 'subjective', 'objective',
                            'assessment', 'assessment_notes', 'plan', 'medications', 'prescription_summary',
                            'studies', 'vitals_at')
CONSULTATION_STRUCTURED = ('diagnoses', 'prescriptions', 'vitals', 'study_orders', 'addenda', 'followup')
CONSULTATION_FIELDS = (*CONSULTATION_BASE_FIELDS,
                       *(part for key in VITALS for part in (key, key+'_unit')),
                       *(key+'_json' for key in CONSULTATION_STRUCTURED))


def safe_csv(value):
    """Neutraliza fórmulas de hoja de cálculo al exportar."""
    text = str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text


# --- Exportación -----------------------------------------------------------------------------------------------

def patient_csv_row(row):
    return [safe_csv(row.get(f, '')) for f in PATIENT_EXPORT_FIELDS]


def check_period(start='', end=''):
    for value in (start, end):
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise DataError('Revisa las fechas del periodo.') from exc
    if start and end and start > end:
        raise DataError('La fecha inicial debe ser anterior o igual a la final.')


def select_consultations(rows, *, start='', end='', doctor_id='', include_drafts=False, identifiers=None):
    """Consultas exportables en orden cronológico; ``rows`` ya debe excluir borradores ajenos."""
    check_period(start, end)
    rows = [r for r in rows if (include_drafts or r['status'] != 'Borrador')
            and (not doctor_id or r['doctor_id'] == doctor_id)
            and (not start or r.get('attended_at', '')[:10] >= start)
            and (not end or r.get('attended_at', '')[:10] <= end)
            and (identifiers is None or r['id'] in identifiers)]
    return sorted(rows, key=lambda r: (r.get('attended_at', ''), r['id']))


def consultation_csv_row(row, patient=None, doctor_name=''):
    """Fila de la exportación de consultas, con las mismas columnas que el escritorio."""
    patient = patient or {}
    latest = max(row.get('vitals', []), key=lambda v: v.get('at', ''), default={})
    data = {key: row.get(key, '') for key in CONSULTATION_BASE_FIELDS}
    data.update(patient_file_number=patient.get('file_number', ''), patient_name=patient.get('name', ''),
                consultation_type=row.get('type', row.get('consultation_type', '')),
                doctor_name=doctor_name,
                prescription_summary='\n'.join(medication_text(m) for m in row.get('prescriptions', [])),
                vitals_at=latest.get('at', ''))
    for key in VITALS:
        item = latest.get('values', {}).get(key, {})
        data[key], data[key+'_unit'] = item.get('value', ''), item.get('unit', '')
    for key in CONSULTATION_STRUCTURED:
        data[key+'_json'] = json.dumps(row.get(key, {} if key == 'followup' else []), ensure_ascii=False)
    return {key: safe_csv(value) for key, value in data.items()}


def write_consultation_csv(stream, rows, patients, doctors):
    """Escribe el CSV en ``stream`` (texto, newline=''); ``patients`` y ``doctors`` son dicts por id."""
    writer = csv.DictWriter(stream, fieldnames=CONSULTATION_FIELDS)
    writer.writeheader()
    for row in rows:
        writer.writerow(consultation_csv_row(row, patients.get(row['patient_id']),
                                             doctors.get(row['doctor_id'], {}).get('name', '')))


def write_patient_csv(stream, rows):
    writer = csv.writer(stream)
    writer.writerow(PATIENT_EXPORT_FIELDS)
    for row in rows:
        writer.writerow(patient_csv_row(row))


# --- Respaldo del escritorio (ZIP con manifiesto v1) -------------------------------------------------------------

def check_member_name(name):
    parts = Path(name).parts
    if (not parts or name.startswith(('/', '\\')) or '..' in parts or ':' in name or '\\' in name
            or parts[0] not in BACKUP_CATEGORIES):
        raise DataError('Ruta no válida en el respaldo.')


def verify_backup(path):
    """Verifica un ZIP de respaldo y devuelve su manifiesto. Lanza ``DataError`` ante cualquier anomalía."""
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip():
                raise DataError('El respaldo tiene archivos corruptos.')
            try:
                manifest = json.loads(archive.read('manifest.json'))
            except (KeyError, ValueError) as exc:
                raise DataError('Manifiesto incompatible.') from exc
            if (not isinstance(manifest, dict) or manifest.get('schema_version') != 1
                    or not isinstance(manifest.get('files'), dict)):
                raise DataError('Manifiesto incompatible.')
            names = archive.namelist()
            if len(names) != len(set(names)) or set(names) != set(manifest['files']) | {'manifest.json'}:
                raise DataError('El respaldo contiene archivos no declarados.')
            for name, expected in manifest['files'].items():
                check_member_name(name)
                with archive.open(name) as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                        raise DataError('No coincide la integridad del respaldo.')
            return manifest
    except zipfile.BadZipFile as exc:
        raise DataError('El archivo no es un respaldo ZIP válido.') from exc


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataError(f'Clave JSON repetida: {key}.')
        result[key] = value
    return result


def loads_strict(data):
    """JSON (texto o bytes UTF-8, con o sin BOM) sin claves repetidas ni NaN/Infinity."""
    def invalid(_):
        raise DataError('Número JSON inválido.')
    try:
        if isinstance(data, (bytes, bytearray)):
            data = bytes(data).decode('utf-8-sig')
        return json.loads(data, object_pairs_hook=reject_duplicate_keys, parse_constant=invalid)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DataError('JSON inválido.') from exc


# --- Importación CSV de pacientes ---------------------------------------------------------------------------------

def read_csv_text(text, delimiter=','):
    """Lee el CSV ya decodificado (UTF-8 con o sin BOM) y devuelve ``{'columns', 'rows'}``."""
    if delimiter not in (',', ';', '\t'):
        raise DataError('Separador CSV no admitido.')
    try:
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter, strict=True)
        columns = reader.fieldnames
        if not columns or len(columns) != len(set(columns)) or any(not c.strip() for c in columns):
            raise DataError('Las columnas deben tener encabezados distintos y no vacíos.')
        rows = list(reader)
        if len(rows) > CSV_MAX_ROWS:
            raise DataError('Cada lote admite hasta 10 000 pacientes.')
        return {'columns': columns, 'rows': rows}
    except (UnicodeError, csv.Error) as exc:
        raise DataError('No se pudo leer el CSV. Revisa UTF-8, comillas y separador.') from exc


def read_csv_bytes(data, name='pacientes.csv', delimiter=','):
    """Valida nombre, tamaño y codificación del archivo subido y lo lee."""
    if not str(name).lower().endswith('.csv') or len(data) > CSV_MAX_BYTES:
        raise DataError('Selecciona un CSV UTF-8 de hasta 10 MB. Los paquetes ZIP y JSON no se importan como pacientes.')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeError as exc:
        raise DataError('No se pudo leer el CSV. Revisa UTF-8, comillas y separador.') from exc
    return read_csv_text(text, delimiter)


def validate_import_patient(row):
    errors = {}
    if not row.get('name', '').strip():
        errors['name'] = 'Nombre obligatorio'
    if row.get('birth_date'):
        try:
            if date.fromisoformat(row['birth_date']) > date.today():
                raise ValueError()
        except ValueError:
            errors['birth_date'] = 'Usa AAAA-MM-DD y una fecha no futura'
    if row.get('email') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', row['email']):
        errors['email'] = 'Correo inválido'
    return errors


def inspect_import(source, mapping, patients):
    """Vista previa de un lote: errores por fila y posibles duplicados (nombre o teléfono).

    ``patients`` son todos los pacientes existentes (activos y archivados) con ``name``, ``file_number`` y
    ``phone``. Devuelve las filas en el mismo formato del escritorio, sin el identificador de lote.
    """
    if not mapping.get('name') or any(column and column not in source['columns'] for column in mapping.values()):
        raise DataError('Mapea Nombre y revisa las columnas seleccionadas.')
    names, phones = {}, {}
    for patient in patients:
        names.setdefault(normalized(patient['name']), []).append(patient['file_number'])
        if patient.get('phone'):
            phones.setdefault(normalized(patient['phone']), []).append(patient['file_number'])
    result = []
    for number, source_row in enumerate(source['rows'], 2):
        row = {key: source_row.get(mapping.get(key), '') or '' for key in IMPORT_FIELDS}
        errors = validate_import_patient(row)
        if None in source_row:
            errors['fila'] = 'Hay más valores que encabezados'
        duplicates = []
        for field, index, label in [('name', names, 'Nombre coincidente'), ('phone', phones, 'Teléfono coincidente')]:
            if row[field] and normalized(row[field]) in index:
                duplicates.append(label+': '+', '.join(index[normalized(row[field])][:5]))
        result.append({'number': number, 'patient': row, 'errors': errors, 'duplicates': duplicates})
        if not errors:
            names.setdefault(normalized(row['name']), []).append('fila '+str(number))
            if row['phone']:
                phones.setdefault(normalized(row['phone']), []).append('fila '+str(number))
    return result
