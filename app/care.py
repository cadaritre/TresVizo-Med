"""Borradores privados, consultas longitudinales y migración conservadora."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import hashlib
import json
import uuid
import zipfile
from app.storage import DataError
from app.services import now, normalized

def migrate(store):
    store.recover()
    version = store.read('config/schema.json', {'version': 1})['version']
    if version > 2:
        raise DataError('La carpeta requiere una versión posterior de la aplicación.')
    if version == 2:
        return
    existing = [p for category in ('data', 'config', 'attachments', 'avatars') for p in (store.root/category).rglob('*') if p.is_file()]
    if existing:
        destination = store.root/'backups'/('antes-migracion-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip')
        destination.parent.mkdir(parents=True, exist_ok=True)
        manifest = {'schema_version': 1, 'files': {}}
        with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in existing:
                name = path.relative_to(store.root).as_posix()
                with path.open('rb') as stream:
                    manifest['files'][name] = hashlib.file_digest(stream, 'sha256').hexdigest()
                archive.write(path, name)
            archive.writestr('manifest.json', json.dumps(manifest))
        with zipfile.ZipFile(destination) as archive:
            if archive.testzip() or any(hashlib.sha256(archive.read(k)).hexdigest() != v for k, v in manifest['files'].items()):
                raise DataError('No se pudo verificar el respaldo previo a la migración.')
    changes = {'config/schema.json': {'version': 2}}
    for kind in ('patients', 'encounters'):
        for row in store.records(kind):
            row.setdefault('legacy', {k: row[k] for k in ('allergies', 'problems', 'history', 'medications', 'objective') if row.get(k)})
            row['schema_version'] = 2
            row.setdefault('archived', False)
            changes[f"data/{kind}/{row['id']}.json"] = row
    store.transaction(changes)

class Care:
    def __init__(self, store, auth, clinic):
        self.store, self.auth, self.clinic = store, auth, clinic

    def drafts(self):
        actor = self.auth.require()
        return [r for r in self.store.records('registration_drafts') if r['doctor_id'] == actor['id'] and r['status'] == 'Borrador']

    def save_draft(self, payload, identifier=None, patient_id=None, revision=None):
        actor = self.auth.require()
        identifier = identifier or str(uuid.uuid4())
        path = f'data/registration_drafts/{uuid.UUID(identifier)}.json'
        with self.store.lock:
            old = self.store.read(path)
            if old and (old['doctor_id'] != actor['id'] or old['status'] != 'Borrador'):
                raise DataError('Este borrador no está disponible para tu sesión.')
            data = {'id': identifier, 'doctor_id': actor['id'], 'schema_version': 2, 'status': 'Borrador',
                    'payload': deepcopy(payload), 'patient_id': patient_id, 'source_revision': revision, 'updated_at': now()}
            self.store.write(path, data)
            return data

    def discard(self, identifier):
        actor = self.auth.require()
        path = f'data/registration_drafts/{uuid.UUID(identifier)}.json'
        row = self.store.read(path)
        if not row or row['doctor_id'] != actor['id']:
            raise DataError('Borrador privado no disponible.')
        row.update(status='Descartado', updated_at=now())
        self.store.write(path, row)

    def register(self, identifier, payload):
        actor = self.auth.require()
        path = f'data/registration_drafts/{uuid.UUID(identifier)}.json'
        with self.store.lock:
            draft = self.store.read(path)
            if not draft or draft['doctor_id'] != actor['id']:
                raise DataError('Borrador privado no disponible.')
            if draft['status'] == 'Registrado':
                return self.store.read(f"data/patients/{draft['patient_id']}.json")
            if draft['status'] != 'Borrador':
                raise DataError('El borrador fue descartado.')
            # Un identificador persistido hace idempotente una recuperación tras cierre inesperado.
            pid = draft.get('patient_id') or draft.setdefault('target_id', str(uuid.uuid4()))
            self.store.write(path, draft)
            changes = {}
            for attachment in self.store.records('attachments'):
                if attachment.get('draft_id') == identifier:
                    attachment.update(patient_id=pid, draft_id=None, updated_at=now())
                    changes[f"data/attachments/{attachment['id']}.json"] = attachment
            revision = draft.get('source_revision')
            draft.update(status='Registrado', patient_id=pid, updated_at=now())
            changes[path] = draft
            return self.clinic.save('patients', {**payload, 'id': pid, 'registration_draft': identifier}, revision, related=changes)

    def catalog(self, query=''):
        self.auth.require()
        return [r for r in self.store.records('medication_catalog') if normalized(query) in normalized(r['name'])]

    def save_catalog(self, row, favorite=False):
        actor = self.auth.require()
        name = row.get('name', '').strip()
        if not name:
            raise DataError('Escribe el nombre del medicamento.')
        known = next((r for r in self.catalog() if normalized(r['name']) == normalized(name) and r.get('strength') == row.get('strength')), None)
        item = {k: row.get(k, '') for k in ('name', 'ingredient', 'presentation', 'strength')}
        item['id'] = known['id'] if known else str(uuid.uuid4())
        item['favorites'] = list(set((known or {}).get('favorites', [])+([actor['id']] if favorite else [])))
        self.store.write(f"data/medication_catalog/{item['id']}.json", item)

    def evolution(self, patient_id, key):
        self.auth.require()
        points = []
        for row in self.store.select_records('encounters', lambda r: r['patient_id'] == patient_id and r['status'] == 'Finalizada' and not r.get('archived')):
            for group in row.get('vitals', []):
                item = group.get('values', {}).get(key)
                if key == 'bmi' and group.get('bmi') is not None:
                    item = {'normalized_value': group['bmi'], 'normalized_unit': 'kg/m²'}
                if item:
                    points.append({'at': group['at'], 'value': item['normalized_value'], 'unit': item['normalized_unit'],
                                   'context': group.get('context', ''), 'encounter_id': row['id'], 'doctor_id': row['doctor_id']})
        return sorted(points, key=lambda p: p['at'])
