from copy import deepcopy

import pytest

from app.themes import BUILTINS
from tests.test_consultation_context import workspace
from tests.test_redesign import settle

pytestmark = pytest.mark.desktop


def test_three_main_fields_visible_and_review_includes_typed_diagnosis(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        app.geometry('1366x768')
        settle(app)
        assert not editor.symptoms_section.opened
        assert not editor.assessment_section.opened
        bottom = editor.scroll.canvas.winfo_rooty()+editor.scroll.canvas.winfo_height()
        for widget in (editor.texts['reason'], editor.diagnosis_input, editor.texts['plan']):
            assert widget.winfo_ismapped()
            assert widget.winfo_rooty()+widget.winfo_height() <= bottom
        editor.texts['reason'].insert('1.0', 'Motivo de demostración')
        editor.texts['plan'].insert('1.0', 'Indicaciones sintéticas')
        editor.diagnosis_var.set('Impresión de prueba')
        review = editor.finish()
        assert editor.model.data['diagnoses'][0]['name'] == 'Impresión de prueba'
        assert not editor.model.problems()
        assert editor.diagnosis_var.get() == ''
        review.cancel()
        editor.save()
        assert editor.record['status'] == 'Borrador'


def test_resize_theme_and_collapsed_notes_preserve_capture_and_focus(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        app.geometry('1366x768')
        editor.goto_issue('subjective')
        text = editor.texts['subjective']
        text.insert('1.0', 'Relato sintético completo sin reinterpretar.')
        text.focus_force()
        text.mark_set('insert', '1.9')
        text.tag_add('sel', '1.1', '1.7')
        app.update()
        before = (text.get('1.0', 'end-1c'), text.index('insert'), tuple(map(str, text.tag_ranges('sel'))))
        for size in ('940x640', '1366x768'):
            app.geometry(size)
            app.theme.apply(BUILTINS['Azul profundo'])
            app.update()
            assert app.focus_get() is text
            assert (text.get('1.0', 'end-1c'), text.index('insert'), tuple(map(str, text.tag_ranges('sel')))) == before
        editor.symptoms_section.toggle()
        settle(app)
        editor.save()
        snapshot = deepcopy(editor.record)
        assert snapshot['subjective'] == before[0]
        assert snapshot['editor_state']['sections']['subjective'] is False
        identifier = editor.record['id']
        app.pages.pop('consulta:'+identifier)
        editor.destroy()
        recovered = app.open_encounter(identifier)
        settle(app)
        assert not recovered.symptoms_section.opened
        assert before[0] in recovered.symptoms_section.summary.cget('text')
        recovered.goto_issue('subjective')
        app.update()
        assert app.focus_get() is recovered.texts['subjective']
