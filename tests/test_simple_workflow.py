"""Recorrido diario simplificado y conservación de información anterior."""
from copy import deepcopy
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import pytest
from app.main_window import Application
from app.storage import DataError
from tests.test_consultation_context import workspace, descendants
from tests.test_redesign import settle


@pytest.mark.desktop
def test_search_retains_selection_and_resume_never_duplicates(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        patient, identifier = editor.patient, editor.record['id']
        app.clinic.save('patients', {'name': patient['name'], 'birth_date': '1980-01-01'})
        app.show('Pacientes')
        page = app.pages['Pacientes']
        page.search_input.insert(0, 'Paciente sintético')
        settle(app)
        tree = next(w for w in descendants(page) if isinstance(w, ttk.Treeview))
        assert len(tree.get_children()) == 2
        assert len({tree.set(i, 'file') for i in tree.get_children()}) == 2
        tree.selection_set(patient['id'])
        tree.focus(patient['id'])
        app.show('Más opciones')
        app.show('Pacientes')
        settle(app)
        assert page.search_input.get() == 'Paciente sintético'
        assert tree.selection() == (patient['id'],)
        with patch('app.main_window.messagebox.askyesno', return_value=True) as prompt:
            app.confirm_encounter(patient)
            app.confirm_encounter(patient)
            settle(app)
        assert prompt.call_count == 1
        assert prompt.call_args.args[0] == 'Retomar consulta pendiente'
        assert app.current_page == 'consulta:'+identifier
        assert len(app.clinic.list('encounters')) == 1
        assert 'Agenda' not in app.nav_buttons and 'Seguimientos' not in app.nav_buttons
        for name in ('Mis estadísticas', 'Configuración', 'Exportar y respaldar'):
            app.show(name)
            settle(app)


@pytest.mark.desktop
def test_minimum_registration_continues_without_optional_panels(tmp_path):
    with workspace(tmp_path) as (app, existing, uid):
        patient = app.patient_editor(attend=True)
        assert not any(isinstance(w, ttk.Notebook) for w in descendants(patient))
        assert not patient.complementary.opened and not patient.document_section.opened
        assert patient.allergy_status.get() == 'No interrogado'
        assert patient.primary_save.cget('text') == 'Guardar y comenzar consulta'
        patient.primary_save.invoke()
        app.update()
        assert app.current_page == 'alta:'+patient.draft_id
        assert app.focus_get() is patient.personal.inputs['name']
        assert not patient.review_section.opened
        patient.personal.vars['name'].set('Alta mínima de prueba')
        patient.primary_save.invoke()
        settle(app)
        visit = app.pages[app.current_page]
        assert app.current_page.startswith('consulta:')
        assert visit.patient['name'] == 'Alta mínima de prueba'
        assert visit.patient['allergy_status'] == 'No interrogado'
        assert len(app.clinic.list('patients')) == 2
        assert visit.soap['S'].opened
        assert not any(visit.soap[k].opened for k in 'OAP')


@pytest.mark.desktop
def test_soap_error_target_draft_recovery_and_failed_save_keep_capture(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        editor.texts['reason'].insert('1.0', 'Motivo de prueba')
        editor.texts['subjective'].insert('1.0', 'Relato sin hallazgos inventados')
        app.update()
        assert not editor.soap['P'].opened
        editor.goto_issue('plan')
        app.update()
        assert editor.soap['P'].opened and app.focus_get() is editor.texts['plan']
        editor.texts['plan'].insert('1.0', 'Indicaciones de prueba')
        editor.reveal_section('A')
        editor.diagnosis_var.set('Impresión sintética')
        editor.add_diagnosis()
        editor.save()
        assert not editor.model.problems()
        before = deepcopy(editor.model.data)
        text = editor.texts['plan']
        text.focus_force()
        text.insert('end', ' Cambio local')
        text.mark_set('insert', '1.4')
        app.update()
        with patch.object(app.clinic, 'save', side_effect=OSError('Fallo sintético de disco')):
            assert editor.save_feedback() is False
        assert text.get('1.0', 'end-1c').endswith('Cambio local')
        assert text.index('insert') == '1.4'
        assert app.store.read(f"data/encounters/{editor.record['id']}.json")['plan'] == before['plan']
        editor.save()
        identifier = editor.record['id']
        app.pages.pop('consulta:'+identifier)
        editor.destroy()
        recovered = app.open_encounter(identifier)
        settle(app)
        assert recovered.soap['P'].opened and recovered.soap['A'].opened
        assert not recovered.soap['O'].opened
        assert 'Cambio local' in recovered.soap['P'].summary.cget('text')
        assert recovered.model.data['subjective'] == 'Relato sin hallazgos inventados'
        recovered.save(final=True)
        final = app.store.read(f'data/encounters/{identifier}.json')
        assert final['status'] == 'Finalizada'
        app.pages.pop('consulta:'+identifier)
        recovered.destroy()
        app.open_encounter(identifier)
        settle(app)
        assert app.current_page == 'historia:'+identifier


@pytest.mark.desktop
def test_legacy_note_and_retired_schedule_files_are_preserved(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        complex_patient = app.clinic.save('patients', {**editor.patient,
            'emergency_contact': {'guardian': 'Responsable de demostración', 'phone': '5555 0100'},
            'histories': {'personal': {'status': 'Antecedentes registrados', 'notes': 'Antecedente ficticio conservado'}},
            'administrative': 'Nota administrativa sintética'}, editor.patient['revision'])
        patient_form = app.patient_editor(complex_patient)
        assert not patient_form.complementary.opened
        assert 'Responsable de demostración' in patient_form.emergency_section.summary.cget('text')
        assert '1 antecedentes' in patient_form.complementary.summary.cget('text')
        assert 'Antecedente ficticio conservado' in patient_form.histories['personal'].master.master.summary.cget('text')
        for field in ('emergency_contact', 'administrative'):
            expected = complex_patient[field]
            actual = patient_form.payload(raw=True)[field]
            assert all(actual[k] == v for k, v in expected.items()) if isinstance(expected, dict) else actual == expected
        appointment = app.clinic.save('appointments', {'patient_id': editor.patient['id'], 'due_at': '2026-10-01T10:00:00', 'status': 'Programada'})
        followup = app.clinic.save('followups', {'patient_id': editor.patient['id'], 'due_at': '2026-10-02', 'status': 'Pendiente'})
        paths = [app.store.root/f"data/appointments/{appointment['id']}.json", app.store.root/f"data/followups/{followup['id']}.json"]
        original_bytes = [p.read_bytes() for p in paths]
        old = app.clinic.save('encounters', {'patient_id': editor.patient['id'], 'status': 'Borrador', 'attended_at': '2026-09-01T10:00:00',
            'reason': 'Motivo anterior', 'subjective': 'Nota original completa; no reinterpretar.', 'assessment': 'Valoración antigua íntegra',
            'medications': 'Texto heredado del médico', 'plan': 'Plan histórico', 'followup': {'date': '2026-10-03', 'reason': 'Dato anterior'}})
        previous = app.open_encounter(old['id'])
        previous.save(final=True)
        final = app.store.read(f"data/encounters/{old['id']}.json")
        for field in ('reason', 'subjective', 'assessment', 'medications', 'plan', 'followup'):
            assert final[field] == old[field]
        assert len(app.clinic.list('followups')) == 1
        assert [p.read_bytes() for p in paths] == original_bytes
        with pytest.raises(DataError):
            editor.open_tool('followup')
        assert getattr(app, 'active_capture', None) is None


@pytest.mark.desktop
@pytest.mark.parametrize('scale', [1, 1.25, 1.5, 2])
def test_simple_actions_fit_small_window_and_tk_scaling(tmp_path, scale):
    original_init = tk.Tk.__init__
    def init(root, *args, **kwargs):
        original_init(root, *args, **kwargs)
        root.tk.call('tk', 'scaling', scale*96/72)
    with patch.object(tk.Tk, '__init__', init):
        app = Application(tmp_path)
    try:
        uid = app.auth.create_user('Doctora de escala', 'escala', 'Sintetica-12345')
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        assert app.current_page == 'Pacientes'
        app.geometry('1024x768' if scale == 1 else '1366x768')
        settle(app)
        for button in descendants(app.pages['Pacientes']):
            if isinstance(button, ttk.Button) and button.cget('text') in ('Nuevo paciente', 'Atender / retomar', 'Abrir expediente'):
                assert button.winfo_ismapped()
                assert button.winfo_height() >= button.winfo_reqheight()
                assert button.winfo_rooty()+button.winfo_height() <= app.winfo_rooty()+app.winfo_height()
        patient = app.patient_editor(attend=True)
        app.update()
        for button in (patient.primary_save, patient.secondary_save):
            assert button.winfo_ismapped()
            assert button.winfo_width() >= button.winfo_reqwidth()
            assert button.winfo_rootx()+button.winfo_width() <= app.winfo_rootx()+app.winfo_width()
            assert button.winfo_rooty()+button.winfo_height() <= app.winfo_rooty()+app.winfo_height()
        patient.personal.vars['name'].set('Paciente de escala')
        patient.register(True)
        editor = app.pages[app.current_page]
        app.update()
        for button in (editor.finish_button, editor.save_button, *editor.quick_buttons.values()):
            assert button.winfo_ismapped()
            assert button.winfo_width() >= button.winfo_reqwidth()
            assert button.winfo_rootx()+button.winfo_width() <= app.winfo_rootx()+app.winfo_width()
            assert button.winfo_rooty()+button.winfo_height() <= app.winfo_rooty()+app.winfo_height()
    finally:
        settle(app)
        app.close()
