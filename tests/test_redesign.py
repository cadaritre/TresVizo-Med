from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import patch
import json
import uuid
import pytest
from PIL import Image
from app.storage import Store, DataError, atomic_json
from app.services import Auth, Clinic
from app.care import Care, migrate
from app.attachments import Attachments
from app.clinical_models import validate_vitals, validate_medications, encounter_sections
from app.main_window import Application

@pytest.fixture
def services(tmp_path):
    store = Store(tmp_path/'clinic')
    auth = Auth(store)
    uid = auth.create_user('Doctora Prueba', 'prueba', 'Sintetica-12345')
    auth.login(uid,'Sintetica-12345')
    clinic = Clinic(store,auth)
    return store,auth,clinic,Care(store,auth,clinic),Attachments(store,auth,clinic)

def test_registration_draft_and_files_publish_together(services,tmp_path):
    store,auth,clinic,care,attachments = services
    draft = care.save_draft({'name':'Paciente sintético'})
    source = tmp_path/'photo.png'
    Image.new('RGB',(80,90),'white').save(source)
    item = attachments.add(source,draft_id=draft['id'])
    assert not clinic.list('patients')
    original = store.transaction
    def failure(changes,files=None):
        if any(k.startswith('data/patients/') for k in changes):
            raise OSError('Fallo simulado de publicación')
        return original(changes,files)
    with patch.object(store,'transaction',failure):
        with pytest.raises(OSError):
            care.register(draft['id'],{'name':'Paciente sintético'})
    assert not clinic.list('patients')
    assert care.drafts()[0]['status'] == 'Borrador'
    patient = care.register(draft['id'],{'name':'Paciente sintético','sex':'No especificado','photo_attachment_id':item['id']})
    assert care.register(draft['id'],{'name':'No duplicar'})['id'] == patient['id']
    assert len(clinic.list('patients')) == 1
    source.unlink()
    assert attachments.path(item['id']).is_file()
    assert attachments.list(patient['id'])[0]['draft_id'] is None
    assert patient['photo_attachment_id'] == item['id']

def test_private_drafts_and_archiving_statistics(services):
    store,auth,clinic,care,attachments = services
    uid = auth.current['id']
    other = auth.create_user('Otro doctor','otro','Sintetica-12345')
    draft = care.save_draft({'name':'Privado'})
    patient = clinic.save('patients',{'name':'Paciente A'})
    encounter = clinic.save('encounters',{'patient_id':patient['id'],'status':'Borrador','attended_at':'2026-09-10T09:00:00',
                                        'reason':'Control','assessment':'Diagnóstico de prueba','plan':'Indicaciones de prueba'})
    clinic.archive('encounters',encounter['id'],'Prueba de papelera')
    assert not clinic.list('encounters')
    assert clinic.list('encounters',True)[0]['id'] == encounter['id']
    auth.login(other,'Sintetica-12345')
    assert not care.drafts()
    assert not clinic.list('encounters',True)
    with pytest.raises(DataError): care.discard(draft['id'])
    with pytest.raises(DataError): clinic.archive('patients',patient['id'],'No autorizado')
    auth.login(uid,'Sintetica-12345')
    restored = clinic.archive('encounters',encounter['id'],'Restaurar',restore=True)
    final = clinic.save('encounters',{**restored,'status':'Finalizada'},restored['revision'])
    clinic.archive('patients',patient['id'],'Retirar de la lista')
    assert not clinic.list('patients')
    assert clinic.statistics('2026-09-01','2026-09-30')['consultations'] == 1
    clinic.archive('encounters',final['id'],'Consulta duplicada')
    assert clinic.statistics('2026-09-01','2026-09-30')['consultations'] == 0

def test_measurement_units_and_medication_structure():
    result = validate_vitals([{'at':'2026-09-10T10:00:00','values':{'weight':{'value':'154.3235835','unit':'lb'},'height':{'value':'1,75','unit':'m'},'temperature':{'value':'98.6','unit':'°F'}}}])[0]
    assert result['bmi'] == 22.86
    assert result['values']['temperature']['normalized_value'] == pytest.approx(37)
    assert 'oxygen' not in result['values']
    with pytest.raises(DataError):
        validate_vitals([{'at':'2026-09-10T10:00:00','values':{'oxygen':{'value':'101','unit':'%'}}}])
    medication = {'name':'Producto sintético','strength':'concentración de prueba','dose':'2','dose_unit':'tableta','route':'Oral','frequency_kind':'Cada N horas','frequency':'12'}
    assert validate_medications([medication],True)[0]['dose'] == '2'
    with pytest.raises(DataError): validate_medications([{**medication,'needs_review':True}],True)

def test_migration_idempotent_preserves_clinical_text(services):
    store,auth,clinic,care,attachments = services
    patient = clinic.save('patients',{'name':'Paciente previo','allergies':'Texto clínico sin interpretar','medications':'Texto original'})
    migrate(store)
    first = store.read(f"data/patients/{patient['id']}.json")
    migrate(store)
    assert store.read(f"data/patients/{patient['id']}.json") == first
    assert first['legacy']['allergies'] == 'Texto clínico sin interpretar'
    assert len(list((store.root/'backups').glob('*.zip'))) == 1

def test_attachment_cross_patient_and_later_addendum(services,tmp_path):
    store,auth,clinic,care,attachments = services
    p = clinic.save('patients',{'name':'Uno'})
    other = clinic.save('patients',{'name':'Dos'})
    visit = clinic.save('encounters',{'patient_id':p['id'],'status':'Finalizada','attended_at':'2026-09-10T10:00:00','reason':'Motivo','assessment':'Diagnóstico','plan':'Plan'})
    source = tmp_path/'photo.png'
    Image.new('RGB',(20,20),'white').save(source)
    with pytest.raises(DataError): attachments.add(source,other['id'],visit['id'])
    with pytest.raises(DataError): attachments.add(source,p['id'],visit['id'])
    item = attachments.add(source,p['id'],visit['id'],reason='Resultado recibido posteriormente')
    saved = store.read(f"data/encounters/{visit['id']}.json")
    assert saved['reason'] == visit['reason']
    assert saved['addenda'][0]['attachment_id'] == item['id']
    with pytest.raises(DataError): attachments.add(source,p['id'])
    attachments.update(item['id'],{'archived':True},1,'Conservar versión anterior')
    assert attachments.path(item['id']).is_file()

def test_transaction_rollback_after_second_replace(services):
    store,*_ = services
    store.write('config/a.json',{'value':1})
    store.write('config/b.json',{'value':2})
    import app.storage as storage
    real = storage.os.replace
    failed = [False]
    def replace(source,target):
        if str(source).endswith('1.new') and not failed[0]:
            failed[0] = True
            raise OSError('Interrupción simulada')
        return real(source,target)
    with patch.object(storage.os,'replace',replace):
        with pytest.raises(OSError): store.transaction({'config/a.json':{'value':3},'config/b.json':{'value':4}})
    assert store.read('config/a.json') == {'value':1}
    assert store.read('config/b.json') == {'value':2}

def test_cold_cache_keeps_concurrent_update_and_does_not_lock_ui(services):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import app.storage as storage
    store, auth, clinic, *_ = services
    patient = clinic.save('patients', {'name': 'Nombre anterior'})
    fresh = Store(store.root)
    started, resume = threading.Event(), threading.Event()
    original = storage.read_json
    def paused(path):
        row = original(path)
        if path.parent.name == 'patients':
            started.set()
            assert resume.wait(3)
        return row
    with patch.object(storage, 'read_json', paused), ThreadPoolExecutor(max_workers=1) as worker:
        future = worker.submit(fresh.records, 'patients')
        assert started.wait(3)
        assert fresh.read(f"data/users/{auth.current['id']}.json")['active']
        fresh.write(f"data/patients/{patient['id']}.json", {**patient, 'name': 'Nombre actualizado'})
        resume.set()
        assert future.result(timeout=3)[0]['name'] == 'Nombre actualizado'
    assert fresh.records('patients')[0]['name'] == 'Nombre actualizado'

@pytest.mark.desktop
def test_workspace_patient_consultation_roundtrip(tmp_path):
    app = Application(tmp_path)
    app.guard = lambda action: action()
    errors = []
    app.report_callback_exception = lambda exc,value,tb:errors.append(value)
    try:
        uid = app.auth.create_user('Doctora UI','ui','Sintetica-12345')
        app.auth.login(uid,'Sintetica-12345')
        app.shell()
        editor = app.patient_editor()
        editor.personal.vars['name'].set('Paciente sintético de interfaz')
        editor.personal.vars['birth_date'].set('15/06/1980')
        editor.unknown.set(False)
        editor.phones.rows = [{'number':'+502 5555 0100 ext 2','type':'Principal'}]
        editor.save()
        draft_id = editor.draft_id
        app.show('Inicio')
        app.show('alta:'+draft_id)
        assert editor.personal.vars['name'].get() == 'Paciente sintético de interfaz'
        editor.register()
        patient = app.clinic.list('patients')[0]
        assert patient['birth_date'] == '1980-06-15'
        assert app.current_page == 'paciente:'+patient['id']
        visit = app.encounter_editor(patient)
        for key,value in [('reason','Control sintético'),('plan','Indicaciones sintéticas')]:
            visit.texts[key].insert('1.0',value)
        visit.diagnosis_var.set('Diagnóstico de prueba')
        visit.add_diagnosis()
        visit.model.apply('medication', str(uuid.uuid4()), {'name':'Producto de prueba','dose':'1','dose_unit':'tableta','route':'Oral','frequency_kind':'Cada N horas','frequency':'12'})
        capture = visit.open_tool('vitals')
        capture.values['weight'].set('70')
        capture.values['height'].set('175')
        assert capture.apply()
        visit.save()
        saved = app.store.read(f"data/encounters/{visit.record['id']}.json")
        assert saved['vitals'][0]['bmi'] == 22.86
        assert saved['prescriptions'][0]['frequency'] == '12'
        visit.save(True)
        assert len(app.care.evolution(patient['id'],'weight')) == 1
        app.open_encounter(visit.record['id'])
        app.show('Mi perfil')
        app.update()
        assert not errors
        for task in list(app.pending): task.result(timeout=10)
    finally:
        settle(app)
        app.close()

def settle(app, seconds=3):
    import time
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        app.update()
        if not app.pending:
            app.update()
            return
        time.sleep(.01)
    raise AssertionError('Las tareas de prueba no terminaron.')

@pytest.mark.desktop
def test_incomplete_forms_and_file_queue_survive_restart(tmp_path):
    app = Application(tmp_path)
    app.guard = lambda action: action()
    try:
        uid = app.auth.create_user('Doctora borradores', 'borradores', 'Sintetica-12345')
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        editor = app.patient_editor()
        editor.personal.vars['name'].set('Registro todavía incompleto')
        editor.personal.vars['birth_date'].set('31/0')
        editor.allergies.new()
        editor.allergies.form.vars['substance'].set('Texto pendiente de confirmar')
        editor.attachments.add_paths([str(tmp_path/'pendiente.png')])
        editor.save()
        draft_id = editor.draft_id
        patient = app.clinic.save('patients', {'name': 'Paciente de prueba'})
        visit = app.encounter_editor(patient)
        header = visit.open_tool('header')
        header.form.vars['date'].set('30/')
        header.defer()
        medicine = visit.open_tool('medication')
        medicine.form.vars['name'].set('Medicamento sin terminar')
        medicine.defer()
        vital = visit.open_tool('vitals')
        vital.values['weight'].set('7,')
        vital.defer()
        visit.save()
        encounter_id = visit.record['id']
        settle(app)
    finally:
        settle(app)
        app.close()
    reopened = Application(tmp_path)
    reopened.guard = lambda action: action()
    try:
        reopened.auth.login(uid, 'Sintetica-12345')
        reopened.shell()
        draft = next(d for d in reopened.care.drafts() if d['id'] == draft_id)
        editor = reopened.patient_editor(draft=draft)
        assert editor.personal.vars['birth_date'].get() == '31/0'
        assert editor.allergies.form.vars['substance'].get() == 'Texto pendiente de confirmar'
        assert editor.allergies.pending
        assert editor.attachments.queue[0]['path'].endswith('pendiente.png')
        visit = reopened.open_encounter(encounter_id)
        header = visit.open_tool('header')
        assert header.form.vars['date'].get() == '30/'
        header.defer()
        medicine = visit.open_tool('medication')
        assert medicine.form.vars['name'].get() == 'Medicamento sin terminar'
        medicine.defer()
        vital = visit.open_tool('vitals')
        assert vital.values['weight'].get() == '7,'
        vital.defer()
        with pytest.raises(DataError): visit.save(True)
        settle(reopened)
    finally:
        settle(reopened)
        reopened.close()

def test_restore_verified_separate_folder_and_invalid_backup(services, tmp_path):
    from app.transfer import Transfer
    import zipfile
    store, auth, clinic, care, attachments = services
    patient = clinic.save('patients', {'name': 'Paciente para restauración'})
    source = tmp_path/'original.png'
    Image.new('RGB', (35, 20), 'white').save(source)
    item = attachments.add(source, patient['id'])
    transfer = Transfer(store, auth, clinic)
    backup = tmp_path/'respaldo.zip'
    transfer.backup(backup)
    destination = transfer.restore(backup, tmp_path/'copia restaurada')
    restored = Store(destination)
    assert restored.read(f"data/patients/{patient['id']}.json") == patient
    assert (destination/item['path']).read_bytes() == source.read_bytes()
    with pytest.raises(DataError): transfer.restore(backup, store.root)
    broken = tmp_path/'corrupto.zip'
    with zipfile.ZipFile(backup) as original, zipfile.ZipFile(broken, 'w') as output:
        for name in original.namelist():
            output.writestr(name, b'{}' if name == item['path'] else original.read(name))
    with pytest.raises(DataError): transfer.restore(broken, tmp_path/'no publicar')
    assert not (tmp_path/'no publicar').exists()
    assert store.read(f"data/patients/{patient['id']}.json") == patient

@pytest.mark.desktop
def test_unit_changes_after_restore_and_provisional_graph(tmp_path):
    from tkinter import ttk
    app = Application(tmp_path)
    app.guard = lambda action: action()
    try:
        uid = app.auth.create_user('Doctor unidades', 'unidades', 'Sintetica-12345')
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        patient = app.clinic.save('patients', {'name': 'Paciente unidades'})
        editor = app.encounter_editor(patient)
        identifier = str(uuid.uuid4())
        editor.model.apply('vitals', identifier, {'at':'2026-09-10T10:00:00', 'values':{'weight':{'value':'154.3235835','unit':'lb'}}})
        panel = editor.open_tool('vitals', identifier)
        combo = panel.unit_boxes['weight']
        panel.units['weight'].set('kg')
        combo.event_generate('<<ComboboxSelected>>')
        assert float(panel.values['weight'].get()) == pytest.approx(70)
        panel.values['systolic'].set('123')
        panel.values['diastolic'].set('81')
        assert panel.apply()
        history = editor.open_history()
        settle(app)
        assert {p['metric'] for p in history.trend.points} == {'systolic', 'diastolic'}
        assert all(p['provisional'] for p in history.trend.points)
        assert not app.care.evolution(patient['id'], 'systolic')
        settle(app)
    finally:
        settle(app)
        app.close()

@pytest.mark.desktop
def test_native_drop_binding_and_private_photo_association(tmp_path):
    app = Application(tmp_path)
    app.guard = lambda action: action()
    try:
        uid = app.auth.create_user('Doctor archivos', 'archivos', 'Sintetica-12345')
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        editor = app.patient_editor()
        drop = editor.attachments.drop
        path = str(tmp_path/'archivo con espacios.png')
        script = drop.dnd_bind('<<Drop>>')
        assert script
        # Ejecutar el mismo callback Tcl que usa tkdnd con la lista entregada por Windows.
        callback = app.tk.splitlist(script)[0]
        data = app.tk.call('format', '%s', app.tk.call('list', path))
        args = ['copy', 'copy', '1', '', '', 'DND_Files', 'DND_Files', data, '<<Drop>>', 'DND_Files', '', 'DND_Files', 'DND_Files', 'DND_Files', 'DND_Files', str(drop), '0', '0']
        assert app.tk.call(callback, *args) == 'copy'
        assert editor.attachments.queue[0]['path'] == path
        patient = app.clinic.save('patients', {'name': 'Uno'})
        other = app.clinic.save('patients', {'name': 'Dos'})
        Image.new('RGB', (20, 20), 'white').save(path)
        photo = app.attachments.add(path, patient['id'])
        with pytest.raises(DataError): app.clinic.save('patients', {**other, 'photo_attachment_id': photo['id']}, other['revision'])
        settle(app)
    finally:
        settle(app)
        app.close()

@pytest.mark.desktop
def test_incremental_pdf_viewer_and_locked_background(tmp_path):
    import time
    import tkinter as tk
    from app.attachment_ui import DocumentViewer
    app = Application(tmp_path)
    app.guard = lambda action: action()
    errors = []
    app.report_callback_exception = lambda exc,value,tb: errors.append(str(value))
    try:
        uid = app.auth.create_user('Doctora visores', 'visores', 'Sintetica-12345')
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        app.pdf_preview('Documento sintético', [('Sección '+str(i), 'Contenido de prueba. '*90) for i in range(15)])
        deadline = time.monotonic()+10
        viewer = None
        while time.monotonic()<deadline:
            app.update(); time.sleep(.01)
            viewer = next((w for w in app.winfo_children() if isinstance(w,DocumentViewer)), None)
            if viewer and hasattr(viewer, 'photo'): break
        assert not errors, errors
        assert viewer and getattr(viewer, 'pages', 0) > 1
        viewer.turn(1)
        settle(app)
        assert viewer.page == 1
        delivered = []
        app.lock_session()
        assert app.state() == 'withdrawn' and viewer.state() == 'withdrawn'
        app.background(lambda: 'resultado', delivered.append)
        for _ in range(15): app.update(); time.sleep(.02)
        assert not delivered
        # Continuar el mismo actor en la prueba; no interactuar con cuentas reales.
        app.locked = False
        app.deiconify()
        for window in app.winfo_children():
            if isinstance(window, tk.Toplevel) and window.title() == 'Sesión bloqueada': window.destroy()
        for _ in range(10): app.update(); time.sleep(.02)
        assert delivered == ['resultado']
        viewer.destroy()
        settle(app)
        assert not errors
    finally:
        settle(app)
        app.close()
