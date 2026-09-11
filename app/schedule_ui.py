"""Agenda con selección explícita y vínculo durable entre cita y consulta."""
from datetime import date
import tkinter as tk
from tkinter import ttk
from app.widgets import DateField, Form
from app.clinical_models import display_date, age_label
from app.consultation_state import attention_time
from app.consultation_tools import action, fit_window
from app.components import ScrollFrame
from app.storage import DataError


class SchedulePage(ttk.Frame):
    def __init__(self, parent, app, kind):
        super().__init__(parent)
        self.app, self.kind, self.ticket = app, kind, 0
        self.rows = {}
        app.heading(self, 'Agenda' if kind == 'appointments' else 'Seguimientos', 'Asignados al doctor activo · el seguimiento sin hora es una tarea por fecha.')
        bar = ttk.Frame(self)
        bar.pack(fill='x')
        self.period = tk.StringVar(value='Hoy')
        selector = ttk.Combobox(bar, textvariable=self.period, values=['Hoy', 'Periodo', 'Todos'], state='readonly', width=12)
        selector.pack(side='left')
        selector.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        self.start = DateField(bar, app.theme, date.today().isoformat())
        self.start.pack(side='left', padx=6)
        self.end = DateField(bar, app.theme, date.today().isoformat())
        self.end.pack(side='left', padx=6)
        action(bar, app, 'Filtrar', self.refresh).pack(side='left')
        self.tree = app.table(self, {'date': 'Fecha / hora', 'patient': 'Paciente · expediente', 'reason': 'Motivo', 'status': 'Estado'})
        self.tree.bind('<Double-1>', lambda e: self.edit_selected())
        self.tree.bind('<Return>', lambda e: self.edit_selected())
        footer = ttk.Frame(self)
        footer.pack(side='bottom', fill='x', before=self.tree.master)
        action(footer, app, 'Nueva cita' if kind == 'appointments' else 'Nuevo seguimiento', self.editor, primary=True).pack(side='left')
        self.edit_button = action(footer, app, 'Editar / reprogramar', self.edit_selected)
        self.edit_button.pack(side='left', padx=8)
        self.attend_button = None
        if kind == 'appointments':
            self.attend_button = action(footer, app, 'Atender / abrir consulta', self.attend)
            self.attend_button.pack(side='left')
        self.notice = ttk.Label(self, style='Subtitle.TLabel', wraplength=800)
        self.notice.pack(side='bottom', fill='x', pady=8, before=self.tree.master)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self.selection_changed())
        self.selection_changed()

    def selected(self):
        return self.rows.get(self.tree.selection()[0]) if self.tree.selection() else None

    def selection_changed(self):
        row = self.selected()
        self.edit_button.state(['!disabled'] if row else ['disabled'])
        if self.attend_button:
            allowed = row and (row.get('encounter_id') or row['status'] not in ('Atendida', 'Cancelada', 'No asistió'))
            self.attend_button.state(['!disabled'] if allowed else ['disabled'])

    def refresh(self):
        self.ticket += 1
        ticket = self.ticket
        mode = self.period.get()
        if mode == 'Hoy':
            start = end = date.today().isoformat()
            self.start.var.set(display_date(start))
            self.end.var.set(display_date(end))
        else:
            start, end = self.start.get(), self.end.get()
        if mode != 'Todos' and (not start or not end or start > end):
            self.notice.configure(text='Revisa el periodo: inicio y fin deben estar en orden.')
            return
        actor = self.app.auth.require()['id']
        def work():
            patients = {p['id']: p for p in self.app.clinic.list('patients', True)}
            rows = [r for r in self.app.clinic.list(self.kind) if r['doctor_id'] == actor and
                    (mode == 'Todos' or start <= r['due_at'][:10] <= end)]
            return patients, sorted(rows, key=lambda r: r['due_at'])
        def done(result):
            if not self.winfo_exists() or ticket != self.ticket:
                return
            patients, rows = result
            selected, position = self.tree.selection(), self.tree.yview()[0]
            self.rows = {r['id']: r for r in rows}
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                patient = patients.get(row['patient_id'], {})
                self.tree.insert('', 'end', iid=row['id'], values=(display_date(row['due_at'])+(' · sin hora' if len(row['due_at']) == 10 else ''),
                    patient.get('name', 'Paciente')+' · '+patient.get('file_number', ''), row.get('reason', ''), row['status']))
            self.tree.selection_set([key for key in selected if key in self.rows])
            self.tree.yview_moveto(position)
            self.selection_changed()
            self.notice.configure(text=f'{len(rows)} registros · {mode}' if rows else 'No hay registros en este periodo. Puedes crear uno o elegir Todos.')
        self.app.background(work, done)

    def edit_selected(self):
        if self.selected():
            self.editor(self.selected())

    def attend(self):
        row = self.selected()
        if row:
            self.app.guard(lambda: self.app.attend_appointment(row['id']))

    def editor(self, record=None, patient=None):
        record = record or {}
        win = self.app.window(('Editar ' if record else 'Nueva ')+('cita' if self.kind == 'appointments' else 'tarea de seguimiento'))
        fit_window(win, self.app, 660, 580)
        footer = ttk.Frame(win, padding=12)
        footer.pack(side='bottom', fill='x')
        body = ScrollFrame(win)
        body.pack(fill='both', expand=True)
        patients = self.app.clinic.list('patients')
        names = {p['file_number']+' · '+p['name']+' · '+age_label(p): p['id'] for p in patients}
        chosen = tk.StringVar(value=next((n for n, pid in names.items() if pid == (patient or {}).get('id', record.get('patient_id'))), ''))
        ttk.Label(body.body, text='Paciente · selección obligatoria', style='Subtitle.TLabel').pack(anchor='w', pady=8)
        picker = ttk.Combobox(body.body, textvariable=chosen, values=list(names), state='readonly')
        picker.pack(fill='x')
        if record.get('encounter_id'):
            picker.state(['disabled'])
            ttk.Label(body.body, text='Paciente de la consulta vinculada. Puedes reprogramar la fecha y actualizar el estado.', style='Subtitle.TLabel', wraplength=550).pack(fill='x', pady=6)
        def created(created_patient):
            self.app.show('Agenda' if self.kind == 'appointments' else 'Seguimientos')
            self.editor(record, created_patient)
        if not record.get('encounter_id'):
            action(body.body, self.app, 'Registrar paciente', lambda: (win.destroy(), self.app.patient_editor(on_created=created))).pack(anchor='w', pady=6)
        due = record.get('due_at', date.today().isoformat())
        statuses = ['Programada', 'Confirmada', 'En espera', 'En consulta', 'Atendida', 'Cancelada', 'No asistió'] if self.kind == 'appointments' else ['Pendiente', 'Completado', 'Cancelado']
        form = Form(body.body, [('date', 'Fecha', 'date'), ('time', 'Hora · HH:MM'+(' · opcional' if self.kind == 'followups' else ''), None),
            ('reason', 'Motivo', 'text'), ('status', 'Estado', statuses)],
            {'date': due[:10], 'time': due[11:16], 'reason': record.get('reason', ''), 'status': record.get('status', statuses[0])}, theme=self.app.theme)
        form.pack(fill='x', pady=8)
        error = ttk.Label(footer, style='error.TLabel', wraplength=600)
        error.pack(fill='x')
        def save():
            try:
                if chosen.get() not in names:
                    picker.focus_set()
                    raise DataError('Selecciona explícitamente al paciente de esta cita.')
                fields = form.values()
                timestamp = fields['date'] if self.kind == 'followups' and not fields['time'].strip() else attention_time(fields, record.get('due_at', ''))
                self.app.clinic.save(self.kind, {**record, 'patient_id': names[chosen.get()], 'due_at': timestamp,
                    'reason': fields['reason'], 'status': fields['status']}, record.get('revision'))
                win.destroy()
                self.refresh()
            except (ValueError, OSError) as exc:
                error.configure(text=str(exc))
        action(footer, self.app, 'Guardar', save, primary=True).pack(side='right')
        action(footer, self.app, 'Cancelar', win.destroy).pack(side='right', padx=8)
        self.app.theme._walk(win)
        picker.focus_set()
