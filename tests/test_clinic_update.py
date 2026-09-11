import csv
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.branding import Identity, APP_ICON, APP_MARK
from app.services import Auth, Clinic, password_matches
from app.setup_service import create_clinic
from app.storage import Store, DataError
from app.transfer import Transfer


def clinic_context(path):
    store = Store(path)
    auth = Auth(store)
    uid = auth.create_user('Administrador sintético', 'admin', 'Prueba08')
    auth.login(uid, 'Prueba08')
    return store, auth, Clinic(store, auth)


def test_recovery_eight_characters_permissions_and_restart(tmp_path):
    store, auth, clinic = clinic_context(tmp_path)
    admin = auth.current['id']
    doctor = auth.create_user('Doctor sintético', 'doctor', 'Prueba08')
    with pytest.raises(DataError):
        auth.update_user(doctor, password='siete77')
    patient = clinic.save('patients', {'name': 'Paciente sintético'})
    patient_file = store.root/f"data/patients/{patient['id']}.json"
    before = patient_file.read_bytes()
    auth.set_recovery_password('Maestra8', 'Prueba08')
    auth.login(doctor, 'Prueba08')
    with pytest.raises(DataError):
        auth.set_recovery_password('NoPerm08', 'Prueba08')
    auth.logout()
    fresh = Auth(Store(tmp_path))
    fresh.reset_password(doctor, 'Maestra8', 'Nueva008')
    assert fresh.current is None
    assert fresh.login(doctor, 'Nueva008')['role'] == 'doctor'
    assert patient_file.read_bytes() == before
    assert fresh.store.read(f'data/users/{admin}.json')['role'] == 'admin'
    for record in store.records('audit'):
        assert not any(secret in json.dumps(record) for secret in ('Prueba08', 'Maestra8', 'Nueva008'))
    assert 'Maestra8' not in (tmp_path/'config/recovery.json').read_text()


def test_wrong_master_is_persistent_and_does_not_change_user(tmp_path):
    store, auth, _ = clinic_context(tmp_path)
    uid = auth.current['id']
    auth.set_recovery_password('Maestra8', 'Prueba08')
    auth.logout()
    original = store.read(f'data/users/{uid}.json')
    with pytest.raises(DataError, match='incorrecta'):
        auth.reset_password(uid, 'Equivoca', 'Nueva008')
    with pytest.raises(DataError, match='Espera'):
        Auth(Store(tmp_path)).reset_password(uid, 'Maestra8', 'Nueva008')
    assert store.read(f'data/users/{uid}.json') == original
    with patch('app.services.time.time', return_value=10**12):
        with pytest.raises(DataError, match='8 caracteres'):
            auth.reset_password(uid, 'Maestra8', 'corta')
        with patch.object(store, 'transaction', side_effect=OSError('Fallo sintético')):
            with pytest.raises(OSError):
                auth.reset_password(uid, 'Maestra8', 'Nueva008')
    assert store.read(f'data/users/{uid}.json') == original


def test_first_setup_validates_and_persists_clinic_logo_recovery_atomically(tmp_path):
    store = Store(tmp_path/'clinic')
    auth = Auth(store)
    identity = Identity(store, auth)
    source = tmp_path/'logo.png'
    Image.new('RGB', (240, 160), '#127A91').save(source)
    fields = dict(clinic_name='Clínica sintética', name='Administración', username='admin', password='Prueba08', master_password='Maestra8', logo_source=source)
    with pytest.raises(DataError):
        create_clinic(auth, identity, **{**fields, 'password': 'corta'})
    assert not auth.users()
    with patch.object(store, 'transaction', side_effect=OSError('Fallo sintético')):
        with pytest.raises(OSError):
            create_clinic(auth, identity, **fields)
    assert not auth.users()
    assert not store.read('config/identity.json')
    uid = create_clinic(auth, identity, **fields)
    source.unlink()
    restored = Identity(Store(store.root), auth)
    assert restored.values['clinic_name'] == fields['clinic_name']
    assert Path(restored.values['clinic_logo']).is_file()
    assert Path(restored.values['clinic_icon']).is_file()
    assert restored.values['use_clinic_icon']
    assert password_matches('Maestra8', store.read('config/recovery.json')['password'])
    with pytest.raises(DataError):
        create_clinic(auth, identity, **fields)
    assert auth.login(uid, 'Prueba08')['role'] == 'admin'
    transfer = Transfer(store, auth, Clinic(store, auth))
    backup = tmp_path/'backup.zip'
    transfer.backup(backup)
    target = transfer.restore(backup, tmp_path/'restored')
    restored_identity = Identity(Store(target), auth).values
    for key in ('clinic_logo', 'clinic_icon'):
        assert Path(restored_identity[key]).parent == target/'config'
        assert Path(restored_identity[key]).is_file()


def test_consultation_csv_scope_structured_values_and_formula_safety(tmp_path):
    store, auth, clinic = clinic_context(tmp_path/'data')
    admin = auth.current['id']
    doctor = auth.create_user('Otro doctor', 'doctor', 'Prueba08')
    patient = clinic.save('patients', {'name': '=Paciente sintético'})
    template = dict(patient_id=patient['id'], attended_at='2026-09-10T10:00:00', reason='Motivo, con coma\ny salto',
                    assessment='Diagnóstico sintético', plan='@Indicaciones', type='Control')
    medication = {'name': 'Producto sintético', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral', 'frequency': '12', 'frequency_kind': 'Cada N horas'}
    vital = {'at': '2026-09-10T10:00:00', 'values': {'weight': {'value': '70', 'unit': 'kg'}}}
    finished = clinic.save('encounters', {**template, 'status': 'Finalizada', 'prescriptions': [medication], 'vitals': [vital]})
    own = clinic.save('encounters', {**template, 'status': 'Borrador'})
    auth.login(doctor, 'Prueba08')
    private = clinic.save('encounters', {**template, 'status': 'Borrador'})
    auth.login(admin, 'Prueba08')
    transfer = Transfer(store, auth, clinic)
    assert [r['id'] for r in transfer.consultation_rows()] == [finished['id']]
    assert {r['id'] for r in transfer.consultation_rows(include_drafts=True)} == {finished['id'], own['id']}
    assert not transfer.consultation_rows(identifiers=[private['id']], include_drafts=True)
    output = tmp_path/'consultas.csv'
    assert transfer.export_consultations(output) == 1
    with output.open(encoding='utf-8-sig', newline='') as stream:
        row = next(csv.DictReader(stream))
    assert row['reason'] == template['reason']
    assert row['patient_name'].startswith("'=") and row['plan'].startswith("'@")
    assert row['consultation_type'] == 'Control'
    assert row['weight'] == '70' and row['weight_unit'] == 'kg'
    assert json.loads(row['prescriptions_json'])[0]['dose'] == '1'
    assert json.loads(row['prescriptions_json'])[0]['frequency'] == '12'
    assert json.loads(row['vitals_json'])[0]['values']['weight']['value'] == '70'
    before = output.read_bytes()
    with pytest.raises(DataError):
        transfer.export_consultations(output, start='2026-10-01', end='2026-09-01')
    with patch('app.transfer.safe_csv', side_effect=OSError('Fallo sintético')):
        with pytest.raises(OSError):
            transfer.export_consultations(output)
    assert output.read_bytes() == before
    assert not transfer.consultation_rows(start='2026-09-11')


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


@pytest.mark.desktop
def test_patient_calendar_every_day_reopen_disable_and_preserve_sex(tmp_path):
    from app.main_window import Application
    app = Application(tmp_path)
    errors = []
    app.report_callback_exception = lambda exc, value, tb: errors.append(value)
    try:
        uid = app.auth.create_user('Admin', 'admin', 'Prueba08')
        app.auth.login(uid, 'Prueba08')
        app.shell()
        editor = app.patient_editor()
        editor.personal.vars['name'].set('Paciente sintético')
        field = editor.personal.inputs['birth_date']
        field.set_date(date(2000, 2, 1))
        editor.unknown.set(False)
        for day in range(1, 30):
            window = field.open()
            app.update_idletasks()
            assert window is field.open()
            button = next(w for w in descendants(window) if w.winfo_class() == 'TButton' and w.cget('text') == str(day))
            button.invoke()
            app.update()
            assert field.get() == f'2000-02-{day:02d}'
            assert not window.winfo_exists()
        window = field.open()
        editor.unknown.set(True)
        assert not window.winfo_exists()
        assert field.entry.instate(['disabled'])
        editor.unknown.set(False)
        assert field.entry.instate(['!disabled'])
        assert tuple(editor.personal.inputs['sex']['values']) == ('Masculino', 'Femenino')
        editor.personal.vars['sex'].set('Otro registrado')
        editor.save()
        assert editor.payload(raw=True)['sex'] == 'Otro registrado'
        assert not errors
    finally:
        app.close()


@pytest.mark.desktop
def test_profile_photo_persists_and_refreshes_widgets_without_clearing_others(tmp_path):
    from app.main_window import Application
    from app.profiles import ProfileEditor, Profiles
    from tkinter import ttk
    app = Application(tmp_path)
    try:
        uid = app.auth.create_user('Admin', 'admin', 'Prueba08')
        app.auth.login(uid, 'Prueba08')
        other_id = app.auth.create_user('Otra doctora', 'otra', 'Prueba08')
        other_user = next(u for u in app.auth.users() if u['id'] == other_id)
        app.shell()
        first, second = ProfileEditor(app, app), ProfileEditor(app, app)
        first.pack()
        second.pack()
        other = ttk.Label(app)
        app.profiles.bind(other, other_user, 32)
        other_image = str(other.profile_photo)
        assert first.use_photo(Image.new('RGB', (300, 300), '#1579C1'))
        app.update()
        for widget, size in ((first.preview, 96), (second.preview, 96), (app.profile_button, 32)):
            assert app.tk.call(str(widget.profile_photo), 'get', size//2, size//2) == (21, 121, 193)
        assert other_image in app.tk.call('image', 'names')
        pref = Profiles(Store(tmp_path), app.auth, app).get(uid)
        assert pref['avatar'] == 'photo'
        with Image.open(tmp_path/pref['photo']) as image:
            assert image.getpixel((128, 128)) == (21, 121, 193)
        app.auth.logout()
        app.login_screen()
        app.login_page.select(next(u for u in app.auth.users() if u['id'] == uid))
        app.update()
        avatar = app.login_page.avatar.profile_photo
        assert app.tk.call(str(avatar), 'get', avatar.width()//2, avatar.height()//2) == (21, 121, 193)
    finally:
        app.close()


def test_clinical_icon_assets_have_alpha_and_windows_sizes():
    with Image.open(APP_MARK) as mark:
        assert mark.mode == 'RGBA'
        assert mark.getchannel('A').getextrema() == (0, 255)
    with Image.open(APP_ICON) as icon:
        assert icon.ico.sizes() == {(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)}


@pytest.mark.desktop
def test_setup_screen_chooses_identity_and_recovery_without_default_credentials(tmp_path):
    from app.main_window import Application
    app = Application(tmp_path)
    try:
        setup = app.setup_page
        setup.variables['clinic_name'].set('Clínica de prueba')
        setup.next()
        for key, value in dict(name='Admin', username='admin', password='Prueba08', confirmation='Prueba08', master_password='Maestra8', master_confirmation='Maestra8').items():
            setup.variables[key].set(value)
        setup.submit_setup()
        app.update()
        assert app.current_page == 'Pacientes'
        assert app.auth.recovery_configured()
        assert Path(app.brand_icon_path) == Path(app.identity.values['clinic_icon'])
        assert app.identity.values['clinic_name'] == 'Clínica de prueba'
    finally:
        app.close()
