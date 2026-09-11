from copy import deepcopy
from threading import Event
from unittest.mock import patch
import pytest
from PIL import Image
from app.widgets import Collection
from tests.test_consultation_context import workspace
from tests.test_redesign import settle
from tests.test_redesign import services
from app.storage import DataError
from app.transfer import Transfer
from app.consultation_state import attention_time, ConsultationDraft
from app.editing_state import merge_draft, VersionConflict


@pytest.mark.desktop
def test_resume_current_allergies_and_search_focus_without_changing_note(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        note = editor.texts['subjective']
        note.insert('1.0', 'Nota local sin reemplazar')
        app.update()
        note.focus_force()
        note.mark_set('insert', '1.5')
        note.tag_add('sel', '1.1', '1.4')
        patient = app.clinic.save('patients', {**editor.patient, 'allergy_status': 'Alergias registradas',
            'allergy_records': [{'substance': 'Alergia sintética'}]}, editor.patient['revision'])
        app.show('Pacientes')
        app.show('consulta:'+editor.record['id'])
        assert 'Alergia sintética' in editor.allergy_label.cget('text')
        assert note.get('1.0', 'end-1c') == 'Nota local sin reemplazar'
        assert note.index('insert') == '1.5'
        note.focus_force()
        note.event_generate('<Control-k>')
        app.update()
        assert app.focus_get() is app.pages['Pacientes'].search_input
        app.focus_get().insert('end', 'Busqueda')
        assert note.get('1.0', 'end-1c') == 'Nota local sin reemplazar'


@pytest.mark.desktop
def test_shared_collection_repeated_add_and_stable_edit_identity(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        collection = Collection(editor, app, 'Productos', [('name', 'Medicamento', None)],
                                [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}])
        collection.new()
        collection.form.vars['name'].set('Captura pendiente')
        with patch('app.widgets.messagebox.askyesno', side_effect=AssertionError('Añadir debe enfocar')):
            collection.new()
        assert collection.form.vars['name'].get() == 'Captura pendiente'
        collection.cancel()
        collection.tree.selection_set('b')
        collection.edit()
        collection.form.vars['name'].set('B editado')
        collection.rows.reverse()
        collection.refresh()
        collection.confirm()
        assert {r['id']: r['name'] for r in collection.rows} == {'a': 'A', 'b': 'B editado'}


@pytest.mark.desktop
def test_copy_finishes_after_generation_change_and_retries_only_failures(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        source = tmp_path/'prueba.png'
        Image.new('RGB', (20, 20), 'white').save(source)
        capture = editor.open_tool('documents')
        panel = capture.panel
        app.update()
        assert not panel.library.winfo_ismapped()
        assert panel.empty_library.winfo_ismapped()
        panel.add_paths([str(source), str(tmp_path/'ausente.png')])
        release = Event()
        original = app.attachments.add
        def blocked(*args, **kwargs):
            assert release.wait(5)
            return original(*args, **kwargs)
        with patch.object(app.attachments, 'add', blocked):
            panel.start()
            app.session_generation += 1
            release.set()
            settle(app)
        assert not panel.busy
        assert panel.queue[0]['status'] == 'Guardado'
        assert panel.queue[1]['status'] != 'Guardado'
        first_id = panel.queue[0]['attachment_id']
        Image.new('RGB', (21, 20), 'black').save(tmp_path/'ausente.png')
        panel.start()
        settle(app)
        assert len(app.attachments.list(**panel.target)) == 2
        assert panel.queue[0]['attachment_id'] == first_id
        assert panel.library.winfo_ismapped()
        panel.tree.selection_set(first_id)
        panel.selection_changed()
        assert panel.document_actions['Archivar / restaurar'].cget('text') == 'Archivar documento'
        capture.close()


def test_attend_and_finalization_relationships_are_atomic_and_idempotent(services):
    store, auth, clinic, care, attachments = services
    patient = clinic.save('patients', {'name': 'Homónimo de prueba'})
    other = clinic.save('patients', {'name': 'Homónimo de prueba'})
    appointment = clinic.save('appointments', {'patient_id': patient['id'], 'due_at': '2026-09-10T10:15:23-06:00', 'status': 'Programada'})
    encounter = clinic.attend(appointment['id'])
    assert clinic.attend(appointment['id'])['id'] == encounter['id']
    assert len(clinic.list('encounters')) == 1
    assert store.read(f"data/appointments/{appointment['id']}.json")['status'] == 'En consulta'
    final = {**encounter, 'status': 'Finalizada', 'reason': 'Prueba', 'assessment': 'Prueba', 'plan': 'Prueba', 'followup': {'date': '2026-10-02'}}
    with patch.object(store, 'transaction', side_effect=OSError('Disco lleno simulado')):
        with pytest.raises(OSError):
            clinic.save('encounters', final, encounter['revision'])
    assert not clinic.list('followups')
    assert store.read(f"data/appointments/{appointment['id']}.json")['status'] == 'En consulta'
    saved = clinic.save('encounters', final, encounter['revision'])
    with pytest.raises(DataError):
        clinic.save('encounters', final, encounter['revision'])
    assert clinic.attend(appointment['id'])['id'] == saved['id']
    assert store.read(f"data/appointments/{appointment['id']}.json")['status'] == 'En consulta'
    assert not clinic.list('followups')
    assert saved['followup']['date'] == '2026-10-02'
    assert saved['patient_id'] == patient['id'] != other['id']
    assert saved['doctor_id'] == auth.current['id']


def test_temporal_semantics_and_three_way_conflict(services):
    store, auth, clinic, care, attachments = services
    stamp = '2026-09-10T10:15:23-06:00'
    assert attention_time({'date': '10/09/2026', 'time': '10:15'}, stamp) == stamp
    assert attention_time({'date': '11/09/2026', 'time': '10:30'}, stamp) == '2026-09-11T10:30:00-06:00'
    patient = clinic.save('patients', {'name': 'Prueba'})
    base = clinic.save('encounters', {'patient_id': patient['id'], 'status': 'Borrador', 'attended_at': stamp, 'reason': 'Base'})
    remote = clinic.save('encounters', {**base, 'reason': 'Remoto', 'plan': 'Plan remoto'}, base['revision'])
    local = {**base, 'reason': 'Local', 'subjective': 'Nota local'}
    with pytest.raises(VersionConflict) as error:
        clinic.save('encounters', local, base['revision'])
    merged, conflicts = merge_draft(base, local, error.value.current)
    assert set(conflicts) == {'reason'}
    assert merged['plan'] == 'Plan remoto' and merged['subjective'] == 'Nota local'
    assert local['reason'] == 'Local'
    merged['reason'] = conflicts['reason']['local']
    saved = clinic.save('encounters', merged, remote['revision'])
    assert saved['attended_at'] == stamp and saved['reason'] == 'Local'


def test_import_mapping_mixed_rows_duplicates_failure_and_idempotent_retry(services, tmp_path):
    import csv
    store, auth, clinic, care, attachments = services
    transfer = Transfer(store, auth, clinic)
    clinic.save('patients', {'name': 'Ana Muñoz'})
    source = tmp_path/'pacientes.csv'
    with source.open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.writer(stream, delimiter=';')
        writer.writerows([['Nombre', 'Nacimiento', 'Correo'], ['María; Luz\nPrueba', '1980-01-02', ''],
                         ['Nombre inválido', '31/02/2020', 'invalido'], ['ANA MUNOZ', '', '']])
    parsed = transfer.read_csv(source, ';')
    preview = transfer.inspect_import(parsed, {'name': 'Nombre', 'birth_date': 'Nacimiento', 'email': 'Correo'})
    assert preview['rows'][0]['patient']['name'] == 'María; Luz\nPrueba'
    assert set(preview['rows'][1]['errors']) == {'birth_date', 'email'}
    assert preview['rows'][2]['duplicates']
    with pytest.raises(DataError):
        transfer.import_patients(preview, {2, 4})
    with patch.object(store, 'transaction', side_effect=OSError('Permiso denegado simulado')):
        with pytest.raises(OSError):
            transfer.import_patients(preview, {2, 4}, {4})
    assert len(clinic.list('patients')) == 1
    result = transfer.import_patients(preview, {2, 4}, {4})
    assert transfer.import_patients(preview, {2, 4}, {4}) == result
    assert len(clinic.list('patients')) == 3
    assert len({p['file_number'] for p in clinic.list('patients')}) == 3


def test_attachment_recovery_finds_committed_operation_without_original(services, tmp_path):
    store, auth, clinic, care, attachments = services
    draft = care.save_draft({})
    source = tmp_path/'source.png'
    Image.new('RGB', (20, 20), 'white').save(source)
    target = dict(patient_id=None, encounter_id=None, draft_id=draft['id'])
    queue = [{'id': 'pending-stable-id', 'path': str(source), 'category': 'Otro documento', 'status': 'Copiando'}]
    saved = attachments.add(source, **target, operation_id=queue[0]['id'])
    source.unlink()
    recovered = attachments.recover_queue(queue, **target)
    assert recovered[0]['status'] == 'Guardado'
    assert recovered[0]['attachment_id'] == saved['id']
    assert attachments.add(source, **target, operation_id=queue[0]['id'])['id'] == saved['id']
    queue[0]['id'] = 'other-pending'
    assert 'Original no disponible' in attachments.recover_queue(queue, **target)[0]['status']


@pytest.mark.desktop
def test_existing_temperature_conversion_both_directions_and_durable_units(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        editor.model.apply('vitals', 'take', {'at': '2026-09-10T10:15:23-06:00', 'values': {'temperature': {'value': '98.6', 'unit': '°F'}}})
        capture = editor.open_tool('vitals', 'take')
        for _ in range(8):
            capture.units['temperature'].set('°C')
            capture.convert('temperature')
            assert float(capture.values['temperature'].get()) == pytest.approx(37)
            capture.units['temperature'].set('°F')
            capture.convert('temperature')
            assert float(capture.values['temperature'].get()) == pytest.approx(98.6)
        capture.units['temperature'].set('°C')
        capture.convert('temperature')
        capture.apply()
        editor.save()
        saved = app.store.read(f"data/encounters/{editor.record['id']}.json")
        assert saved['vitals'][0]['values']['temperature']['unit'] == '°C'
        assert float(saved['vitals'][0]['values']['temperature']['value']) == pytest.approx(37)
        assert saved['vitals'][0]['at'].endswith('23-06:00')


@pytest.mark.desktop
def test_statistics_invalidates_on_filter_edit_and_labels_selected_doctor(tmp_path):
    from app.statistics_ui import StatisticsPage
    with workspace(tmp_path) as (app, editor, uid):
        other = app.auth.create_user('Otro doctor', 'otro', 'Sintetica-67890')
        page = StatisticsPage(app.content, app)
        settle(app)
        assert page.ready
        selected = next(name for name, identifier in page.doctors.items() if identifier == other)
        page.filters.vars['doctor'].set(selected)
        assert not page.ready and page.export_buttons[0].instate(['disabled'])
        page.refresh()
        page.filters.vars['type'].set('Cambio durante carga')
        settle(app)
        assert not page.ready
        page.refresh()
        settle(app)
        assert page.ready and page.latest['_scope']['doctor'] == selected
        from datetime import date, timedelta
        from app import statistics_ui
        next_day = date.today()+timedelta(days=1)
        class Tomorrow(date):
            @classmethod
            def today(cls):
                return next_day
        page.period.set('Hoy')
        with patch.object(statistics_ui, 'date', Tomorrow):
            page.refresh()
            settle(app)
            assert page.latest['_scope']['start'] == next_day.isoformat() == page.latest['_scope']['end']
        with patch.object(app, 'pdf_preview') as preview:
            page.pdf()
            assert preview.call_args.kwargs['doctor'] == selected
        page.destroy()


def test_annul_restore_permissions_history_and_statistics(services):
    store, auth, clinic, care, attachments = services
    actor = auth.current['id']
    other = auth.create_user('Otro doctor', 'otro', 'Sintetica-67890')
    patient = clinic.save('patients', {'name': 'Prueba'})
    visit = clinic.save('encounters', {'patient_id': patient['id'], 'status': 'Finalizada', 'attended_at': '2026-09-10T23:30:00-06:00',
        'reason': 'Prueba', 'assessment': 'Prueba', 'plan': 'Prueba'})
    clinic.archive('encounters', visit['id'], 'Anulación sintética', revision=visit['revision'])
    assert clinic.statistics('2026-09-10', '2026-09-10')['consultations'] == 0
    auth.login(other, 'Sintetica-67890')
    with pytest.raises(DataError):
        clinic.archive('encounters', visit['id'], 'Sin permiso', restore=True)
    auth.login(actor, 'Sintetica-12345')
    restored = clinic.archive('encounters', visit['id'], 'Restauración sintética', restore=True)
    assert restored['doctor_id'] == actor and restored['status'] == 'Finalizada'
    assert len(restored['addenda']) == 2
    assert clinic.statistics('2026-09-10', '2026-09-10')['consultations'] == 1


def test_patient_search_index_normalizes_words_and_invalidates_on_changes(services):
    store, auth, clinic, care, attachments = services
    patient = clinic.save('patients', {'name': 'Ana María Muñoz', 'phone': '5555'})
    rows, count, page = clinic.search_patients(' MUNOZ   ANA 5555 ')
    assert count == 1 and rows[0]['id'] == patient['id']
    rows[0]['name'] = 'No mutar el índice'
    assert clinic.search_patients('ana')[0][0]['name'] == patient['name']
    clinic.save('patients', {**patient, 'name': 'Nombre actualizado'}, patient['revision'])
    assert clinic.search_patients('ana')[1] == 0
    assert clinic.search_patients('actualizado')[1] == 1


def test_linked_encounter_patient_and_relations_cannot_be_reassigned(services):
    store, auth, clinic, care, attachments = services
    patient = clinic.save('patients', {'name': 'Paciente original'})
    other = clinic.save('patients', {'name': 'Otro paciente'})
    appointment = clinic.save('appointments', {'patient_id': patient['id'], 'due_at': '2026-09-10T10:00:00-06:00', 'status': 'Programada'})
    visit = clinic.attend(appointment['id'])
    linked = store.read(f"data/appointments/{appointment['id']}.json")
    for kind, row in [('encounters', visit), ('appointments', linked)]:
        with pytest.raises(DataError, match='paciente original'):
            clinic.save(kind, {**row, 'patient_id': other['id']}, row['revision'])
        assert store.read(f"data/{kind}/{row['id']}.json") == row
    with pytest.raises(DataError, match='atención original'):
        clinic.save('appointments', {**linked, 'encounter_id': None}, linked['revision'])


@pytest.mark.desktop
def test_application_lock_hides_capture_and_reconciles_copy(tmp_path):
    with workspace(tmp_path) as (app, editor, uid):
        source = tmp_path/'lock.png'
        Image.new('RGB', (20, 20), 'white').save(source)
        capture = editor.open_tool('documents')
        panel = capture.panel
        panel.add_paths([str(source)])
        release = Event()
        original = app.attachments.add
        def blocked(*args, **kwargs):
            assert release.wait(5)
            return original(*args, **kwargs)
        with patch.object(app.attachments, 'add', blocked):
            panel.start()
            app.lock_session()
            assert app.state() == 'withdrawn' and capture.state() == 'withdrawn'
            release.set()
            settle(app)
        assert not panel.busy
        assert len(app.attachments.list(**panel.target)) == 1
        assert app.locked and app.state() == 'withdrawn'
        # Reanudación programática de la sesión sintética, sin automatizar el diálogo de autenticación.
        for window in app.winfo_children():
            if isinstance(window, __import__('tkinter').Toplevel) and window is not capture:
                window.destroy()
        app.locked = False
        app.deiconify()
        capture.deiconify()
        app.after(160, app.quit)
        app.mainloop()
        assert not panel.busy and panel.queue[0]['status'] == 'Guardado'
        capture.close()


@pytest.mark.desktop
def test_first_file_selection_is_durable_and_missing_source_is_reported(tmp_path):
    with workspace(tmp_path) as (app, visit, uid):
        editor = app.patient_editor()
        assert not editor.state['dirty']
        source = tmp_path/'only-file.png'
        Image.new('RGB', (20, 20), 'white').save(source)
        editor.attachments.add_paths([str(source)])
        assert editor.state['dirty']
        editor.save()
        identifier = editor.draft_id
        editor.state['dirty'] = False
        editor.destroy()
        app.pages.pop('alta:'+identifier)
        source.unlink()
        recovered = app.patient_editor(draft=app.care.drafts()[0])
        assert len(recovered.attachments.queue) == 1
        assert 'Original no disponible' in recovered.attachments.queue[0]['status']
        recovered.state['dirty'] = False


@pytest.mark.desktop
def test_day_rollover_keeps_current_patient_and_retired_routes_unavailable(tmp_path):
    from datetime import date, timedelta
    from app import main_window
    with workspace(tmp_path) as (app, visit, uid):
        app.show('Pacientes')
        page = app.pages['Pacientes']
        page.search_input.insert(0, 'Paciente')
        next_day = date.today()+timedelta(days=1)
        class Tomorrow(date):
            @classmethod
            def today(cls):
                return next_day
        with patch.object(main_window, 'date', Tomorrow):
            app.check_day()
            settle(app)
            assert app.day_key == next_day
        assert page.search_input.get() == 'Paciente'
        for retired in ('Agenda', 'Seguimientos'):
            with pytest.raises(ValueError):
                app.show(retired)
        assert app.current_page == 'Pacientes'


@pytest.mark.desktop
def test_document_buffer_recovery_keeps_base_revision_and_requires_conflict_choice(tmp_path):
    from tests.test_consultation_context import descendants
    from tkinter import ttk
    with workspace(tmp_path) as (app, editor, uid):
        source = tmp_path/'metadata.png'
        Image.new('RGB', (20, 20), 'white').save(source)
        row = app.attachments.add(source, editor.patient['id'], editor.record['id'])
        capture = editor.open_tool('documents')
        capture.edit_details(row['id'])
        capture.details_form.inputs['notes'].insert('1.0', 'Mi nota documental')
        capture.changed()
        capture.defer()
        app.attachments.update(row['id'], {'notes': 'Nota remota'}, row['revision'])
        capture = editor.open_tool('documents')
        assert capture.metadata_row['revision'] == row['revision']
        capture.apply_details()
        assert capture.apply_button.cget('text') == 'Revisar diferencias'
        window = capture.review_metadata_conflict()
        assert not getattr(app, 'active_capture', None)
        assert app.attachments.get(row['id'])['notes'] == 'Nota remota'
        choices = [w for w in descendants(window) if isinstance(w, ttk.Combobox)]
        assert choices
        for choice in choices:
            choice.set('Conservar mi captura')
        next(w for w in descendants(window) if isinstance(w, ttk.Button) and w.cget('text') == 'Combinar y guardar').invoke()
        assert app.attachments.get(row['id'])['notes'] == 'Mi nota documental', [w.cget('text') for w in descendants(window) if isinstance(w, ttk.Label)] if window.winfo_exists() else 'Ventana cerrada'
        assert not any(p['kind'] == 'document_metadata' for p in editor.model.pending.values())


@pytest.mark.desktop
def test_import_ui_mapping_preview_and_commit_and_bounded_views(tmp_path):
    from app.import_ui import ImportWindow
    with workspace(tmp_path) as (app, editor, uid):
        path = tmp_path/'pacientes.csv'
        path.write_text('Nombre,Nacimiento\nPersona importada,1980-01-02\nFila inválida,31/02/2020\n', encoding='utf-8-sig')
        window = ImportWindow(app)
        with patch('app.import_ui.filedialog.askopenfilename', return_value=str(path)):
            window.choose()
        window.mapping.vars['name'].set('Nombre')
        window.mapping.vars['birth_date'].set('Nacimiento')
        window.inspect()
        assert window.selected == {2}
        window.import_selected()
        settle(app)
        assert len(app.clinic.list('patients')) == 2
        window.close()
        for i in range(10):
            patient = app.clinic.save('patients', {'name': f'Paciente de caché {i}'})
            app.patient_record(patient['id'])
            settle(app)
        assert len([key for key in app.pages if ':' in key]) <= 8
        assert all(widget.winfo_exists() for widget, _, _ in app.editors)
