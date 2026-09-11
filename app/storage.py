"""Almacenamiento JSON atómico y rutas conocidas de Windows."""
from __future__ import annotations
import ctypes
import json
import os
import threading
import uuid
import shutil
from copy import deepcopy
from pathlib import Path


class DataError(ValueError):
    pass


def documents_dir() -> Path:
    if os.name != 'nt':
        return Path.home() / 'Documents'
    class GUID(ctypes.Structure):
        _fields_ = [('data1', ctypes.c_ulong), ('data2', ctypes.c_ushort),
                    ('data3', ctypes.c_ushort), ('data4', ctypes.c_ubyte * 8)]
    folder = GUID.from_buffer_copy(uuid.UUID('FDD39AD0-238F-46AF-ADB4-6C85480369C7').bytes_le)
    result = ctypes.c_wchar_p()
    hr = ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder), 0, None, ctypes.byref(result))
    if hr:
        raise OSError('No se pudo localizar la carpeta Documentos de Windows.')
    try:
        return Path(result.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(result)


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DataError(f'Clave JSON repetida: {key}.')
        result[key] = value
    return result


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=reject_duplicates,
                          parse_constant=lambda value: (_ for _ in ()).throw(DataError('Número JSON inválido.')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise DataError(f'Archivo inválido: {path.name}. Se conserva para recuperación.') from exc


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        with temp.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


class Store:
    def __init__(self, root=None):
        self.root = Path(root) if root else documents_dir() / 'RegistroClinico'
        self.lock = threading.RLock()
        self.root.mkdir(parents=True, exist_ok=True)

    def read(self, name, default=None):
        with self.lock:
            path = self.root / name
            return read_json(path) if path.exists() else deepcopy(default)

    def write(self, name, data):
        with self.lock:
            atomic_json(self.root / name, data)

    def records(self, kind):
        with self.lock:
            return [read_json(p) for p in (self.root / 'data' / kind).glob('*.json')]

    def path(self, name):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root.resolve()) or path == self.root.resolve():
            raise DataError('Ruta fuera de la carpeta administrada.')
        return path

    def transaction(self, changes, files=None):
        """Publicar un conjunto completo; las operaciones sin commit se revierten."""
        with self.lock:
            folder = self.root / 'operations' / str(uuid.uuid4())
            folder.mkdir(parents=True)
            entries = []
            try:
                for index, name in enumerate([*changes, *(files or {})]):
                    destination = self.path(name)
                    old, staged = folder / f'{index}.old', folder / f'{index}.new'
                    if destination.exists():
                        shutil.copy2(destination, old)
                    if name in changes:
                        atomic_json(staged, changes[name])
                    else:
                        with open(files[name], 'rb') as source, staged.open('wb') as target:
                            shutil.copyfileobj(source, target, 1024*1024)
                            target.flush()
                            os.fsync(target.fileno())
                    entries.append({'name': name, 'index': index, 'existed': old.exists()})
                atomic_json(folder / 'journal.json', {'entries': entries, 'committed': False})
                for item in entries:
                    target = self.path(item['name'])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(folder / f"{item['index']}.new", target)
                atomic_json(folder / 'journal.json', {'entries': entries, 'committed': True})
            except BaseException:
                if (folder / 'journal.json').exists():
                    self._recover_operation(folder)
                else:
                    shutil.rmtree(folder)
                raise
            shutil.rmtree(folder, ignore_errors=True)

    def _recover_operation(self, folder):
        journal = read_json(folder / 'journal.json')
        if not journal['committed']:
            for item in journal['entries']:
                target = self.path(item['name'])
                old = folder / f"{int(item['index'])}.old"
                if item['existed']:
                    # Conservar el respaldo del journal hasta completar toda la recuperación.
                    target.parent.mkdir(parents=True, exist_ok=True)
                    temp = target.with_name(target.name+'.recover')
                    shutil.copy2(old, temp)
                    os.replace(temp, target)
                elif target.exists():
                    target.unlink()
        shutil.rmtree(folder)

    def recover(self):
        with self.lock:
            for folder in (self.root / 'operations').glob('*'):
                if (folder / 'journal.json').is_file():
                    self._recover_operation(folder)



class InstanceLock:
    def __init__(self, root):
        self.file = (root / '.instance.lock').open('a+b')
        self.file.write(b'0')
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise DataError('La aplicación ya está abierta para esta carpeta de datos.') from exc

    def close(self):
        self.file.close()
