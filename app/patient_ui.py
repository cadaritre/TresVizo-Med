"""Registro de pacientes en el espacio principal, con borrador privado."""
from copy import deepcopy
from datetime import date, datetime
import re
import tkinter as tk
from tkinter import ttk, messagebox
from app.components import ScrollFrame
from app.widgets import Form, Collection, Collapsible, wrap_actions
from app.consultation_ui import medication_specs
from app.clinical_models import age_label, medication_text, numeric
from app.attachment_ui import AttachmentPanel
from app.storage import DataError

class PatientEditor(ttk.Frame):
    def __init__(self, parent, app, record=None, draft=None, attend=False):
        super().__init__(parent)
        self.app, self.original, self.loading = app, deepcopy(record or {}), True
        self.timer = self.deadline = None
        self.state = {'dirty': False}
        self.draft = draft or app.care.save_draft(self.original, patient_id=(record or {}).get('id'), revision=(record or {}).get('revision'))
        data = self.draft['payload'] or self.original
        self.photo_id = data.get('photo_attachment_id')
        self.draft_id = self.draft['id']
        self.on_created = None
        self.attend_after_save = attend
        top = ttk.Frame(self)
        top.pack(fill='x')
        ttk.Button(top, text='‹ Pacientes', style='Link.TButton', command=lambda: app.show('Pacientes')).pack(side='left')
        ttk.Label(top, text='Editar paciente' if record else 'Nuevo paciente', style='Title.TLabel').pack(side='left', padx=12)
        ttk.Label(self, text='Registro a cargo de '+app.auth.current['name']+' · solo el nombre es obligatorio', style='Subtitle.TLabel').pack(anchor='w', pady=8)
        footer = ttk.Frame(self)
        footer.pack(side='bottom', fill='x', pady=8)
        self.conflict_action = ttk.Button(self, text='Revisar diferencias con el expediente guardado', command=self.resolve_conflict)
        self.indicator = tk.StringVar(value='Borrador privado guardado')
        footer_actions = ttk.Frame(footer)
        footer_actions.pack(fill='x')
        self.primary_save = ttk.Button(footer_actions, text='Guardar y comenzar consulta' if attend else 'Guardar paciente', style='Primary.TButton', command=lambda: self.register(self.attend_after_save))
        self.primary_save.pack(side='left')
        self.secondary_save = ttk.Button(footer_actions, text='Guardar solo paciente' if attend else 'Guardar y comenzar consulta', command=lambda: self.register(not self.attend_after_save))
        self.secondary_save.pack(side='left', padx=8)
        cancel_button = ttk.Button(footer_actions, text='Salir del registro', command=self.cancel)
        wrap_actions(footer_actions, [self.primary_save, self.secondary_save, cancel_button])
        ttk.Label(footer, textvariable=self.indicator, style='Subtitle.TLabel', wraplength=760).pack(fill='x', pady=(6, 0))
        self.scroll = ScrollFrame(self)
        self.scroll.pack(fill='both', expand=True)
        body = self.scroll.body
        self.complementary = Collapsible(body, 'Antecedentes y medicación habitual', summary='Problemas, antecedentes, tratamientos y notas complementarias.')
        self.document_section = Collapsible(body, 'Documentos e imágenes', summary='Archivos para el expediente general del paciente.')
        self.review_section = Collapsible(body, 'Revisar todos los datos antes de guardar')
        pages = [body, self.complementary.body, self.document_section.body, self.review_section.body]
        self.personal = Form(pages[0], [('name', 'Nombre completo *', None), ('preferred_name', 'Nombre preferido', None),
                                      ('birth_date', 'Fecha de nacimiento', 'date'), ('sex', 'Sexo registrado', ['No especificado', 'Femenino', 'Masculino', 'Intersexual', 'Otro registrado'])],
                             {**data, 'sex': data.get('sex', 'No especificado')}, self.changed, app.theme)
        self.personal.pack(fill='x')
        self.search_input = self.personal.inputs['name']
        self.personal.inputs['sex'].configure(state='readonly')
        self.unknown = tk.BooleanVar(value=data.get('birth_unknown', bool(data.get('approx_age', {}).get('value'))))
        ttk.Checkbutton(pages[0], text='Fecha de nacimiento desconocida', variable=self.unknown).pack(anchor='w', pady=5)
        try:
            initial_age = age_label(data)
        except ValueError:
            initial_age = 'Fecha pendiente de completar'
        self.age = ttk.Label(pages[0], text=initial_age, style='Section.TLabel')
        self.age.pack(anchor='w', pady=8)
        self.approx = Form(pages[0], [('value', 'Edad aproximada (opcional)', None), ('unit', 'Unidad de edad', ['años', 'meses', 'días']), ('at', 'Fecha de referencia', 'date')],
                           data.get('approx_age', {'unit': 'años', 'at': date.today().isoformat()}), self.changed, app.theme)
        self.approx.pack(fill='x')
        self.unknown.trace_add('write', lambda *a: self.update_age_mode())
        self.personal.vars['birth_date'].trace_add('write', lambda *a: self.unknown.set(False) if self.personal.vars['birth_date'].get().strip() else None)
        self.allergy_status = tk.StringVar(value=data.get('allergy_status', 'No interrogado'))
        ttk.Label(pages[0], text='Estado de alergias', style='Section.TLabel').pack(anchor='w', pady=10)
        ttk.Combobox(pages[0], textvariable=self.allergy_status, state='readonly', values=['No interrogado', 'Desconocido', 'Sin alergias conocidas', 'Alergias registradas']).pack(anchor='w')
        self.allergy_status.trace_add('write', lambda *a: self.changed())
        self.allergy_section = Collapsible(pages[0], 'Registrar alergias', opened=bool(data.get('allergy_records')), summary='Distingue alergias conocidas, ausencia confirmada e información desconocida.')
        self.allergy_section.pack(fill='x')
        self.allergies = Collection(self.allergy_section.body, app, 'Alergias', [('substance', 'Sustancia', None), ('reaction', 'Reacción documentada', None),
                                    ('severity', 'Gravedad documentada', ['No documentada', 'Leve', 'Moderada', 'Grave']), ('date', 'Fecha conocida', 'date'), ('notes', 'Observaciones', 'text')],
                                    data.get('allergy_records'), changed=self.changed, defaults={'severity': 'No documentada'})
        self.allergies.pack(fill='x')
        contact = self.contact_section = Collapsible(pages[0], 'Contacto', summary=data.get('phone') or data.get('email') or 'Teléfonos, correo y dirección opcionales.')
        contact.pack(fill='x')
        phones = data.get('phones', [{'type': 'Principal', 'number': data['phone']}] if data.get('phone') else [])
        self.phones = Collection(contact.body, app, 'Teléfonos', [('number', 'Número, prefijo o extensión', None), ('type', 'Tipo', ['Principal', 'Móvil', 'Casa', 'Trabajo', 'Otro'])], phones, changed=self.changed)
        self.phones.pack(fill='x')
        self.contact = Form(contact.body, [('email', 'Correo electrónico', None), ('address', 'Dirección', 'text')], data, self.changed, app.theme)
        self.contact.pack(fill='x')
        self.contact.inputs['email'].bind('<FocusOut>', self.check_email)
        self.email_error = ttk.Label(contact.body, style='error.TLabel')
        emergency = self.emergency_section = Collapsible(pages[0], 'Contacto de emergencia y responsable', summary=data.get('emergency_contact', {}).get('name') or data.get('emergency') or 'Opcional · añadir una persona de contacto.')
        emergency.pack(fill='x')
        self.emergency = Form(emergency.body, [('name', 'Contacto de emergencia', None), ('relationship', 'Relación declarada', None), ('phone', 'Teléfono', None),
                                              ('guardian', 'Tutor o responsable (opcional)', None), ('guardian_relation', 'Relación del responsable', None)], data.get('emergency_contact', {}), self.changed, app.theme)
        self.emergency.pack(fill='x')
        if data.get('emergency'):
            ttk.Label(emergency.body, text='Contacto heredado: '+data['emergency'], wraplength=700).pack(fill='x')
        self.problems = Collection(pages[1], app, 'Problemas activos', [('name', 'Problema', None), ('status', 'Estado', ['Activo', 'Resuelto', 'En estudio']), ('date', 'Fecha conocida', 'date'), ('notes', 'Observaciones', 'text')], data.get('problem_records'), changed=self.changed)
        self.problems.pack(fill='x')
        self.histories = {}
        for key, title in [('personal', 'Antecedentes personales'), ('family', 'Antecedentes familiares'), ('surgical', 'Cirugías'), ('hospital', 'Hospitalizaciones'), ('other', 'Otros antecedentes')]:
            box = Collapsible(pages[1], title)
            box.pack(fill='x')
            form = Form(box.body, [('status', 'Estado de la información', ['No registrado', 'Desconocido', 'Sin antecedentes declarados', 'Antecedentes registrados']), ('notes', 'Descripción', 'text')],
                        data.get('histories', {}).get(key, {'status': 'No registrado'}), self.changed, app.theme)
            form.pack(fill='x')
            self.histories[key] = form
        self.medications = Collection(pages[1], app, 'Medicamentos habituales', medication_specs(app), data.get('medication_records'), medication_text, self.changed,
                                      {'status': 'Activo', 'frequency_kind': 'Cada N horas', 'duration_unit': 'días'})
        self.medications.pack(fill='x')
        self.medications.show_preview(medication_text)
        self.notes = Form(pages[1], [('administrative', 'Notas administrativas · visibles para doctores autorizados', 'text'), ('clinical_notes', 'Notas clínicas', 'text')], data, self.changed, app.theme)
        self.notes.pack(fill='x')
        inherited = '\n\n'.join(f'{k}: {v}' for k, v in data.get('legacy', {}).items() if v)
        if inherited:
            box = Collapsible(pages[1], 'Información heredada · pendiente de revisión')
            box.pack(fill='x')
            ttk.Label(box.body, text=inherited, wraplength=740, justify='left').pack(fill='x')
        def photo(identifier):
            self.photo_id = identifier
            self.changed()
        self.attachments = AttachmentPanel(pages[2], app, draft_id=self.draft_id, on_photo=photo, changed=self.changed)
        self.attachments.pack(fill='both', expand=True)
        if record:
            ttk.Button(pages[2], text='Ver documentos ya incorporados al expediente', command=lambda: app.patient_record(record['id'])).pack(anchor='w', pady=8)
        self.review = ttk.Label(pages[3], justify='left', wraplength=750, padding=20, style='Card.TLabel')
        self.review.pack(fill='x', pady=12)
        self.error = ttk.Label(pages[3], style='error.TLabel', wraplength=700)
        for panel in (self.complementary, self.document_section, self.review_section):
            panel.pack(fill='x', pady=3)
        editor_state = data.get('editor_state', {})
        self.attachments.restore_queue(editor_state.get('attachment_queue',[]))
        for name in ('phones', 'allergies', 'problems', 'medications'):
            getattr(self, name).restore(editor_state.get(name))
        self.update_age_mode()
        self.loading = False
        app.editors.append((self, self.save, self.state))
        self.bind('<Destroy>', self.cleanup, add='+')
        self.show_review()
        self.update_summaries()

    def reveal(self, widget):
        ancestor = widget
        while ancestor is not self:
            if isinstance(ancestor, Collapsible):
                ancestor.reveal()
            ancestor = ancestor.master
        self.update_idletasks()
        offset = widget.winfo_rooty()-self.scroll.body.winfo_rooty()
        self.scroll.canvas.yview_moveto(max(0, (offset-8)/max(1, self.scroll.body.winfo_height())))

    def update_summaries(self):
        if not hasattr(self, 'attachments'):
            return
        contacts = self.contact.values(raw=True)
        self.contact_section.set_summary(' · '.join(filter(None, [self.phones.summary(self.phones.rows[0]) if self.phones.rows else '', contacts.get('email'), contacts.get('address')]))[:180] or 'Teléfonos, correo y dirección opcionales.')
        emergency = self.emergency.values(raw=True)
        self.emergency_section.set_summary(' · '.join(filter(None, [emergency.get('name'), emergency.get('guardian'), emergency.get('phone')]))[:180] or self.original.get('emergency') or 'Opcional · añadir una persona de contacto.')
        self.allergy_section.set_summary(self.allergy_status.get()+' · '+(', '.join(r.get('substance', '') for r in self.allergies.rows) or 'Sin sustancias registradas'))
        histories = 0
        for form in self.histories.values():
            values = form.values(raw=True)
            status, notes = values.get('status', ''), values.get('notes', '').strip()
            histories += bool(notes or status not in ('', 'No registrado'))
            form.master.master.set_summary(' · '.join(filter(None, [status, ' '.join(notes.split())[:150]])))
        self.complementary.set_summary(f'{len(self.problems.rows)} problemas · {histories} antecedentes · {len(self.medications.rows)} medicamentos habituales'+(' · hay notas' if any(self.notes.values(raw=True).values()) else ''))
        generation = self.app.store.generation('attachments')
        if getattr(self, '_attachment_generation', None) != generation:
            self._incorporated_count = len(self.app.attachments.list(draft_id=self.draft_id))
            self._attachment_generation = generation
        incorporated = self._incorporated_count
        pending = sum(r['status'] != 'Guardado' for r in self.attachments.queue)
        self.document_section.set_summary(f'{incorporated} documentos incorporados al borrador'+(f' · ⚠ {pending} pendientes' if pending else ''))

    def update_age_mode(self):
        for widget in self.personal.inputs['birth_date'].winfo_children():
            if hasattr(widget, 'state'):
                widget.state(['disabled'] if self.unknown.get() else ['!disabled'])
        if self.unknown.get():
            self.approx.pack(fill='x', after=self.age)
        else:
            self.approx.pack_forget()
        self.changed()

    def check_email(self, event=None):
        value = self.contact.vars['email'].get()
        valid = not value or re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value)
        self.contact.inputs['email'].state(['!invalid'] if valid else ['invalid'])
        if valid:
            self.email_error.pack_forget()
        else:
            self.email_error.configure(text='Revisa el formato del correo electrónico.')
            self.email_error.pack(fill='x')
        return valid

    def payload(self, raw=False):
        data = {**self.original, **self.personal.values(raw), **self.contact.values(raw), **self.notes.values(raw),
                'birth_unknown': self.unknown.get(), 'approx_age': self.approx.values(raw), 'phones': deepcopy(self.phones.rows),
                'emergency_contact': self.emergency.values(raw), 'allergy_status': self.allergy_status.get(), 'allergy_records': deepcopy(self.allergies.rows),
                'problem_records': deepcopy(self.problems.rows), 'histories': {k: v.values(raw) for k, v in self.histories.items()},
                'medication_records': deepcopy(self.medications.rows), 'editor_state': {k: getattr(self, k).state() for k in ('phones', 'allergies', 'problems', 'medications')}}
        data['photo_attachment_id'] = self.photo_id
        data['editor_state']['attachment_queue'] = deepcopy(self.attachments.queue) if hasattr(self,'attachments') else []
        data['phone'] = next((p['number'] for p in data['phones']), '')
        if not raw:
            if data['birth_unknown']:
                data['birth_date'] = ''
            else:
                data['approx_age'] = {}
            if data.get('approx_age', {}).get('value'):
                numeric(data['approx_age']['value'], 'Edad aproximada', minimum=0)
            if not data['name'].strip():
                self.reveal(self.personal)
                self.personal.inputs['name'].focus_set()
                raise DataError('El nombre del paciente es obligatorio.')
            if not self.check_email():
                self.reveal(self.contact.inputs['email'])
                self.contact.inputs['email'].focus_set()
                raise DataError('Revisa el correo electrónico.')
            if data['allergy_records'] and data['allergy_status'] == 'Sin alergias conocidas':
                self.reveal(self.allergy_section)
                raise DataError('Hay alergias registradas. Revisa el estado antes de declarar ausencia de alergias.')
            if data['allergy_records']:
                data['allergy_status'] = 'Alergias registradas'
            for key in ('phones', 'allergies', 'problems', 'medications'):
                if getattr(self, key).pending:
                    self.reveal(getattr(self, key))
                    raise DataError('Confirma o cancela el elemento que estás editando antes de registrar al paciente.')
            data.pop('editor_state', None)
        return data

    def changed(self):
        if self.loading:
            return
        self.show_review()
        self.update_summaries()
        self.state['dirty'] = True
        self.indicator.set('Cambios pendientes…')
        if self.timer:
            self.after_cancel(self.timer)
        self.timer = self.after(900, self.autosave)
        if not self.deadline:
            self.deadline = self.after(5000, self.autosave)
        try:
            p = self.personal.values()
            self.age.configure(text=age_label(p) if not self.unknown.get() else 'Fecha desconocida · puedes registrar una edad aproximada')
        except ValueError:
            self.age.configure(text='Revisa la fecha de nacimiento.')

    def save(self):
        self.draft = self.app.care.save_draft(self.payload(raw=True), self.draft_id, self.original.get('id'), self.original.get('revision'))
        self.state['dirty'] = False
        self.indicator.set('Borrador guardado · '+datetime.now().strftime('%H:%M:%S'))
        return True

    def autosave(self):
        for timer in (self.timer, self.deadline):
            if timer:
                self.after_cancel(timer)
        self.timer = self.deadline = None
        if self.state['dirty'] and self.app.auth.current:
            try:
                self.save()
            except (ValueError, OSError) as exc:
                self.indicator.set('No se pudo guardar: '+str(exc))

    def show_review(self, event=None):
        if not hasattr(self, 'review'):
            return
        data = self.payload(raw=True)
        self.review.configure(text='Revisión del registro\n\n'+(data.get('name') or 'Nombre pendiente')+'\n'+data.get('sex', 'No especificado')+
                              f"\n\n{len(self.phones.rows)} teléfonos · {len(self.allergies.rows)} alergias · {len(self.medications.rows)} medicamentos habituales\n\n"+
                              'Los archivos incorporados al borrador pasarán al expediente general.\nEl borrador todavía no aparece como paciente registrado.')

    def register(self, attend=False):
        try:
            data = self.payload()
            if self.attachments.busy or any(r['status'] != 'Guardado' for r in self.attachments.queue):
                self.reveal(self.attachments)
                raise DataError('Termina la incorporación de documentos o retira los archivos pendientes antes de guardar.')
            from app.services import normalized
            duplicates = [p for p in self.app.clinic.list('patients', include_archived=True) if p['id'] != self.original.get('id') and
                          (normalized(p['name']) == normalized(data['name']) or data.get('phone') and data['phone'] == p.get('phone'))]
            if duplicates and not messagebox.askyesno('Revisar posible duplicado', '\n'.join(p['name']+' · '+p['file_number'] for p in duplicates[:5])+'\n\n¿Registrar este expediente como una persona distinta?', parent=self):
                return
            self.save()
            patient = self.app.care.register(self.draft_id, data)
            if 'Pacientes' in self.app.pages:
                self.app.pages['Pacientes'].preferred_patient = patient['id']
            self.state['dirty'] = False
            self.app.pages.pop('alta:'+self.draft_id, None)
            self.destroy()
            if getattr(self, 'on_created', None):
                self.on_created(patient)
            elif attend:
                self.app.encounter_editor(patient)
            else:
                self.app.patient_record(patient['id'])
        except (ValueError, OSError) as exc:
            from app.editing_state import VersionConflict
            if isinstance(exc, VersionConflict):
                self.conflict_action.pack(side='bottom', fill='x', pady=6)
            self.indicator.set(str(exc))
            self.error.configure(text=str(exc))
            self.error.pack(fill='x', pady=8)

    def resolve_conflict(self):
        from app.conflict_ui import review_conflict
        remote = self.app.store.read(f"data/patients/{self.original['id']}.json")
        local = self.payload(raw=True)
        def apply(merged, current):
            self.loading = True
            try:
                for name in ('personal', 'contact', 'notes'):
                    getattr(self, name).load(merged)
                self.emergency.load(merged.get('emergency_contact', {}))
                self.approx.load(merged.get('approx_age', {}))
                self.unknown.set(merged.get('birth_unknown', False))
                self.allergy_status.set(merged.get('allergy_status', 'No interrogado'))
                for name, field in [('phones', 'phones'), ('allergies', 'allergy_records'), ('problems', 'problem_records'), ('medications', 'medication_records')]:
                    collection = getattr(self, name)
                    collection.rows = deepcopy(merged.get(field, []))
                    collection.refresh()
                    collection.restore(merged.get('editor_state', {}).get(name))
                for key, form in self.histories.items():
                    form.load(merged.get('histories', {}).get(key, {}))
                self.original = deepcopy(current)
            finally:
                self.loading = False
            self.save()
            self.conflict_action.pack_forget()
            self.indicator.set('Diferencias combinadas en el borrador. Revisa y pulsa Guardar paciente para publicarlo.')
        return review_conflict(self.app, self.original, local, remote, apply)

    def cancel(self):
        answer = messagebox.askyesnocancel('Salir del registro', '¿Conservar el borrador privado para continuarlo después?\nSí: conservar. No: descartar este borrador.', parent=self)
        if answer is None:
            return
        if answer:
            if not self.app.guard(self.save):
                return
        else:
            self.app.care.discard(self.draft_id)
        self.state['dirty'] = False
        self.app.pages.pop('alta:'+self.draft_id, None)
        self.destroy()
        self.app.show('Pacientes')

    def cleanup(self, event):
        if event.widget is self:
            for timer in (self.timer, self.deadline):
                if timer:
                    self.after_cancel(timer)
