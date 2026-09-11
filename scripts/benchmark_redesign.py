"""Carga sintética reproducible; nunca abre la carpeta clínica del usuario."""
from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.storage import Store
from app.services import Auth, Clinic, normalized
from app.care import migrate

with tempfile.TemporaryDirectory(prefix='tresvizo-carga-sintetica-') as directory:
    store = Store(directory)
    migrate(store)
    auth = Auth(store)
    uid = auth.create_user('Doctor de carga sintética', 'carga', 'Prueba-carga-12345')
    auth.login(uid, 'Prueba-carga-12345')
    patients = [str(uuid.uuid4()) for _ in range(10000)]
    started = time.perf_counter()
    for kind, total in [('patients', 10000), ('encounters', 50000)]:
        folder = store.root/'data'/kind
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(total):
            identifier = patients[index] if kind == 'patients' else str(uuid.uuid4())
            row = {'schema_version': 2, 'id': identifier, 'revision': 1, 'archived': False,
                   'created_at': '2026-09-01T08:00:00', 'updated_at': '2026-09-01T08:00:00', 'created_by': uid}
            if kind == 'patients':
                row.update(name=f'Paciente sintético {index:05d}', file_number=f'RC-{index+1:06d}', birth_date='1980-01-01', sex='No especificado')
            else:
                row.update(patient_id=patients[index % len(patients)], doctor_id=uid, captured_by=uid, status='Finalizada',
                           attended_at=f'2026-09-{index%10+1:02d}T09:00:00', reason='Carga sintética', assessment='Diagnóstico sintético',
                           plan='Texto ficticio para prueba de carga. '*12, vitals=[], prescriptions=[], addenda=[])
            (folder/(identifier+'.json')).write_text(json.dumps(row, ensure_ascii=False), encoding='utf-8')
    results = {'patients': 10000, 'encounters': 50000, 'seed_seconds': round(time.perf_counter()-started,3)}
    store = Store(directory)
    auth = Auth(store)
    auth.login(uid, 'Prueba-carga-12345')
    clinic = Clinic(store, auth)
    started = time.perf_counter()
    stats = clinic.statistics('2026-09-01', '2026-09-30')
    results['statistics_cold_seconds'] = round(time.perf_counter()-started,3)
    assert stats['consultations'] == 50000 and stats['patients'] == 10000
    started = time.perf_counter()
    clinic.statistics('2026-09-01', '2026-09-30')
    results['statistics_cached_seconds'] = round(time.perf_counter()-started,3)
    started = time.perf_counter()
    matches = [p for p in clinic.list('patients') if '09999' in normalized(p['name'])]
    results['patient_search_cached_ms'] = round((time.perf_counter()-started)*1000,2)
    assert len(matches) == 1
    print(json.dumps(results), flush=True)
    from app.main_window import Application
    app = Application(directory)
    failures = []
    app.report_callback_exception = lambda exc,value,tb: failures.append(str(value))
    app.auth.login(uid, 'Prueba-carga-12345')
    app.shell()
    app.show('Pacientes')
    gaps, last, ticks = [], [time.perf_counter()], [0]
    def heartbeat():
        current = time.perf_counter()
        gaps.append(current-last[0])
        last[0] = current
        ticks[0] += 1
        app.after(25, heartbeat)
    app.after(25, heartbeat)
    started = time.perf_counter()
    while time.perf_counter()-started < 60:
        app.update()
        time.sleep(.005)
        if time.perf_counter()-started > 2 and not any(not f.done() for f in app.pending): break
    app.update()
    results['ui_heartbeat_max_gap_ms'] = round(max(gaps)*1000,2)
    results['ui_heartbeat_ticks'] = ticks[0]
    results['ui_errors'] = failures
    for future in list(app.pending): future.result(timeout=60)
    app.close()
    output = Path('artifacts/benchmark-redesign.json')
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results), flush=True)
    assert not failures
