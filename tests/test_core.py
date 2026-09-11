import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from unittest.mock import patch
import pytest
from app.storage import Store, DataError, atomic_json, InstanceLock
from app.services import Auth, Clinic
from app.themes import Appearance, BUILTINS, issues, repair, derived, contrast, validate_theme, validate_url
from app.branding import Identity


@pytest.fixture
def context(tmp_path):
    store = Store(tmp_path)
    auth = Auth(store)
    uid = auth.create_user('Administración de prueba', 'admin_test', 'Sintetica-12345')
    auth.login(uid, 'Sintetica-12345')
    return store, auth, Clinic(store, auth), Appearance(store, auth)


@pytest.mark.parametrize('name', BUILTINS)
def test_builtin_contrast(name):
    assert not issues(BUILTINS[name])
    t = derived(BUILTINS[name])
    for key in ('button', 'secondary', 'header', 'sidebar', 'selection'):
        for suffix in ('', '_hover', '_pressed', '_disabled'):
            assert contrast(t[key+suffix], t['on_'+key+suffix]) >= 4.5


def test_restart_and_session_preferences(context):
    store, auth, clinic, appearance = context
    admin = auth.current['id']
    doctor = auth.create_user('Doctora de prueba', 'doctor_test', 'Sintetica-12345')
    appearance.apply('Verde suave', clinic=True)
    auth.login(doctor, 'Sintetica-12345')
    assert appearance.active_key() == 'Verde suave'
    appearance.apply('Azul profundo')
    restored = Appearance(Store(store.root), auth)
    assert restored.active_key() == 'Azul profundo'
    auth.logout()
    assert restored.active_key() == 'Verde suave'
    auth.login(admin, 'Sintetica-12345')
    assert restored.active_key() == 'Verde suave'


@pytest.mark.parametrize('invalid', [{'schema_version': 2}, {'name': 'x'}, [], None,
    {'schema_version': 1, 'name': 'x', 'tokens': {**BUILTINS['Clínico'], 'text': '#fff'}},
    {'schema_version': True, 'name': 'x', 'tokens': BUILTINS['Clínico']}])
def test_bad_json_does_not_change_config(context, tmp_path, invalid):
    store, auth, clinic, appearance = context
    appearance.apply('Neutro')
    before = (store.root/'config/appearance.json').read_bytes()
    path = tmp_path/'invalid.json'
    path.write_text(json.dumps(invalid), encoding='utf-8')
    with pytest.raises(DataError):
        appearance.import_theme(path)
    assert before == (store.root/'config/appearance.json').read_bytes()


def test_duplicate_json_keys(context, tmp_path):
    appearance = context[3]
    path = tmp_path/'duplicated.json'
    path.write_text('{"name":"one", "name":"two"}')
    with pytest.raises(DataError):
        appearance.import_theme(path)
    assert not appearance.state['custom']


def test_custom_theme_lifecycle_and_permissions(context, tmp_path):
    store, auth, clinic, appearance = context
    uid = auth.create_user('Prueba', 'prueba', 'Sintetica-12345')
    other = auth.create_user('Otra prueba', 'otra', 'Sintetica-12345')
    auth.login(uid, 'Sintetica-12345')
    theme = appearance.save_theme('Mi paleta', BUILTINS['Neutro'])
    appearance.rename(theme, 'Mi paleta nueva')
    export = tmp_path/'theme.json'
    appearance.export_theme(export, theme)
    assert validate_theme(json.loads(export.read_text(encoding='utf-8')))['name'] == 'Mi paleta nueva'
    with pytest.raises(DataError):
        appearance.apply(theme, clinic=True)
    appearance.apply(theme)
    with pytest.raises(DataError):
        appearance.delete(theme)
    appearance.apply('Clínico')
    auth.login(other, 'Sintetica-12345')
    with pytest.raises(DataError):
        appearance.rename(theme, 'No permitido')
    auth.login(uid, 'Sintetica-12345')
    appearance.delete(theme)
    assert theme not in Appearance(store, auth).state['custom']


def test_repair_and_semantic_tokens():
    t = {k: '#FFFFFF' for k in BUILTINS['Clínico']}
    assert issues(t)
    fixed = repair(t)
    assert not issues(fixed)
    for kind in ('error', 'success', 'warning'):
        for suffix in ('bg', 'fg'):
            assert derived(fixed)[kind+'_'+suffix] == derived(BUILTINS['Azul profundo'])[kind+'_'+suffix]


@pytest.mark.parametrize('url', ['file:///c:/x', 'javascript:alert(1)', 'ftp://example.com', 'https://', 'https://a b.com', 'https://user:password@example.com', 'https://example.com:bad'])
def test_bad_links(url):
    with pytest.raises(DataError):
        validate_url(url)


def test_web_link_only_on_click_and_documents_independent(context):
    store, auth, clinic, appearance = context
    with patch('app.branding.webbrowser.open', return_value=True) as opened:
        identity = Identity(store, auth)
        before = deepcopy(identity.values)
        appearance.apply('Azul profundo')
        assert Identity(store, auth).values == before
        opened.assert_not_called()
        identity.open_website()
        opened.assert_called_once_with('https://www.tresvizo.com/', new=2)


def test_atomic_failure_preserves_previous(tmp_path):
    path = tmp_path/'config.json'
    atomic_json(path, {'version': 1})
    with patch('app.storage.os.replace', side_effect=OSError('Simulación')):
        with pytest.raises(OSError):
            atomic_json(path, {'version': 2})
    assert json.loads(path.read_text()) == {'version': 1}


def test_corruption_is_not_replaced(context):
    store, auth, clinic, appearance = context
    path = store.root/'config/appearance.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text('{invalid')
    with pytest.raises(DataError):
        Appearance(store, auth)
    assert path.read_text() == '{invalid'


def test_second_instance(tmp_path):
    lock = InstanceLock(tmp_path)
    try:
        with pytest.raises(DataError):
            InstanceLock(tmp_path)
    finally:
        lock.close()


def test_clinical_authorship_revision_and_addenda(context):
    store, auth, clinic, appearance = context
    patient = clinic.save('patients', {'name': 'Paciente sintético Álvarez'})
    record = clinic.save('encounters', {'patient_id': patient['id'], 'attended_at': '2026-09-10T09:00:00-06:00',
        'status': 'Borrador', 'reason': 'Prueba', 'assessment': 'Prueba A; Prueba A; Prueba B', 'plan': 'Texto sintético'})
    original_doctor = auth.current['id']
    with pytest.raises(DataError):
        clinic.save('encounters', record, 0)
    final = clinic.save('encounters', {**record, 'status': 'Finalizada'}, record['revision'])
    other = auth.create_user('Otra doctora', 'otra', 'Sintetica-12345')
    auth.login(other, 'Sintetica-12345')
    with pytest.raises(DataError):
        clinic.save('encounters', final, final['revision'])
    clinic.addendum(final['id'], 'Aclaración de prueba', 'Texto de prueba')
    saved = clinic.list('encounters')[0]
    assert saved['doctor_id'] == original_doctor
    assert saved['addenda'][0]['actor'] == other
    assert saved['assessment'] == record['assessment']


def test_patient_counts_and_diagnoses(context):
    store, auth, clinic, appearance = context
    patient = clinic.save('patients', {'name': 'Paciente sintético'})
    for day in (1, 2, 3):
        clinic.save('encounters', {'patient_id': patient['id'], 'attended_at': f'2026-09-{day:02d}T09:00:00-06:00',
                    'status': 'Finalizada', 'reason': 'Ejemplo', 'assessment': 'A; A; B', 'plan': 'Ejemplo'})
    stats = clinic.statistics('2026-09-01', '2026-09-30')
    assert (stats['consultations'], stats['patients'], stats['new']) == (3, 1, 1)
    assert stats['diagnoses'] == {'a': 3, 'b': 3}
    assert clinic.statistics('2026-09-02', '2026-09-30')['recurrent'] == 1


def test_last_administrator_and_failed_auth(context):
    store, auth, clinic, appearance = context
    uid = auth.current['id']
    with pytest.raises(DataError):
        auth.update_user(uid, active=False)
    auth.logout()
    with pytest.raises(DataError):
        auth.login(uid, 'incorrecta')
    assert auth.current is None
