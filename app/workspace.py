"""Navegación persistente y pantallas del espacio clínico."""
from datetime import date, datetime
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from app.components import ScrollFrame
from app.widgets import text_editor
from app.services import now, normalized
from app.clinical_models import age_label, display_date, medication_text, encounter_sections
from app.patient_ui import PatientEditor
from app.consultation_ui import ConsultationEditor, TrendPanel
from app.attachment_ui import AttachmentPanel
from app.profiles import ProfileEditor

class Workspace:
    def statistics(self, parent):
        from app.statistics_ui import StatisticsPage
        page = StatisticsPage(parent,self)
        page.pack(fill='both',expand=True)
        parent.refresh = page.refresh

    def login_screen(self):
        users = [u for u in self.auth.users() if u['active']]
        if not users:
            return self._legacy_login_screen()
        self.clear()
        self.theme.apply(self.appearance.tokens())
        scroll = ScrollFrame(self)
        scroll.pack(fill='both', expand=True)
        scroll.body.columnconfigure(0, weight=1)
        outer = ttk.Frame(scroll.body, padding=24)
        outer.grid(row=0, column=0, pady=18)
        self.brand(outer).pack(pady=6)
        ttk.Label(outer, text='TresVizo Med', style='Title.TLabel').pack()
        ttk.Label(outer, text=self.identity.values['clinic_name'], style='Subtitle.TLabel').pack(pady=(4,20))
        ttk.Label(outer, text='Selecciona tu perfil', style='Section.TLabel').pack(anchor='w', pady=8)
        query = tk.StringVar()
        if len(users) > 6:
            ttk.Entry(outer, textvariable=query, width=45).pack(fill='x', pady=8)
        gallery = ttk.Frame(outer)
        gallery.pack(fill='x')
        chosen = tk.StringVar(value=users[0]['id'])
        self.login_cards = {}
        self.login_photos = []
        page = [0]
        password = tk.StringVar()
        selected_name = tk.StringVar(value=users[0]['name'])
        def select(user):
            chosen.set(user['id'])
            password.set('')
            selected_name.set(user['name'])
            for uid, button in self.login_cards.items():
                button.configure(style='Active.Nav.TButton' if uid == user['id'] else 'TButton')
            entry.focus_set()
        def render(*args):
            for child in gallery.winfo_children():
                child.destroy()
            self.login_cards.clear()
            rows = [u for u in users if normalized(query.get()) in normalized(u['name']+' '+u['username'])]
            shown = rows[page[0]*9:page[0]*9+9]
            for i, user in enumerate(shown):
                photo = self.profiles.image(user, 80)
                button = ttk.Button(gallery, text=user['name'], image=photo, compound='top', width=20,
                                    style='Active.Nav.TButton' if user['id'] == chosen.get() else 'TButton', command=lambda u=user: select(u))
                button.grid(row=i//3, column=i%3, padx=6, pady=6, sticky='nsew')
                self.login_cards[user['id']] = button
            self.theme._walk(outer)
        if len(users) > 9:
            controls = ttk.Frame(outer)
            controls.pack(fill='x')
            def turn(delta):
                page[0] = max(0, min((len(users)-1)//9, page[0]+delta))
                render()
            ttk.Button(controls, text='Anterior', command=lambda: turn(-1), style='Link.TButton').pack(side='left')
            ttk.Button(controls, text='Siguiente', command=lambda: turn(1), style='Link.TButton').pack(side='right')
        ttk.Label(outer, textvariable=selected_name, font=('Segoe UI Semibold', 12)).pack(pady=(16,6))
        ttk.Label(outer, text='Contraseña', style='Subtitle.TLabel').pack(anchor='w')
        entry = ttk.Entry(outer, textvariable=password, show='•', width=40)
        entry.pack(fill='x', pady=6)
        visible = tk.BooleanVar()
        ttk.Checkbutton(outer, text='Mostrar contraseña', variable=visible, command=lambda: entry.configure(show='' if visible.get() else '•')).pack(anchor='w')
        def login():
            self.auth.login(chosen.get(), password.get())
            password.set('')
            self.shell()
        entry.bind('<Return>', lambda e: self.guard(login))
        ttk.Button(outer, text='Entrar', style='Primary.TButton', command=lambda: self.guard(login)).pack(fill='x', pady=16)
        ttk.Button(outer, text=self.identity.values['website_text']+' ↗', style='Link.TButton', command=lambda: self.guard(self.identity.open_website)).pack()
        query.trace_add('write', lambda *a: (page.__setitem__(0,0), render()))
        render()

    def shell(self):
        self.session_generation += 1
        self.clear()
        self.theme.apply(self.appearance.tokens())
        self.activity()
        self.pages, self.nav_buttons, self.editors = {}, {}, []
        self.current_page = 'Inicio'
        header = ttk.Frame(self, style='Header.TFrame', padding=(20,10))
        header.pack(fill='x')
        ttk.Label(header, text=self.identity.values['clinic_name'], style='Header.TLabel', font=('Segoe UI Semibold', 13)).pack(side='left')
        self.profile_button = ttk.Menubutton(header, text=self.auth.current['name'], image=self.profiles.image(self.auth.current,32), compound='left')
        self.profile_button.pack(side='right')
        menu = tk.Menu(self.profile_button, tearoff=False)
        menu.add_command(label='Mi perfil', command=lambda: self.show('Mi perfil'))
        menu.add_command(label='Apariencia', command=lambda: self.show('Configuración'))
        menu.add_separator()
        menu.add_command(label='Bloquear sesión', command=self.lock_session)
        menu.add_command(label='Cambiar doctor', command=self.logout)
        self.profile_button.configure(menu=menu)
        ttk.Label(self, textvariable=self.status, style='Subtitle.TLabel', padding=(20,5)).pack(side='bottom', fill='x')
        nav = ttk.Frame(self, style='Nav.TFrame', padding=12, width=int(225*self.ui_scale))
        nav.pack(side='left', fill='y')
        nav.pack_propagate(False)
        self.brand(nav, 'Nav.TLabel').pack(anchor='w', pady=(6,0))
        ttk.Label(nav, text='TresVizo Med', style='Nav.TLabel', font=('Segoe UI Semibold',15)).pack(anchor='w', pady=(4,20))
        for name in ('Inicio', 'Pacientes', 'Consultas', 'Agenda', 'Seguimientos', 'Mis estadísticas', 'Exportar y respaldar'):
            button = ttk.Button(nav, text=name, style='Nav.TButton', command=lambda n=name: self.show(n))
            button.pack(fill='x', pady=2)
            self.nav_buttons[name] = button
            self.icons.bind(button,{'Inicio':'house','Pacientes':'users','Consultas':'stethoscope','Agenda':'calendar-days','Seguimientos':'calendar-check','Mis estadísticas':'chart-no-axes-combined','Exportar y respaldar':'archive'}[name],token='on_sidebar')
        bottom = ttk.Frame(nav, style='Nav.TFrame')
        bottom.pack(side='bottom', fill='x', pady=12)
        for name in ('Configuración', 'Acerca de'):
            button = ttk.Button(bottom, text=name, style='Nav.TButton', command=lambda n=name: self.show(n))
            button.pack(fill='x', pady=2)
            self.nav_buttons[name] = button
            self.icons.bind(button,'settings' if name == 'Configuración' else 'info',token='on_sidebar')
        self.content = ttk.Frame(self, padding=(20,14))
        self.content.pack(side='left', fill='both', expand=True)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)
        self.show('Inicio')

    def show(self, name):
        if not self.auth.current or self.locked:
            return
        builders = {'Inicio': self.home, 'Pacientes': self.patients, 'Consultas': self.encounters,
                    'Agenda': lambda p: self.schedule(p,'appointments'), 'Seguimientos': lambda p: self.schedule(p,'followups'),
                    'Mis estadísticas': self.statistics, 'Exportar y respaldar': self.exports,
                    'Configuración': self.settings, 'Acerca de': self.about,
                    'Mi perfil': lambda p: ProfileEditor(p,self).pack(fill='both', expand=True)}
        if name not in self.pages:
            frame = ttk.Frame(self.content)
            frame.grid(row=0, column=0, sticky='nsew')
            self.pages[name] = frame
            builders[name](frame)
        self.pages[name].tkraise()
        self.current_page = name
        section = 'Pacientes' if name.startswith(('paciente:', 'alta:')) else 'Consultas' if name.startswith(('consulta:', 'historia:')) else name
        for key, button in self.nav_buttons.items():
            button.configure(style='Active.Nav.TButton' if key == section else 'Nav.TButton')
        if hasattr(self.pages[name], 'refresh'):
            self.guard(self.pages[name].refresh)
        self.theme._walk(self.pages[name])

    def mount(self, key, factory):
        if key not in self.pages:
            frame = factory(self.content)
            frame.grid(row=0, column=0, sticky='nsew')
            self.pages[key] = frame
        self.show(key)
        return self.pages[key]

    def lock_session(self):
        if self.locked or not self.auth.current:
            return
        self.locked = True
        self.session_generation += 1
        focus = self.focus_get()
        windows = [w for w in self.winfo_children() if isinstance(w,tk.Toplevel)]
        self.withdraw()
        for win in windows:
            win.withdraw()
        uid = self.auth.current['id']
        cover = tk.Toplevel(self)
        cover.title('Sesión bloqueada')
        cover.geometry('480x330')
        cover.protocol('WM_DELETE_WINDOW', lambda: None)
        ttk.Label(cover, text='Sesión bloqueada', style='Title.TLabel', padding=20).pack()
        ttk.Label(cover, text=self.auth.current['name'], padding=10).pack()
        secret = tk.StringVar()
        entry = ttk.Entry(cover, textvariable=secret, show='•')
        entry.pack(fill='x', padx=30, pady=10)
        def unlock():
            self.auth.login(uid, secret.get())
            secret.set('')
            cover.destroy()
            self.locked = False
            self.activity()
            self.deiconify()
            for win in windows:
                if win.winfo_exists():
                    win.deiconify()
            if focus and focus.winfo_exists():
                focus.focus_set()
        ttk.Button(cover, text='Desbloquear', style='Primary.TButton', command=lambda: self.guard(unlock)).pack(pady=10)
        ttk.Button(cover, text='Cambiar doctor', command=lambda: (cover.destroy(), setattr(self,'locked',False), self.logout())).pack()
        entry.bind('<Return>', lambda e: self.guard(unlock))
        self.theme._walk(cover)
        entry.focus_set()

    def home(self, parent):
        scroll = ScrollFrame(parent)
        scroll.pack(fill='both', expand=True)
        body = scroll.body
        self.heading(body, 'Hola, '+self.auth.current['name'], datetime.now().strftime('%d/%m/%Y')+' · Tu jornada')
        actions = ttk.Frame(body)
        actions.pack(fill='x', pady=(4,16))
        ttk.Button(actions, text='Atender paciente', style='Primary.TButton', command=lambda: self.show('Pacientes')).pack(side='left')
        ttk.Button(actions, text='Registrar paciente', style='Link.TButton', command=self.patient_editor).pack(side='left', padx=12)
        ttk.Button(actions, text='Ver agenda', style='Link.TButton', command=lambda: self.show('Agenda')).pack(side='left')
        metrics = ttk.Frame(body)
        metrics.pack(fill='x', pady=8)
        values = []
        for label in ('Atenciones hoy', 'Pacientes hoy', 'Borradores de consulta'):
            frame = ttk.Frame(metrics, style='Card.TFrame', padding=14)
            frame.pack(side='left', fill='both', expand=True, padx=(0,8))
            value = ttk.Label(frame, text='—', style='Metric.TLabel')
            value.pack(anchor='w')
            ttk.Label(frame, text=label, style='Card.TLabel').pack(anchor='w')
            values.append(value)
        lists = {}
        for key, title in [('appointments','Próximas citas'), ('drafts','Continuar consulta'), ('registrations','Registros de pacientes en curso'), ('followups','Seguimientos pendientes')]:
            ttk.Label(body, text=title, style='Section.TLabel').pack(anchor='w', pady=(18,6))
            lists[key] = ttk.Frame(body)
            lists[key].pack(fill='x')
        def refresh():
            actor = self.auth.current['id']
            today = date.today().isoformat()
            patients = {p['id']: p for p in self.clinic.list('patients', True)}
            encounters = self.clinic.list('encounters')
            drafts = [r for r in encounters if r['status'] == 'Borrador' and r['doctor_id'] == actor]
            final = [r for r in encounters if r['status'] == 'Finalizada' and r['doctor_id'] == actor and r['attended_at'][:10] == today]
            for w,v in zip(values, (len(final), len({r['patient_id'] for r in final}), len(drafts))):
                w.configure(text=str(v))
            data = {'drafts': drafts, 'registrations': self.care.drafts(),
                    'appointments': sorted([r for r in self.clinic.list('appointments') if r['doctor_id'] == actor and r['due_at'][:10] >= today and r['status'] in ('Programada','Confirmada','Pendiente')], key=lambda r:r['due_at'])[:5],
                    'followups': sorted([r for r in self.clinic.list('followups') if r['doctor_id'] == actor and r['status'] == 'Pendiente'], key=lambda r:r['due_at'])[:5]}
            for key, box in lists.items():
                for child in box.winfo_children():
                    child.destroy()
                for row in data[key][:5]:
                    line = ttk.Frame(box, style='Card.TFrame', padding=(12,7))
                    line.pack(fill='x', pady=2)
                    name = row.get('payload',{}).get('name') or patients.get(row.get('patient_id'),{}).get('name','Registro sin nombre')
                    text = name+' · '+display_date(row.get('due_at',row.get('updated_at',row.get('attended_at',''))))
                    ttk.Label(line, text=text, style='Card.TLabel').pack(side='left')
                    command = (lambda r=row:self.open_encounter(r['id'])) if key == 'drafts' else (lambda r=row:self.patient_editor(draft=r)) if key == 'registrations' else (lambda r=row:self.patient_record(r['patient_id']))
                    ttk.Button(line, text='Retomar' if key in ('drafts','registrations') else 'Ver expediente', style='Link.TButton', command=command).pack(side='right')
                if not data[key]:
                    empty = {'appointments':'No tienes próximas citas.', 'drafts':'No tienes consultas pendientes de continuar.', 'registrations':'No tienes registros de pacientes incompletos.', 'followups':'No tienes seguimientos pendientes.'}[key]
                    ttk.Label(box, text=empty, style='Subtitle.TLabel', padding=8).pack(anchor='w')
        parent.refresh = refresh

    def patients(self, parent):
        self.heading(parent, 'Pacientes', 'Buscar y atender · Ctrl+K')
        bar = ttk.Frame(parent)
        bar.pack(fill='x')
        query = tk.StringVar()
        ttk.Label(bar, text='Buscar').pack(side='left', padx=(0,8))
        ttk.Entry(bar, textvariable=query).pack(side='left', fill='x', expand=True)
        mode = tk.StringVar(value='Activos')
        mode_box = ttk.Combobox(bar, textvariable=mode, values=['Activos','Archivados','Todos'], state='readonly', width=12)
        mode_box.pack(side='left', padx=8)
        ttk.Button(bar, text='+ Nuevo paciente', style='Primary.TButton', command=self.patient_editor).pack(side='left')
        tree = self.table(parent, {'name':'Paciente', 'file':'Expediente', 'age':'Edad', 'phone':'Contacto'})
        tree.column('name', width=330)
        tree.column('file', width=120, stretch=False)
        tree.column('age', width=125)
        bottom = ttk.Frame(parent)
        bottom.pack(fill='x')
        ttk.Button(bottom, text='Abrir expediente', command=lambda: self.patient_record(tree.selection()[0]) if tree.selection() else None).pack(side='left')
        ttk.Button(bottom, text='Atender', style='Primary.TButton', command=lambda: self.confirm_encounter(self.store.read('data/patients/'+tree.selection()[0]+'.json')) if tree.selection() else None).pack(side='left', padx=8)
        if self.auth.current['role'] == 'admin':
            def archive():
                if not tree.selection(): return
                row = self.store.read('data/patients/'+tree.selection()[0]+'.json')
                reason = simpledialog.askstring('Restaurar paciente' if row.get('archived') else 'Eliminar de la lista', row['name']+' · '+row['file_number']+'\nEl expediente y su historial se conservarán.\nMotivo:', parent=self)
                if reason:
                    self.guard(lambda:self.clinic.archive('patients',row['id'],reason,restore=row.get('archived',False),revision=row['revision']))
                    refresh()
            ttk.Button(bottom, text='Archivar / restaurar', style='Link.TButton', command=archive).pack(side='left')
        page = [0]
        count = ttk.Label(bottom, style='Subtitle.TLabel')
        count.pack(side='right')
        def turn(delta):
            page[0] = max(0,page[0]+delta)
            refresh()
        ttk.Button(bottom, text='›', width=3, command=lambda:turn(1)).pack(side='right')
        ttk.Button(bottom, text='‹', width=3, command=lambda:turn(-1)).pack(side='right')
        timer = [None]
        def refresh():
            rows = self.clinic.list('patients',True)
            q = normalized(query.get())
            rows = [r for r in rows if q in normalized(' '.join(str(r.get(k,'')) for k in ('name','preferred_name','file_number','phone'))) and
                    (mode.get() == 'Todos' or bool(r.get('archived')) == (mode.get() == 'Archivados'))]
            rows.sort(key=lambda r:normalized(r['name']))
            page[0] = min(page[0],max(0,(len(rows)-1)//100))
            selected = tree.selection()
            position = tree.yview()[0]
            tree.delete(*tree.get_children())
            for row in rows[page[0]*100:page[0]*100+100]:
                tree.insert('', 'end', iid=row['id'], values=(row['name'],row['file_number'],age_label(row),row.get('phone','')))
            if selected and tree.exists(selected[0]):
                tree.selection_set(selected[0])
                tree.yview_moveto(position)
            count.configure(text=f'{len(rows)} pacientes · página {page[0]+1}')
        def changed(*args):
            if timer[0]: parent.after_cancel(timer[0])
            page[0] = 0
            timer[0] = parent.after(250,refresh)
        query.trace_add('write',changed)
        mode_box.bind('<<ComboboxSelected>>',changed)
        tree.bind('<Double-1>',lambda e:self.patient_record(tree.selection()[0]) if tree.selection() else None)
        tree.bind('<Return>',lambda e:self.patient_record(tree.selection()[0]) if tree.selection() else None)
        parent.refresh = refresh

    def patient_editor(self, record=None, refresh=lambda:None, draft=None):
        if draft:
            if draft.get('patient_id'):
                record = self.store.read(f"data/patients/{draft['patient_id']}.json")
        elif record:
            draft = next((d for d in self.care.drafts() if d.get('patient_id') == record['id']),None)
        draft = draft or self.care.save_draft(record or {}, patient_id=(record or {}).get('id'), revision=(record or {}).get('revision'))
        return self.mount('alta:'+draft['id'], lambda parent:PatientEditor(parent,self,record,draft))

    def patient_record(self, identifier):
        def build(parent):
            frame = ttk.Frame(parent)
            def refresh():
                for child in frame.winfo_children(): child.destroy()
                patient = self.store.read(f'data/patients/{identifier}.json')
                bar = ttk.Frame(frame)
                bar.pack(fill='x')
                ttk.Button(bar,text='‹ Pacientes',style='Link.TButton',command=lambda:self.show('Pacientes')).pack(side='left')
                ttk.Button(bar,text='Editar',command=lambda:self.patient_editor(patient)).pack(side='right')
                ttk.Button(bar,text='Nueva consulta',style='Primary.TButton',command=lambda:self.confirm_encounter(patient),state='disabled' if patient.get('archived') else 'normal').pack(side='right',padx=8)
                self.heading(frame,patient['name'],patient['file_number']+' · '+age_label(patient)+' · '+patient.get('sex','No especificado')+(' · Archivado' if patient.get('archived') else ''))
                allergy = ', '.join(r.get('substance','') for r in patient.get('allergy_records',[])) or patient.get('allergies') or patient.get('allergy_status','No interrogado')
                ttk.Label(frame,text='⚠ Alergias: '+allergy,style='warning.TLabel',wraplength=850).pack(fill='x',pady=6)
                tabs = ttk.Notebook(frame)
                tabs.pack(fill='both',expand=True)
                overview = ScrollFrame(tabs)
                tabs.add(overview,text='Resumen')
                for title, content in [('Contacto',patient.get('phone','')+'\n'+patient.get('email','')+'\n'+patient.get('address','')),
                                       ('Problemas activos','\n'.join(r['name']+' · '+r.get('status','') for r in patient.get('problem_records',[])) or patient.get('problems','')),
                                       ('Medicamentos habituales','\n'.join(medication_text(r) for r in patient.get('medication_records',[])) or patient.get('medications','')),
                                       ('Antecedentes','\n\n'.join(k+': '+v.get('status','')+'\n'+v.get('notes','') for k,v in patient.get('histories',{}).items()) or patient.get('history','')),
                                       ('Notas clínicas',patient.get('clinical_notes','')), ('Notas administrativas',patient.get('administrative',''))]:
                    ttk.Label(overview.body,text=title,style='Section.TLabel').pack(anchor='w',pady=(14,5))
                    ttk.Label(overview.body,text=content.strip() or 'No registrado',wraplength=760,justify='left').pack(anchor='w')
                history = ttk.Frame(tabs)
                tabs.add(history,text='Consultas')
                tree = self.table(history,{'date':'Fecha','doctor':'Doctor','state':'Estado','reason':'Motivo'})
                doctors = {u['id']:u['name'] for u in self.auth.users()}
                for row in sorted(self.clinic.list('encounters'),key=lambda r:r['attended_at'],reverse=True):
                    if row['patient_id'] == identifier:
                        tree.insert('','end',iid=row['id'],values=(display_date(row['attended_at']),doctors.get(row['doctor_id'],'Doctor'),row['status'],row.get('reason','')))
                tree.bind('<Double-1>',lambda e:self.open_encounter(tree.selection()[0]) if tree.selection() else None)
                trend = ScrollFrame(tabs)
                tabs.add(trend,text='Evolución')
                TrendPanel(trend.body,self,identifier).pack(fill='both',expand=True)
                docs = ScrollFrame(tabs)
                tabs.add(docs,text='Documentos e imágenes')
                AttachmentPanel(docs.body,self,identifier).pack(fill='both',expand=True)
            frame.refresh = refresh
            return frame
        return self.mount('paciente:'+identifier,build)

    def encounter_editor(self, patient, record=None):
        record = record or self.clinic.save('encounters',{'patient_id':patient['id'],'status':'Borrador','attended_at':now()})
        return self.mount('consulta:'+record['id'],lambda parent:ConsultationEditor(parent,self,patient,record))

    def encounters(self, parent):
        self.heading(parent,'Consultas','Tus borradores y el historial compartido de atenciones finalizadas.')
        show_trash = tk.BooleanVar()
        ttk.Checkbutton(parent,text='Mostrar mi papelera de borradores',variable=show_trash,command=lambda:refresh()).pack(anchor='w')
        tree = self.table(parent,{'date':'Fecha','patient':'Paciente','doctor':'Doctor','state':'Estado','reason':'Motivo'})
        tree.column('patient',width=260)
        def refresh():
            tree.delete(*tree.get_children())
            patients = {p['id']:p for p in self.clinic.list('patients',True)}
            doctors = {u['id']:u['name'] for u in self.auth.users()}
            for row in sorted(self.clinic.list('encounters',True),key=lambda r:r['attended_at'],reverse=True):
                if bool(row.get('archived')) != show_trash.get(): continue
                tree.insert('','end',iid=row['id'],values=(display_date(row['attended_at']),patients[row['patient_id']]['name'],doctors.get(row['doctor_id'],'Doctor'),row['status'],row.get('reason','')))
        def open_row():
            if tree.selection(): self.open_encounter(tree.selection()[0])
        def remove():
            if not tree.selection(): return
            row = self.store.read('data/encounters/'+tree.selection()[0]+'.json')
            title = 'Restaurar borrador' if row.get('archived') else 'Anular consulta' if row['status'] == 'Finalizada' else 'Eliminar borrador'
            reason = simpledialog.askstring(title,'Consulta del '+display_date(row['attended_at'])+'\nSe conservarán el registro y su historial.\nMotivo:',parent=self)
            if reason:
                self.guard(lambda:self.clinic.archive('encounters',row['id'],reason,restore=row.get('archived',False),revision=row['revision']))
                refresh()
        bar = ttk.Frame(parent)
        bar.pack(fill='x')
        ttk.Button(bar,text='Abrir consulta',command=open_row).pack(side='left')
        ttk.Button(bar,text='Eliminar / anular / restaurar',style='Link.TButton',command=remove).pack(side='left',padx=12)
        tree.bind('<Double-1>',lambda e:open_row())
        tree.bind('<Return>',lambda e:open_row())
        parent.refresh = refresh

    def open_encounter(self, identifier):
        record = next((r for r in self.clinic.list('encounters',True) if r['id'] == identifier),None)
        if not record: return
        patient = self.store.read(f"data/patients/{record['patient_id']}.json")
        if record['status'] == 'Borrador' and not record.get('archived'):
            return self.encounter_editor(patient,record)
        def build(parent):
            frame = ttk.Frame(parent)
            def refresh():
                row = self.store.read(f'data/encounters/{identifier}.json')
                for child in frame.winfo_children(): child.destroy()
                ttk.Button(frame,text='‹ Expediente',style='Link.TButton',command=lambda:self.patient_record(patient['id'])).pack(anchor='w')
                self.heading(frame,patient['name'],display_date(row['attended_at'])+' · '+row['status'])
                actions = ttk.Frame(frame)
                actions.pack(fill='x',pady=6)
                doctor = next(u['name'] for u in self.auth.users() if u['id'] == row['doctor_id'])
                ttk.Button(actions,text='Vista previa / PDF',command=lambda:self.pdf_preview('Consulta médica',encounter_sections(row),doctor,patient['name'])).pack(side='left')
                ttk.Button(actions,text='Receta e indicaciones',command=lambda:self.pdf_preview('Receta e indicaciones',[('Fecha',display_date(row['attended_at'])),('Tratamiento','\n\n'.join(medication_text(m)+'\n'+m.get('instructions','') for m in row.get('prescriptions',[])) or row.get('medications','')),('Indicaciones',row.get('plan',''))],doctor,patient['name'])).pack(side='left',padx=8)
                if row['status'] == 'Finalizada':
                    def addendum():
                        win = self.window('Agregar adenda','700x500')
                        ttk.Label(win,text='Motivo',padding=10).pack(anchor='w')
                        reason = tk.StringVar()
                        ttk.Entry(win,textvariable=reason).pack(fill='x',padx=15)
                        text = text_editor(win,'',10)
                        text.pack(fill='both',expand=True,padx=15,pady=10)
                        def save():
                            self.clinic.addendum(identifier,reason.get(),text.get('1.0','end-1c'))
                            win.destroy(); refresh()
                        ttk.Button(win,text='Guardar adenda',command=lambda:self.guard(save)).pack(pady=10)
                        self.theme._walk(win)
                    ttk.Button(actions,text='Agregar adenda',command=addendum).pack(side='left')
                tabs = ttk.Notebook(frame)
                tabs.pack(fill='both',expand=True)
                scroll = ScrollFrame(tabs)
                tabs.add(scroll,text='Atención')
                ttk.Label(scroll.body,text='Responsable: '+doctor,style='Section.TLabel').pack(anchor='w',pady=10)
                for label,content in encounter_sections(row):
                    if content:
                        ttk.Label(scroll.body,text=label,style='Section.TLabel').pack(anchor='w',pady=(14,5))
                        ttk.Label(scroll.body,text=content,wraplength=760,justify='left').pack(anchor='w')
                docs = ScrollFrame(tabs)
                tabs.add(docs,text='Documentos')
                AttachmentPanel(docs.body,self,patient['id'],identifier).pack(fill='both',expand=True)
            frame.refresh = refresh
            return frame
        return self.mount('historia:'+identifier,build)
