"""Alcance explícito de exportaciones de pacientes."""
import os
import tkinter as tk
from tkinter import ttk, filedialog
from pathlib import Path
from app.consultation_tools import action, fit_window


def export_patients(app, filtered=None, selected=None):
    win = app.window('Exportar pacientes · elegir alcance')
    fit_window(win, app, 660, 420)
    body = ttk.Frame(win, padding=18)
    body.pack(fill='both', expand=True)
    choices = {'Todos los pacientes activos': None}
    if filtered is not None:
        choices['Resultado filtrado'] = list(filtered)
    if selected:
        choices['Pacientes seleccionados'] = list(selected)
    mode = tk.StringVar(value='Pacientes seleccionados' if selected else 'Resultado filtrado' if filtered is not None else 'Todos los pacientes activos')
    count = ttk.Label(body, style='Section.TLabel')
    def update():
        identifiers = choices[mode.get()]
        total = len(identifiers) if identifiers is not None else app.clinic.search_patients()[1]
        count.configure(text=f'{total} pacientes · {mode.get()}')
    for label in choices:
        ttk.Radiobutton(body, text=label, value=label, variable=mode, command=update).pack(anchor='w', pady=5)
    count.pack(fill='x', pady=14)
    update()
    ttk.Label(body, text='CSV incluye identidad y contacto. JSON conserva los datos estructurados del paciente. Para consultas y archivos usa Exportar expediente desde Documentos.', wraplength=590).pack(fill='x', pady=8)
    notice = ttk.Label(body, wraplength=590, style='Subtitle.TLabel')
    notice.pack(fill='x')
    folder_button = action(body, app, 'Abrir carpeta', lambda: None)
    def run():
        destination = filedialog.asksaveasfilename(parent=win, defaultextension='.csv', initialfile='pacientes.csv', filetypes=[('Pacientes CSV', '*.csv'), ('Pacientes JSON', '*.json')])
        if not destination:
            return
        identifiers = choices[mode.get()]
        scope = mode.get()
        button.state(['disabled'])
        notice.configure(text='Generando '+scope.lower()+'…')
        def work():
            try:
                return app.transfer.export_patients(destination, identifiers)
            except (ValueError, OSError) as exc:
                return exc
        def done(result):
            if not win.winfo_exists():
                return
            button.state(['!disabled'])
            if isinstance(result, Exception):
                notice.configure(text='No se pudo guardar el archivo. Tus opciones se conservan; elige otro destino o reintenta.')
            else:
                notice.configure(text=scope+' exportado en '+destination)
                folder_button.configure(command=lambda: os.startfile(str(Path(destination).parent)))
                folder_button.pack(anchor='w', pady=6)
        app.background(work, done)
    button = action(body, app, 'Elegir destino y exportar', run, primary=True)
    button.pack(side='bottom', anchor='e', pady=10)
    app.theme._walk(win)
    return win
