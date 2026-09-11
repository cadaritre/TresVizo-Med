from copy import deepcopy
from contextlib import contextmanager
import uuid
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk

import pytest
from PIL import Image

from app.main_window import Application
from app.consultation_state import ConsultationDraft, measurement_summary
from app.clinical_models import encounter_sections
from app.documents import create_pdf
from app.storage import DataError
from tests.test_redesign import settle


def record(**values):
    return {'id': str(uuid.uuid4()), 'status': 'Borrador', 'attended_at': '2026-09-10T10:00:23-06:00',
            'revision': 1, 'reason': 'Motivo sintético', 'plan': 'Plan de prueba', **values}


def test_legacy_editor_state_recovers_pending_without_confirming_or_overwriting():
    group_id, medicine_id = str(uuid.uuid4()), str(uuid.uuid4())
    original = record(vitals=[{'id': group_id, 'at': '2026-09-09T10:00:00', 'values': {'weight': {'value': '70', 'unit': 'kg'}}}],
                      prescriptions=[{'id': medicine_id, 'name': 'Producto previo'}],
                      editor_state={'header': {'date': '31/0', 'time': '1', 'type': 'Control'},
                        'medications': {'rows': [{'id': medicine_id, 'name': 'Producto previo'}], 'index': 0, 'pending': {'name': 'Cambio sin confirmar', 'dose': '1,'}},
                        'vitals': {'id': group_id, 'date': '10/09/2026', 'time': '10:30', 'values': {'weight': '7,'}, 'units': {'weight': 'lb'}},
                        'followup': {'date': '30/', 'reason': 'Fecha incompleta'}, 'custom_future_field': {'preserved': True}})
    untouched = deepcopy(original)
    model = ConsultationDraft(original)
    assert model.data['vitals'][0]['values']['weight']['value'] == '70'
    assert model.data['prescriptions'][0]['name'] == 'Producto previo'
    assert model.initial('vitals')[1]['values']['weight'] == '7,'
    assert model.initial('medication')[1]['name'] == 'Cambio sin confirmar'
    assert model.initial('header')[1]['date'] == '31/0'
    recovered = ConsultationDraft(model.snapshot())
    assert recovered.pending == model.pending
    assert recovered.legacy_state == {'custom_future_field': {'preserved': True}}
    with pytest.raises(DataError):
        recovered.snapshot(final=True)
    assert original == untouched


def test_cancel_is_copy_only_and_takes_keep_ids_times_and_partial_pressure():
    identifier = str(uuid.uuid4())
    model = ConsultationDraft(record(diagnoses=[{'name': 'Diagnóstico sintético'}]))
    model.apply('vitals', identifier, {'at': '2026-09-10T10:30:17-06:00', 'values': {'systolic': {'value': '120', 'unit': 'mmHg'}}})
    old = deepcopy(model.data)
    _, temporary, _ = model.initial('vitals', identifier)
    temporary['values']['systolic']['value'] = '999'
    model.remember('vitals', identifier, temporary)
    model.discard('vitals', identifier)
    assert model.data == old
    assert 'sin diastólica' in measurement_summary(model.data['vitals'][0])
    model.apply('vitals', str(uuid.uuid4()), {'at': '2026-09-10T11:00:00', 'values': {'temperature': {'value': '98.6', 'unit': '°F'}}})
    assert model.data['vitals'][0]['at'].endswith('17-06:00')
    assert len(model.data['vitals']) == 2
    with pytest.raises(DataError):
        model.apply('vitals', identifier, {'at': '2026-09-10T10:00:00', 'values': {'oxygen': {'value': '101', 'unit': '%'}}})
    assert model.data['vitals'][0] == old['vitals'][0]


def test_removing_last_diagnosis_does_not_finalize_with_stale_assessment():
    model = ConsultationDraft(record(diagnoses=[{'id': 'one', 'name': 'No conservar al quitar'}], assessment='No conservar al quitar'))
    model.remove('diagnosis', 'one')
    assert model.snapshot()['assessment'] == ''
    assert any(target == 'diagnosis' for target, _ in model.problems())


@contextmanager
def workspace(path):
    app = Application(path)
    errors = []
    app.report_callback_exception = lambda exc, value, tb: errors.append(value)
    app.guard = lambda operation: operation()
    try:
        uid = app.auth.create_user('Doctora contexto', 'contexto', 'Sintetica-12345')
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        patient = app.clinic.save('patients', {'name': 'Paciente sintético de consulta', 'allergy_status': 'No interrogado'})
        editor = app.encounter_editor(patient)
        app.geometry('1366x768')
        app.update()
        yield app, editor, uid
        settle(app)
        assert not errors
    finally:
        settle(app)
        app.close()


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


@pytest.mark.desktop
def test_complete_contextual_visit_final_view_and_pdf_match(tmp_path):
    from pypdf import PdfReader
    with workspace(tmp_path) as (app, editor, uid):
        assert not any(isinstance(w, ttk.Notebook) for w in descendants(editor))
        editor.texts['reason'].insert('1.0', 'Control de prueba')
        editor.texts['subjective'].insert('1.0', 'Evolución sintética sin hallazgos supuestos.')
        editor.texts['plan'].insert('1.0', 'Indicaciones individualizadas de demostración.')
        app.update()
        text = editor.texts['subjective']
        text.focus_force()
        text.mark_set('insert', '1.7')
        text.tag_add('sel', '1.1', '1.5')
        original = (str(text), text.get('1.0', 'end-1c'), text.index('insert'), tuple(map(str, text.tag_ranges('sel'))))
        with patch.object(app.care, 'evolution', side_effect=AssertionError('No cargar histórico al capturar')):
            capture = editor.open_tool('vitals')
            capture.values['weight'].set('70')
            capture.values['height'].set('175')
            capture.values['systolic'].set('120')
            assert capture.apply()
        app.update()
        assert (str(text), text.get('1.0', 'end-1c'), text.index('insert'), tuple(map(str, text.tag_ranges('sel')))) == original
        assert app.focus_get() is text
        first = deepcopy(editor.model.data['vitals'][0])
        capture = editor.edit_take()
        capture.values['weight'].set('90')
        capture.cancel()
        assert capture.resolution.winfo_manager()
        capture.discard()
        assert editor.model.data['vitals'][0] == first
        capture = editor.open_tool('vitals', str(uuid.uuid4()))
        capture.values['heart_rate'].set('78')
        assert capture.apply()
        assert len(editor.model.data['vitals']) == 2
        editor.diagnosis_var.set('Diagnóstico sintético')
        editor.add_diagnosis()
        for name in ('Producto A de prueba', 'Producto B de prueba'):
            capture = editor.open_tool('medication')
            for key, value in {'name': name, 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral', 'frequency_kind': 'Cada N horas', 'frequency': '12', 'duration': '3', 'duration_unit': 'días'}.items():
                capture.form.vars[key].set(value)
            assert capture.apply()
        medication = editor.model.data['prescriptions'][0]
        capture = editor.open_tool('medication', medication['id'])
        capture.form.vars['frequency_kind'].set('Horarios')
        capture.form.vars['frequency'].set('08:00 y 20:00')
        assert capture.apply()
        capture = editor.open_tool('study')
        capture.form.vars['name'].set('Estudio sintético')
        capture.form.inputs['notes'].insert('1.0', 'Indicaciones del estudio de prueba')
        assert capture.apply()
        editor.model.remember('followup', 'followup', {'date': '20/09/2026', 'reason': ''})
        capture = editor.open_tool('followup')
        capture.form.vars['date'].set('20/09/2026')
        capture.form.inputs['reason'].insert('1.0', 'Revisión sintética')
        assert capture.apply()
        image = tmp_path/'documento de prueba.png'
        Image.new('RGB', (80, 60), 'white').save(image)
        capture = editor.open_tool('documents')
        assert capture.panel.winfo_manager()
        capture.panel.add_paths([str(image)])
        capture.panel.start()
        settle(app)
        assert capture.panel.queue[0]['status'] == 'Guardado'
        capture.cancel()
        editor.save()
        identifier = editor.record['id']
        persisted = app.store.read(f'data/encounters/{identifier}.json')
        assert persisted['vitals'][0]['bmi'] == 22.86
        assert len(persisted['prescriptions']) == 2
        app.pages.pop('consulta:'+identifier)
        editor.destroy()
        editor = app.open_encounter(identifier)
        assert editor.model.data['subjective'] == original[1]
        assert len(editor.model.data['vitals']) == 2
        assert editor.model.data['prescriptions'][0]['frequency'] == '08:00 y 20:00'
        review = editor.finish()
        assert not editor.model.problems()
        review.finalize()
        final = app.store.read(f'data/encounters/{identifier}.json')
        assert final['status'] == 'Finalizada'
        assert 'editor_state' not in final
        assert not app.clinic.list('followups')
        assert final['followup']['reason'] == 'Revisión sintética'
        final_view = app.pages['historia:'+identifier]
        assert not any(isinstance(w, ttk.Notebook) for w in descendants(final_view))
        sections = encounter_sections(final)
        pdf = tmp_path/'consulta.pdf'
        create_pdf(pdf, app.identity.values, 'Consulta de prueba', sections, app.auth.current['name'], editor.patient['name'])
        extracted = '\n'.join(p.extract_text() for p in PdfReader(pdf).pages)
        for expected in ('Producto A de prueba', '08:00 y 20:00', 'Estudio sintético', 'Indicaciones del estudio de prueba', 'Revisión sintética', '22.86'):
            assert expected in extracted
        assert app.attachments.list(final['patient_id'], identifier)[0]['original_name'] == image.name


@pytest.mark.desktop
def test_single_capture_cancel_keyboard_autosave_failure_and_private_recovery(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        patient_id = editor.patient['id']
        other = app.auth.create_user('Otro doctor', 'otro', 'Sintetica-12345')
        capture = editor.open_tool('medication')
        assert editor.open_tool('vitals') is capture
        app.show('Pacientes')
        assert app.current_page == 'consulta:'+editor.record['id']
        capture.form.vars['name'].set('Pauta todavía sin aplicar')
        capture.more.toggle()
        note = capture.extra.inputs['instructions']
        note.insert('1.0', 'Una línea')
        note.focus_force()
        app.update()
        note.mark_set('insert', 'end-1c')
        note.event_generate('<KeyPress-Return>')
        note.insert('insert', 'Otra línea')
        app.update()
        capture.event_generate('<Escape>')
        app.update()
        assert capture.winfo_exists() and capture.resolution.winfo_manager()
        capture.defer()
        with patch.object(app.clinic, 'save', side_effect=OSError('Disco no disponible')):
            assert not editor.save_feedback()
        assert editor.state['dirty'] and editor.model.pending
        assert 'No se guardó' in editor.indicator.get()
        assert editor.save_feedback()
        capture = editor.open_tool('medication')
        assert capture.form.vars['name'].get() == 'Pauta todavía sin aplicar'
        capture.form.vars['dose'].set('1,')
        editor.autosave()
        identifier = editor.record['id']
        assert app.store.read(f'data/encounters/{identifier}.json')['editor_state']['pending']
        app.lock_session()
        app.update()
        assert capture.state() == 'withdrawn'
        assert app.grab_current() is None
        app.logout()
        settle(app)
        assert app.auth.current is None
        app.auth.login(other, 'Sintetica-12345')
        app.shell()
        assert identifier not in {r['id'] for r in app.clinic.list('encounters')}
        assert not getattr(app, 'active_capture', None)
        app.logout()
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        editor = app.open_encounter(identifier)
        capture = editor.open_tool('medication')
        assert capture.form.vars['dose'].get() == '1,'
        assert capture.extra.inputs['instructions'].get('1.0', 'end-1c') == 'Una línea\nOtra línea'
        capture.discard()
        assert not editor.model.data['prescriptions'] and not editor.model.pending


@pytest.mark.desktop
@pytest.mark.parametrize('scale', [1, 1.25, 1.5, 2])
def test_context_capture_actions_fit_and_theme_preserves_pending(scale, tmp_path):
    from app.themes import BUILTINS
    original_init = tk.Tk.__init__
    def init(root, *args, **kwargs):
        original_init(root, *args, **kwargs)
        root.tk.call('tk', 'scaling', scale*96/72)
    with patch.object(tk.Tk, '__init__', init), workspace(tmp_path) as (app, editor, uid):
        capture = editor.open_tool('vitals')
        capture.values['systolic'].set('12,')
        capture.entries['systolic'].focus_force()
        app.update()
        widget = capture.entries['systolic']
        for name in ('Clínico', 'Azul profundo'):
            app.theme.apply(BUILTINS[name])
            app.update_idletasks()
            assert capture.values['systolic'].get() == '12,'
            assert app.focus_get() is widget
        for button in (capture.cancel_button, capture.apply_button):
            assert capture.winfo_rootx() <= button.winfo_rootx()
            assert button.winfo_rootx()+button.winfo_width() <= capture.winfo_rootx()+capture.winfo_width()
            assert button.winfo_rooty()+button.winfo_height() <= capture.winfo_rooty()+capture.winfo_height()
        assert not any(isinstance(w, ttk.Notebook) for w in descendants(editor))
        capture.discard()


@pytest.mark.desktop
def test_legacy_save_backup_and_document_metadata_pending_recovery(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        patient, identifier = editor.patient, editor.record['id']
        settle(app)
        legacy = app.clinic.save('encounters', {**editor.record, 'editor_state': {
            'medications': {'rows': [], 'pending': {'name': 'Pauta heredada pendiente'}, 'index': None},
            'header': {'date': '30/', 'time': '10:00', 'type': 'Control'}}}, editor.record['revision'])
        app.pages.pop('consulta:'+identifier)
        editor.destroy()
        editor = app.open_encounter(identifier)
        editor.save()
        backup = app.store.read(f"backups/editor-consulta/{identifier}-r{legacy['revision']}.json")
        assert backup == legacy
        source = tmp_path/'metadatos.png'
        Image.new('RGB', (40, 40), 'white').save(source)
        item = app.attachments.add(source, patient['id'], identifier)
        capture = editor.open_tool('documents')
        capture.edit_details(item['id'])
        capture.details_form.inputs['notes'].insert('1.0', 'Descripción todavía sin aplicar')
        app.update()
        capture.defer()
        editor.save()
        assert app.attachments.get(item['id'])['notes'] == ''
        settle(app)
        app.pages.pop('consulta:'+identifier)
        editor.destroy()
        editor = app.open_encounter(identifier)
        capture = editor.open_tool('document_metadata', item['id'])
        assert capture.details_form.inputs['notes'].get('1.0', 'end-1c') == 'Descripción todavía sin aplicar'
        capture.apply_details()
        assert app.attachments.get(item['id'])['notes'] == 'Descripción todavía sin aplicar'
        assert not any(p['kind'] == 'document_metadata' for p in editor.model.pending.values())
        capture.cancel()
