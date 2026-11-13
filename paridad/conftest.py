"""Ejecutor de paridad: compara la lógica de la rama `web` con el escritorio de `main`.

`main` se extrae con `git archive main` a un directorio temporal: no se hace checkout, no se tocan ramas ni se
usan worktrees. Los módulos del escritorio quedan importables como `app.*` solo durante la sesión de pruebas.
La rama a comparar se puede cambiar con `TV_PARIDAD_REF` (por omisión, `main`).
"""
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
REF = os.environ.get('TV_PARIDAD_REF', 'main')


@pytest.fixture(scope='session')
def escritorio():
    """Ruta del árbol de `main` extraído."""
    with tempfile.TemporaryDirectory(prefix='paridad-main-') as carpeta:
        salida = subprocess.run(['git', 'archive', '--format=tar', REF], cwd=RAIZ, capture_output=True, check=True).stdout
        destino = Path(carpeta)/'main'
        destino.mkdir()
        import io
        with tarfile.open(fileobj=io.BytesIO(salida)) as tar:
            tar.extractall(destino, filter='data')
        assert (destino/'app'/'storage.py').is_file(), 'La referencia no contiene el escritorio (app/)'
        sys.path.insert(0, str(destino))
        try:
            yield destino
        finally:
            sys.path.remove(str(destino))
            for name in [n for n in sys.modules if n == 'app' or n.startswith('app.')]:
                del sys.modules[name]


@pytest.fixture(scope='session')
def viejo(escritorio):
    """Módulos del escritorio, por nombre corto."""
    import importlib
    nombres = ('storage', 'services', 'themes', 'clinical_models', 'consultation_state', 'editing_state', 'transfer',
               'care', 'documents', 'attachments', 'branding', 'setup_service')
    class Modulos:
        pass
    modulos = Modulos()
    for nombre in nombres:
        setattr(modulos, nombre, importlib.import_module('app.'+nombre))
    return modulos


class Clinica:
    """Clínica sintética del escritorio (Store + Auth + Clinic) con datos de ejemplo."""
    def __init__(self, viejo, carpeta):
        self.v = viejo
        self.store = viejo.storage.Store(carpeta)
        self.auth = viejo.services.Auth(self.store)
        self.uid = self.auth.create_user('Dra. Sintética', 'dra', 'Sintetica-12345')
        self.auth.login(self.uid, 'Sintetica-12345')
        self.clinic = viejo.services.Clinic(self.store, self.auth)
        self.transfer = viejo.transfer.Transfer(self.store, self.auth, self.clinic)
        self.care = viejo.care.Care(self.store, self.auth, self.clinic)

    def poblar(self):
        c = self.clinic
        ana = c.save('patients', {'name': 'Ana Muñoz', 'birth_date': '1990-05-01', 'sex': 'Mujer', 'phone': '5551234'})
        luis = c.save('patients', {'name': '=Luis Pérez', 'birth_date': '2020-01-01', 'sex': 'Hombre'})
        med = {'name': 'Producto sintético', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral',
               'frequency': '12', 'frequency_kind': 'Cada N horas'}

        def vital(momento, sistolica):
            return {'at': momento, 'values': {'systolic': {'value': sistolica, 'unit': 'mmHg'},
                                             'weight': {'value': '70', 'unit': 'kg'}, 'height': {'value': '175', 'unit': 'cm'}}}
        base = dict(status='Finalizada', reason='Motivo, con coma\ny salto', plan='@Indicaciones', type='General')
        c.save('encounters', {**base, 'patient_id': ana['id'], 'attended_at': '2026-08-20T09:00:00', 'assessment': 'Gastritis',
                              'vitals': [vital('2026-08-20T09:00:00', '118')], 'prescriptions': [med]})
        c.save('encounters', {**base, 'patient_id': ana['id'], 'attended_at': '2026-09-10T10:00:00',
                              'assessment': 'Gastritis; Reflujo', 'vitals': [vital('2026-09-10T10:00:00', '126')]})
        c.save('encounters', {**base, 'patient_id': luis['id'], 'attended_at': '2026-09-12T11:00:00', 'assessment': 'Dolor abdominal',
                              'type': 'Control', 'prescriptions': [med]})
        c.save('encounters', {**base, 'status': 'Borrador', 'patient_id': luis['id'], 'attended_at': '2026-09-14T11:00:00',
                              'assessment': 'Borrador'})
        return ana, luis


@pytest.fixture
def clinica(viejo, tmp_path):
    c = Clinica(viejo, tmp_path/'clinica')
    c.poblar()
    return c
