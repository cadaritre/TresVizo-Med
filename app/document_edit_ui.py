"""Edición documental con buffer privado recuperable y cierre explícito."""
from copy import deepcopy
import tkinter as tk
from tkinter import ttk
from app.components import ScrollFrame
from app.widgets import Form
from app.consultation_tools import action, fit_window
from app.editing_state import VersionConflict


def edit_document(panel, row, on_apply=lambda: None):
    app = panel.app
    key = 'document_metadata:'+row['id']
    saved = app.attachments.load_metadata_edits(**panel.target) or {}
    pending = saved.get(key, {})
    current = deepcopy(row)
    if pending.get('base'):
        row = deepcopy(pending['base'])
    if pending.get('revision'):
        row['revision'] = pending['revision']
    def clear_pending():
        with app.store.lock:
            buffers = app.attachments.load_metadata_edits(**panel.target) or {}
            buffers.pop(key, None)
            app.attachments.save_metadata_edits(buffers, **panel.target)
        on_apply()
    if row['revision'] != current['revision'] and pending.get('values'):
        from app.clinical_models import local_date
        values = deepcopy(pending['values'])
        try:
            values['document_date'] = local_date(values.get('document_date', ''))
        except ValueError:
            pass
        else:
            from app.conflict_ui import review_conflict
            def resolve(merged, remote):
                app.attachments.update(row['id'], merged, remote['revision'], values.get('reason', ''))
                clear_pending()
                if panel.winfo_exists():
                    panel.refresh()
            return review_conflict(app, row, {**row, **values}, current, resolve)
    existing = getattr(app, 'metadata_windows', {}).get(row['id'])
    if existing and existing.winfo_exists():
        existing.lift()
        return existing
    app.metadata_windows = getattr(app, 'metadata_windows', {})
    win = app.window('Detalles del documento · '+row['title'])
    app.metadata_windows[row['id']] = win
    fit_window(win, app, 720, 650)
    initial = saved.get(key, {}).get('values', row)
    state, timer = {'dirty': False}, [None]
    footer = ttk.Frame(win, padding=12)
    footer.pack(side='bottom', fill='x')
    scroll = ScrollFrame(win)
    scroll.pack(fill='both', expand=True)
    notice = ttk.Label(footer, style='Subtitle.TLabel', wraplength=650)
    notice.pack(fill='x')
    def save_buffer():
        with app.store.lock:
            buffers = app.attachments.load_metadata_edits(**panel.target) or {}
            buffers[key] = {'kind': 'document_metadata', 'id': row['id'], 'values': form.values(raw=True), 'revision': row['revision'], 'base': deepcopy(row)}
            app.attachments.save_metadata_edits(buffers, **panel.target)
        state['dirty'] = False
        notice.configure(text='Captura guardada para recuperación · todavía sin aplicar al documento.')
        return True
    def autosave():
        timer[0] = None
        try:
            save_buffer()
        except (ValueError, OSError):
            notice.configure(text='La captura sigue en memoria; no se pudo guardar en disco.')
    def changed():
        state['dirty'] = True
        if timer[0]:
            win.after_cancel(timer[0])
        timer[0] = win.after(800, autosave)
    form = Form(scroll.body, [('title', 'Título', None), ('category', 'Categoría', panel.categories), ('document_date', 'Fecha del documento', 'date'),
                             ('notes', 'Descripción', 'text'), ('reason', 'Motivo del cambio', None)], initial, changed, app.theme)
    form.pack(fill='x', padx=16, pady=10)
    baseline = deepcopy(form.values(raw=True)) if key not in saved else {k: row.get(k, '') for k in form.vars}
    resolution = ttk.Frame(footer)
    def clear_buffer():
        clear_pending()
    def close():
        if form.values(raw=True) != baseline or key in saved:
            resolution.pack(fill='x', pady=8)
        else:
            win.destroy()
    def discard():
        clear_buffer()
        state['dirty'] = False
        win.destroy()
    def keep():
        save_buffer()
        win.destroy()
    for label, command in [('Conservar pendiente', keep), ('Descartar captura', discard), ('Seguir editando', resolution.pack_forget)]:
        action(resolution, app, label, lambda fn=command: app.guard(fn)).pack(side='left', padx=4)
    def committed():
        clear_buffer()
        state['dirty'] = False
        win.destroy()
        if panel.winfo_exists():
            panel.refresh()
    def apply():
        try:
            values = form.values()
            app.attachments.update(row['id'], values, row['revision'], values.get('reason', ''))
            committed()
        except VersionConflict as conflict:
            from app.conflict_ui import review_conflict
            def resolve(merged, remote):
                app.attachments.update(row['id'], merged, remote['revision'], form.values().get('reason', ''))
                committed()
            review_conflict(app, row, {**row, **values}, conflict.current, resolve)
        except (ValueError, OSError) as exc:
            notice.configure(text=str(exc))
    action(footer, app, 'Aplicar cambios', apply, primary=True).pack(side='right')
    action(footer, app, 'Cancelar', close).pack(side='right', padx=8)
    app.editors.append((win, save_buffer, state))
    win.protocol('WM_DELETE_WINDOW', close)
    win.bind('<Escape>', lambda event: (close(), 'break')[1])
    def cleanup(event):
        if event.widget is win:
            if timer[0]:
                win.after_cancel(timer[0])
            app.metadata_windows.pop(row['id'], None)
    win.bind('<Destroy>', cleanup, add='+')
    app.theme._walk(win)
    form.inputs['title'].focus_set()
    return win
