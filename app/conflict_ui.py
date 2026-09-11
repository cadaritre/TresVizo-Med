"""Resolución revisable de cambios concurrentes; no sustituye captura al fallar."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
from app.components import ScrollFrame
from app.consultation_tools import action, fit_window
from app.editing_state import merge_draft
from app.storage import atomic_json

FIELD_NAMES = {'name': 'Nombre', 'reason': 'Motivo', 'subjective': 'Síntomas y evolución', 'objective': 'Exploración',
    'assessment': 'Impresión diagnóstica', 'assessment_notes': 'Valoración', 'plan': 'Plan', 'prescriptions': 'Tratamientos',
    'vitals': 'Signos vitales', 'diagnoses': 'Diagnósticos', 'study_orders': 'Estudios', 'followup': 'Seguimiento',
    'attended_at': 'Fecha de atención', 'notes': 'Descripción', 'title': 'Título', 'category': 'Categoría',
    'document_date': 'Fecha del documento', 'editor_state': 'Capturas pendientes', 'birth_date': 'Nacimiento',
    'phone': 'Teléfono', 'email': 'Correo', 'allergy_status': 'Estado de alergias', 'allergy_records': 'Alergias',
    'medication_records': 'Medicación habitual', 'dose': 'Dosis', 'frequency': 'Frecuencia', 'route': 'Vía', 'duration': 'Duración'}


def readable_value(key, value):
    if isinstance(value, list):
        if key == 'vitals':
            from app.consultation_state import measurement_summary
            return '\n\n'.join(measurement_summary(row) for row in value)
        if key in ('prescriptions', 'medication_records'):
            from app.clinical_models import medication_text
            return '\n'.join(medication_text(row) for row in value)
        return '\n'.join(readable_value('', item) for item in value) or 'Sin registros'
    if isinstance(value, dict):
        return '\n'.join(FIELD_NAMES.get(field, field.replace('_', ' ').capitalize())+': '+readable_value(field, item)
                         for field, item in value.items() if field not in ('id', 'revision', 'schema_version', 'generation', 'selected_take'))
    return str(value) if value not in (None, '') else 'No registrado'


def review_conflict(app, base, local, remote, apply):
    win = app.window('Revisar cambios antes de guardar')
    fit_window(win, app, 820, 680)
    footer = ttk.Frame(win, padding=12)
    footer.pack(side='bottom', fill='x')
    body = ScrollFrame(win)
    body.pack(fill='both', expand=True)
    merged, conflicts = merge_draft(base, local, remote)
    ttk.Label(body.body, text='Tu captura se conserva. Revisa los campos modificados en ambas versiones. Los cambios independientes se combinarán.', wraplength=740).pack(fill='x', pady=10)
    ttk.Label(body.body, text=f"Versión guardada: {remote.get('revision')} · modificada {remote.get('updated_at', '')}", style='Subtitle.TLabel').pack(fill='x')
    choices = {}
    for key, values in conflicts.items():
        ttk.Label(body.body, text=FIELD_NAMES.get(key, key.replace('_', ' ').capitalize()), style='Section.TLabel').pack(anchor='w', pady=(14, 4))
        for label, value in [('Mi captura', values['local']), ('Guardado', values['remote'])]:
            text = readable_value(key, value)
            ttk.Label(body.body, text=label+': '+text, wraplength=720, justify='left').pack(fill='x', pady=3)
        choices[key] = tk.StringVar(value='Elegir versión')
        ttk.Combobox(body.body, textvariable=choices[key], values=['Conservar mi captura', 'Usar guardado'], state='readonly').pack(fill='x')
    status = ttk.Label(footer, style='error.TLabel', wraplength=700)
    status.pack(fill='x')
    def confirm():
        if any(choice.get() == 'Elegir versión' for choice in choices.values()):
            status.configure(text='Elige una versión para cada campo en conflicto.')
            return
        for key, choice in choices.items():
            merged[key] = conflicts[key]['local' if choice.get() == 'Conservar mi captura' else 'remote']
        try:
            apply(merged, remote)
            win.destroy()
        except (ValueError, OSError) as exc:
            status.configure(text=str(exc))
    def export():
        path = filedialog.asksaveasfilename(parent=win, defaultextension='.json', initialfile='captura-local-recuperacion.json')
        if path:
            atomic_json(Path(path), {'kind': 'local-edit-recovery', 'base': base, 'capture': local})
            status.configure(text='Copia local guardada en '+path)
    action(footer, app, 'Conservar copia de recuperación…', export).pack(side='left')
    action(footer, app, 'Seguir editando', win.destroy).pack(side='right', padx=8)
    allowed = remote.get('status') in (None, 'Borrador') and not remote.get('archived')
    button = action(footer, app, 'Combinar y guardar', confirm, primary=True)
    button.pack(side='right')
    if not allowed:
        button.state(['disabled'])
        status.configure(text='El registro guardado ya está cerrado o archivado. Conserva una copia de tu captura para revisar una corrección autorizada.')
    app.theme._walk(win)
    return win
