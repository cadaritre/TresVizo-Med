from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from concurrent.futures import ThreadPoolExecutor
from app.storage import Store, InstanceLock, DataError
from app.services import Auth, Clinic, normalized, now
from app.themes import Appearance, luminance
from app.ui_theme import ThemeManager
from app.branding import Identity, logo_photo, ASSETS
from app.appearance_ui import AppearanceEditor
from app.components import ScrollFrame, field, DatePicker, Chart, Tooltip
from app.transfer import Transfer


class Application(tk.Tk):
    def __init__(self, data_dir=None):
        super().__init__()
        self.withdraw()
        self.store = Store(data_dir)
        self.instance = InstanceLock(self.store.root)
        self.auth = Auth(self.store)
        self.clinic = Clinic(self.store, self.auth)
        self.transfer = Transfer(self.store, self.auth, self.clinic)
        self.appearance = Appearance(self.store, self.auth)
        self.identity = Identity(self.store, self.auth)
        self.theme = ThemeManager(self)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.pending = set()
        self.session_generation = 0
        self.editors = []
        self.locked = False
        self.last_activity = time.monotonic()
        self.status = tk.StringVar(value='Datos guardados localmente en Documentos.')
        self.title(self.identity.values['app_name'])
        scale = max(1.0, float(self.tk.call('tk', 'scaling'))/(96/72))
        self.ui_scale = scale
        width = min(int(1220*scale), self.winfo_screenwidth()-40)
        height = min(int(820*scale), self.winfo_screenheight()-70)
        self.geometry(f'{width}x{height}')
        self.minsize(min(940, width), min(640, height))
        self.logo = logo_photo(96)
        self.iconphoto(True, self.logo)
        if (ASSETS / 'tresvizo_medico.ico').exists():
            self.iconbitmap(str(ASSETS / 'tresvizo_medico.ico'))
        self.theme.apply(self.appearance.tokens())
        self.bind_all('<KeyPress>', self.activity, add='+')
        self.bind_all('<ButtonPress>', self.activity, add='+')
        self.bind('<Control-k>', lambda e: self.show('Pacientes') if self.auth.current else None)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(1000, self.check_idle)
        self.login_screen()
        self.deiconify()

    def activity(self, event=None):
        self.last_activity = time.monotonic()

    def guard(self, fn):
        try:
            return fn()
        except (DataError, OSError, ValueError) as exc:
            messagebox.showerror('No se pudo completar', str(exc), parent=self)
            return None

    def report_callback_exception(self, exc, value, tb):
        messagebox.showerror('Error', f'La operación no se completó ({exc.__name__}). Conserva tus cambios y vuelve a intentar.', parent=self)
        import traceback
        traceback.print_exception(exc, value, tb)

    def clear(self):
        for widget in self.winfo_children():
            widget.destroy()

    def brand(self, parent, style='TLabel'):
        label = ttk.Label(parent, style=style)
        def refresh(tokens):
            background = tokens['sidebar'] if style == 'Nav.TLabel' else tokens['background']
            label.logo = logo_photo(96, dark=luminance(background) < .25)
            label.configure(image=label.logo)
        self.theme.subscribe(label, refresh)
        return label

    def login_screen(self):
        self.clear()
        self.theme.apply(self.appearance.tokens())
        login_scroll = ScrollFrame(self)
        login_scroll.pack(fill='both', expand=True)
        login_scroll.body.columnconfigure(0, weight=1)
        outer = ttk.Frame(login_scroll.body, padding=40)
        outer.grid(row=0, column=0, pady=24)
        self.brand(outer).pack(pady=8)
        ttk.Label(outer, text='TresVizo', font=('Segoe UI Semibold', 27)).pack()
        ttk.Label(outer, text=self.identity.values['app_name'], style='Subtitle.TLabel').pack(pady=(0, 18))
        users = [u for u in self.auth.users() if u['active']]
        if not users:
            ttk.Label(outer, text='Bienvenido · Configura tu clínica', font=('Segoe UI Semibold', 16)).pack(anchor='w')
            clinic, _ = field(outer, 'Nombre de la clínica')
            name, _ = field(outer, 'Nombre del primer administrador')
            username, _ = field(outer, 'Usuario')
            password, entry = field(outer, 'Contraseña · al menos 10 caracteres', secret=True)
            def setup():
                if not clinic.get().strip():
                    raise DataError('Escribe el nombre de la clínica.')
                uid = self.auth.create_user(name.get(), username.get(), password.get())
                self.auth.login(uid, password.get())
                self.identity.save({'clinic_name': clinic.get()})
                password.set('')
                self.shell()
            ttk.Button(outer, text='Crear clínica y entrar', style='Primary.TButton', command=lambda: self.guard(setup)).pack(fill='x', pady=18)
        else:
            ttk.Label(outer, text=self.identity.values['clinic_name'], font=('Segoe UI Semibold', 16)).pack(pady=8)
            user_id = tk.StringVar(value=users[0]['id'])
            accounts = ScrollFrame(outer)
            accounts.canvas.configure(height=min(150, len(users)*48), width=420)
            accounts.pack(fill='x')
            for user in users:
                initials = ''.join(n[0] for n in user['name'].split()[:2]).upper()
                ttk.Radiobutton(accounts.body, text=f"{initials}   {user['name']}  ·  {user['username']}",
                                value=user['id'], variable=user_id).pack(fill='x', pady=6)
            password, entry = field(outer, 'Contraseña', secret=True)
            show = tk.BooleanVar()
            ttk.Checkbutton(outer, text='Mostrar contraseña', variable=show,
                            command=lambda: entry.configure(show='' if show.get() else '•')).pack(anchor='w', pady=6)
            def login():
                self.auth.login(user_id.get(), password.get())
                password.set('')
                self.shell()
            entry.bind('<Return>', lambda e: self.guard(login))
            ttk.Button(outer, text='Iniciar sesión', style='Primary.TButton', command=lambda: self.guard(login)).pack(fill='x', pady=14)
        ttk.Button(outer, text=self.identity.values['website_text']+' ↗', command=lambda: self.guard(self.identity.open_website)).pack(pady=(10, 0))
        self.theme._walk(outer)

    def shell(self):
        self.session_generation += 1
        self.clear()
        self.theme.apply(self.appearance.tokens())
        self.activity()
        self.pages = {}
        self.editors = []
        header = ttk.Frame(self, style='Header.TFrame', padding=(20, 12))
        header.pack(fill='x')
        ttk.Label(header, text=self.identity.values['clinic_name'], style='Header.TLabel', font=('Segoe UI Semibold', 16)).pack(side='left')
        ttk.Button(header, text='Bloquear / Cambiar doctor', command=self.logout).pack(side='right')
        ttk.Label(header, text=self.auth.current['name']+'   ', style='Header.TLabel').pack(side='right')
        ttk.Label(self, textvariable=self.status, padding=(20, 6)).pack(side='bottom', fill='x')
        nav_scroll = ScrollFrame(self)
        nav_scroll.canvas.configure(width=int(180*self.ui_scale))
        nav_scroll.canvas.own_palette = True
        self.theme.subscribe(nav_scroll, lambda t: nav_scroll.canvas.configure(background=t['sidebar']))
        nav_scroll.pack(side='left', fill='y')
        nav = nav_scroll.body
        nav.configure(style='Nav.TFrame', padding=12)
        self.brand(nav, 'Nav.TLabel').pack(pady=(8, 0))
        ttk.Label(nav, text='TresVizo', style='Nav.TLabel', font=('Segoe UI Semibold', 19)).pack(pady=(0, 24))
        for name in ('Inicio', 'Pacientes', 'Consultas', 'Agenda', 'Seguimientos', 'Mis estadísticas', 'Exportar y respaldar', 'Configuración', 'Acerca de'):
            ttk.Button(nav, text=name, style='Nav.TButton', command=lambda n=name: self.show(n)).pack(fill='x', pady=3)
        self.content = ttk.Frame(self, padding=18)
        self.content.pack(side='left', fill='both', expand=True)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)
        self.show('Inicio')

    def show(self, name):
        if not self.auth.current:
            return
        builders = {'Inicio': self.home, 'Pacientes': self.patients, 'Consultas': self.encounters,
                    'Agenda': lambda p: self.schedule(p, 'appointments'), 'Seguimientos': lambda p: self.schedule(p, 'followups'),
                    'Mis estadísticas': self.statistics, 'Exportar y respaldar': self.exports, 'Configuración': self.settings, 'Acerca de': self.about}
        if name not in self.pages:
            frame = ttk.Frame(self.content)
            frame.grid(row=0, column=0, sticky='nsew')
            self.pages[name] = frame
            builders[name](frame)
        self.pages[name].tkraise()
        if hasattr(self.pages[name], 'refresh'):
            self.guard(self.pages[name].refresh)
        self.theme._walk(self.pages[name])

    def heading(self, parent, title, hint=''):
        ttk.Label(parent, text=title, style='Title.TLabel').pack(anchor='w', pady=(0, 6))
        if hint:
            ttk.Label(parent, text=hint, style='Subtitle.TLabel', wraplength=780).pack(anchor='w', pady=(0, 16))

    def home(self, parent):
        self.heading(parent, 'Tu jornada, en un lugar', 'Selecciona un paciente, revisa sus antecedentes y documenta la atención.')
        cards = ttk.Frame(parent)
        cards.pack(fill='x', pady=12)
        values = []
        for label in ('Consultas este mes', 'Pacientes atendidos', 'Nuevos para ti'):
            card = ttk.Frame(cards, style='Card.TFrame', padding=20)
            card.pack(side='left', fill='both', expand=True, padx=(0, 12))
            number = ttk.Label(card, text='—', style='Metric.TLabel')
            number.pack(anchor='w')
            ttk.Label(card, text=label, style='Card.TLabel').pack(anchor='w')
            values.append(number)
        ttk.Button(parent, text='Buscar o registrar paciente', style='Primary.TButton', command=lambda: self.show('Pacientes')).pack(anchor='w', pady=20)
        chart = Chart(parent, self.theme)
        chart.pack(fill='x', pady=12)
        ttk.Label(parent, text='⚠ Los campos vacíos de antecedentes no significan “sin alergias”.', style='warning.TLabel').pack(fill='x', pady=12)
        def refresh():
            today = date.today()
            self.background(lambda: self.clinic.statistics(today.replace(day=1).isoformat(), today.isoformat()),
                            lambda data: ([w.configure(text=str(data[k])) for w, k in zip(values, ('consultations', 'patients', 'new'))], chart.set(data['activity'])))
        parent.refresh = refresh

    def background(self, work, done):
        generation = self.session_generation
        future = self.executor.submit(work)
        self.pending.add(future)
        def poll():
            if future.done():
                self.pending.discard(future)
            if generation != self.session_generation or not self.auth.current:
                return
            if not future.done():
                self.after(50, poll)
                return
            self.guard(lambda: done(future.result()))
        self.after(50, poll)

    def table(self, parent, columns):
        box = ttk.Frame(parent)
        box.pack(fill='both', expand=True, pady=10)
        tree = ttk.Treeview(box, columns=list(columns), show='headings', selectmode='browse')
        for key, title in columns.items():
            tree.heading(key, text=title, command=lambda k=key: self.sort_table(tree, k))
            tree.column(key, width=150, minwidth=65)
        scroll = ttk.Scrollbar(box, command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True)
        return tree

    @staticmethod
    def sort_table(tree, key):
        for index, (_, row) in enumerate(sorted((tree.set(r, key), r) for r in tree.get_children())):
            tree.move(row, '', index)

    def patients(self, parent):
        self.heading(parent, 'Pacientes', 'Busca por nombre, expediente o teléfono. Los expedientes se comparten entre doctores.')
        bar = ttk.Frame(parent)
        bar.pack(fill='x')
        query = tk.StringVar()
        entry = ttk.Entry(bar, textvariable=query)
        entry.pack(side='left', fill='x', expand=True, padx=(0, 12))
        ttk.Button(bar, text='Nuevo paciente', style='Primary.TButton', command=lambda: self.patient_editor(refresh=parent.refresh)).pack(side='right')
        tree = self.table(parent, {'file': 'Expediente', 'name': 'Nombre', 'birth': 'Nacimiento', 'phone': 'Teléfono'})
        def refresh():
            tree.delete(*tree.get_children())
            rows = self.clinic.list('patients')
            for r in rows:
                if normalized(query.get()) in normalized(' '.join(str(r.get(k, '')) for k in ('name', 'file_number', 'phone'))):
                    tree.insert('', 'end', iid=r['id'], values=(r['file_number'], r['name'], r.get('birth_date', '') or 'Desconocido', r.get('phone', '')))
        parent.refresh = refresh
        query.trace_add('write', lambda *a: self.guard(refresh))
        tree.bind('<Double-1>', lambda e: self.patient_record(tree.selection()[0]) if tree.selection() else None)
        tree.bind('<Return>', lambda e: self.patient_record(tree.selection()[0]) if tree.selection() else None)
        ttk.Button(parent, text='Abrir expediente seleccionado', command=lambda: self.patient_record(tree.selection()[0]) if tree.selection() else None).pack(anchor='w')

    def window(self, title, size='800x700'):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry(size)
        win.transient(self)
        self.theme._walk(win)
        return win

    def patient_editor(self, record=None, refresh=lambda: None):
        record = record or {}
        win = self.window('Editar paciente' if record else 'Nuevo paciente')
        scroll = ScrollFrame(win)
        scroll.pack(fill='both', expand=True, padx=20, pady=16)
        fields = {}
        for key, label in [('name', 'Nombre completo *'), ('preferred_name', 'Nombre preferido'),
                           ('birth_date', 'Fecha de nacimiento · AAAA-MM-DD (vacío si se desconoce)'),
                           ('phone', 'Teléfono'), ('email', 'Correo'), ('address', 'Dirección'),
                           ('emergency', 'Contacto de emergencia'), ('allergies', 'Alergias · sustancia, reacción y gravedad'),
                           ('problems', 'Problemas activos'), ('history', 'Antecedentes'), ('medications', 'Medicamentos habituales'),
                           ('administrative', 'Notas administrativas')]:
            fields[key], _ = field(scroll.body, label, record.get(key, ''))
        def save():
            data = {**record, **{k: v.get() for k, v in fields.items()}}
            possible = [p for p in self.clinic.list('patients') if p['id'] != record.get('id') and
                        (normalized(p['name']) == normalized(data['name']) or (data['phone'] and p.get('phone') == data['phone']))]
            if possible and not messagebox.askyesno('Posible duplicado', 'Hay un paciente con nombre o teléfono coincidente. ¿Guardar como persona diferente?', parent=win):
                return
            self.clinic.save('patients', data, record.get('revision'))
            win.destroy()
            refresh()
            self.status.set('Paciente guardado.')
        ttk.Button(win, text='Guardar paciente', style='Primary.TButton', command=lambda: self.guard(save)).pack(pady=12)
        self.theme._walk(win)

    def patient_record(self, identifier):
        record = next(p for p in self.clinic.list('patients') if p['id'] == identifier)
        win = self.window(f"Expediente {record['file_number']}", '920x740')
        body = ttk.Frame(win, padding=20)
        body.pack(fill='both', expand=True)
        self.heading(body, record['name'], record['file_number'])
        ttk.Label(body, text='⚠ Alergias: '+(record.get('allergies') or 'No interrogadas / no registradas'), style='warning.TLabel', wraplength=800).pack(fill='x')
        for key, label in [('problems', 'Problemas activos'), ('history', 'Antecedentes'), ('medications', 'Medicamentos habituales')]:
            ttk.Label(body, text=f"{label}: {record.get(key) or 'No registrado'}", wraplength=800).pack(anchor='w', pady=8)
        actions = ttk.Frame(body)
        actions.pack(fill='x')
        ttk.Button(actions, text='Iniciar consulta', style='Primary.TButton', command=lambda: self.confirm_encounter(record)).pack(side='left')
        ttk.Button(actions, text='Editar paciente', command=lambda: self.patient_editor(record)).pack(side='left', padx=8)
        tree = self.table(body, {'date': 'Atención', 'status': 'Estado', 'doctor': 'Doctor', 'reason': 'Motivo'})
        doctors = {u['id']: u['name'] for u in self.auth.users()}
        for row in sorted(self.clinic.list('encounters'), key=lambda r: r['attended_at'], reverse=True):
            if row['patient_id'] == identifier:
                tree.insert('', 'end', iid=row['id'], values=(row['attended_at'][:16], row['status'], doctors.get(row['doctor_id'], 'Autor desconocido'), row.get('reason', '')))
        tree.bind('<Double-1>', lambda e: self.open_encounter(tree.selection()[0]) if tree.selection() else None)
        self.theme._walk(win)

    def confirm_encounter(self, patient):
        if messagebox.askyesno('Confirmar paciente', f"¿Iniciar atención para {patient['name']}?\nExpediente {patient['file_number']}", parent=self):
            self.encounter_editor(patient)

    def encounter_editor(self, patient, record=None):
        record = record or {'patient_id': patient['id'], 'status': 'Borrador', 'attended_at': now()}
        win = self.window('Consulta · '+patient['name'], '900x800')
        footer = ttk.Frame(win, padding=12)
        footer.pack(side='bottom', fill='x')
        scroll = ScrollFrame(win)
        scroll.pack(fill='both', expand=True, padx=20, pady=12)
        ttk.Label(scroll.body, text=f"{patient['name']} · {patient['file_number']}", font=('Segoe UI Semibold', 17)).pack(anchor='w')
        ttk.Label(scroll.body, text='⚠ Alergias: '+(patient.get('allergies') or 'No interrogadas / no registradas'), style='warning.TLabel', wraplength=780).pack(fill='x', pady=10)
        fields = {}
        fields['attended_at'], _ = field(scroll.body, 'Fecha y hora de atención (ISO 8601)', record['attended_at'])
        fields['type'], _ = field(scroll.body, 'Tipo de consulta', record.get('type', 'General'))
        texts = {}
        for key, label in [('reason', 'Motivo de consulta *'), ('subjective', 'S · Síntomas y evolución'),
                           ('objective', 'O · Signos vitales y exploración (incluye unidades)'), ('assessment', 'A · Impresión diagnóstica * (separa diagnósticos con ;)'),
                           ('plan', 'P · Plan e indicaciones *'), ('medications', 'Medicamentos · dosis, vía, frecuencia, duración'), ('studies', 'Estudios solicitados')]:
            ttk.Label(scroll.body, text=label).pack(anchor='w', pady=(10, 4))
            text = tk.Text(scroll.body, height=3, wrap='word', undo=True, font=('Segoe UI', 11), relief='flat', highlightthickness=1)
            text.pack(fill='x')
            text.insert('1.0', record.get(key, ''))
            texts[key] = text
        state = {'record': record, 'dirty': False, 'timer': None}
        indicator = tk.StringVar(value='Borrador sin guardar' if not record.get('id') else 'Guardado')
        def save(final=False):
            data = {**state['record'], **{k: v.get() for k, v in fields.items()}, **{k: v.get('1.0', 'end-1c') for k, v in texts.items()}}
            data['status'] = 'Finalizada' if final else 'Borrador'
            result = self.clinic.save('encounters', data, state['record'].get('revision'))
            state['record'], state['dirty'] = result, False
            indicator.set('Guardado · '+datetime.now().strftime('%H:%M:%S'))
            if final:
                win.destroy()
            return True
        def auto_save():
            if win.winfo_exists() and state['dirty'] and self.auth.current:
                try:
                    save()
                except (DataError, OSError):
                    indicator.set('No se pudo guardar. Revisa los campos y pulsa Guardar.')
        def changed(event=None):
            state['dirty'] = True
            indicator.set('Cambios pendientes…')
            if state['timer']:
                win.after_cancel(state['timer'])
            state['timer'] = win.after(900, auto_save)
        for text in texts.values():
            text.bind('<KeyRelease>', changed)
        for var in fields.values():
            var.trace_add('write', lambda *a: changed())
        def finish():
            if messagebox.askyesno('Revisar y finalizar', f"Paciente: {patient['name']}\n\n{str(texts['assessment'].get('1.0', 'end-1c'))}\n\nLa consulta se conservará sin sobrescribir. Las correcciones serán adendas. ¿Finalizar?", parent=win):
                self.guard(lambda: save(True))
        def close_editor():
            if state['dirty'] and not self.guard(save):
                return
            win.destroy()
        self.editors.append((win, save, state))
        win.protocol('WM_DELETE_WINDOW', close_editor)
        win.bind('<Control-s>', lambda e: self.guard(save))
        win.bind('<Control-Return>', lambda e: finish())
        ttk.Button(footer, text='Guardar borrador · Ctrl+S', command=lambda: self.guard(save)).pack(side='left')
        ttk.Button(footer, text='Revisar y finalizar', style='Primary.TButton', command=finish).pack(side='left', padx=8)
        ttk.Label(footer, textvariable=indicator).pack(side='right')
        self.theme._walk(win)

    def encounters(self, parent):
        self.heading(parent, 'Consultas', 'Tus borradores y el historial compartido de consultas finalizadas.')
        tree = self.table(parent, {'date': 'Atención', 'patient': 'Paciente', 'status': 'Estado', 'reason': 'Motivo'})
        def refresh():
            patients = {p['id']: p['name'] for p in self.clinic.list('patients')}
            tree.delete(*tree.get_children())
            for row in sorted(self.clinic.list('encounters'), key=lambda r: r['attended_at'], reverse=True):
                tree.insert('', 'end', iid=row['id'], values=(row['attended_at'][:16], patients.get(row['patient_id'], 'Paciente no disponible'), row['status'], row.get('reason', '')))
        parent.refresh = refresh
        tree.bind('<Double-1>', lambda e: self.open_encounter(tree.selection()[0]) if tree.selection() else None)
        ttk.Button(parent, text='Abrir consulta seleccionada', command=lambda: self.open_encounter(tree.selection()[0]) if tree.selection() else None).pack(anchor='w')

    def open_encounter(self, identifier):
        record = next(r for r in self.clinic.list('encounters') if r['id'] == identifier)
        patient = next(p for p in self.clinic.list('patients') if p['id'] == record['patient_id'])
        if record['status'] == 'Borrador':
            return self.encounter_editor(patient, record)
        win = self.window('Consulta · '+record['status'])
        text = tk.Text(win, wrap='word', font=('Segoe UI', 11), padx=20, pady=20)
        text.pack(fill='both', expand=True)
        content = '\n\n'.join(f'{key}:\n{record.get(key, "")}' for key in ('attended_at', 'reason', 'subjective', 'objective', 'assessment', 'plan', 'medications', 'studies', 'addenda'))
        text.insert('1.0', patient['name']+'\n\n'+content)
        text.configure(state='disabled')
        def adenda():
            reason = simpledialog.askstring('Adenda', 'Motivo de la adenda:', parent=win)
            if not reason:
                return
            content = simpledialog.askstring('Adenda', 'Contenido de la adenda:', parent=win)
            if content:
                self.guard(lambda: self.clinic.addendum(identifier, reason, content))
                win.destroy()
        ttk.Button(win, text='Agregar adenda', command=adenda).pack(pady=10)
        def export():
            doctor = next((u['name'] for u in self.auth.users() if u['id'] == record['doctor_id']), 'Autor desconocido')
            self.pdf_preview('Consulta médica', [('Atención', record['attended_at']), ('Motivo', record.get('reason')),
                ('Impresión diagnóstica', record.get('assessment')), ('Plan', record.get('plan')),
                ('Medicamentos e indicaciones', record.get('medications'))], doctor, patient['name'])
        ttk.Button(win, text='Vista previa y exportar PDF', command=export).pack(pady=6)
        self.theme._walk(win)

    def pdf_preview(self, title, sections, doctor='', patient=''):
        from app.documents import create_pdf
        from tempfile import TemporaryDirectory
        from PIL import ImageTk
        import pypdfium2 as pdfium
        import shutil
        work = TemporaryDirectory(prefix='registro-preview-')
        path = Path(work.name)/'documento.pdf'
        identity = dict(self.identity.values)
        generation = self.session_generation
        self.status.set('Preparando documento…')
        def generate():
            create_pdf(path, identity, title, sections, doctor, patient)
            pdf = pdfium.PdfDocument(path)
            images = []
            try:
                for page in pdf:
                    bitmap = page.render(scale=1.15)
                    images.append(bitmap.to_pil().copy())
                    bitmap.close()
                    page.close()
            finally:
                pdf.close()
            return images
        def done(images):
            win = self.window('Vista previa · '+title, '850x800')
            scroll = ScrollFrame(win)
            scroll.pack(fill='both', expand=True)
            win.images = [ImageTk.PhotoImage(image) for image in images]
            for image in win.images:
                ttk.Label(scroll.body, image=image).pack(pady=8)
            def save():
                destination = filedialog.asksaveasfilename(parent=win, defaultextension='.pdf', filetypes=[('Documento PDF', '*.pdf')])
                if destination:
                    shutil.copyfile(path, destination)
                    self.auth.audit('exportar_pdf', title)
                    self.status.set('Documento exportado.')
            ttk.Button(win, text='Guardar PDF', style='Primary.TButton', command=lambda: self.guard(save)).pack(pady=10)
            def cleanup(event):
                if event.widget is win:
                    work.cleanup()
            win.bind('<Destroy>', cleanup, add='+')
            self.status.set('Vista previa lista. Revisa el contenido antes de exportar.')
        self.background(generate, done)

    def schedule(self, parent, kind):
        self.heading(parent, 'Agenda' if kind == 'appointments' else 'Seguimientos', 'Pendientes asignados al doctor autenticado.')
        tree = self.table(parent, {'date': 'Fecha y hora', 'patient': 'Paciente', 'reason': 'Motivo', 'status': 'Estado'})
        def refresh():
            patients = {p['id']: p['name'] for p in self.clinic.list('patients')}
            tree.delete(*tree.get_children())
            for row in sorted(self.clinic.list(kind), key=lambda r: r['due_at']):
                if row['doctor_id'] == self.auth.current['id']:
                    tree.insert('', 'end', iid=row['id'], values=(row['due_at'], patients.get(row['patient_id'], ''), row.get('reason', ''), row['status']))
        parent.refresh = refresh
        def editor(record=None):
            record = record or {}
            patients = self.clinic.list('patients')
            if not patients:
                return messagebox.showinfo('Primero registra un paciente', 'Abre Pacientes para crear un expediente.', parent=self)
            win = self.window('Cita' if kind == 'appointments' else 'Seguimiento', '620x500')
            body = ttk.Frame(win, padding=20)
            body.pack(fill='both', expand=True)
            names = {f"{p['file_number']} · {p['name']}": p['id'] for p in patients}
            patient = tk.StringVar(value=next((n for n, pid in names.items() if pid == record.get('patient_id')), next(iter(names))))
            ttk.Label(body, text='Paciente').pack(anchor='w')
            ttk.Combobox(body, textvariable=patient, values=list(names), state='readonly').pack(fill='x', pady=8)
            due, _ = field(body, 'Fecha y hora · AAAA-MM-DD HH:MM', record.get('due_at', date.today().isoformat()+' 09:00'))
            reason, _ = field(body, 'Motivo', record.get('reason', ''))
            status = tk.StringVar(value=record.get('status', 'Programada' if kind == 'appointments' else 'Pendiente'))
            options = ('Programada', 'Confirmada', 'En espera', 'En consulta', 'Atendida', 'Cancelada', 'No asistió') if kind == 'appointments' else ('Pendiente', 'Completado', 'Cancelado')
            ttk.Combobox(body, textvariable=status, values=options, state='readonly').pack(fill='x', pady=16)
            def save():
                self.clinic.save(kind, {**record, 'patient_id': names[patient.get()], 'due_at': due.get(), 'reason': reason.get(), 'status': status.get()}, record.get('revision'))
                win.destroy()
                refresh()
            ttk.Button(body, text='Guardar', style='Primary.TButton', command=lambda: self.guard(save)).pack(anchor='w')
            self.theme._walk(win)
        ttk.Button(parent, text='Nuevo registro', style='Primary.TButton', command=editor).pack(anchor='w')
        tree.bind('<Double-1>', lambda e: editor(next(r for r in self.clinic.list(kind) if r['id'] == tree.selection()[0])) if tree.selection() else None)

    def statistics(self, parent):
        self.heading(parent, 'Mis estadísticas', 'Consultas finalizadas por fecha de atención. Las adendas y anulaciones no suman actividad.')
        filters = ttk.Frame(parent)
        filters.pack(fill='x', pady=8)
        period = tk.StringVar(value='Este mes')
        period_box = ttk.Combobox(filters, values=['Hoy', 'Esta semana', 'Este mes', 'Personalizado'], textvariable=period, state='readonly', width=14)
        period_box.pack(side='left', padx=4)
        doctors = {u['name']+' · '+u['username']: u['id'] for u in self.auth.users()}
        doctors['Toda la clínica'] = '*'
        doctor = tk.StringVar(value=next(n for n, uid in doctors.items() if uid == self.auth.current['id']))
        if self.auth.current['role'] == 'admin':
            ttk.Combobox(filters, values=list(doctors), textvariable=doctor, state='readonly', width=23).pack(side='left', padx=4)
        group = tk.StringVar(value='Todos')
        ttk.Combobox(filters, values=['Todos', 'Nuevos', 'Recurrentes'], textvariable=group, state='readonly', width=14).pack(side='left', padx=4)
        bar = ttk.Frame(parent)
        bar.pack(fill='x')
        start = DatePicker(bar, self.theme, date.today().replace(day=1).isoformat())
        start.pack(side='left', fill='x', expand=True, padx=(0, 8))
        end = DatePicker(bar, self.theme, date.today().isoformat())
        end.pack(side='left', fill='x', expand=True)
        filters2 = ttk.Frame(parent)
        filters2.pack(fill='x', pady=8)
        ttk.Label(filters2, text='Tipo:').pack(side='left')
        kind = tk.StringVar()
        ttk.Entry(filters2, textvariable=kind, width=15).pack(side='left', padx=6)
        ttk.Label(filters2, text='Diagnóstico:').pack(side='left')
        diagnosis = tk.StringVar()
        ttk.Entry(filters2, textvariable=diagnosis, width=22).pack(side='left', padx=6)
        summary = tk.StringVar()
        ttk.Label(parent, textvariable=summary, font=('Segoe UI Semibold', 13), wraplength=780).pack(anchor='w', pady=14)
        chart = Chart(parent, self.theme)
        chart.pack(fill='x')
        tree = self.table(parent, {'diagnosis': 'Diagnósticos más registrados', 'count': 'Consultas asociadas', 'percent': '% de consultas'})
        latest = {}
        view = tk.StringVar(value='Actividad por día')
        distributions = {'Actividad por día': 'activity', 'Tipos de consulta': 'types', 'Estados de citas': 'appointments',
                         'Edad en la atención': 'ages', 'Sexo registrado': 'sexes', 'Motivos frecuentes': 'reasons'}
        view_box = ttk.Combobox(filters2, values=list(distributions), textvariable=view, state='readonly', width=20)
        view_box.pack(side='right')
        view_box.bind('<<ComboboxSelected>>', lambda e: chart.set(latest.get(distributions[view.get()], {})))
        def refresh():
            a, b = date.fromisoformat(start.var.get()), date.fromisoformat(end.var.get())
            if a > b:
                raise DataError('La fecha inicial debe ser anterior o igual a la final.')
            args = (a.isoformat(), b.isoformat(), doctors[doctor.get()], kind.get(), diagnosis.get(), group.get())
            summary.set('Actualizando estadísticas…')
            def done(data):
                latest.clear()
                latest.update(data)
                variation = f"{data['variation']:+.1f}%" if data['variation'] is not None else 'Sin porcentaje: periodo anterior con cero consultas'
                summary.set(f"{data['start']} — {data['end']}\n{data['consultations']} consultas · {data['patients']} pacientes únicos · {data['new']} nuevos · {data['recurrent']} recurrentes\nPromedio: {data['average']:.1f} en {data['days']} días activos · {data['pending']} seguimientos pendientes ({data['overdue']} vencidos)\nFrente a {data['previous_start']} — {data['previous_end']}: {data['difference']:+d} · {variation}")
                chart.set(data[distributions[view.get()]])
                tree.delete(*tree.get_children())
                for diagnosis, count in data['diagnoses'].items():
                    tree.insert('', 'end', values=(diagnosis, count, f"{100*count/data['consultations']:.1f}%"))
            self.background(lambda: self.clinic.statistics(*args), done)
        def set_period(event=None):
            today = date.today()
            if period.get() == 'Hoy':
                start.var.set(today.isoformat())
            elif period.get() == 'Esta semana':
                start.var.set((today-timedelta(days=today.weekday())).isoformat())
            elif period.get() == 'Este mes':
                start.var.set(today.replace(day=1).isoformat())
            end.var.set(today.isoformat())
            self.guard(refresh)
        period_box.bind('<<ComboboxSelected>>', set_period)
        def previous_period():
            a, b = date.fromisoformat(start.var.get()), date.fromisoformat(end.var.get())
            span = (b-a).days+1
            start.var.set((a-timedelta(days=span)).isoformat())
            end.var.set((a-timedelta(days=1)).isoformat())
            period.set('Personalizado')
            refresh()
        ttk.Button(filters, text='← Periodo anterior', command=lambda: self.guard(previous_period)).pack(side='right')
        ttk.Button(bar, text='Actualizar', command=lambda: self.guard(refresh)).pack(side='left', padx=8)
        ttk.Label(parent, text='Una consulta puede tener varios diagnósticos: los porcentajes pueden sumar más de 100 %.').pack(anchor='w')
        exports = ttk.Frame(parent)
        exports.pack(fill='x', pady=8)
        def export_csv():
            if not latest:
                return
            path = filedialog.asksaveasfilename(parent=self, defaultextension='.csv', filetypes=[('Resumen CSV', '*.csv')])
            if path:
                import csv
                from app.transfer import safe_csv
                with open(path, 'w', newline='', encoding='utf-8-sig') as stream:
                    writer = csv.writer(stream)
                    writer.writerow(['Indicador', 'Valor'])
                    for key, value in latest.items():
                        if isinstance(value, dict):
                            for subkey, subvalue in value.items():
                                writer.writerow([safe_csv(key+' · '+str(subkey)), safe_csv(subvalue)])
                        else:
                            writer.writerow([key, safe_csv(value)])
                self.auth.audit('exportar_estadisticas', latest['doctor'])
                self.status.set('Resumen CSV exportado.')
        ttk.Button(exports, text='Exportar resumen CSV', command=lambda: self.guard(export_csv)).pack(side='left')
        def export_pdf():
            if latest:
                self.pdf_preview('Resumen de actividad', [('Periodo e indicadores', summary.get()),
                    ('Diagnósticos más registrados', '\n'.join(f'{d}: {n} consultas' for d, n in latest['diagnoses'].items())),
                    ('Definiciones', 'Consultas finalizadas, por fecha de atención. Pacientes únicos deduplicados. Nuevos: primera atención con el doctor o ámbito seleccionado. Excluye borradores, anulaciones y adendas. Los diagnósticos no representan prevalencia poblacional.')], doctor=doctor.get())
        ttk.Button(exports, text='Vista previa PDF', command=export_pdf).pack(side='left', padx=8)
        parent.refresh = refresh

    def settings(self, parent):
        tabs = ttk.Notebook(parent)
        tabs.pack(fill='both', expand=True)
        appearance = AppearanceEditor(tabs, self)
        tabs.add(appearance, text='Apariencia')
        identity = ScrollFrame(tabs)
        tabs.add(identity, text='Clínica e identidad')
        values = {}
        for key, label in [('app_name', 'Nombre de la aplicación'), ('clinic_name', 'Nombre de la clínica'), ('contact', 'Contacto de la clínica'),
                           ('website', 'Enlace web (HTTP o HTTPS)'), ('website_text', 'Texto visible del enlace'),
                           ('document_primary', 'Color principal de documentos'), ('document_text', 'Color del texto de documentos')]:
            values[key], _ = field(identity.body, label, self.identity.values[key])
        for key, label in [('document_website', 'Incluir el enlace en documentos exportados'), ('document_app_brand', 'Incluir la marca de la aplicación en documentos')]:
            values[key] = tk.BooleanVar(value=self.identity.values[key])
            ttk.Checkbutton(identity.body, text=label, variable=values[key]).pack(anchor='w', pady=10)
        ttk.Label(identity.body, text='La identidad de la aplicación está separada de la clínica.\nEstos ajustes globales requieren permisos de administrador.', style='Subtitle.TLabel').pack(anchor='w', pady=12)
        def save_identity():
            self.identity.save({key: value.get() for key, value in values.items()})
            self.title(self.identity.values['app_name'])
            self.status.set('Identidad guardada.')
        ttk.Button(identity.body, text='Guardar identidad', command=lambda: self.guard(save_identity)).pack(anchor='w', pady=12)
        def clinic_logo():
            path = filedialog.askopenfilename(parent=self, filetypes=[('Logo PNG o JPEG', '*.png *.jpg *.jpeg')])
            if path:
                self.guard(lambda: self.identity.set_clinic_logo(path))
                self.status.set('Logo de la clínica guardado para documentos.')
        ttk.Button(identity.body, text='Elegir logo de la clínica', command=clinic_logo).pack(anchor='w', pady=8)
        security = ttk.Frame(tabs, padding=20)
        tabs.add(security, text='Seguridad')
        minutes, _ = field(security, 'Bloqueo por inactividad (minutos)', str(self.store.read('config/security.json', {'idle_minutes': 10})['idle_minutes']))
        def save_security():
            self.auth.require('admin')
            n = int(minutes.get())
            if not 1 <= n <= 120:
                raise DataError('Elige entre 1 y 120 minutos.')
            self.store.write('config/security.json', {'idle_minutes': n})
            self.status.set('Política de bloqueo guardada.')
        ttk.Button(security, text='Guardar política', command=lambda: self.guard(save_security)).pack(anchor='w', pady=12)
        ttk.Button(security, text='Cambiar mi contraseña', command=self.change_password).pack(anchor='w')
        if self.auth.current['role'] == 'admin':
            users = ttk.Frame(tabs, padding=20)
            tabs.add(users, text='Doctores')
            self.doctors(users)

    def change_password(self):
        old = simpledialog.askstring('Verificar identidad', 'Contraseña actual:', show='•', parent=self)
        if old is None:
            return
        def action():
            self.auth.login(self.auth.current['id'], old)
            new = simpledialog.askstring('Nueva contraseña', 'Al menos 10 caracteres:', show='•', parent=self)
            if new is not None:
                self.auth.update_user(self.auth.current['id'], password=new)
                self.status.set('Contraseña actualizada.')
        self.guard(action)

    def doctors(self, parent):
        tree = self.table(parent, {'name': 'Nombre', 'username': 'Usuario', 'role': 'Rol', 'active': 'Activo'})
        def refresh():
            tree.delete(*tree.get_children())
            for u in self.auth.users():
                tree.insert('', 'end', iid=u['id'], values=(u['name'], u['username'], u['role'], 'Sí' if u['active'] else 'No'))
        def create():
            win = self.window('Nuevo doctor', '620x480')
            form = ttk.Frame(win, padding=24)
            form.pack(fill='both', expand=True)
            name, _ = field(form, 'Nombre completo')
            username, _ = field(form, 'Usuario')
            password, _ = field(form, 'Contraseña inicial · al menos 10 caracteres', secret=True)
            role = tk.StringVar(value='doctor')
            ttk.Combobox(form, textvariable=role, values=['doctor', 'admin'], state='readonly').pack(fill='x', pady=16)
            def save():
                self.auth.create_user(name.get(), username.get(), password.get(), role.get())
                win.destroy()
                refresh()
            ttk.Button(form, text='Crear usuario', command=lambda: self.guard(save)).pack(anchor='w')
        def toggle():
            if not tree.selection():
                return
            uid = tree.selection()[0]
            active = next(u['active'] for u in self.auth.users() if u['id'] == uid)
            self.auth.update_user(uid, active=not active)
            refresh()
        ttk.Button(parent, text='Crear doctor', command=create).pack(side='left', padx=8)
        ttk.Button(parent, text='Activar / desactivar', command=lambda: self.guard(toggle)).pack(side='left')
        refresh()

    def about(self, parent):
        self.heading(parent, 'Acerca de', self.identity.values['app_name'])
        self.brand(parent).pack(anchor='w', pady=12)
        ttk.Label(parent, text='TresVizo', font=('Segoe UI Semibold', 27)).pack(anchor='w')
        ttk.Label(parent, text='Registro de pacientes y consultas · Almacenamiento local', style='Subtitle.TLabel').pack(anchor='w', pady=12)
        ttk.Button(parent, text=self.identity.values['website_text']+' ↗', command=lambda: self.guard(self.identity.open_website)).pack(anchor='w')
        ttk.Label(parent, text='Datos y configuración:\n'+str(self.store.root), wraplength=780).pack(anchor='w', pady=20)

    def exports(self, parent):
        self.heading(parent, 'Exportar y respaldar', 'Las exportaciones contienen información sensible. Elige una ubicación bajo tu control.')
        def patients():
            destination = filedialog.asksaveasfilename(parent=self, defaultextension='.csv', filetypes=[('Pacientes CSV', '*.csv'), ('Expedientes JSON', '*.json')])
            if destination:
                self.background(lambda: self.transfer.export_patients(destination), lambda _: self.status.set('Exportación guardada.'))
        ttk.Button(parent, text='Exportar pacientes · CSV / JSON', command=patients, style='Primary.TButton').pack(anchor='w', pady=10)
        if self.auth.current['role'] == 'admin':
            def backup():
                destination = filedialog.asksaveasfilename(parent=self, defaultextension='.zip', initialfile='respaldo-'+date.today().isoformat()+'.zip', filetypes=[('Respaldo ZIP', '*.zip')])
                if destination:
                    self.background(lambda: self.transfer.backup(destination), lambda _: self.status.set('Respaldo creado y verificado.'))
            ttk.Button(parent, text='Crear respaldo completo verificado', command=backup).pack(anchor='w', pady=10)
            ttk.Label(parent, text='Incluye datos, configuración, adjuntos y avatares.\nUna copia en el mismo disco no protege frente a la pérdida del equipo.', wraplength=750).pack(anchor='w', pady=10)

    def check_idle(self):
        if self.auth.current and not self.locked:
            minutes = self.store.read('config/security.json', {'idle_minutes': 10})['idle_minutes']
            if time.monotonic()-self.last_activity >= minutes*60:
                self.logout(force=True)
        self.after(1000, self.check_idle)

    def logout(self, force=False):
        # Ocultar inmediatamente todas las ventanas, incluso si falla el guardado.
        self.withdraw()
        if not self.locked:
            self.session_generation += 1
        self.locked = True
        windows = [w for w in self.winfo_children() if isinstance(w, tk.Toplevel)]
        for win in windows:
            win.withdraw()
        if any(not task.done() for task in self.pending):
            self.after(50, lambda: self.logout(force))
            return
        failed = False
        for win, save, state in self.editors:
            if win.winfo_exists() and state['dirty']:
                try:
                    save()
                except (OSError, DataError):
                    failed = True
        if failed:
            # Mantener el árbol oculto hasta que el mismo doctor reautentique.
            self.reauthenticate_hidden()
            return
        self.session_generation += 1
        self.auth.logout()
        self.locked = False
        self.editors = []
        self.login_screen()
        self.deiconify()

    def reauthenticate_hidden(self):
        uid = self.auth.current['id']
        cover = tk.Toplevel(self)
        cover.title('Sesión bloqueada')
        cover.geometry('540x280')
        cover.protocol('WM_DELETE_WINDOW', lambda: None)
        ttk.Label(cover, text='Sesión bloqueada. Hay cambios sin guardar.\nAutentícate para recuperarlos.', padding=20).pack()
        password, _ = field(cover, 'Contraseña del doctor anterior', secret=True)
        def unlock():
            self.auth.login(uid, password.get())
            password.set('')
            cover.destroy()
            self.deiconify()
            for win, _, _ in self.editors:
                if win.winfo_exists():
                    win.deiconify()
            self.activity()
            self.locked = False
        ttk.Button(cover, text='Desbloquear', command=lambda: self.guard(unlock)).pack(pady=16)
        self.theme._walk(cover)

    def close(self):
        if any(not task.done() for task in self.pending):
            self.status.set('Espera a que termine la operación de archivos antes de cerrar.')
            self.after(100, self.close)
            return
        for win, save, state in self.editors:
            if win.winfo_exists() and state['dirty'] and not self.guard(save):
                return
        if self.auth.current:
            self.auth.logout()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.instance.close()
        self.destroy()
