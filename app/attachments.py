"""Archivos administrados, asociaciones verificadas y versiones conservadas."""
from pathlib import Path
from copy import deepcopy
import hashlib
import uuid
import zipfile
from PIL import Image
from app.storage import DataError
from app.services import now

CATEGORIES = ['Fotografía clínica', 'Laboratorio', 'Estudio', 'Referencia', 'Consentimiento', 'Otro documento']

class Attachments:
    def __init__(self, store, auth, clinic):
        self.store, self.auth, self.clinic = store, auth, clinic

    def authorize(self, patient_id=None, encounter_id=None, draft_id=None):
        actor = self.auth.require()
        if draft_id:
            draft = self.store.read(f'data/registration_drafts/{uuid.UUID(draft_id)}.json')
            if not draft or draft['doctor_id'] != actor['id'] or draft['status'] != 'Borrador':
                raise DataError('Este borrador es privado o ya fue cerrado.')
        else:
            if not self.store.read(f'data/patients/{uuid.UUID(patient_id)}.json'):
                raise DataError('No existe el paciente.')
            if encounter_id:
                row = self.store.read(f'data/encounters/{uuid.UUID(encounter_id)}.json')
                if not row or row['patient_id'] != patient_id:
                    raise DataError('La consulta no pertenece a este paciente.')
                if row['status'] == 'Borrador' and row['doctor_id'] != actor['id']:
                    raise DataError('No puedes consultar adjuntos de un borrador ajeno.')
        return actor

    def list(self, patient_id=None, encounter_id=None, draft_id=None, archived=False):
        self.authorize(patient_id, encounter_id, draft_id)
        result = []
        for row in self.store.records('attachments'):
            match = row.get('draft_id') == draft_id if draft_id else row.get('patient_id') == patient_id and not row.get('draft_id')
            if not match or encounter_id and row.get('encounter_id') != encounter_id or not archived and row.get('archived'):
                continue
            try:
                self.authorize(row.get('patient_id'), row.get('encounter_id'), row.get('draft_id'))
            except DataError:
                continue
            result.append(row)
        return sorted(result, key=lambda r: r['created_at'], reverse=True)

    def get(self, identifier):
        row = self.store.read(f'data/attachments/{uuid.UUID(identifier)}.json')
        if not row:
            raise DataError('No existe el documento.')
        self.authorize(row.get('patient_id'), row.get('encounter_id'), row.get('draft_id'))
        return row

    def path(self, identifier):
        row = self.get(identifier)
        path = self.store.path(row['path'])
        if not path.is_file():
            raise DataError('El archivo está ausente. El registro se conserva para recuperación.')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != row['sha256']:
            raise DataError('La integridad del documento no coincide. Restaura una copia verificada.')
        return path

    @staticmethod
    def validate(path):
        path = Path(path)
        size = path.stat().st_size
        if size <= 0 or size > 50*1024*1024:
            raise DataError('El archivo debe tener contenido y no superar 50 MiB.')
        suffix = path.suffix.lower()
        if suffix in ('.jpg', '.jpeg', '.png'):
            with Image.open(path) as image:
                if image.format not in ('PNG', 'JPEG') or image.width*image.height > 40_000_000:
                    raise DataError('Imagen incompatible o mayor de 40 megapíxeles.')
                image.verify()
            return 'image/png' if suffix == '.png' else 'image/jpeg'
        if suffix == '.pdf':
            from pypdf import PdfReader
            reader = PdfReader(path)
            if reader.is_encrypted:
                raise DataError('El PDF está protegido. Incorpora una copia accesible.')
            if not len(reader.pages):
                raise DataError('El PDF no tiene páginas.')
            return 'application/pdf'
        if suffix == '.docx':
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                if '[Content_Types].xml' not in names or 'word/document.xml' not in names or any('vbaProject' in n for n in names):
                    raise DataError('El archivo no es un DOCX admitido.')
                if sum(i.file_size for i in archive.infolist()) > 200*1024*1024:
                    raise DataError('El contenido descomprimido del DOCX supera el límite.')
            return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        raise DataError('Formatos admitidos: JPEG, PNG, PDF y DOCX.')

    def add(self, source, patient_id=None, encounter_id=None, draft_id=None, category='Otro documento', notes='', reason='', allow_duplicate=False, replaces=None, progress=lambda n: None):
        actor = self.authorize(patient_id, encounter_id, draft_id)
        source = Path(source)
        mime = self.validate(source)
        identifier = str(uuid.uuid4())
        relative = f'attachments/originals/{identifier}{source.suffix.lower()}'
        staged = self.store.root/'attachments'/'staging'/(identifier+source.suffix.lower())
        staged.parent.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256()
        total = source.stat().st_size
        try:
            import os
            with source.open('rb') as src, staged.open('xb') as out:
                copied = 0
                while chunk := src.read(1024*1024):
                    out.write(chunk)
                    sha.update(chunk)
                    copied += len(chunk)
                    progress(copied/total)
                out.flush()
                os.fsync(out.fileno())
            self.validate(staged)
            # La huella y el contenido se verifican sobre la copia que se publicará.
            with staged.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != sha.hexdigest():
                    raise DataError('No se pudo verificar la copia del archivo.')
            with self.store.lock:
                self.authorize(patient_id, encounter_id, draft_id)
                if not allow_duplicate and any(r['sha256'] == sha.hexdigest() for r in self.list(patient_id, None, draft_id, archived=True)):
                    raise DataError('Ya existe un archivo idéntico en este expediente. Revisa la coincidencia o permite incorporarlo otra vez.')
                row = {'schema_version': 2, 'id': identifier, 'patient_id': patient_id, 'encounter_id': encounter_id,
                       'draft_id': draft_id, 'title': source.stem, 'original_name': source.name, 'path': relative,
                       'mime': mime, 'size': total, 'sha256': sha.hexdigest(), 'category': category, 'notes': notes,
                       'document_date': '', 'doctor_id': actor['id'], 'created_at': now(), 'updated_at': now(),
                       'revision': 1, 'archived': False, 'replaces': replaces, 'provenance': 'Archivo local'}
                changes = {f'data/attachments/{identifier}.json': row}
                if encounter_id:
                    encounter = self.store.read(f'data/encounters/{encounter_id}.json')
                    if encounter['status'] != 'Borrador':
                        if not reason.strip():
                            raise DataError('Indica el motivo para añadir un documento a una consulta finalizada.')
                        encounter.setdefault('addenda', []).append({'id': str(uuid.uuid4()), 'actor': actor['id'], 'at': now(), 'reason': reason,
                                                                  'content': 'Documento incorporado: '+source.name, 'attachment_id': identifier})
                        encounter['revision'] += 1
                        changes[f'data/encounters/{encounter_id}.json'] = encounter
                aid = str(uuid.uuid4())
                changes[f'data/audit/{aid}.json'] = {'id': aid, 'actor': actor['id'], 'at': now(), 'action': 'incorporar_adjunto', 'target': identifier}
                self.store.transaction(changes, {relative: staged})
                return row
        finally:
            staged.unlink(missing_ok=True)

    def update(self, identifier, values, revision, reason=''):
        actor = self.auth.require()
        with self.store.lock:
            row = self.get(identifier)
            if row['doctor_id'] != actor['id']:
                self.auth.require('admin')
            if row['revision'] != revision:
                raise DataError('El documento cambió. Actualiza la lista.')
            changes = {}
            eid = row.get('encounter_id')
            if eid:
                encounter = self.store.read(f'data/encounters/{eid}.json')
                if encounter['status'] != 'Borrador':
                    if not reason.strip():
                        raise DataError('Indica el motivo del cambio documental.')
                    encounter['addenda'].append({'id': str(uuid.uuid4()), 'actor': actor['id'], 'at': now(), 'reason': reason, 'content': 'Metadatos/estado del documento actualizados: '+row['title'], 'attachment_id': identifier})
                    encounter['revision'] += 1
                    changes[f'data/encounters/{eid}.json'] = encounter
            row.setdefault('history', []).append({'at': now(), 'actor': actor['id'], 'reason': reason, 'previous': {k: row.get(k) for k in values}})
            allowed = ('title', 'category', 'notes', 'document_date', 'archived')
            row.update({k: v for k, v in values.items() if k in allowed})
            row.update(revision=revision+1, updated_at=now())
            changes[f'data/attachments/{identifier}.json'] = row
            self.store.transaction(changes)
            self.auth.audit('actualizar_adjunto', identifier)
            return row
