"""Consulta estructurada, captura de mediciones y evolución longitudinal."""
from copy import deepcopy
from datetime import datetime, date, timedelta
import uuid
import tkinter as tk
from tkinter import ttk, messagebox
from app.components import ScrollFrame
from app.widgets import wrap_actions, Form, Collection, DateField, text_editor
from app.clinical_models import VITALS, MED_FIELDS, validate_vitals, medication_text, encounter_sections, age_label, display_date
from app.services import now
from app.storage import DataError
from app.attachment_ui import AttachmentPanel
from app.consultation_state import ConsultationDraft, COLLECTIONS, CAPTURE_NAMES, measurement_summary
from app.consultation_tools import (action, DetailCapture, VitalsCapture, MedicationCapture,
                                    DocumentsCapture, HistoryCapture, ReuseCapture, ReviewCapture)
from app.widgets import Collapsible

MED_OPTIONS = {'dose_unit': ['mg', 'g', 'mcg', 'mL', 'tableta', 'cápsula', 'gota', 'UI', 'inhalación'],
               'route': ['Oral', 'Tópica', 'Inhalada', 'Intravenosa', 'Intramuscular', 'Subcutánea', 'Oftálmica', 'Ótica'],
               'frequency_kind': ['Cada N horas', 'Veces al día', 'Horarios', 'Pauta personalizada', 'Según necesidad'],
               'duration_unit': ['días', 'semanas', 'meses'], 'status': ['Activo', 'Suspendido', 'Completado'],
               'start': 'date', 'end': 'date', 'instructions': 'text', 'dose': 'number', 'duration': 'number', 'quantity': 'number'}

def medication_specs(app, catalog=None):
    catalog = app.care.catalog() if catalog is None else catalog
    return [(key, label, [r['name'] for r in catalog] if key == 'name' else MED_OPTIONS.get(key)) for key, label in MED_FIELDS]

class TrendPanel(ttk.Frame):
    def __init__(self, parent, app, patient_id, provisional=lambda: []):
        super().__init__(parent)
        self.app, self.patient_id, self.points = app, patient_id, []
        self.provisional = provisional
        ttk.Label(self, text='Evolución del paciente', style='Section.TLabel').pack(anchor='w', pady=8)
        controls = ttk.Frame(self)
        controls.pack(fill='x')
        self.keys = {'Presión arterial': 'blood_pressure', **{label: key for key, (label, _) in VITALS.items()}, 'IMC': 'bmi'}
        self.metric = tk.StringVar(value='Presión arterial')
        self.period = tk.StringVar(value='Un año')
        box = ttk.Combobox(controls, textvariable=self.metric, values=list(self.keys), state='readonly', width=24)
        box.pack(side='left')
        box.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        period = ttk.Combobox(controls, textvariable=self.period, values=['30 días', '90 días', 'Un año', 'Todo', 'Personalizado'], state='readonly', width=14)
        period.pack(side='left', padx=8)
        period.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Button(controls, text='Actualizar', command=self.refresh, style='Link.TButton').pack(side='left')
        self.range = ttk.Frame(self)
        self.start, self.end = DateField(self.range, app.theme), DateField(self.range, app.theme)
        ttk.Label(self.range, text='Desde').pack(side='left')
        self.start.pack(side='left', padx=6)
        ttk.Label(self.range, text='Hasta').pack(side='left')
        self.end.pack(side='left', padx=6)
        self.message = ttk.Label(self, style='Subtitle.TLabel', wraplength=700)
        self.message.pack(fill='x', pady=5)
        self.canvas = tk.Canvas(self, height=215, highlightthickness=0)
        self.canvas.pack(fill='x', pady=8)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.table = ttk.Treeview(self, columns=('at', 'metric', 'value', 'context'), show='headings', height=4)
        for key, label in [('at', 'Fecha y hora'), ('metric', 'Medición'), ('value', 'Valor exacto'), ('context', 'Contexto / origen')]:
            self.table.heading(key, text=label)
            self.table.column(key, width=140)
        self.table.pack(fill='x')
        self.table.bind('<Double-1>', self.open_source)
        app.theme.subscribe(self, lambda t: self.draw())
        self.refresh()

    def open_source(self, event=None):
        if self.table.selection():
            row = self.points[int(self.table.selection()[0])]
            if row.get('encounter_id'):
                self.app.open_encounter(row['encounter_id'])

    def refresh(self):
        self.request = getattr(self, 'request', 0)+1
        request = self.request
        key = self.keys[self.metric.get()]
        keys = ['systolic', 'diastolic'] if key == 'blood_pressure' else [key]
        self.message.configure(text='Cargando evolución…', style='Subtitle.TLabel')
        self.app.background(lambda: {k: self.app.care.evolution(self.patient_id, k) for k in keys},
                            lambda history: self.loaded(history, request))

    def loaded(self, history, request):
        if not self.winfo_exists() or request != self.request:
            return
        key = self.keys[self.metric.get()]
        keys = ['systolic', 'diastolic'] if key == 'blood_pressure' else [key]
        points = []
        for k in keys:
            for item in history[k]:
                points.append({**item, 'metric': k, 'provisional': False})
            for group in self.provisional():
                value = group.get('values', {}).get(k)
                if k == 'bmi' and group.get('bmi') is not None:
                    value = {'normalized_value': group['bmi'], 'normalized_unit': 'kg/m²'}
                if value:
                    points.append({'at': group['at'], 'metric': k, 'value': value['normalized_value'], 'unit': value['normalized_unit'],
                                   'context': group.get('context', ''), 'encounter_id': None, 'provisional': True})
        days = {'30 días': 30, '90 días': 90, 'Un año': 365}.get(self.period.get())
        start = (date.today()-timedelta(days=days)).isoformat() if days else ''
        end = ''
        self.range.pack_forget()
        if self.period.get() == 'Personalizado':
            self.range.pack(fill='x', pady=8, before=self.message)
            try:
                start, end = self.start.get(), self.end.get()
                if start and end and start > end:
                    raise ValueError('La fecha inicial debe ser anterior a la final.')
            except ValueError as exc:
                self.message.configure(text=str(exc), style='error.TLabel')
                return
        points = [p for p in points if (not start or p['at'][:10] >= start) and (not end or p['at'][:10] <= end)]
        self.points = sorted(points, key=lambda p: p['at'])
        self.table.delete(*self.table.get_children())
        for i, row in enumerate(self.points):
            label = 'IMC' if row['metric'] == 'bmi' else VITALS[row['metric']][0]
            context = ('Borrador · ' if row['provisional'] else '') + row['context']
            self.table.insert('', 'end', iid=str(i), values=(display_date(row['at']), label, f"{row['value']:.6g} {row['unit']}", context))
        self.message.configure(text='Sistólica y diastólica en series separadas. ' * (key == 'blood_pressure') + 'Los círculos vacíos pertenecen al borrador. Doble clic en una fila histórica para abrir su consulta.', style='Subtitle.TLabel')
        self.draw()

    def draw(self):
        if not hasattr(self, 'canvas'):
            return
        c, t = self.canvas, self.app.theme.tokens
        c.configure(background=t['surface'])
        c.delete('all')
        w = max(c.winfo_width(), 300)
        if not self.points:
            c.create_text(w/2, 90, text='Todavía no hay mediciones en este periodo.', fill=t['muted'], width=w-40)
            return
        numbers = [p['value'] for p in self.points]
        low, high = min(numbers), max(numbers)
        margin = max((high-low)*.12, 1)
        low, high = low-margin, high+margin
        stamps = [datetime.fromisoformat(p['at']).replace(tzinfo=None).timestamp() for p in self.points]
        span = max(1, max(stamps)-min(stamps))
        c.create_line(55, 25, 55, 163, w-18, 163, fill=t['separator'])
        for i in range(4):
            val = low+(high-low)*i/3
            y = 160-i*42
            c.create_text(48, y, text=f'{val:.1f}', anchor='e', fill=t['muted'], font=('Segoe UI', 9))
        c.create_text(58, 195, text=display_date(self.points[0]['at'][:10]), anchor='w', fill=t['muted'])
        c.create_text(w-18, 195, text=display_date(self.points[-1]['at'][:10])+' · '+self.points[-1]['unit'], anchor='e', fill=t['muted'])
        previous = {}
        for row, stamp in zip(self.points, stamps):
            x = 60+(w-90)*(stamp-min(stamps))/span if span > 1 else (w+40)/2
            y = 160-(row['value']-low)/(high-low)*126
            color = t['chart2'] if row['metric'] == 'diastolic' else t['chart1']
            series = (row['metric'], row['context'] if row['metric'] == 'glucose' else '', row['provisional'])
            last = previous.get(series)
            if last and not row['provisional']:
                c.create_line(*last, x, y, fill=color, width=2)
            item = c.create_oval(x-4, y-4, x+4, y+4, fill=t['surface'] if row['provisional'] else color, outline=color, width=2)
            c.tag_bind(item, '<Enter>', lambda e, r=row: self.app.status.set(display_date(r['at'])+f" · {r['value']:.6g} {r['unit']} · "+('Borrador' if r['provisional'] else 'Consulta finalizada')))
            previous[series] = (x, y)
        if self.keys[self.metric.get()] == 'blood_pressure':
            c.create_text(60, 10, text='● Sistólica', anchor='w', fill=t['chart1'])
            c.create_text(170, 10, text='● Diastólica', anchor='w', fill=t['chart2'])


class SummaryRows(ttk.Frame):
    def __init__(self, parent, app, edit=None, remove=None, edit_label='Editar'):
        super().__init__(parent)
        self.app, self.edit, self.remove = app, edit, remove
        self.edit_label = edit_label
        self.signature = None

    def render(self, rows, summary, empty='Sin registrar.'):
        signature = [(r['id'], summary(r)) for r in rows]
        if signature == self.signature:
            return
        self.signature = signature
        for child in self.winfo_children():
            child.destroy()
        if not rows:
            ttk.Label(self, text=empty, style='Subtitle.TLabel').pack(anchor='w', pady=4)
        for row, (_, text) in zip(rows, signature):
            line = ttk.Frame(self, padding=(10, 6), style='Card.TFrame')
            line.pack(fill='x', pady=3)
            actions = ttk.Frame(line, style='Card.TFrame')
            actions.pack(side='right', padx=(8, 0))
            if self.edit:
                action(actions, self.app, self.edit_label, lambda key=row['id']: self.edit(key), 'folder-open' if self.edit_label == 'Ver' else 'pencil').pack(side='left')
            if self.remove:
                action(actions, self.app, 'Quitar', lambda key=row['id']: self.remove(key)).pack(side='left', padx=(5, 0))
            label = ttk.Label(line, text=text, style='Card.TLabel', wraplength=720, justify='left')
            label.pack(side='left', fill='x', expand=True)
            line.bind('<Configure>', lambda e, w=label, a=actions: w.configure(wraplength=max(160, e.width-a.winfo_reqwidth()-40)))
        self.app.theme._walk(self)


class ConsultationEditor(ttk.Frame):
    def __init__(self, parent, app, patient, record):
        super().__init__(parent)
        self.app, self.patient, self.record = app, patient, deepcopy(record)
        self.model = ConsultationDraft(record)
        self.state = {'record': self.record, 'dirty': False}
        self.loading, self.timer, self.deadline = True, None, None
        self._catalog, self.document_rows, self.document_ticket = None, [], 0
        self.last_text = None
        top = ttk.Frame(self)
        top.pack(fill='x')
        action(top, app, '‹ Expediente', lambda: app.patient_record(patient['id'])).pack(side='right')
        title = self.patient_title = ttk.Label(top, text=patient['name'], style='Section.TLabel', wraplength=850)
        title.pack(side='left', fill='x', expand=True)
        top.bind('<Configure>', lambda e, label=title: label.configure(wraplength=max(260, e.width-170)))
        self.identity_label = ttk.Label(self, text=patient['file_number']+' · '+age_label(patient)+' · Responsable: '+app.auth.current['name'], style='Subtitle.TLabel', wraplength=1000)
        self.identity_label.pack(anchor='w', pady=(3, 0))
        context = ttk.Frame(self)
        context.pack(fill='x')
        self.context_label = ttk.Label(context, style='Subtitle.TLabel')
        self.context_label.pack(side='left', fill='x', expand=True)
        context.bind('<Configure>', lambda e: self.context_label.configure(wraplength=max(200, e.width-190)))
        action(context, app, 'Editar detalles', lambda: self.open_tool('header'), 'pencil').pack(side='left', padx=10, pady=3)
        allergy = ', '.join(r.get('substance', '') for r in patient.get('allergy_records', [])) or patient.get('allergies') or patient.get('allergy_status') or 'No interrogadas'
        self.allergy_label = ttk.Label(self, text='⚠ Alergias: '+allergy, style='warning.TLabel', wraplength=1000)
        self.allergy_label.pack(fill='x', pady=(2, 7))
        self.bind('<Configure>', lambda e: (self.allergy_label.configure(wraplength=max(220, e.width-24)),
                                           self.identity_label.configure(wraplength=max(220, e.width-24))), add='+')
        self.quick = ttk.Frame(self)
        self.quick.pack(fill='x', pady=(0, 6))
        self.quick_buttons = {}
        self.quick_labels = {'S': 'S · Subjetivo', 'O': 'O · Objetivo', 'A': 'A · Análisis', 'P': 'P · Plan'}
        for key, label in self.quick_labels.items():
            self.quick_buttons[key] = action(self.quick, app, label, lambda k=key: self.reveal_section(k))
        self.quick.bind('<Configure>', self.layout_quick)
        footer = self.footer = ttk.Frame(self, padding=(0, 8))
        footer.pack(side='bottom', fill='x')
        self.indicator = tk.StringVar(value='Borrador guardado')
        footer_actions = ttk.Frame(footer)
        footer_actions.pack(fill='x')
        self.save_button = action(footer_actions, app, 'Guardar borrador', self.save_feedback, 'save')
        self.save_button.pack(side='left')
        self.finish_button = action(footer_actions, app, 'Finalizar consulta', self.finish, primary=True)
        self.finish_button.pack(side='right')
        self.save_label = ttk.Label(footer, textvariable=self.indicator, style='Subtitle.TLabel', wraplength=440)
        self.save_label.pack(fill='x', pady=(4, 0))
        footer.bind('<Configure>', lambda e: self.save_label.configure(wraplength=max(160, e.width-12)))
        wrap_actions(footer_actions, [self.finish_button, self.save_button])
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill='both', expand=True)
        body = self.scroll.body
        self.pending_box = ttk.Frame(body)
        self.pending_box.pack(fill='x')
        self.pending_signature = None
        self.texts, self.soap = {}, {}
        descriptions = [('S', 'SUBJETIVO', 'Lo que refiere el paciente'),
                        ('O', 'OBJETIVO', 'Hallazgos y mediciones'),
                        ('A', 'ANÁLISIS', 'Valoración y diagnóstico'),
                        ('P', 'PLAN', 'Tratamiento e indicaciones')]
        self.soap_descriptions = {key: description for key, _, description in descriptions}
        for key, title, description in descriptions:
            panel = Collapsible(body, key+' — '+title,
                                opened=self.model.section_state.get(key, key == 'S'), changed=self.sections_changed)
            panel.pack(fill='x', pady=(0, 3))
            self.soap[key] = panel
        subjective, objective, analysis, plan = (self.soap[k].body for k in 'SOAP')
        self.note(subjective, 'reason', 'Motivo de consulta *', 1, 3)
        self.search_input = self.texts['reason']
        self.note(subjective, 'subjective', 'Síntomas y evolución', 2, 12)
        measurement_header = ttk.Frame(objective)
        measurement_header.pack(fill='x', pady=6)
        action(measurement_header, app, 'Añadir signos vitales', lambda: self.open_tool('vitals', str(uuid.uuid4())), 'activity').pack(side='left')
        action(measurement_header, app, 'Ver evolución', self.open_history).pack(side='left', padx=8)
        self.take_box = ttk.Frame(objective)
        self.take_box.pack(fill='x')
        self.take_choice = tk.StringVar()
        self.take_selector = ttk.Combobox(self.take_box, textvariable=self.take_choice, state='readonly')
        self.take_selector.bind('<<ComboboxSelected>>', self.select_take)
        self.take_summary = ttk.Label(self.take_box, wraplength=920, justify='left', style='Subtitle.TLabel')
        self.take_summary.pack(side='left', fill='x', expand=True, pady=6)
        self.take_edit = action(self.take_box, app, 'Editar toma', self.edit_take, 'pencil')
        self.take_box.bind('<Configure>', lambda e: self.take_summary.configure(wraplength=max(260, e.width-180)))
        self.exploration = Collapsible(objective, 'Registrar exploración', opened=bool(record.get('objective', '').strip()))
        self.exploration.pack(fill='x')
        self.note(self.exploration.body, 'objective', '', 2, 8)
        diagnosis_row = ttk.Frame(analysis)
        diagnosis_row.pack(fill='x', pady=6)
        self.diagnosis_var = tk.StringVar()
        self.diagnosis_input = ttk.Combobox(diagnosis_row, textvariable=self.diagnosis_var, values=[])
        self.diagnosis_input.pack(side='left', fill='x', expand=True)
        self.diagnosis_input.bind('<Return>', lambda e: (self.add_diagnosis(), 'break')[1])
        self.diagnosis_input.bind('<FocusIn>', self.diagnosis_suggestions)
        action(diagnosis_row, app, 'Añadir diagnóstico o impresión', self.add_diagnosis, 'plus').pack(side='left', padx=8)
        self.inline_id = str(uuid.uuid4())
        pending_diagnosis = next((p for p in self.model.pending.values() if p['kind'] == 'diagnosis' and p['id'] not in {r['id'] for r in self.model.data['diagnoses']}), None)
        if pending_diagnosis:
            self.inline_id = pending_diagnosis['id']
            self.diagnosis_var.set(pending_diagnosis['values'].get('name', ''))
        self.diagnosis_var.trace_add('write', self.diagnosis_changed)
        self.diagnosis_error = ttk.Label(analysis, style='error.TLabel')
        self.diagnoses = SummaryRows(analysis, app, lambda i: self.open_tool('diagnosis', i), lambda i: self.remove('diagnosis', i))
        self.diagnoses.pack(fill='x')
        if self.model.legacy_assessment:
            ttk.Label(analysis, text='Valoración heredada · conservada sin interpretar\n'+self.model.legacy_assessment, style='warning.TLabel', wraplength=920).pack(fill='x', pady=6)
        self.note(analysis, 'assessment_notes', 'Valoración clínica · notas complementarias', 2, 6)
        self.note(plan, 'plan', 'Escribir indicaciones *', 2, 10)
        med_header = self.section(plan, 'Medicamentos')
        action(med_header, app, 'Añadir medicamento', lambda: self.open_tool('medication'), 'pill').pack(side='right')
        self.medications = SummaryRows(plan, app, lambda i: self.open_tool('medication', i), lambda i: self.remove('medication', i))
        self.medications.pack(fill='x')
        self.treatment_options = Collapsible(plan, 'Opciones de tratamiento y estudios')
        self.treatment_options.pack(fill='x')
        med_tools = ttk.Frame(self.treatment_options.body)
        med_tools.pack(fill='x', pady=5)
        action(med_tools, app, 'Revisar medicación habitual o previa', lambda: self.open_tool('reuse')).pack(anchor='w')
        action(med_tools, app, 'Vista previa de receta', self.preview_prescription).pack(anchor='w', pady=5)
        if record.get('medications'):
            ttk.Label(self.treatment_options.body, text='Medicamentos heredados · revisar\n'+record['medications'], style='warning.TLabel', wraplength=900).pack(fill='x', pady=5)
        study_header = self.section(self.treatment_options.body, 'Estudios solicitados y resultados')
        action(study_header, app, 'Añadir estudio', lambda: self.open_tool('study'), 'plus').pack(side='right')
        self.studies = SummaryRows(self.treatment_options.body, app, lambda i: self.open_tool('study', i), lambda i: self.remove('study', i))
        self.studies.pack(fill='x')
        if record.get('studies'):
            ttk.Label(self.treatment_options.body, text='Estudios heredados · conservados sin interpretar\n'+record['studies'], style='warning.TLabel', wraplength=900).pack(fill='x', pady=6)
        self.followup_summary = ttk.Label(self.treatment_options.body, style='Subtitle.TLabel', wraplength=900)
        if self.model.data.get('followup'):
            self.followup_summary.pack(fill='x', pady=8)
        self.docs_section = Collapsible(body, 'Documentos de esta consulta', summary='Ver documentos o incorporar archivos a esta atención.')
        self.docs_section.pack(fill='x', pady=5)
        action(self.docs_section.body, app, 'Añadir / gestionar documentos', lambda: self.open_tool('documents'), 'file-up').pack(anchor='w', pady=6)
        self.documents = SummaryRows(self.docs_section.body, app, self.open_document, edit_label='Ver')
        self.documents.pack(fill='x')
        self.documents_status = ttk.Label(self.docs_section.body, text='JPEG, PNG, PDF y DOCX · arrastra archivos aquí. Destino: esta consulta.', style='Subtitle.TLabel', wraplength=900, padding=(0, 8))
        self.documents_status.pack(fill='x')
        if hasattr(self.documents_status, 'drop_target_register'):
            self.documents_status.drop_target_register('DND_Files')
            self.documents_status.dnd_bind('<<Drop>>', self.drop_files)
        self.loading = False
        app.editors.append((self, self.save, self.state))
        self.bind('<Destroy>', self.cleanup, add='+')
        self.refresh_summaries()
        self.refresh_documents()

    def refresh(self):
        """Contexto actual del expediente; la captura histórica/local no se recarga."""
        patient = self.app.store.read(f"data/patients/{self.patient['id']}.json")
        if patient:
            self.patient = patient
            self.patient_title.configure(text=patient['name'])
            doctor = next((u['name'] for u in self.app.auth.users() if u['id'] == self.record['doctor_id']), 'Doctor')
            self.identity_label.configure(text=patient['file_number']+' · '+age_label(patient)+' · Responsable: '+doctor)
            allergy = ', '.join(r.get('substance', '') for r in patient.get('allergy_records', [])) or patient.get('allergies') or patient.get('allergy_status') or 'No interrogadas'
            self.allergy_label.configure(text='⚠ Alergias: '+allergy)
        self.refresh_documents()

    def section(self, parent, label):
        frame = ttk.Frame(parent)
        frame.pack(fill='x', pady=(12, 4))
        ttk.Label(frame, text=label, style='Section.TLabel').pack(side='left')
        return frame

    def note(self, parent, key, label, minimum, maximum):
        heading = ttk.Frame(parent)
        heading.pack(fill='x', pady=(8, 3))
        if label:
            ttk.Label(heading, text=label, style='Subtitle.TLabel').pack(side='left')
        text = text_editor(parent, self.model.data.get(key, ''), minimum, lambda: self.note_changed(key))
        text.pack(fill='x')
        text.minimum, text.maximum, text.expanded = minimum, maximum, False
        self.texts[key] = text
        def expand():
            text.expanded = not text.expanded
            button.configure(text='Reducir' if text.expanded else 'Ampliar')
            self.grow(text)
        button = action(heading, self.app, 'Ampliar', expand)
        button.pack(side='right')
        text.bind('<FocusIn>', lambda e: setattr(self, 'last_text', text), add='+')
        self.grow(text)

    @staticmethod
    def grow(widget):
        lines = sum(max(1, (len(line)+99)//100) for line in widget.get('1.0', 'end-1c').splitlines())
        widget.configure(height=max(widget.minimum, min(22 if widget.expanded else widget.maximum, lines)))

    def note_changed(self, key):
        if key in self.texts:
            widget = self.texts[key]
            self.model.data[key] = widget.get('1.0', 'end-1c')
            self.grow(widget)
            self.touch()
            self.refresh_soap_summaries()

    def flush_notes(self):
        for key, text in self.texts.items():
            self.model.data[key] = text.get('1.0', 'end-1c')

    def layout_quick(self, event=None):
        width = self.quick.winfo_width()
        buttons = list(self.quick_buttons.values())
        required = max(b.winfo_reqwidth()+8 for b in buttons)
        columns = next((n for n in (4, 2) if n*required <= width), 1)
        for i in range(4):
            self.quick.columnconfigure(i, weight=1 if i < columns else 0)
        for i, button in enumerate(buttons):
            button.grid(row=i//columns, column=i%columns, sticky='ew', padx=(0, 7), pady=2)

    def touch(self):
        if self.loading or self.record.get('status') != 'Borrador':
            return
        self.model.generation += 1
        self.state['dirty'] = True
        self.indicator.set('Cambios pendientes de guardar…')
        if self.timer:
            self.after_cancel(self.timer)
        self.timer = self.after(900, self.autosave)
        if not self.deadline:
            self.deadline = self.after(5000, self.autosave)

    def applied(self):
        self.touch()
        self.indicator.set('Aplicado al borrador · pendiente de guardar')
        self.refresh_summaries()

    def autosave(self):
        for timer in (self.timer, self.deadline):
            if timer:
                self.after_cancel(timer)
        self.timer = self.deadline = None
        if self.state['dirty'] and self.app.auth.current:
            self.save_feedback()

    def save_feedback(self):
        try:
            return self.save()
        except (ValueError, OSError) as exc:
            from app.editing_state import VersionConflict
            if isinstance(exc, VersionConflict):
                self.conflict = exc.current
                self.save_button.configure(text='Revisar conflicto', command=self.resolve_conflict)
            self.indicator.set('No se guardó · tu captura sigue en memoria · '+str(exc))
            self.save_label.configure(style='error.TLabel')
            return False

    def resolve_conflict(self):
        from app.conflict_ui import review_conflict
        self.flush_notes()
        local = self.model.snapshot()
        remote = self.app.store.read(f"data/encounters/{self.record['id']}.json")
        def apply(merged, remote):
            self.loading = True
            try:
                for key, widget in self.texts.items():
                    if widget.get('1.0', 'end-1c') != merged.get(key, ''):
                        widget.delete('1.0', 'end')
                        widget.insert('1.0', merged.get(key, ''))
                        widget.edit_modified(False)
                self.model = ConsultationDraft(merged)
                self.record = deepcopy(remote)
                self.state.update(record=self.record, dirty=True)
            finally:
                self.loading = False
            self.save()
            self.refresh_summaries()
        return review_conflict(self.app, self.record, local, remote, apply)

    def save(self, final=False):
        if self.record['status'] != 'Borrador':
            return True
        self.flush_notes()
        active = getattr(self.app, 'active_capture', None)
        if active and getattr(active, 'owner', None) is self and active.kind == 'documents':
            active.sync_pending()
            if final and active.panel.busy:
                raise DataError('Espera a que termine la incorporación de documentos.')
        elif active and getattr(active, 'owner', None) is self and active.kind in CAPTURE_NAMES:
            if active.recovered or active.raw() != active.baseline:
                active.changed()
        snapshot = self.model.snapshot(final)
        generation = self.model.generation
        backup = {}
        if self.record.get('editor_state') and self.record['editor_state'].get('version') != 3:
            backup[f"backups/editor-consulta/{self.record['id']}-r{self.record['revision']}.json"] = deepcopy(self.record)
        record = self.app.clinic.save('encounters', snapshot, self.record.get('revision'), related=backup)
        self.record = record
        self.model.saved(record)
        self.state.update(record=record, dirty=self.model.generation != generation)
        self.save_label.configure(style='Subtitle.TLabel')
        self.save_button.configure(text='Guardar borrador', command=self.save_feedback)
        self.indicator.set(('Consulta finalizada' if final else 'Guardado · '+datetime.now().strftime('%H:%M:%S'))+
                           (' · hay capturas pendientes de aplicar' if self.model.pending else ''))
        self.refresh_pending()
        return True

    def open_tool(self, kind, identifier=None):
        if kind == 'document_metadata':
            kind = 'documents'
        active = getattr(self.app, 'active_capture', None)
        if active and active.winfo_exists():
            active.lift()
            return active
        self.flush_notes()
        if kind == 'followup' and not (self.model.data.get('followup') or any(p['kind'] == 'followup' for p in self.model.pending.values())):
            raise DataError('La programación de seguimientos ya no está disponible.')
        title = {'vitals': 'Registrar signos vitales', 'medication': 'Medicamento de la consulta',
                 'study': 'Registrar estudio', 'followup': 'Revisar captura histórica de seguimiento', 'documents': 'Documentos de la consulta',
                 'header': 'Detalles de la consulta', 'diagnosis': 'Editar diagnóstico', 'history': 'Evolución del paciente',
                 'reuse': 'Revisar tratamientos previos', 'review': 'Revisar y finalizar'}[kind]
        cls = {'vitals': VitalsCapture, 'medication': MedicationCapture, 'documents': DocumentsCapture,
               'history': HistoryCapture, 'reuse': ReuseCapture, 'review': ReviewCapture}.get(kind, DetailCapture)
        return cls(self, kind, title, identifier, width=880 if kind == 'documents' else 760 if kind in ('history', 'review') else 700,
                   height=740 if kind in ('documents', 'medication', 'review') else 660 if kind == 'vitals' else 520)

    def open_history(self):
        return self.open_tool('history')

    def refresh_summaries(self):
        data = self.model.data
        if self.diagnosis_var.get() and self.model.key('diagnosis', self.inline_id) not in self.model.pending:
            self.diagnosis_var.set('')
            self.inline_id = str(uuid.uuid4())
        self.context_label.configure(text=display_date(data['attended_at'])+' · '+data.get('type', 'General')+' · Borrador')
        self.diagnoses.render(data['diagnoses'], lambda r: r['name'])
        self.medications.render(data['prescriptions'], lambda r: ('⚠ Pauta pendiente de revisión · ' if r.get('needs_review') else '')+medication_text(r)+('\n'+r['instructions'] if r.get('instructions') else ''), 'Sin tratamientos registrados.')
        self.studies.render(data['study_orders'], lambda r: r['name']+' · '+r.get('status', 'Sin estado')+('\n'+r['notes'] if r.get('notes') else ''), 'Sin estudios registrados.')
        followup = data.get('followup', {})
        self.followup_summary.configure(text='Dato histórico de seguimiento: '+display_date(followup['date'])+' · '+followup.get('reason', '') if followup.get('date') else '')
        self.refresh_soap_summaries()
        rows = data['vitals']
        self.take_selector.pack_forget()
        self.take_edit.pack_forget()
        selected = next((r for r in rows if r['id'] == self.model.selected_take), rows[-1] if rows else None)
        if selected:
            self.model.selected_take = selected['id']
            self.take_summary.configure(text=measurement_summary(selected))
            self.take_edit.pack(side='right')
        else:
            self.take_summary.configure(text='Sin mediciones registradas. Usa Signos vitales para una nueva toma.')
        if len(rows) > 1:
            self.take_choices = {f'Toma {i+1} · '+display_date(r['at']): r['id'] for i, r in enumerate(rows)}
            self.take_selector.configure(values=list(self.take_choices))
            self.take_choice.set(next(k for k, v in self.take_choices.items() if v == self.model.selected_take))
            self.take_selector.pack(side='top', fill='x', pady=4, before=self.take_summary)
        self.refresh_pending()

    def select_take(self, event=None):
        self.model.selected_take = self.take_choices[self.take_choice.get()]
        self.refresh_summaries()

    def edit_take(self):
        if self.model.selected_take:
            return self.open_tool('vitals', self.model.selected_take)

    def refresh_pending(self):
        signature = [(k, p['kind']) for k, p in self.model.pending.items()]
        if signature == self.pending_signature:
            return
        self.pending_signature = signature
        for child in self.pending_box.winfo_children():
            child.destroy()
        for key, kind in signature:
            line = ttk.Frame(self.pending_box)
            line.pack(fill='x', pady=2)
            action(line, self.app, 'Continuar captura', lambda k=key: self.goto_issue(k)).pack(side='right')
            ttk.Label(line, text='⚠ '+CAPTURE_NAMES.get(kind, kind)+' en edición · todavía no aplicado', style='warning.TLabel').pack(side='left', fill='x', expand=True)

    def diagnosis_changed(self, *args):
        if self.diagnosis_var.get().strip():
            self.model.remember('diagnosis', self.inline_id, {'name': self.diagnosis_var.get()})
        else:
            self.model.discard('diagnosis', self.inline_id)
        self.touch()

    def add_diagnosis(self):
        name = self.diagnosis_var.get().strip()
        if not name:
            self.diagnosis_error.configure(text='Escribe el diagnóstico antes de añadirlo.')
            self.diagnosis_error.pack(fill='x', before=self.diagnoses)
            self.diagnosis_input.focus_set()
            return
        self.model.apply('diagnosis', self.inline_id, {'name': name})
        self.diagnosis_var.set('')
        self.inline_id = str(uuid.uuid4())
        self.diagnosis_error.pack_forget()
        self.applied()

    def diagnosis_suggestions(self, event=None):
        if getattr(self, '_diagnoses_loaded', False):
            return
        self._diagnoses_loaded = True
        def work():
            return sorted({d['name'] for r in self.app.clinic.list('encounters') for d in r.get('diagnoses', []) if d.get('name')})
        def ready(rows):
            if self.winfo_exists():
                self.diagnosis_input.configure(values=rows)
        self.app.background(work, ready)

    def remove(self, kind, identifier):
        self.model.remove(kind, identifier)
        self.applied()

    def catalog_items(self):
        if self._catalog is None:
            self._catalog = self.app.care.catalog()
        return self._catalog

    def refresh_documents(self):
        self.document_ticket += 1
        ticket = self.document_ticket
        pid, eid = self.patient['id'], self.record['id']
        def ready(rows):
            if not self.winfo_exists() or ticket != self.document_ticket:
                return
            self.document_rows = rows
            self.documents.render(rows, lambda r: r['title']+' · '+r['mime'].split('/')[-1]+' · Incorporado', 'Sin documentos incorporados a esta consulta.')
            pending = sum(r.get('status') != 'Guardado' for r in self.model.queue)
            self.documents_status.configure(text=(f'{pending} archivos en cola · pendientes de incorporar. ' if pending else '')+'JPEG, PNG, PDF y DOCX · arrastra archivos aquí. Los adjuntos generales permanecen en el expediente.')
            self.refresh_soap_summaries()
        self.app.background(lambda: self.app.attachments.list(pid, eid), ready)

    def open_document(self, identifier):
        from app.attachment_ui import DocumentViewer
        try:
            row = self.app.attachments.get(identifier)
            path = self.app.attachments.path(identifier)
            if row['mime'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
                import os
                os.startfile(path)
            else:
                DocumentViewer(self.app, path, row['title'])
        except (ValueError, OSError) as exc:
            self.documents_status.configure(text=str(exc), style='error.TLabel')

    def drop_files(self, event):
        capture = self.open_tool('documents')
        if capture.kind == 'documents':
            capture.panel.add_paths(self.tk.splitlist(event.data))
            return 'copy'
        return 'refuse_drop'

    def preview_prescription(self):
        try:
            from app.clinical_models import validate_medications
            if any(p['kind'] == 'medication' for p in self.model.pending.values()):
                raise DataError('Aplica o descarta la pauta pendiente antes de revisar la receta.')
            self.flush_notes()
            rows = validate_medications(self.model.data['prescriptions'], final=True)
            self.app.pdf_preview('BORRADOR · Receta e indicaciones', [('Estado', 'Consulta todavía sin finalizar.'),
                ('Tratamiento', '\n\n'.join(medication_text(r)+'\n'+r.get('instructions', '') for r in rows)),
                ('Indicaciones', self.model.data.get('plan', ''))], self.app.auth.current['name'], self.patient['name'])
        except (ValueError, OSError) as exc:
            self.indicator.set(str(exc))

    def sections_changed(self):
        self.model.section_state = {key: panel.opened for key, panel in self.soap.items()}
        self.touch()

    def refresh_soap_summaries(self):
        data = self.model.data
        compact = lambda value: ' '.join(str(value or '').split())[:160]
        summaries = {
            'S': compact(data.get('reason') or data.get('subjective')) or 'Motivo, síntomas y evolución · listo para escribir.',
            'O': ' · '.join(filter(None, [f"{len(data['vitals'])} toma(s)" if data['vitals'] else '', compact(data.get('objective'))])) or 'Sin mediciones ni exploración registradas.',
            'A': compact('; '.join(r['name'] for r in data['diagnoses']) or self.model.legacy_assessment or data.get('assessment_notes')) or 'Diagnóstico o impresión pendiente.',
            'P': ' · '.join(filter(None, [compact(data.get('plan')), f"{len(data['prescriptions'])} medicamento(s)" if data['prescriptions'] else '', f"{len(data['study_orders'])} estudio(s)" if data['study_orders'] else ''])) or 'Indicaciones y tratamiento pendientes.'}
        for key, text in summaries.items():
            if key in self.soap:
                self.soap[key].set_summary(self.soap_descriptions[key]+' · '+text)
        if hasattr(self, 'treatment_options'):
            count = len(data['study_orders'])
            self.treatment_options.set_summary((f'{count} estudio(s) · revisar tratamientos previos o receta' if count else 'Medicación previa, receta y solicitudes de estudios.')+(' · contiene datos heredados' if any(data.get(k) for k in ('medications', 'studies', 'followup')) else ''))
        if hasattr(self, 'docs_section'):
            waiting = sum(r.get('status') != 'Guardado' for r in self.model.queue)
            self.docs_section.set_summary(f'{len(self.document_rows)} incorporado(s) a esta consulta'+(f' · ⚠ {waiting} archivo(s) pendiente(s)' if waiting else ' · ver o añadir documentos'))

    def reveal_section(self, key, focus=True):
        self.soap[key].reveal()
        target = self.diagnosis_input if key == 'A' else self.texts[{'S': 'reason', 'O': 'objective', 'P': 'plan'}[key]]
        if key == 'O':
            self.exploration.reveal()
        self.scroll_to(self.soap[key])
        if focus:
            target.focus_set()

    def scroll_to(self, widget):
        self.update_idletasks()
        offset = widget.winfo_rooty()-self.scroll.body.winfo_rooty()
        self.scroll.canvas.yview_moveto(max(0, (offset-8)/max(1, self.scroll.body.winfo_height())))

    def goto_issue(self, key):
        if key in self.texts:
            section = {'reason': 'S', 'subjective': 'S', 'objective': 'O', 'assessment_notes': 'A', 'plan': 'P'}[key]
            self.reveal_section(section, focus=False)
            widget = self.texts[key]
            self.scroll_to(widget)
            widget.focus_set()
        elif key == 'diagnosis':
            self.reveal_section('A')
        elif ':' in key:
            kind, identifier = key.split(':', 1)
            self.open_tool(kind, identifier)
        else:
            self.open_tool(key)

    def finish(self):
        return self.open_tool('review')

    def cleanup(self, event):
        if event.widget is self:
            for timer in (self.timer, self.deadline):
                if timer:
                    self.after_cancel(timer)


class ConsultationDocuments(ttk.Frame):
    """Resumen y gestión a demanda en la lectura continua de una atención."""
    def __init__(self, parent, app, patient, record):
        super().__init__(parent)
        self.app, self.patient, self.record = app, patient, record
        self.model = ConsultationDraft(record)
        self.last_text = None
        self.document_ticket, self.document_rows = 0, []
        ttk.Label(self, text='Documentos de esta consulta', style='Section.TLabel').pack(anchor='w')
        action(self, app, 'Agregar / gestionar documentos', lambda: self.open_tool('documents'), 'file-up').pack(anchor='w', pady=6)
        self.documents = SummaryRows(self, app, self.open_document, edit_label='Ver')
        self.documents.pack(fill='x')
        self.documents_status = ttk.Label(self, style='Subtitle.TLabel', wraplength=900)
        self.documents_status.pack(fill='x')
        self.refresh_documents()

    open_tool = ConsultationEditor.open_tool
    open_document = ConsultationEditor.open_document

    def flush_notes(self):
        pass

    def touch(self):
        self.refresh_documents()

    def refresh_documents(self):
        self.document_ticket += 1
        ticket = self.document_ticket
        def ready(rows):
            if self.winfo_exists() and ticket == self.document_ticket:
                self.document_rows = rows
                self.documents.render(rows, lambda r: r['title']+' · '+r['mime'].split('/')[-1]+' · Incorporado', 'Sin documentos de esta consulta.')
                self.documents_status.configure(text='Los documentos del expediente general permanecen separados. Las incorporaciones posteriores conservan autoría y motivo.')
        self.app.background(lambda: self.app.attachments.list(self.patient['id'], self.record['id']), ready)
