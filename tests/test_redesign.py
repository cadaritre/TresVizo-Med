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
    patient = care.register(draft['id'],{'name':'Paciente sintético','sex':'No especificado'})
    assert care.register(draft['id'],{'name':'No duplicar'})['id'] == patient['id']
    assert len(clinic.list('patients')) == 1
    source.unlink()
    assert attachments.path(item['id']).is_file()
    assert attachments.list(patient['id'])[0]['draft_id'] is None

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

def test_workspace_patient_consultation_roundtrip(tmp_path):
    app = Application(tmp_path)
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
        visit.diagnoses.rows = [{'name':'Diagnóstico de prueba'}]
        visit.medications.rows = [{'name':'Producto de prueba','dose':'1','dose_unit':'tableta','route':'Oral','frequency_kind':'Cada N horas','frequency':'12'}]
        visit.vitals.values['weight'].set('70')
        visit.vitals.values['height'].set('175')
        visit.vitals.confirm()
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
        app.close()
