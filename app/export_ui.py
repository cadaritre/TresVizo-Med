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
    ttk.Label(body, text='CSV incluye identidad y contacto. JSON conserva los datos del paciente. También puedes exportar consultas en CSV desde Exportar y respaldar; los archivos adjuntos se incluyen al exportar el expediente.', wraplength=590).pack(fill='x', pady=8)
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


def export_consultations(app, identifiers=None):
    from app.widgets import DateField
    from app.storage import DataError
    win = app.window('Exportar consultas · CSV')
    fit_window(win, app, 700, 610)
    body = ttk.Frame(win, padding=20)
    body.pack(fill='both', expand=True)
    ttk.Label(body, text='Consultas con sus datos clínicos', style='Section.TLabel').pack(anchor='w')
    ttk.Label(body, text='Una fila por consulta. Incluye paciente, médico, nota, signos vitales, diagnósticos y medicamentos con dosis y frecuencia. No incluye archivos adjuntos.', wraplength=620).pack(fill='x', pady=12)
    period = ttk.Frame(body)
    period.pack(fill='x')
    dates = []
    for label in ('Desde · opcional', 'Hasta · opcional'):
        box = ttk.Frame(period)
        box.pack(side='left', fill='x', expand=True, padx=(0, 12))
        ttk.Label(box, text=label).pack(anchor='w')
        widget = DateField(box, app.theme)
        widget.pack(fill='x', pady=4)
        dates.append(widget)
    own = tk.BooleanVar(value=False)
    drafts = tk.BooleanVar(value=False)
    ttk.Checkbutton(body, text='Solo consultas a mi cargo', variable=own).pack(anchor='w', pady=(14, 5))
    ttk.Checkbutton(body, text='Incluir mis borradores guardados', variable=drafts).pack(anchor='w', pady=5)
    ttk.Label(body, text='Se excluyen consultas archivadas y borradores de otros médicos. Las columnas terminadas en _json conservan todas las mediciones, tratamientos y adendas.', wraplength=620, style='Subtitle.TLabel').pack(fill='x', pady=12)
    count = ttk.Label(body, style='Section.TLabel')
    count.pack(anchor='w', pady=8)
    notice = ttk.Label(body, wraplength=620)
    notice.pack(fill='x', pady=8)
    def filters():
        return dict(start=dates[0].get(), end=dates[1].get(),
                    doctor_id=app.auth.current['id'] if own.get() else '',
                    include_drafts=drafts.get(), identifiers=identifiers)
    def update(*args):
        try:
            total = len(app.transfer.consultation_rows(**filters()))
            count.configure(text=f'{total} consultas para exportar')
            notice.configure(text='')
            button.state(['!disabled'] if total else ['disabled'])
        except (DataError, ValueError) as exc:
            count.configure(text='Revisa el periodo')
            notice.configure(text=str(exc))
            button.state(['disabled'])
    def run():
        chosen = filters()
        destination = filedialog.asksaveasfilename(parent=win, defaultextension='.csv', initialfile='consultas.csv', filetypes=[('Consultas CSV', '*.csv')])
        if not destination:
            return
        button.state(['disabled'])
        notice.configure(text='Exportando consultas…')
        def work():
            try:
                return app.transfer.export_consultations(destination, **chosen)
            except (ValueError, OSError) as exc:
                return exc
        def done(result):
            if not win.winfo_exists():
                return
            update()
            notice.configure(text=str(result) if isinstance(result, Exception) else f'{result} consultas exportadas en {destination}')
        app.background(work, done)
    button = action(body, app, 'Elegir destino y exportar CSV', lambda: app.guard(run), primary=True)
    button.pack(side='bottom', anchor='e', pady=10)
    for variable in (own, drafts, dates[0].var, dates[1].var):
        variable.trace_add('write', update)
    update()
    app.theme._walk(win)
    return win
