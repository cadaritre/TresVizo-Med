"""Exportación e importación de pacientes y copias locales verificables."""
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import zipfile
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
                        if path.is_file() and path.suffix != '.tmp':
                            content = path.read_bytes()
                            name = path.relative_to(self.store.root).as_posix()
                            manifest['files'][name] = hashlib.sha256(content).hexdigest()
                            archive.writestr(name, content)
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
            if set(archive.namelist()) != set(manifest['files']) | {'manifest.json'}:
                raise DataError('El respaldo contiene archivos no declarados.')
            for name, expected in manifest['files'].items():
                parts = Path(name).parts
                if name.startswith(('/', '\\')) or '..' in parts or ':' in name or parts[0] not in ('config', 'data', 'attachments', 'avatars'):
                    raise DataError('Ruta no válida en el respaldo.')
                if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                    raise DataError('No coincide la integridad del respaldo.')
            return manifest

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
