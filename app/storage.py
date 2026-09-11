"""Almacenamiento JSON atómico y rutas conocidas de Windows."""
from __future__ import annotations
import ctypes
import json
import os
import threading
import uuid
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
