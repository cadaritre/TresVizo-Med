from unittest.mock import patch
from tkinter import ttk

import pytest

from tests.test_consultation_context import workspace, descendants
from tests.test_redesign import settle


def request_x(window):
    window.tk.call(window.protocol('WM_DELETE_WINDOW'))


@pytest.mark.desktop
def test_x_closes_medication_while_combobox_list_is_open(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        capture = editor.open_tool('medication')
        box = capture.form.inputs['route']
        app.update()
        app.tk.call('ttk::combobox::Post', str(box))
        app.update()
        try:
            assert capture.raw() == capture.baseline
            errors = []
            with patch.object(app, 'report_callback_exception', side_effect=lambda exc, value, tb: errors.append(value)):
                request_x(capture)
            assert not errors, repr(errors)
            app.update()
            assert not capture.winfo_exists(), 'La X debe cerrar una captura intacta incluso con una lista desplegada.'
            assert not app.tk.call('grab', 'current', app._w)
            assert not getattr(app, 'active_capture', None)
        finally:
            if capture.winfo_exists():
                app.tk.call('ttk::combobox::Unpost', str(box))
                capture.close()


@pytest.mark.desktop
def test_close_choices_fit_small_window_and_receive_focus(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        capture = editor.open_tool('medication')
        capture.geometry('460x480')
        capture.form.vars['name'].set('Medicamento sintético pendiente')
        capture.form.inputs['name'].focus_force()
        app.update()
        request_x(capture)
        app.update()
        assert capture.resolution.winfo_ismapped()
        choices = [w for w in descendants(capture.resolution) if isinstance(w, ttk.Button)]
        for button in choices:
            assert button.winfo_ismapped()
            assert button.winfo_rootx()+button.winfo_width() <= capture.winfo_rootx()+capture.winfo_width()
            assert button.winfo_rooty()+button.winfo_height() <= capture.winfo_rooty()+capture.winfo_height()
        assert app.focus_get() in choices, 'La decisión para cerrar debe recibir el foco.'
        capture.defer()


@pytest.mark.desktop
@pytest.mark.parametrize('control', ['x', 'cancel', 'escape'])
def test_all_consultation_captures_close_and_allow_reopening(tmp_path, control):
    with workspace(tmp_path) as (app, editor, uid):
        note = editor.texts['subjective']
        note.insert('1.0', 'Nota que debe conservarse')
        note.focus_force()
        app.update()
        note.mark_set('insert', '1.5')
        for kind in ('medication', 'vitals', 'study', 'followup', 'header', 'diagnosis', 'history', 'reuse', 'review', 'documents'):
            capture = editor.open_tool(kind)
            capture.focus_force()
            app.update()
            if control == 'x':
                request_x(capture)
            elif control == 'cancel':
                # Las capturas de lectura/documentos presentan Volver en vez de Cancelar.
                if kind in ('history', 'documents'):
                    capture.apply_button.invoke()
                else:
                    capture.cancel_button.invoke()
            else:
                capture.event_generate('<Escape>')
            app.update()
            assert not capture.winfo_exists(), (kind, control)
            assert not app.tk.call('grab', 'current', app._w)
            assert not getattr(app, 'active_capture', None)
            assert note.get('1.0', 'end-1c') == 'Nota que debe conservarse'
            assert note.index('insert') == '1.5'
            assert app.focus_get() is note
            settle(app)


@pytest.mark.desktop
def test_x_with_dropdown_preserves_raw_values_and_all_close_decisions(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        capture = editor.open_tool('medication')
        capture.form.vars['name'].set('Medicamento sintético')
        capture.form.vars['dose'].set('1,')
        box = capture.form.inputs['route']
        app.update()
        app.tk.call('ttk::combobox::Post', str(box))
        app.update()
        request_x(capture)
        app.update()
        assert capture.resolution.winfo_ismapped()
        assert not app.tk.call('winfo', 'ismapped', box._w+'.popdown')
        assert str(app.tk.call('grab', 'current', app._w)) == str(capture)
        assert app.focus_get() is capture.defer_button
        capture.continue_button.invoke()
        app.update()
        assert app.focus_get() is box
        assert capture.form.vars['dose'].get() == '1,'
        request_x(capture)
        capture.defer_button.invoke()
        app.update()
        assert not capture.winfo_exists()
        assert editor.save()
        saved = app.store.read(f"data/encounters/{editor.record['id']}.json")
        assert next(p for p in saved['editor_state']['pending'].values() if p['kind'] == 'medication')['values']['dose'] == '1,'
        recovered = editor.open_tool('medication')
        assert recovered.form.vars['dose'].get() == '1,'
        request_x(recovered)
        recovered.discard_button.invoke()
        assert not recovered.winfo_exists()
        assert not editor.model.pending and not editor.model.data['prescriptions']
        assert not app.tk.call('grab', 'current', app._w)


@pytest.mark.desktop
def test_x_closes_document_metadata_instead_of_only_returning_to_list(tmp_path):
    from PIL import Image
    with workspace(tmp_path) as (app, editor, uid):
        source = tmp_path/'documento-sintetico.png'
        Image.new('RGB', (20, 20), 'white').save(source)
        row = app.attachments.add(source, editor.patient['id'], editor.record['id'])
        capture = editor.open_tool('documents')
        capture.edit_details(row['id'])
        request_x(capture)
        assert not capture.winfo_exists()
        capture = editor.open_tool('documents')
        capture.edit_details(row['id'])
        capture.details_form.vars['title'].set('Cambio que se descarta')
        request_x(capture)
        app.update()
        assert capture.resolution.winfo_ismapped()
        capture.discard_button.invoke()
        assert not capture.winfo_exists()
        assert app.attachments.get(row['id'])['title'] == row['title']
