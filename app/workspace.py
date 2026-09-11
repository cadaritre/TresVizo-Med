"""Navegación persistente y pantallas del espacio clínico."""
from datetime import date, datetime
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from app.components import ScrollFrame, Tooltip
from app.widgets import text_editor, Collapsible
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
        parent.day_changed = page.period_changed

    def login_screen(self):
        users = [u for u in self.auth.users() if u['active']]
        if not users:
            return self._legacy_login_screen()
        self.clear()
        self.theme.apply(self.appearance.tokens())
        from app.login_ui import LoginPage
        self.login_page = LoginPage(self, self, users)
        self.login_page.pack(fill='both', expand=True)
        self.theme._walk(self.login_page)

    def shell(self):
        self.session_generation += 1
        self.clear()
        self.theme.apply(self.appearance.tokens())
        self.activity()
        self.pages, self.nav_buttons, self.editors = {}, {}, []
        self._starting_patients = set()
        self.current_page = 'Pacientes'
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
        nav = ttk.Frame(self, style='Nav.TFrame', padding=8, width=int(210*self.ui_scale))
        nav.pack(side='left', fill='y')
        nav.pack_propagate(False)
        brand = self.brand(nav, 'Nav.TLabel', size=44)
        brand.pack(pady=(6,20))
        Tooltip(brand, 'TresVizo Med', self.theme)
        for name in ('Pacientes', 'Consultas', 'Más opciones'):
            button = ttk.Button(nav, text=name, style='Nav.TButton', command=lambda n=name: self.show(n))
            button.pack(fill='x', pady=2)
            self.nav_buttons[name] = button
            self.icons.bind(button,{'Pacientes':'users','Consultas':'stethoscope','Más opciones':'settings'}[name],token='on_sidebar', show_text=True)
        bottom = ttk.Frame(nav, style='Nav.TFrame')
        bottom.pack(side='bottom', fill='x', pady=12)
        for name in ('Exportar y respaldar', 'Acerca de'):
            button = ttk.Button(bottom, text=name, style='Nav.TButton', command=lambda n=name: self.show(n))
            button.pack(fill='x', pady=2)
            self.nav_buttons[name] = button
            self.icons.bind(button,'archive' if name == 'Exportar y respaldar' else 'info',token='on_sidebar', show_text=True)
        self.content = ttk.Frame(self, padding=(20,14))
        self.content.pack(side='left', fill='both', expand=True)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)
        self.show('Pacientes')

    def show(self, name):
        if not self.auth.current or self.locked:
            return
        capture = getattr(self, 'active_capture', None)
        if capture and capture.winfo_exists() and name != getattr(self, 'current_page', ''):
            capture.lift()
            return
        builders = {'Inicio': self.home, 'Pacientes': self.patients, 'Consultas': self.encounters,
                    'Más opciones': self.more_options,
                    'Mis estadísticas': self.statistics, 'Exportar y respaldar': self.exports,
                    'Configuración': self.settings, 'Acerca de': self.about,
                    'Mi perfil': lambda p: ProfileEditor(p,self).pack(fill='both', expand=True)}
        if name not in self.pages and name not in builders:
            raise ValueError('Esta sección ya no está disponible.')
        if name not in self.pages:
            frame = ttk.Frame(self.content)
            frame.grid(row=0, column=0, sticky='nsew')
            self.pages[name] = frame
            builders[name](frame)
        previous = self.pages.get(getattr(self, 'current_page', ''))
        focus = self.focus_get()
        if previous is not self.pages[name] and previous and focus and str(focus).startswith(str(previous)+'.'):
            previous.return_focus = focus
        self.pages[name].tkraise()
        self.current_page = name
        section = 'Pacientes' if name.startswith(('paciente:', 'alta:')) else 'Consultas' if name.startswith(('consulta:', 'historia:')) else name
        if section in ('Mis estadísticas', 'Configuración', 'Mi perfil', 'Inicio'):
            section = 'Más opciones'
        for key, button in self.nav_buttons.items():
            button.configure(style='Active.Nav.TButton' if key == section else 'Nav.TButton')
            button.refresh_icon()
        if hasattr(self.pages[name], 'refresh'):
            self.guard(self.pages[name].refresh)
        self.theme._walk(self.pages[name])
        self.pages[name].last_used = getattr(self, '_view_clock', 0)+1
        self._view_clock = self.pages[name].last_used
        if previous is not self.pages[name]:
            target = getattr(self.pages[name], 'return_focus', None) or getattr(self.pages[name], 'search_input', None)
            if target and target.winfo_exists():
                target.focus_set()
            else:
                self.pages[name].focus_set()
        self.prune_pages()

    def prune_pages(self):
        dynamic = [(key, page) for key, page in self.pages.items() if ':' in key]
        for key, page in sorted(dynamic, key=lambda item: getattr(item[1], 'last_used', 0)):
            if len(dynamic) <= 8:
                break
            edit_state = getattr(page, 'state', None)
            if key == self.current_page or isinstance(edit_state, dict) and edit_state.get('dirty'):
                continue
            capture = getattr(self, 'active_capture', None)
            if capture and capture.winfo_exists() and getattr(capture, 'owner', None) is page:
                continue
            def busy(widget):
                return getattr(widget, 'busy', False) is True or any(busy(child) for child in widget.winfo_children())
            if busy(page):
                continue
            self.pages.pop(key)
            page.destroy()
            dynamic = [(k, p) for k, p in dynamic if k != key]
        self.editors = [(widget, save, state) for widget, save, state in self.editors if widget.winfo_exists()]

    def focus_patient_search(self, event=None):
        if self.auth.current and not self.locked:
            self.show('Pacientes')
            if self.current_page == 'Pacientes':
                self.pages['Pacientes'].search_input.focus_set()
        return 'break'

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
        focus = self.focus_get()
        windows = [w for w in self.winfo_children() if isinstance(w,tk.Toplevel)]
        self.withdraw()
        for win in windows:
            win.withdraw()
        capture = getattr(self, 'active_capture', None)
        if capture and capture.winfo_exists():
            capture.grab_release()
            if hasattr(capture, 'persist_feedback'):
                capture.persist_feedback()
            if hasattr(capture.owner, 'save_feedback'):
                capture.owner.save_feedback()
        self.theme.apply(self.appearance.list()[self.appearance.state['clinic']]['tokens'])
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
            self.theme.apply(self.appearance.tokens())
            self.activity()
            self.deiconify()
            for win in windows:
                if win.winfo_exists():
                    win.deiconify()
            if focus and focus.winfo_exists():
                focus.focus_set()
            if capture and capture.winfo_exists():
                capture.grab_set()
        ttk.Button(cover, text='Desbloquear', style='Primary.TButton', command=lambda: self.guard(unlock)).pack(pady=10)
        ttk.Button(cover, text='Cambiar doctor', command=lambda: (cover.destroy(), setattr(self,'locked',False), self.logout())).pack()
        entry.bind('<Return>', lambda e: self.guard(unlock))
        self.theme._walk(cover)
        entry.focus_set()

    def more_options(self, parent):
        scroll = ScrollFrame(parent)
        scroll.pack(fill='both', expand=True)
        self.heading(scroll.body, 'Más opciones', 'Herramientas complementarias, disponibles cuando las necesites.')
        for name, description, destination, icon in [
                ('Registros en curso', 'Retomar un alta incompleta o una consulta en borrador.', 'Inicio', 'clipboard-list'),
                ('Mis estadísticas', 'Consultar actividad, filtros y gráficas detalladas.', 'Mis estadísticas', 'chart-no-axes-combined'),
                ('Configuración', 'Apariencia, identidad de la clínica, doctores y preferencias.', 'Configuración', 'settings'),
                ('Exportar y respaldar', 'Exportaciones, copias de seguridad e importación administrativa.', 'Exportar y respaldar', 'archive'),
                ('Mi perfil', 'Datos profesionales y avatar.', 'Mi perfil', 'users')]:
            box = ttk.Frame(scroll.body, style='Card.TFrame', padding=12)
            box.pack(fill='x', pady=5)
            button = ttk.Button(box, text=name, command=lambda n=destination: self.show(n))
            button.pack(anchor='w')
            self.icons.bind(button, icon, show_text=True)
            label = ttk.Label(box, text=description, style='Card.TLabel', wraplength=700)
            label.pack(fill='x', pady=(6, 0))
            box.bind('<Configure>', lambda e, label=label: label.configure(wraplength=max(180, e.width-24)))

    def home(self, parent):
        scroll = ScrollFrame(parent)
        scroll.pack(fill='both', expand=True)
        self.heading(scroll.body, 'Registros en curso', 'Borradores privados del doctor activo.')
        ttk.Button(scroll.body, text='Buscar paciente', command=self.focus_patient_search).pack(anchor='w', pady=8)
        lists = {}
        for key, title in [('drafts', 'Consultas por continuar'), ('registrations', 'Altas de pacientes incompletas')]:
            ttk.Label(scroll.body, text=title, style='Section.TLabel').pack(anchor='w', pady=(12, 6))
            lists[key] = ttk.Frame(scroll.body)
            lists[key].pack(fill='x')
        ticket = [0]
        def refresh():
            ticket[0] += 1
            request = ticket[0]
            actor = self.auth.current['id']
            def gather():
                patients = {p['id']: p for p in self.clinic.list('patients', True)}
                drafts = [r for r in self.clinic.list('encounters') if r['status'] == 'Borrador' and r['doctor_id'] == actor]
                return patients, {'drafts': drafts, 'registrations': self.care.drafts()}
            def done(result):
                if not parent.winfo_exists() or request != ticket[0]: return
                patients, data = result
                for key, box in lists.items():
                    for child in box.winfo_children(): child.destroy()
                    for row in data[key]:
                        line = ttk.Frame(box, style='Card.TFrame', padding=8)
                        line.pack(fill='x', pady=3)
                        patient = patients.get(row.get('patient_id'), {})
                        name = row.get('payload', {}).get('name') or patient.get('name') or 'Registro sin nombre'
                        label = ttk.Label(line, text=name+' · '+patient.get('file_number', '')+' · '+display_date(row.get('updated_at', '')), style='Card.TLabel', wraplength=650)
                        label.pack(side='left', fill='x', expand=True)
                        command = (lambda r=row: self.open_encounter(r['id'])) if key == 'drafts' else (lambda r=row: self.patient_editor(draft=r))
                        ttk.Button(line, text='Retomar', command=command).pack(side='right')
                        line.bind('<Configure>', lambda e, label=label: label.configure(wraplength=max(180, e.width-140)))
                    if not data[key]:
                        ttk.Label(box, text='No hay registros pendientes.', style='Subtitle.TLabel').pack(anchor='w')
            self.background(gather, done)
        parent.refresh = refresh

    def patients(self, parent):
        heading = ttk.Frame(parent)
        heading.pack(fill='x')
        self.heading(heading, 'Pacientes', 'Busca por nombre, expediente o contacto · Ctrl+K')
        tools = ttk.Frame(parent)
        tools.pack(fill='x', pady=(0, 8))
        new = ttk.Button(tools, text='Nuevo paciente', style='Primary.TButton', command=lambda: self.patient_editor(attend=True))
        new.pack(side='left')
        self.icons.bind(new, 'plus', show_text=True)
        ttk.Button(tools, text='Registros en curso', style='Link.TButton', command=lambda: self.show('Inicio')).pack(side='left', padx=12)
        bar = ttk.Frame(parent)
        bar.pack(fill='x')
        query = tk.StringVar()
        ttk.Label(bar, text='Buscar').pack(side='left', padx=(0,8))
        parent.search_input = ttk.Entry(bar, textvariable=query, font=('Segoe UI', 13))
        parent.search_input.pack(side='left', fill='x', expand=True)
        mode = tk.StringVar(value='Activos')
        mode_box = ttk.Combobox(bar, textvariable=mode, values=['Activos','Archivados','Todos'], state='readonly', width=12)
        mode_box.pack(side='left', padx=8)
        ttk.Button(bar, text='Limpiar', style='Link.TButton', command=lambda: (query.set(''), mode.set('Activos'))).pack(side='left')
        tree = self.table(parent, {'name':'Paciente', 'file':'Expediente', 'age':'Edad', 'phone':'Contacto'})
        tree.column('name', width=330)
        tree.column('file', width=120, stretch=False)
        tree.column('age', width=125)
        bottom = ttk.Frame(parent)
        bottom.pack(side='bottom', fill='x', before=tree.master)
        open_button = ttk.Button(bottom, text='Abrir expediente', command=lambda: self.patient_record(tree.selection()[0]) if tree.selection() else None, state='disabled')
        open_button.pack(side='left')
        attend_button = ttk.Button(bottom, text='Atender / retomar', style='Primary.TButton', command=lambda: self.confirm_encounter(self.store.read('data/patients/'+tree.selection()[0]+'.json')) if tree.selection() else None, state='disabled')
        attend_button.pack(side='left', padx=8)
        def selected_changed(event=None):
            row = self.store.read('data/patients/'+tree.selection()[0]+'.json') if tree.selection() else None
            new.configure(style='TButton' if row and not row.get('archived') else 'Primary.TButton')
            new.refresh_icon()
            open_button.state(['!disabled'] if row else ['disabled'])
            attend_button.state(['!disabled'] if row and not row.get('archived') else ['disabled'])
        tree.bind('<<TreeviewSelect>>', selected_changed)
        def select_result(event=None):
            if tree.get_children():
                tree.focus_set()
                tree.selection_set(tree.get_children()[0])
                tree.focus(tree.get_children()[0])
            return 'break'
        parent.search_input.bind('<Down>', select_result)
        def export_filtered():
            from app.export_ui import export_patients
            q, current_mode, selected = query.get(), mode.get(), list(tree.selection())
            def work():
                total = self.clinic.search_patients(q, current_mode)[1]
                return [r['id'] for r in self.clinic.search_patients(q, current_mode, page_size=max(1, total))[0]]
            self.background(work, lambda identifiers: export_patients(self, identifiers, selected))
        more = ttk.Menubutton(bottom, text='Más acciones')
        more.pack(side='left', padx=8)
        advanced = tk.Menu(more, tearoff=False)
        advanced.add_command(label='Exportar pacientes…', command=export_filtered)
        more.configure(menu=advanced)
        if self.auth.current['role'] == 'admin':
            def archive():
                if not tree.selection(): return
                row = self.store.read('data/patients/'+tree.selection()[0]+'.json')
                reason = simpledialog.askstring('Restaurar paciente' if row.get('archived') else 'Eliminar de la lista', row['name']+' · '+row['file_number']+'\nEl expediente y su historial se conservarán.\nMotivo:', parent=self)
                if reason:
                    self.guard(lambda:self.clinic.archive('patients',row['id'],reason,restore=row.get('archived',False),revision=row['revision']))
                    refresh()
            advanced.add_command(label='Archivar / restaurar paciente…', command=archive)
        pagination = ttk.Frame(parent)
        pagination.pack(side='bottom', fill='x', pady=5, before=bottom)
        page = [0]
        count = ttk.Label(pagination, style='Subtitle.TLabel')
        count.pack(side='right')
        def turn(delta):
            page[0] = max(0,page[0]+delta)
            refresh()
        ttk.Button(pagination, text='›', width=3, command=lambda:turn(1)).pack(side='right')
        ttk.Button(pagination, text='‹', width=3, command=lambda:turn(-1)).pack(side='right')
        timer = [None]
        ticket = [0]
        def refresh():
            ticket[0] += 1
            current = ticket[0]
            q, selected_mode, page_number = normalized(query.get()), mode.get(), page[0]
            count.configure(text='Buscando…')
            def work():
                return self.clinic.search_patients(q, selected_mode, page_number)
            def done(result):
                if not parent.winfo_exists() or current != ticket[0]: return
                rows, total, page[0] = result
                selected, position = tree.selection(), tree.yview()[0]
                preferred = getattr(parent, 'preferred_patient', None)
                if preferred and any(row['id'] == preferred for row in rows):
                    selected = (preferred,)
                    parent.preferred_patient = None
                tree.delete(*tree.get_children())
                for row in rows:
                    tree.insert('', 'end', iid=row['id'], values=(row['name']+(' · Archivado' if row.get('archived') else ''),row['file_number'],age_label(row),row.get('phone','')))
                if selected and tree.exists(selected[0]):
                    tree.selection_set(selected[0])
                    tree.yview_moveto(position)
                count.configure(text=f'{total} pacientes · página {page[0]+1}')
                if not total:
                    count.configure(text='Sin resultados · limpia los filtros o registra un paciente' if q or selected_mode != 'Activos' else 'Aún no hay pacientes · usa Nuevo paciente')
                selected_changed()
            self.background(work, done)
        def changed(*args):
            if timer[0]: parent.after_cancel(timer[0])
            page[0] = 0
            timer[0] = parent.after(250,refresh)
        query.trace_add('write',changed)
        mode_box.bind('<<ComboboxSelected>>',changed)
        tree.bind('<Double-1>',lambda e:self.patient_record(tree.selection()[0]) if tree.selection() else None)
        tree.bind('<Return>',lambda e:self.patient_record(tree.selection()[0]) if tree.selection() else None)
        parent.refresh = refresh

    def patient_editor(self, record=None, refresh=lambda:None, draft=None, on_created=None, attend=False):
        if draft:
            if draft.get('patient_id'):
                record = self.store.read(f"data/patients/{draft['patient_id']}.json")
        elif record:
            draft = next((d for d in self.care.drafts() if d.get('patient_id') == record['id']),None)
        draft = draft or self.care.save_draft(record or {}, patient_id=(record or {}).get('id'), revision=(record or {}).get('revision'))
        editor = self.mount('alta:'+draft['id'], lambda parent:PatientEditor(parent,self,record,draft,attend=attend))
        if on_created:
            editor.on_created = on_created
        return editor

    def patient_record(self, identifier):
        def build(parent):
            frame = ttk.Frame(parent)
            def render(encounters):
                signature = (self.store.generation('patients'), self.store.generation('encounters'), self.store.generation('attachments'))
                if getattr(frame, 'record_signature', None) == signature:
                    return
                old_tabs = next((w for w in frame.winfo_children() if isinstance(w, ttk.Notebook)), None)
                selected_tab = old_tabs.index('current') if old_tabs else 0
                old_position = {}
                if old_tabs:
                    for index, child in enumerate(old_tabs.winfo_children()):
                        if isinstance(child, ScrollFrame):
                            old_position[index] = child.canvas.yview()[0]
                    panel = getattr(frame, 'documents_panel', None)
                    if panel and (panel.busy or any(r['status'] != 'Guardado' for r in panel.queue)):
                        current = self.store.read(f'data/patients/{identifier}.json')
                        allergy = ', '.join(r.get('substance', '') for r in current.get('allergy_records', [])) or current.get('allergies') or current.get('allergy_status', 'No interrogado')
                        frame.allergy_label.configure(text='⚠ Alergias: '+allergy)
                        return
                for child in frame.winfo_children(): child.destroy()
                patient = self.store.read(f'data/patients/{identifier}.json')
                bar = ttk.Frame(frame)
                bar.pack(fill='x')
                ttk.Button(bar,text='‹ Pacientes',style='Link.TButton',command=lambda:self.show('Pacientes')).pack(side='left')
                ttk.Button(bar,text='Editar',command=lambda:self.patient_editor(patient)).pack(side='right')
                ttk.Button(bar,text='Atender / retomar',style='Primary.TButton',command=lambda:self.confirm_encounter(patient),state='disabled' if patient.get('archived') else 'normal').pack(side='right',padx=8)
                self.heading(frame,patient['name'],patient['file_number']+' · '+age_label(patient)+' · '+patient.get('sex','No especificado')+(' · Archivado' if patient.get('archived') else ''))
                if patient.get('photo_attachment_id'):
                    try:
                        from PIL import Image,ImageTk
                        image_path = self.attachments.thumbnail(patient['photo_attachment_id'],80)
                        if image_path:
                            with Image.open(image_path) as source:
                                frame.patient_photo = ImageTk.PhotoImage(source.copy(),master=self)
                            ttk.Label(frame,image=frame.patient_photo).pack(anchor='w',pady=4)
                    except (ValueError,OSError):
                        ttk.Label(frame,text='Foto no disponible',style='Subtitle.TLabel').pack(anchor='w')
                allergy = ', '.join(r.get('substance','') for r in patient.get('allergy_records',[])) or patient.get('allergies') or patient.get('allergy_status','No interrogado')
                frame.allergy_label = ttk.Label(frame,text='⚠ Alergias: '+allergy,style='warning.TLabel',wraplength=850)
                frame.allergy_label.pack(fill='x',pady=6)
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
                for row in sorted(encounters,key=lambda r:r['attended_at'],reverse=True):
                    if row['patient_id'] == identifier:
                        tree.insert('','end',iid=row['id'],values=(display_date(row['attended_at']),doctors.get(row['doctor_id'],'Doctor'),row['status'],row.get('reason','')))
                open_visit = ttk.Button(history, text='Abrir atención completa', command=lambda: self.open_encounter(tree.selection()[0]) if tree.selection() else None, state='disabled')
                open_visit.pack(side='bottom', fill='x', pady=6, before=tree.master)
                tree.bind('<<TreeviewSelect>>', lambda e: open_visit.state(['!disabled'] if tree.selection() else ['disabled']))
                tree.bind('<Return>', lambda e: open_visit.invoke())
                tree.bind('<Double-1>', lambda e: open_visit.invoke())
                trend = ScrollFrame(tabs)
                tabs.add(trend,text='Evolución')
                TrendPanel(trend.body,self,identifier).pack(fill='both',expand=True)
                docs = ScrollFrame(tabs)
                tabs.add(docs,text='Documentos e imágenes')
                frame.documents_panel = AttachmentPanel(docs.body,self,identifier)
                frame.documents_panel.pack(fill='both',expand=True)
                tabs.select(min(selected_tab, len(tabs.tabs())-1))
                for index, child in enumerate(tabs.winfo_children()):
                    if isinstance(child, ScrollFrame) and index in old_position:
                        child.canvas.update_idletasks()
                        child.canvas.yview_moveto(old_position[index])
                frame.record_signature = signature
            ticket = [0]
            ttk.Label(frame, text='Cargando expediente…', style='Subtitle.TLabel').pack(anchor='w', pady=12)
            def refresh():
                signature = (self.store.generation('patients'), self.store.generation('encounters'), self.store.generation('attachments'))
                if getattr(frame, 'record_signature', None) == signature:
                    return
                ticket[0] += 1
                request = ticket[0]
                actor = self.auth.require()['id']
                def gather():
                    rows = self.store.select_records('encounters', lambda r: r['patient_id'] == identifier and not r.get('archived') and
                        (r['status'] != 'Borrador' or r['doctor_id'] == actor))
                    self.attachments.list(identifier)
                    patient = self.store.read(f'data/patients/{identifier}.json')
                    if patient.get('photo_attachment_id'):
                        try:
                            self.attachments.thumbnail(patient['photo_attachment_id'], 80)
                        except (ValueError, OSError):
                            pass
                    return rows
                def ready(rows):
                    if frame.winfo_exists() and request == ticket[0]:
                        render(rows)
                        self.theme._walk(frame)
                self.background(gather, ready)
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
        page, ticket = [0], [0]
        def refresh():
            ticket[0] += 1
            current, trash, page_number = ticket[0], show_trash.get(), page[0]
            def work():
                patients = {p['id']:p for p in self.clinic.list('patients', True)}
                doctors = {u['id']:u['name'] for u in self.auth.users()}
                rows = sorted([r for r in self.clinic.list('encounters', True) if bool(r.get('archived')) == trash], key=lambda r:r['attended_at'], reverse=True)
                current_page = min(page_number, max(0,(len(rows)-1)//100))
                return rows[current_page*100:current_page*100+100], patients, doctors, len(rows), current_page
            def done(result):
                if not parent.winfo_exists() or current != ticket[0]: return
                rows, patients, doctors, total, page[0] = result
                selected, position = tree.selection(), tree.yview()[0]
                tree.delete(*tree.get_children())
                for row in rows:
                    patient = patients.get(row['patient_id'], {})
                    name = patient.get('name', 'Expediente no disponible')+(' · Archivado' if patient.get('archived') else '')
                    tree.insert('', 'end', iid=row['id'], values=(display_date(row['attended_at']),name,doctors.get(row['doctor_id'],'Doctor'),row['status'],row.get('reason','')))
                if selected and tree.exists(selected[0]):
                    tree.selection_set(selected[0]); tree.yview_moveto(position)
                count.configure(text=f'{total} consultas · página {page[0]+1}')
            self.background(work, done)
        def open_row():
            if tree.selection(): self.open_encounter(tree.selection()[0])
        def remove():
            if not tree.selection(): return
            row = self.store.read('data/encounters/'+tree.selection()[0]+'.json')
            restoring = row.get('archived', False) or row['status'] == 'Anulada'
            title = 'Restaurar consulta' if restoring else 'Anular consulta' if row['status'] == 'Finalizada' else 'Archivar borrador'
            effect = 'La consulta finalizada volverá a contar en estadísticas.' if row['status'] == 'Anulada' else 'La consulta dejará de contar en estadísticas. El registro y sus documentos se conservan.' if row['status'] == 'Finalizada' else 'El borrador y sus documentos se conservan para recuperación.'
            reason = simpledialog.askstring(title,'Consulta del '+display_date(row['attended_at'])+'\n'+effect+'\nMotivo:',parent=self)
            if reason:
                def apply():
                    editor = self.pages.get('consulta:'+row['id'])
                    if editor and editor.winfo_exists() and editor.state['dirty']:
                        editor.save()
                    current = self.store.read('data/encounters/'+row['id']+'.json')
                    self.clinic.archive('encounters',row['id'],reason,restore=restoring,revision=current['revision'])
                    if editor and editor.winfo_exists():
                        editor.state['dirty'] = False
                        self.pages.pop('consulta:'+row['id'], None)
                        editor.destroy()
                self.guard(apply)
                refresh()
        bar = ttk.Frame(parent)
        bar.pack(side='bottom', fill='x', before=tree.master)
        ttk.Button(bar,text='Abrir consulta',command=open_row).pack(side='left')
        lifecycle = ttk.Button(bar,text='Selecciona una consulta',style='Link.TButton',command=remove, state='disabled')
        lifecycle.pack(side='left',padx=12)
        def selection_changed(event=None):
            row = self.store.read('data/encounters/'+tree.selection()[0]+'.json') if tree.selection() else None
            allowed = row and (row['doctor_id'] == self.auth.current['id'] or self.auth.current['role'] == 'admin' and row['status'] != 'Borrador')
            lifecycle.configure(text=('Restaurar consulta' if row.get('archived') or row['status'] == 'Anulada' else 'Anular consulta' if row['status'] == 'Finalizada' else 'Archivar borrador') if row else 'Selecciona una consulta', state='normal' if allowed else 'disabled')
        tree.bind('<<TreeviewSelect>>', selection_changed)
        count = ttk.Label(bar, style='Subtitle.TLabel')
        count.pack(side='right')
        def turn(delta):
            page[0] = max(0, page[0]+delta)
            refresh()
        ttk.Button(bar, text='›', width=3, command=lambda: turn(1)).pack(side='right')
        ttk.Button(bar, text='‹', width=3, command=lambda: turn(-1)).pack(side='right')
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
                authors = {u['id']: u['name'] for u in self.auth.users()}
                profile = self.profiles.get(row['doctor_id'])
                professional = ' · '.join(filter(None, [doctor, profile.get('specialty'), profile.get('license'), profile.get('professional_phone')]))
                ttk.Button(actions,text='Vista previa / PDF',command=lambda:self.pdf_preview('Consulta médica',encounter_sections(row, authors),professional,patient['name'])).pack(side='left')
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
                scroll = ScrollFrame(frame)
                scroll.pack(fill='both', expand=True)
                ttk.Label(scroll.body, text='Responsable: '+doctor, style='Section.TLabel').pack(anchor='w', pady=10)
                allergy = ', '.join(r.get('substance', '') for r in patient.get('allergy_records', [])) or patient.get('allergies') or patient.get('allergy_status') or 'No interrogadas'
                ttk.Label(scroll.body, text='⚠ Alergias: '+allergy, style='warning.TLabel', wraplength=900).pack(fill='x', pady=6)
                for label, content in encounter_sections(row, authors):
                    if content:
                        ttk.Label(scroll.body, text=label, style='Section.TLabel').pack(anchor='w', pady=(14, 5))
                        value = ttk.Label(scroll.body, text=content, wraplength=900, justify='left')
                        value.pack(fill='x')
                        value.bind('<Configure>', lambda e, w=value: w.configure(wraplength=max(200, e.width-12)))
                from app.consultation_ui import ConsultationDocuments
                ConsultationDocuments(scroll.body, self, patient, row).pack(fill='x', pady=12)
            frame.refresh = refresh
            return frame
        return self.mount('historia:'+identifier,build)
