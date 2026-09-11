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
from app.storage import DataError, read_json, atomic_json


def safe_csv(value):
    text = str(value if value is not None else '')
    return "'"+text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text


class Transfer:
    def __init__(self, store, auth, clinic):
        self.store, self.auth, self.clinic = store, auth, clinic

    def export_patients(self, destination, identifiers=None):
        self.auth.require()
        rows = self.clinic.list('patients')
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
                    if target.suffix == '.json':
                        read_json(target)
            schema = staging/'config'/'schema.json'
            if schema.exists() and read_json(schema).get('version',1) > 2:
                raise DataError('El respaldo requiere una versión posterior.')
            # Logos históricos usaban rutas absolutas; remapear únicamente copias incluidas.
            identity_path = staging/'config'/'identity.json'
            if identity_path.exists():
                identity = read_json(identity_path)
                logo = identity.get('clinic_logo','')
                if logo and (staging/'config'/Path(logo).name).is_file():
                    identity['clinic_logo'] = str(destination/'config'/Path(logo).name)
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
