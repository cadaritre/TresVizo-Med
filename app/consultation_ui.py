"""Consulta estructurada, captura de mediciones y evolución longitudinal."""
from copy import deepcopy
from datetime import datetime, date, timedelta
import uuid
import tkinter as tk
from tkinter import ttk, messagebox
from app.components import ScrollFrame
from app.widgets import Form, Collection, DateField, text_editor
from app.clinical_models import VITALS, MED_FIELDS, validate_vitals, medication_text, encounter_sections, age_label, display_date
from app.services import now
from app.storage import DataError
from app.attachment_ui import AttachmentPanel

MED_OPTIONS = {'dose_unit': ['mg', 'g', 'mcg', 'mL', 'tableta', 'cápsula', 'gota', 'UI', 'inhalación'],
               'route': ['Oral', 'Tópica', 'Inhalada', 'Intravenosa', 'Intramuscular', 'Subcutánea', 'Oftálmica', 'Ótica'],
               'frequency_kind': ['Cada N horas', 'Veces al día', 'Horarios', 'Pauta personalizada', 'Según necesidad'],
               'duration_unit': ['días', 'semanas', 'meses'], 'status': ['Activo', 'Suspendido', 'Completado'],
               'start': 'date', 'end': 'date', 'instructions': 'text'}

def medication_specs(app):
    return [(key, label, [r['name'] for r in app.care.catalog()] if key == 'name' else MED_OPTIONS.get(key)) for key, label in MED_FIELDS]

class VitalsPanel(ttk.Frame):
    def __init__(self, parent, app, patient_id, rows=None, changed=lambda: None):
        super().__init__(parent)
        self.app, self.patient_id, self.rows, self.changed = app, patient_id, deepcopy(rows or []), changed
        self.loading = True
        self.current_id = str(uuid.uuid4())
        ttk.Label(self, text='Signos vitales y mediciones', style='Section.TLabel').pack(anchor='w', pady=10)
        ttk.Label(self, text='Registra solo lo que se midió. Cada toma conserva su fecha, hora y unidades.', style='Subtitle.TLabel').pack(anchor='w')
        stamp = ttk.Frame(self)
        stamp.pack(fill='x', pady=10)
        self.day = DateField(stamp, app.theme, date.today().isoformat())
        self.day.pack(side='left')
        self.time = tk.StringVar(value=datetime.now().strftime('%H:%M'))
        ttk.Entry(stamp, textvariable=self.time, width=7).pack(side='left', padx=8)
        ttk.Label(stamp, text='Fecha y hora de la toma', style='Subtitle.TLabel').pack(side='left')
        self.grid = ttk.Frame(self)
        self.grid.pack(fill='x')
        self.values, self.units, self.tiles = {}, {}, []
        for key, (label, units) in VITALS.items():
            tile = ttk.Frame(self.grid, style='Card.TFrame', padding=12)
            ttk.Label(tile, text=label, style='Card.TLabel', font=('Segoe UI Semibold', 10)).pack(anchor='w')
            row = ttk.Frame(tile, style='Card.TFrame')
            row.pack(fill='x', pady=8)
            var, unit = tk.StringVar(), tk.StringVar(value=units[0])
            self.values[key], self.units[key] = var, unit
            ttk.Entry(row, textvariable=var, width=9).pack(side='left', fill='x', expand=True)
            combo = ttk.Combobox(row, textvariable=unit, values=units, state='readonly', width=7)
            combo.pack(side='left', padx=(6, 0))
            previous = [units[0]]
            def convert(event=None, k=key, old=previous):
                from app.clinical_models import normalize_measurement
                new = self.units[k].get()
                if self.values[k].get().strip():
                    try:
                        canonical, _ = normalize_measurement(k, self.values[k].get(), old[0])
                        factor = {'lb': 1/0.45359237, 'm': .01, 'in': 1/2.54, 'mmol/L': 1/18.0182}.get(new, 1)
                        converted = canonical*9/5+32 if new == '°F' else canonical*factor
                        self.values[k].set(f'{converted:.6g}')
                    except ValueError:
                        self.units[k].set(old[0])
                        return
                old[0] = new
                self.notify()
            combo.bind('<<ComboboxSelected>>', convert)
            var.trace_add('write', lambda *a: self.notify())
            self.tiles.append(tile)
        self.columns = 0
        self.grid.bind('<Configure>', self.layout)
        self.context = tk.StringVar(value='No especificado')
        ttk.Label(self, text='Contexto de glucosa', style='Subtitle.TLabel').pack(anchor='w', pady=(8, 3))
        ttk.Combobox(self, textvariable=self.context, values=['No especificado', 'Ayuno', 'Posprandial', 'Aleatoria'], state='readonly').pack(anchor='w')
        self.context.trace_add('write', lambda *a: self.notify())
        self.day.var.trace_add('write', lambda *a: self.notify())
        self.time.trace_add('write', lambda *a: self.notify())
        self.bmi = ttk.Label(self, text='IMC: se calcula al confirmar peso y estatura de esta toma.', style='Subtitle.TLabel')
        self.bmi.pack(anchor='w', pady=8)
        ttk.Button(self, text='Confirmar medición', style='Primary.TButton', command=self.confirm).pack(anchor='w')
        self.error = ttk.Label(self, style='error.TLabel', wraplength=600)
        self.tree = ttk.Treeview(self, columns=('date', 'values'), show='headings', height=3)
        self.tree.heading('date', text='Fecha y hora')
        self.tree.heading('values', text='Mediciones confirmadas')
        self.tree.column('date', width=150, stretch=False)
        self.tree.column('values', width=440)
        self.tree.pack(fill='x', pady=10)
        ttk.Button(self, text='Editar toma seleccionada', command=self.edit, style='Link.TButton').pack(anchor='w')
        self.trend = TrendPanel(self, app, patient_id)
        self.trend.pack(fill='both', expand=True, pady=12)
        self.loading = False
        self.refresh()

    def layout(self, event=None):
        cols = 4 if self.grid.winfo_width() >= 920 else 2 if self.grid.winfo_width() >= 420 else 1
        if cols == self.columns:
            return
        self.columns = cols
        for i in range(4):
            self.grid.columnconfigure(i, weight=1 if i < cols else 0)
        for i, tile in enumerate(self.tiles):
            tile.grid(row=i//cols, column=i%cols, padx=(0, 8), pady=4, sticky='nsew')

    def notify(self):
        if not self.loading:
            self.changed()
            try:
                item = self.current()
                self.bmi.configure(text=f"IMC de esta toma: {item['bmi']} kg/m²" if item.get('bmi') else 'IMC: requiere peso y estatura en esta toma.')
            except (ValueError, KeyError):
                self.bmi.configure(text='IMC: completa mediciones válidas.')

    def current(self):
        stamp = self.day.get()+'T'+self.time.get()+':00'
        datetime.fromisoformat(stamp)
        values = {k: {'value': var.get().strip(), 'unit': self.units[k].get()} for k, var in self.values.items() if var.get().strip()}
        return validate_vitals([{'id': self.current_id, 'at': stamp, 'context': self.context.get(), 'values': values}])[0]

    def confirm(self):
        try:
            item = self.current()
            if not item['values']:
                raise DataError('Registra al menos una medición.')
            self.rows = [r for r in self.rows if r['id'] != item['id']]+[item]
            self.loading = True
            for var in self.values.values():
                var.set('')
            self.loading = False
            self.current_id = str(uuid.uuid4())
            self.error.pack_forget()
            self.refresh()
            self.changed()
        except ValueError as exc:
            self.error.configure(text=str(exc))
            self.error.pack(fill='x', pady=6)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            self.tree.insert('', 'end', iid=str(i), values=(display_date(row['at']), ' · '.join(VITALS[k][0]+': '+str(v['value'])+' '+v['unit'] for k, v in row['values'].items())))

    def edit(self):
        if not self.tree.selection():
            return
        item = self.rows[int(self.tree.selection()[0])]
        self.loading = True
        self.current_id = item['id']
        self.day.var.set(display_date(item['at'][:10]))
        self.time.set(item['at'][11:16])
        self.context.set(item.get('context', 'No especificado'))
        for key in self.values:
            self.values[key].set(str(item.get('values', {}).get(key, {}).get('value', '')))
            self.units[key].set(item.get('values', {}).get(key, {}).get('unit', VITALS[key][1][0]))
        self.loading = False
        self.changed()

    def state(self):
        return {'id': self.current_id, 'date': self.day.var.get(), 'time': self.time.get(), 'context': self.context.get(),
                'values': {k: v.get() for k, v in self.values.items()}, 'units': {k: v.get() for k, v in self.units.items()}}

    def restore(self, state):
        if not state:
            return
        self.loading = True
        self.current_id = state.get('id', self.current_id)
        self.day.var.set(state.get('date', ''))
        self.time.set(state.get('time', ''))
        self.context.set(state.get('context', 'No especificado'))
        for k, value in state.get('values', {}).items():
            self.values[k].set(value)
            self.units[k].set(state['units'][k])
        self.loading = False

class TrendPanel(ttk.Frame):
    def __init__(self, parent, app, patient_id):
        super().__init__(parent)
        self.app, self.patient_id, self.points = app, patient_id, []
        ttk.Label(self, text='Evolución del paciente', style='Section.TLabel').pack(anchor='w', pady=8)
        controls = ttk.Frame(self)
        controls.pack(fill='x')
        self.keys = {label: key for key, (label, _) in VITALS.items()}
        self.keys['IMC'] = 'bmi'
        self.metric = tk.StringVar(value='Presión sistólica')
        self.period = tk.StringVar(value='Un año')
        box = ttk.Combobox(controls, textvariable=self.metric, values=list(self.keys), state='readonly', width=24)
        box.pack(side='left')
        box.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        period = ttk.Combobox(controls, textvariable=self.period, values=['30 días', '90 días', 'Un año', 'Todo'], state='readonly', width=12)
        period.pack(side='left', padx=8)
        period.bind('<<ComboboxSelected>>', lambda e: self.refresh())
        ttk.Button(controls, text='Actualizar', command=self.refresh, style='Link.TButton').pack(side='left')
        self.canvas = tk.Canvas(self, height=190, highlightthickness=0)
        self.canvas.pack(fill='x', pady=8)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.table = ttk.Treeview(self, columns=('at', 'value', 'context'), show='headings', height=3)
        for key, label in [('at', 'Fecha y hora'), ('value', 'Valor exacto'), ('context', 'Contexto')]:
            self.table.heading(key, text=label)
            self.table.column(key, width=150)
        self.table.pack(fill='x')
        self.table.bind('<Double-1>', lambda e: app.open_encounter(self.table.selection()[0].split('|')[0]) if self.table.selection() else None)
        app.theme.subscribe(self, lambda t: self.draw())
        self.refresh()

    def refresh(self):
        points = self.app.care.evolution(self.patient_id, self.keys[self.metric.get()])
        days = {'30 días': 30, '90 días': 90, 'Un año': 365}.get(self.period.get())
        if days:
            start = (date.today()-timedelta(days=days)).isoformat()
            points = [p for p in points if p['at'][:10] >= start]
        self.points = points
        self.table.delete(*self.table.get_children())
        for i, row in enumerate(points):
            self.table.insert('', 'end', iid=row['encounter_id']+'|'+str(i), values=(display_date(row['at']), f"{row['value']:.6g} {row['unit']}", row['context']))
        self.draw()

    def draw(self):
        if not hasattr(self, 'canvas'):
            return
        c, t = self.canvas, self.app.theme.tokens
        c.configure(background=t['surface'])
        c.delete('all')
        w = max(c.winfo_width(), 300)
        if not self.points:
            c.create_text(w/2, 90, text='Todavía no hay mediciones finalizadas en este periodo.', fill=t['muted'], width=w-40)
            return
        rows = self.points
        numbers = [p['value'] for p in rows]
        low, high = min(numbers), max(numbers)
        margin = max((high-low)*.12, 1)
        low, high = low-margin, high+margin
        stamps = [datetime.fromisoformat(p['at']).replace(tzinfo=None).timestamp() for p in rows]
        span = max(1, max(stamps)-min(stamps))
        c.create_line(55, 15, 55, 153, w-18, 153, fill=t['separator'])
        for i in range(4):
            val = low+(high-low)*i/3
            y = 150-i*42
            c.create_text(48, y, text=f'{val:.1f}', anchor='e', fill=t['muted'], font=('Segoe UI', 9))
        c.create_text(58, 175, text=display_date(rows[0]['at'][:10]), anchor='w', fill=t['muted'])
        c.create_text(w-18, 175, text=display_date(rows[-1]['at'][:10])+' · '+rows[-1]['unit'], anchor='e', fill=t['muted'])
        last = None
        for row, stamp in zip(rows, stamps):
            x, y = 60+(w-90)*(stamp-min(stamps))/span, 150-(row['value']-low)/(high-low)*126
            if last and (self.keys[self.metric.get()] != 'glucose' or last[2] == row['context']):
                c.create_line(last[0], last[1], x, y, fill=t['chart1'], width=2)
            item = c.create_oval(x-4, y-4, x+4, y+4, fill=t['chart1'], outline=t['surface'])
            c.tag_bind(item, '<Enter>', lambda e, r=row: self.app.status.set(display_date(r['at'])+f" · {r['value']:.6g} {r['unit']}"))
            last = (x, y, row['context'])

class ConsultationEditor(ttk.Frame):
    def __init__(self, parent, app, patient, record):
        super().__init__(parent)
        self.app, self.patient, self.record = app, patient, deepcopy(record)
        self.loading, self.timer, self.deadline = True, None, None
        self.state = {'record': self.record, 'dirty': False}
        top = ttk.Frame(self)
        top.pack(fill='x')
        ttk.Button(top, text='‹ Expediente', style='Link.TButton', command=lambda: app.patient_record(patient['id'])).pack(side='left')
        ttk.Label(top, text='Consulta · '+patient['name'], style='Title.TLabel').pack(side='left', padx=8)
        ttk.Label(self, text=patient['file_number']+' · '+age_label(patient), style='Subtitle.TLabel').pack(anchor='w', pady=4)
        allergy = ', '.join(r.get('substance', '') for r in patient.get('allergy_records', [])) or patient.get('allergies') or patient.get('allergy_status', 'No interrogadas')
        ttk.Label(self, text='⚠ Alergias: '+allergy, style='warning.TLabel', wraplength=900).pack(fill='x', pady=8)
        footer = ttk.Frame(self)
        footer.pack(side='bottom', fill='x', pady=8)
        self.indicator = tk.StringVar(value='Borrador guardado')
        ttk.Button(footer, text='Guardar borrador', command=lambda: app.guard(self.save)).pack(side='left')
        ttk.Button(footer, text='Revisar y finalizar', style='Primary.TButton', command=self.finish).pack(side='left', padx=8)
        ttk.Label(footer, textvariable=self.indicator, style='Subtitle.TLabel').pack(side='right')
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill='both', expand=True)
        pages = []
        for title in ('Resumen clínico', 'Signos vitales', 'Diagnósticos y tratamiento', 'Estudios y seguimiento', 'Documentos'):
            scroll = ScrollFrame(self.tabs)
            self.tabs.add(scroll, text=title)
            pages.append(scroll.body)
        self.header = Form(pages[0], [('date', 'Fecha de atención', 'date'), ('time', 'Hora', None), ('type', 'Tipo de consulta', ['General', 'Control', 'Urgencia', 'Primera vez'])],
                           {'date': record['attended_at'][:10], 'time': record['attended_at'][11:16], 'type': record.get('type', 'General')}, self.changed, app.theme)
        self.header.pack(fill='x')
        self.texts = {}
        for key, label in [('reason', 'Motivo de consulta *'), ('subjective', 'Síntomas y evolución'), ('objective', 'Exploración física')]:
            ttk.Label(pages[0], text=label, style='Section.TLabel').pack(anchor='w', pady=(14, 6))
            self.texts[key] = text_editor(pages[0], record.get(key, ''), 4, self.changed)
            self.texts[key].pack(fill='x')
        self.vitals = VitalsPanel(pages[1], app, patient['id'], record.get('vitals'), self.changed)
        self.vitals.pack(fill='both', expand=True)
        diagnoses = [{'name': v.strip()} for v in record.get('assessment', '').split(';') if v.strip()]
        self.diagnoses = Collection(pages[2], app, 'Diagnósticos *', [('name', 'Diagnóstico', None)], diagnoses, lambda r: r['name'], self.changed)
        self.diagnoses.pack(fill='x')
        self.medications = Collection(pages[2], app, 'Medicamentos de esta consulta', medication_specs(app), record.get('prescriptions'), medication_text, self.changed,
                                      {'frequency_kind': 'Cada N horas', 'duration_unit': 'días', 'status': 'Activo'})
        self.medications.pack(fill='x')
        tools = ttk.Frame(pages[2])
        tools.pack(fill='x', pady=5)
        ttk.Button(tools, text='Guardar en catálogo / favoritos', style='Link.TButton', command=self.favorite).pack(side='left')
        ttk.Button(tools, text='Revisar medicación habitual', style='Link.TButton', command=self.reuse).pack(side='left', padx=8)
        if record.get('medications'):
            ttk.Label(pages[2], text='Medicamentos heredados · revisar antes de estructurar\n'+record['medications'], wraplength=700, style='warning.TLabel').pack(fill='x', pady=10)
        ttk.Label(pages[2], text='Plan e indicaciones *', style='Section.TLabel').pack(anchor='w', pady=10)
        self.texts['plan'] = text_editor(pages[2], record.get('plan', ''), 5, self.changed)
        self.texts['plan'].pack(fill='x')
        self.studies = Collection(pages[3], app, 'Estudios solicitados', [('name', 'Estudio', None), ('status', 'Estado', ['Solicitado', 'Pendiente', 'Recibido']), ('notes', 'Indicaciones / resultado', 'text')], record.get('study_orders'), changed=self.changed, defaults={'status': 'Solicitado'})
        self.studies.pack(fill='x')
        self.followup = Form(pages[3], [('date', 'Fecha de seguimiento', 'date'), ('reason', 'Motivo de seguimiento', None)], record.get('followup', {}), self.changed, app.theme)
        self.followup.pack(fill='x', pady=12)
        self.attachments = AttachmentPanel(pages[4], app, patient['id'], record['id'])
        self.attachments.pack(fill='both', expand=True)
        saved = record.get('editor_state', {})
        for name in ('diagnoses', 'medications', 'studies'):
            getattr(self, name).restore(saved.get(name))
        self.vitals.restore(saved.get('vitals'))
        self.loading = False
        app.editors.append((self, self.save, self.state))
        self.bind('<Control-s>', lambda e: app.guard(self.save))
        self.bind('<Destroy>', self.cleanup, add='+')

    def cleanup(self, event):
        if event.widget is self:
            for timer in (self.timer, self.deadline):
                if timer:
                    self.after_cancel(timer)

    def changed(self):
        if self.loading:
            return
        self.state['dirty'] = True
        self.indicator.set('Cambios pendientes…')
        if self.timer:
            self.after_cancel(self.timer)
        self.timer = self.after(900, self.autosave)
        if not self.deadline:
            self.deadline = self.after(5000, self.autosave)

    def autosave(self):
        for timer in (self.timer, self.deadline):
            if timer:
                self.after_cancel(timer)
        self.timer = self.deadline = None
        if self.state['dirty'] and self.app.auth.current:
            try:
                self.save()
            except (ValueError, OSError) as exc:
                self.indicator.set('Pendiente de guardar: '+str(exc))

    def save(self, final=False):
        fields = self.header.values()
        data = {**self.record, **{k: t.get('1.0', 'end-1c') for k, t in self.texts.items()}, 'type': fields['type'],
                'attended_at': fields['date']+'T'+fields['time']+':00', 'status': 'Finalizada' if final else 'Borrador',
                'assessment': '; '.join(r['name'] for r in self.diagnoses.rows), 'prescriptions': self.medications.rows,
                'vitals': self.vitals.rows, 'study_orders': self.studies.rows, 'followup': self.followup.values(),
                'editor_state': {name: getattr(self, name).state() for name in ('diagnoses', 'medications', 'studies', 'vitals')}}
        if final:
            for name in ('diagnoses', 'medications', 'studies'):
                collection = getattr(self, name)
                if collection.pending:
                    raise DataError('Confirma o cancela el elemento que estás editando antes de finalizar.')
            if any(v.get().strip() for v in self.vitals.values.values()):
                raise DataError('Confirma la medición pendiente antes de finalizar.')
            data.pop('editor_state', None)
        self.record = self.app.clinic.save('encounters', data, self.record.get('revision'))
        self.state.update(record=self.record, dirty=False)
        self.indicator.set('Guardado · '+datetime.now().strftime('%H:%M:%S'))
        if final and data['followup'].get('date'):
            fid = str(uuid.uuid5(uuid.UUID(self.record['id']), 'followup'))
            old = self.app.store.read(f'data/followups/{fid}.json')
            self.app.clinic.save('followups', {'id': fid, 'patient_id': self.patient['id'], 'due_at': data['followup']['date']+'T09:00:00', 'reason': data['followup']['reason'], 'status': 'Pendiente', 'encounter_id': self.record['id']}, (old or {}).get('revision'))
        return True

    def finish(self):
        if not messagebox.askyesno('Revisar y finalizar', self.patient['name']+'\n'+self.patient['file_number']+'\n\n'+str(len(self.medications.rows))+' medicamentos · '+str(len(self.vitals.rows))+' tomas de signos vitales.\nLas correcciones posteriores se registrarán como adendas. ¿Finalizar?', parent=self):
            return
        if self.app.guard(lambda: self.save(True)):
            identifier = self.record['id']
            self.app.pages.pop('consulta:'+identifier, None)
            self.destroy()
            self.app.open_encounter(identifier)

    def favorite(self):
        selection = self.medications.tree.selection()
        if selection:
            row = self.medications.rows[int(selection[0])]
            self.app.guard(lambda: self.app.care.save_catalog(row, favorite=True))
            self.app.status.set('Medicamento añadido a favoritos; las dosis se revisan en cada consulta.')

    def reuse(self):
        known = self.patient.get('medication_records', [])
        if not known:
            self.app.status.set('No hay medicamentos habituales estructurados para revisar.')
            return
        win = self.app.window('Revisar medicación habitual', '760x480')
        for original in known:
            row = deepcopy(original)
            def add(r=row):
                r['id'] = str(uuid.uuid4())
                r['needs_review'] = True
                self.medications.rows.append(r)
                self.medications.refresh()
                self.changed()
                win.destroy()
                self.app.status.set('Tratamiento añadido pendiente de revisión. Ábrelo y confirma su pauta.')
            ttk.Button(win, text=medication_text(row), command=add).pack(fill='x', padx=15, pady=8)
