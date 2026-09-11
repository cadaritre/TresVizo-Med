"""Exportación e importación de pacientes y copias locales verificables."""
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import zipfile
import shutil
import tempfile
import uuid
import re
from datetime import date
from app.services import normalized, now
from app.storage import DataError, read_json, atomic_json


def safe_csv(value):
    text = str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text


class Transfer:
    def __init__(self, store, auth, clinic):
        self.store, self.auth, self.clinic = store, auth, clinic

    def export_patients(self, destination, identifiers=None):
        self.auth.require()
        rows = self.clinic.list('patients', include_archived=identifiers is not None)
        if identifiers is not None:
            rows = [r for r in rows if r['id'] in identifiers]
        path = Path(destination)
        if path.suffix.lower() == '.json':
            atomic_json(path, {'schema_version': 1, 'patients': rows})
        else:
            with path.open('w', newline='', encoding='utf-8-sig') as stream:
                writer = csv.writer(stream)
                fields = ('id', 'file_number', 'name', 'birth_date', 'phone', 'email')
                writer.writerow(fields)
                for row in rows:
                    writer.writerow([safe_csv(row.get(f, '')) for f in fields])
        self.auth.audit('exportar_pacientes', str(len(rows)))

    def consultation_rows(self, *, start='', end='', doctor_id='', include_drafts=False, identifiers=None):
        self.auth.require()
        for value in (start, end):
            if value:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise DataError('Revisa las fechas del periodo.') from exc
        if start and end and start > end:
            raise DataError('La fecha inicial debe ser anterior o igual a la final.')
        rows = self.clinic.list('encounters')
        rows = [r for r in rows if (include_drafts or r['status'] != 'Borrador')
                and (not doctor_id or r['doctor_id'] == doctor_id)
                and (not start or r.get('attended_at', '')[:10] >= start)
                and (not end or r.get('attended_at', '')[:10] <= end)
                and (identifiers is None or r['id'] in identifiers)]
        return sorted(rows, key=lambda r: (r.get('attended_at', ''), r['id']))

    def export_consultations(self, destination, **filters):
        from app.clinical_models import VITALS, medication_text
        rows = self.consultation_rows(**filters)
        patients = {r['id']: r for r in self.clinic.list('patients', True)}
        doctors = {u['id']: u for u in self.auth.users()}
        base = ('id', 'patient_id', 'patient_file_number', 'patient_name', 'doctor_id', 'doctor_name',
                'attended_at', 'status', 'consultation_type', 'reason', 'subjective', 'objective',
                'assessment', 'assessment_notes', 'plan', 'medications', 'prescription_summary', 'studies', 'vitals_at')
        structured = ('diagnoses', 'prescriptions', 'vitals', 'study_orders', 'addenda', 'followup')
        fields = (*base, *(part for key in VITALS for part in (key, key+'_unit')),
                  *(key+'_json' for key in structured))
        target = Path(destination)
        temporary = target.with_name('.'+target.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('x', newline='', encoding='utf-8-sig') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                for row in rows:
                    patient = patients.get(row['patient_id'], {})
                    latest = max(row.get('vitals', []), key=lambda v: v.get('at', ''), default={})
                    data = {key: row.get(key, '') for key in base}
                    data.update(patient_file_number=patient.get('file_number', ''), patient_name=patient.get('name', ''),
                                doctor_name=doctors.get(row['doctor_id'], {}).get('name', ''),
                                prescription_summary='\n'.join(medication_text(m) for m in row.get('prescriptions', [])),
                                vitals_at=latest.get('at', ''))
                    for key in VITALS:
                        item = latest.get('values', {}).get(key, {})
                        data[key], data[key+'_unit'] = item.get('value', ''), item.get('unit', '')
                    for key in structured:
                        data[key+'_json'] = json.dumps(row.get(key, {} if key == 'followup' else []), ensure_ascii=False)
                    writer.writerow({key: safe_csv(value) for key, value in data.items()})
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        self.auth.audit('exportar_consultas', str(len(rows)))
        return len(rows)

    def backup(self, destination):
        self.auth.require('admin')
        destination = Path(destination).resolve()
        manifest = {'schema_version': 1, 'created_at': datetime.now().astimezone().isoformat(), 'files': {}}
        temp = destination.with_suffix('.zip.tmp')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.store.lock:
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as archive:
                for category in ('config', 'data', 'attachments', 'avatars'):
                    for path in (self.store.root/category).rglob('*'):
                        if path.is_file() and path.suffix != '.tmp' and 'staging' not in path.relative_to(self.store.root).parts:
                            name = path.relative_to(self.store.root).as_posix()
                            with path.open('rb') as stream:
                                manifest['files'][name] = hashlib.file_digest(stream, 'sha256').hexdigest()
                            archive.write(path, name)
                archive.writestr('manifest.json', json.dumps(manifest))
            self.verify_backup(temp)
            temp.replace(destination)
        self.auth.audit('respaldo', 'copia_local')
        self.store.write('config/last_backup.json', {'path': str(destination), 'created_at': manifest['created_at'], 'files': len(manifest['files']), 'verified': True})
        return manifest

    def verify_backup(self, path):
        with zipfile.ZipFile(path) as archive:
            if archive.testzip():
                raise DataError('El respaldo tiene archivos corruptos.')
            manifest = json.loads(archive.read('manifest.json'))
            if manifest.get('schema_version') != 1 or not isinstance(manifest.get('files'), dict):
                raise DataError('Manifiesto incompatible.')
            if len(archive.namelist()) != len(set(archive.namelist())) or set(archive.namelist()) != set(manifest['files']) | {'manifest.json'}:
                raise DataError('El respaldo contiene archivos no declarados.')
            for name, expected in manifest['files'].items():
                parts = Path(name).parts
                if name.startswith(('/', '\\')) or '..' in parts or ':' in name or parts[0] not in ('config', 'data', 'attachments', 'avatars'):
                    raise DataError('Ruta no válida en el respaldo.')
                with archive.open(name) as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                        raise DataError('No coincide la integridad del respaldo.')
            return manifest

    def restore(self, source, destination):
        self.auth.require('admin')
        manifest = self.verify_backup(source)
        destination = Path(destination).resolve()
        if destination == self.store.root.resolve() or destination.is_relative_to(self.store.root.resolve()):
            raise DataError('Restaura en una carpeta separada de la clínica activa.')
        if destination.exists():
            raise DataError('Elige una carpeta nueva; no se reemplazará una carpeta existente.')
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix='.restaurar-', dir=destination.parent))
        try:
            with zipfile.ZipFile(source) as archive:
                for name in manifest['files']:
                    target = (staging/name).resolve()
                    if not target.is_relative_to(staging.resolve()):
                        raise DataError('Ruta inválida en respaldo.')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as src, target.open('wb') as dst:
                        shutil.copyfileobj(src,dst,1024*1024)
                    with target.open('rb') as stream:
                        if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['files'][name]:
                            raise DataError('La copia restaurada no coincide con el respaldo.')
                    if target.suffix == '.json':
                        read_json(target)
            schema = staging/'config'/'schema.json'
            if schema.exists() and read_json(schema).get('version',1) > 2:
                raise DataError('El respaldo requiere una versión posterior.')
            for metadata in (staging/'data'/'attachments').glob('*.json'):
                row = read_json(metadata)
                original = (staging/row.get('path', '')).resolve()
                if not original.is_relative_to(staging.resolve()) or not original.is_file():
                    raise DataError('Falta un original declarado por los documentos del respaldo.')
                with original.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != row.get('sha256'):
                        raise DataError('Un documento restaurado no coincide con sus metadatos.')
            # Logos históricos usaban rutas absolutas; remapear únicamente copias incluidas.
            identity_path = staging/'config'/'identity.json'
            if identity_path.exists():
                identity = read_json(identity_path)
                for key in ('clinic_logo', 'clinic_icon'):
                    logo = identity.get(key, '')
                    if logo and (staging/'config'/Path(logo).name).is_file():
                        identity[key] = str(destination/'config'/Path(logo).name)
                atomic_json(identity_path,identity)
            staging.rename(destination)
        except BaseException:
            shutil.rmtree(staging,ignore_errors=True)
            raise
        self.auth.audit('restaurar_respaldo','copia_separada')
        return destination

    def export_package(self, destination, patient_id, attachment_ids, encounter_id=None):
        from app.attachments import Attachments
        documents = Attachments(self.store,self.auth,self.clinic)
        documents.authorize(patient_id,encounter_id)
        patient = self.store.read(f'data/patients/{patient_id}.json')
        encounters = [r for r in self.clinic.list('encounters') if r['patient_id'] == patient_id and (not encounter_id or r['id'] == encounter_id)]
        rows = [documents.get(i) for i in attachment_ids]
        if any(r['patient_id'] != patient_id or r.get('draft_id') or encounter_id and r.get('encounter_id') != encounter_id for r in rows):
            raise DataError('La selección contiene documentos de otro destino.')
        manifest = {'schema_version':2,'kind':'patient-export','files':{}}
        destination = Path(destination)
        temp = destination.with_suffix('.zip.tmp')
        with self.store.lock:
            with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
                payload = json.dumps({'schema_version':2,'patient':patient,'encounters':encounters,'attachments':rows},ensure_ascii=False).encode('utf-8')
                archive.writestr('expediente.json',payload)
                manifest['files']['expediente.json'] = hashlib.sha256(payload).hexdigest()
                for row in rows:
                    path = documents.path(row['id'])
                    archive.write(path,row['path'])
                    manifest['files'][row['path']] = row['sha256']
                archive.writestr('manifest.json',json.dumps(manifest))
            with zipfile.ZipFile(temp) as archive:
                if archive.testzip():
                    raise DataError('No se pudo verificar el paquete.')
            temp.replace(destination)
        self.auth.audit('exportar_expediente',patient_id)

    def preview_csv(self, path, delimiter=','):
        self.auth.require('admin')
        path = Path(path)
        if path.stat().st_size > 10_000_000:
            raise DataError('Importación limitada a 10 MB.')
        text = path.read_text(encoding='utf-8-sig')
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames or 'name' not in reader.fieldnames:
            raise DataError('El CSV debe contener la columna name. Opcionales: birth_date, phone, email.')
        result = []
        for number, row in enumerate(reader, 2):
            if not row.get('name', '').strip():
                raise DataError(f'Fila {number}: falta name.')
            result.append({key: row.get(key, '') for key in ('name', 'birth_date', 'phone', 'email')})
        return result

    def read_csv(self, path, delimiter=','):
        self.auth.require('admin')
        path = Path(path)
        if path.suffix.lower() != '.csv' or path.stat().st_size > 10_000_000:
            raise DataError('Selecciona un CSV UTF-8 de hasta 10 MB. Los paquetes ZIP y JSON no se importan como pacientes.')
        if delimiter not in (',', ';', '\t'):
            raise DataError('Separador CSV no admitido.')
        try:
            reader = csv.DictReader(io.StringIO(path.read_text(encoding='utf-8-sig')), delimiter=delimiter, strict=True)
            columns = reader.fieldnames
            if not columns or len(columns) != len(set(columns)) or any(not c.strip() for c in columns):
                raise DataError('Las columnas deben tener encabezados distintos y no vacíos.')
            rows = list(reader)
            if len(rows) > 10000:
                raise DataError('Cada lote admite hasta 10 000 pacientes.')
            return {'columns': columns, 'rows': rows}
        except (UnicodeError, csv.Error) as exc:
            raise DataError('No se pudo leer el CSV. Revisa UTF-8, comillas y separador.') from exc

    @staticmethod
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

    def inspect_import(self, source, mapping):
        self.auth.require('admin')
        if not mapping.get('name') or any(column and column not in source['columns'] for column in mapping.values()):
            raise DataError('Mapea Nombre y revisa las columnas seleccionadas.')
        patients = self.clinic.list('patients', True)
        names, phones = {}, {}
        for patient in patients:
            names.setdefault(normalized(patient['name']), []).append(patient['file_number'])
            if patient.get('phone'):
                phones.setdefault(normalized(patient['phone']), []).append(patient['file_number'])
        result = []
        for number, source_row in enumerate(source['rows'], 2):
            row = {key: source_row.get(mapping.get(key), '') or '' for key in ('name', 'birth_date', 'phone', 'email')}
            errors = self.validate_import_patient(row)
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
        return {'id': str(uuid.uuid4()), 'rows': result, 'versions': {p['id']: p['revision'] for p in patients}}

    def import_patients(self, preview, selected, accepted_duplicates=()):
        actor = self.auth.require('admin')
        batch_id = str(uuid.UUID(preview['id']))
        with self.store.lock:
            receipt_path = f'data/import_batches/{batch_id}.json'
            previous = self.store.read(receipt_path)
            if previous:
                return previous
            patients = self.clinic.list('patients', True)
            if {p['id']: p['revision'] for p in patients} != preview['versions']:
                raise DataError('Los pacientes cambiaron desde la vista previa. Vuelve a validar el lote; no se importó ninguna fila.')
            rows = [r for r in preview['rows'] if r['number'] in selected]
            if not rows:
                raise DataError('Selecciona al menos una fila válida.')
            changes, identifiers = {}, []
            for offset, item in enumerate(rows, 1):
                row = dict(item['patient'])
                if item['errors'] or self.validate_import_patient(row):
                    raise DataError(f"Fila {item['number']}: corrige los campos indicados antes de importar.")
                if item['duplicates'] and item['number'] not in accepted_duplicates:
                    raise DataError(f"Fila {item['number']}: confirma que corresponde a una persona distinta.")
                identifier = str(uuid.uuid5(uuid.UUID(batch_id), str(item['number'])))
                row.update(id=identifier, schema_version=2, revision=1, file_number=f'RC-{len(patients)+offset:06d}',
                    created_at=now(), updated_at=now(), created_by=actor['id'], updated_by=actor['id'],
                    allergy_status='No interrogado', provenance={'import_batch': batch_id, 'row': item['number']})
                changes[f'data/patients/{identifier}.json'] = row
                identifiers.append(identifier)
            receipt = {'schema_version': 1, 'id': batch_id, 'actor': actor['id'], 'at': now(), 'patients': identifiers, 'count': len(rows)}
            changes[receipt_path] = receipt
            changes[f'data/audit/{batch_id}.json'] = {'id': batch_id, 'actor': actor['id'], 'at': now(), 'action': 'importar_pacientes', 'target': batch_id}
            self.store.transaction(changes)
            return receipt
