"""Comparación reproducible de búsqueda y recorridos sobre clínicas sintéticas."""
from pathlib import Path
import json
import platform
import sys
import tempfile
import time
import uuid
import argparse
import faulthandler
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.storage import Store
from app.services import Auth, Clinic, normalized
from app.care import migrate
from app.main_window import Application
from PIL import Image


def timed(operation):
    start = time.perf_counter()
    result = operation()
    return round((time.perf_counter()-start)*1000, 3), result


def settle(app):
    deadline = time.monotonic()+60
    while app.pending and time.monotonic() < deadline:
        app.update()
        time.sleep(.005)
    app.update()
    if app.pending:
        app.executor.shutdown(wait=True, cancel_futures=True)
        app.close()
        raise RuntimeError('Operación sintética excedió 60 segundos')


parser = argparse.ArgumentParser()
parser.add_argument('--count', type=int, choices=[1000, 10000], required=True)
args = parser.parse_args()
faulthandler.dump_traceback_later(90, repeat=True)
results = {'environment': {'python': platform.python_version(), 'windows': platform.platform(), 'machine': platform.machine()}, 'volumes': []}
for count in (args.count,):
    with tempfile.TemporaryDirectory(prefix='tresvizo-hardening-benchmark-') as folder:
        store = Store(folder)
        migrate(store)
        auth = Auth(store)
        actor = auth.create_user('Doctor sintético', 'benchmark', 'Sintetica-12345')
        auth.login(actor, 'Sintetica-12345')
        base = {'schema_version': 2, 'revision': 1, 'created_at': '2026-09-01T10:00:00-06:00', 'updated_at': '2026-09-01T10:00:00-06:00', 'created_by': actor, 'updated_by': actor}
        (store.root/'data/patients').mkdir(parents=True, exist_ok=True)
        (store.root/'data/encounters').mkdir(parents=True, exist_ok=True)
        patients, visits = [], 0
        for index in range(count):
            patient = {**base, 'id': str(uuid.uuid4()), 'name': f'Paciente sintético {index:05d}', 'file_number': f'RC-{index+1:06d}', 'birth_date': '1980-01-01',
                       'histories': {'Personales': {'status': 'No interrogado', 'notes': 'Texto de prueba. '*40}}}
            patients.append(patient)
            (store.root/f"data/patients/{patient['id']}.json").write_text(json.dumps(patient), encoding='utf-8')
            for visit_number in range(index % 4):
                encounter = {**base, 'id': str(uuid.uuid4()), 'patient_id': patient['id'], 'doctor_id': actor, 'captured_by': actor, 'status': 'Finalizada',
                    'attended_at': f'2026-09-0{visit_number+1}T10:00:00-06:00', 'reason': 'Control sintético', 'assessment': 'Prueba', 'plan': 'Texto sintético. '*30, 'vitals': [], 'prescriptions': [], 'addenda': []}
                (store.root/f"data/encounters/{encounter['id']}.json").write_text(json.dumps(encounter), encoding='utf-8')
                visits += 1
        # La siembra escribe archivos de prueba directamente: abrir un Store nuevo
        # evita medir la caché vacía que había leído la migración inicial.
        store = Store(folder)
        auth = Auth(store)
        auth.login(actor, 'Sintetica-12345')
        clinic = Clinic(store, auth)
        volume = {'patients': count, 'encounters': visits}
        query = f'{count-1:05d}'
        def baseline():
            return [row for row in clinic.list('patients', True) if query in normalized(' '.join(str(row.get(k, '')) for k in ('name', 'preferred_name', 'file_number', 'phone')))]
        volume['previous_search_cold_ms'], matches = timed(baseline)
        volume['previous_search_warm_ms'], _ = timed(baseline)
        volume['index_build_ms'], found = timed(lambda: clinic.search_patients(query))
        volume['indexed_search_warm_ms'], _ = timed(lambda: clinic.search_patients(query))
        assert matches and {r['id'] for r in matches} == {r['id'] for r in found[0]}
        print(json.dumps({'search': volume}), flush=True)
        app = Application(folder)
        errors = []
        app.report_callback_exception = lambda exc, value, tb: errors.append(exc.__name__)
        app.guard = lambda operation: operation()
        app.auth.login(actor, 'Sintetica-12345')
        app.shell()
        settle(app)
        gaps, last = [], [time.perf_counter()]
        def heartbeat():
            stamp = time.perf_counter()
            gaps.append(stamp-last[0])
            last[0] = stamp
            app.after(25, heartbeat)
        app.after(25, heartbeat)
        def open_patient():
            result = app.patient_record(patients[0]['id'])
            settle(app)
            return result
        volume['open_patient_ms'], _ = timed(open_patient)
        editor = app.encounter_editor(patients[0])
        editor.texts['reason'].insert('1.0', 'Motivo sintético')
        editor.texts['plan'].insert('1.0', 'Plan sintético')
        editor.diagnosis_var.set('Diagnóstico de prueba')
        editor.add_diagnosis()
        volume['save_draft_ms'], _ = timed(editor.save)
        app.show('Inicio')
        settle(app)
        volume['resume_draft_ms'], _ = timed(lambda: app.show('consulta:'+editor.record['id']))
        source = Path(folder)/'documento-sintetico.png'
        Image.new('RGB', (300, 200), 'white').save(source)
        volume['incorporate_document_ms'], _ = timed(lambda: app.attachments.add(source, patients[0]['id'], editor.record['id']))
        volume['finalize_ms'], _ = timed(lambda: editor.save(True))
        volume['change_view_ms'], _ = timed(lambda: app.show('Pacientes'))
        settle(app)
        volume['heartbeat_max_gap_ms'] = round(max(gaps, default=0)*1000, 3)
        volume['ui_errors'] = errors
        app.close()
        assert not errors
        results['volumes'].append(volume)
        print(json.dumps(volume), flush=True)
output = Path(__file__).resolve().parents[1]/f'artifacts/benchmark-hardening-{args.count}.json'
output.write_text(json.dumps(results, indent=2), encoding='utf-8')
faulthandler.cancel_dump_traceback_later()
