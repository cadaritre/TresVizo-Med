from __future__ import annotations
from datetime import date, datetime, timedelta
from pathlib import Path
import time
import gc
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from concurrent.futures import ThreadPoolExecutor
from app.storage import Store, InstanceLock, DataError
from app.services import Auth, Clinic, normalized, now
from app.themes import Appearance, luminance
from app.ui_theme import ThemeManager
from app.branding import Identity, logo_photo, register_windows_identity, set_window_icon
from app.appearance_ui import AppearanceEditor
from app.components import ScrollFrame, field, DatePicker, Chart, Tooltip
from app.widgets import DateField
from app.clinical_models import display_date
from app.transfer import Transfer
from app.care import Care, migrate
from app.attachments import Attachments
from app.profiles import Profiles
from app.workspace import Workspace
from tkinterdnd2 import TkinterDnD


class Application(Workspace, TkinterDnD.Tk):
    def __init__(self, data_dir=None):
        self.windows_identity_registered = register_windows_identity()
        # Tk solo permite liberar sus variables e imágenes en el hilo gráfico.
        # Las tareas de archivos no deben disparar la recolección de pantallas cerradas.
        gc.disable()
        gc.collect()
        super().__init__()
        self.withdraw()
        self.store = Store(data_dir)
        self.instance = InstanceLock(self.store.root)
        migrate(self.store)
        self.auth = Auth(self.store)
        self.clinic = Clinic(self.store, self.auth)
        self.care = Care(self.store, self.auth, self.clinic)
        self.attachments = Attachments(self.store, self.auth, self.clinic)
        self.profiles = Profiles(self.store, self.auth, self)
        self.transfer = Transfer(self.store, self.auth, self.clinic)
        self.appearance = Appearance(self.store, self.auth)
        self.identity = Identity(self.store, self.auth)
        self.theme = ThemeManager(self)
        from app.icons import Icons
        self.icons = Icons(self.theme)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.pending = set()
        self.session_generation = 0
        self.editors = []
        self.locked = False
        self.last_activity = time.monotonic()
        self.day_key = date.today()
        self.status = tk.StringVar(value='Datos guardados localmente en Documentos.')
        self.title(self.identity.values['app_name'])
        scale = max(1.0, float(self.tk.call('tk', 'scaling'))/(96/72))
        self.ui_scale = scale
        width = min(int(1220*scale), self.winfo_screenwidth()-40)
        height = min(int(820*scale), self.winfo_screenheight()-70)
        self.geometry(f'{width}x{height}')
        self.minsize(min(940, width), min(640, height))
        set_window_icon(self, default=True)
        self.theme.apply(self.appearance.tokens())
        self.bind_all('<KeyPress>', self.activity, add='+')
        self.bind_all('<ButtonPress>', self.activity, add='+')
        self.bind('<Control-k>', self.focus_patient_search)
        for widget_class in ('Text', 'Entry', 'TEntry', 'TCombobox'):
            self.bind_class(widget_class, '<Control-k>', self.focus_patient_search)
        self.bind('<Control-s>', self.save_current)
        self.bind('<Control-Return>', self.finish_current)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(1000, self.check_idle)
        self.after(5000, self.collect_ui_objects)
        self.login_screen()
        self.deiconify()

    def activity(self, event=None):
        self.last_activity = time.monotonic()

    def collect_ui_objects(self):
        gc.collect()
        self.after(5000,self.collect_ui_objects)

    def save_current(self,event=None):
        if self.auth.current and not self.locked:
            page = getattr(self,'pages',{}).get(getattr(self,'current_page',''))
            if page is not None and hasattr(page,'save'):
                self.guard(page.save)
                return 'break'

    def guard(self, fn):
        try:
            return fn()
        except (DataError, OSError, ValueError) as exc:
            messagebox.showerror('No se pudo completar', str(exc), parent=self)
            return None

    def finish_current(self, event=None):
        if self.auth.current and not self.locked:
            page = getattr(self, 'pages', {}).get(getattr(self, 'current_page', ''))
            if page is not None and hasattr(page, 'finish'):
                page.finish()
                return 'break'

    def report_callback_exception(self, exc, value, tb):
        if not self.locked:
            messagebox.showerror('Error', 'La operación no se completó. La captura sigue abierta; revisa su estado de guardado antes de salir.', parent=self)
        import traceback
        # No registrar valores de campos, documentos ni texto clínico en diagnósticos.
        print(exc.__name__+': '+', '.join(Path(frame.filename).name+':'+str(frame.lineno)+' '+frame.name for frame in traceback.extract_tb(tb)))

    def clear(self):
        for widget in self.winfo_children():
            widget.destroy()

    def brand(self, parent, style='TLabel', size=72):
        label = ttk.Label(parent, style=style)
        def refresh(tokens):
            background = tokens['sidebar'] if style == 'Nav.TLabel' else tokens['background']
            label.logo = logo_photo(int(size*self.ui_scale), dark=luminance(background) < .25, master=self)
            label.configure(image=label.logo)
        self.theme.subscribe(label, refresh)
        return label

    def _legacy_login_screen(self):
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



    def heading(self, parent, title, hint=''):
        label = ttk.Label(parent, text=title, style='Title.TLabel', wraplength=780)
        label.pack(anchor='w', fill='x', pady=(0, 6))
        parent.bind('<Configure>',lambda e:label.configure(wraplength=max(240,e.width-20)) if label.winfo_exists() else None,add='+')
        if hint:
            ttk.Label(parent, text=hint, style='Subtitle.TLabel', wraplength=780).pack(anchor='w', pady=(0, 16))


    def background(self, work, done, settled=None):
        """Finalización independiente de la entrega a una sesión/vista.

        settled recibe el Future terminado en el hilo Tk, incluso al invalidar la
        sesión; solo debe reconciliar estado interno, nunca mostrar información.
        """
        generation = self.session_generation
        actor = (self.auth.current or {}).get('id')
        future = self.executor.submit(work)
        self.pending.add(future)
        reconciled = False
        def poll():
            nonlocal reconciled
            if future.done():
                self.pending.discard(future)
                if not reconciled:
                    reconciled = True
                    if settled:
                        settled(future)
            if not future.done():
                self.after(50, poll)
                return
            if generation != self.session_generation or actor != (self.auth.current or {}).get('id'):
                return
            if self.locked:
                self.after(100, poll)
                return
            self.guard(lambda: done(future.result()))
        self.after(50, poll)
        return future

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


    def window(self, title, size='800x700'):
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry(size)
        win.transient(self)
        self.theme._walk(win)
        return win



    def confirm_encounter(self, patient):
        if not patient:
            return
        actor = self.auth.require()['id']
        current = self.store.read(f"data/patients/{patient['id']}.json")
        if not current or current.get('archived'):
            raise DataError('Este paciente no está activo. Revisa su expediente.')
        pending = getattr(self, '_starting_patients', set())
        self._starting_patients = pending
        if current['id'] in pending:
            return
        pending.add(current['id'])
        def find_drafts():
            try:
                return sorted(self.store.select_records('encounters', lambda r: r['patient_id'] == current['id'] and
                    r['doctor_id'] == actor and r['status'] == 'Borrador' and not r.get('archived')), key=lambda r: r['updated_at'], reverse=True)
            except (ValueError, OSError):
                pending.discard(current['id'])
                raise
        def continue_visit(drafts):
            latest = self.store.read(f"data/patients/{current['id']}.json")
            if not latest or latest.get('archived'):
                raise DataError('El paciente ya no está activo. Su expediente se conserva.')
            if drafts:
                draft = drafts[0]
                if messagebox.askyesno('Retomar consulta pendiente', latest['name']+' · '+latest['file_number']+
                        '\nYa tienes una consulta en borrador del '+display_date(draft['attended_at'])+'.\n¿Retomarla?', parent=self):
                    self.open_encounter(draft['id'])
                return
            if messagebox.askyesno('Confirmar paciente', latest['name']+' · '+latest['file_number']+'\n¿Comenzar la consulta?', parent=self):
                self.encounter_editor(latest)
        def ready(drafts):
            try:
                continue_visit(drafts)
            finally:
                pending.discard(current['id'])
        self.background(find_drafts, ready)

    def pdf_preview(self, title, sections, doctor='', patient=''):
        from app.documents import create_pdf
        from app.attachment_ui import DocumentViewer
        from tempfile import TemporaryDirectory
        import shutil
        work = TemporaryDirectory(prefix='registro-preview-')
        path = Path(work.name)/'documento.pdf'
        identity = dict(self.identity.values)
        self.status.set('Preparando documento…')
        def generate():
            create_pdf(path, identity, title, sections, doctor, patient)
            return work
        def done(temporary):
            win = DocumentViewer(self, path, 'Vista previa · '+title)
            win.temporary = temporary
            def save():
                destination = filedialog.asksaveasfilename(parent=win, defaultextension='.pdf', filetypes=[('Documento PDF', '*.pdf')])
                if destination:
                    shutil.copyfile(path, destination)
                    self.auth.audit('exportar_pdf', title)
                    self.status.set('Documento exportado.')
            ttk.Button(win.toolbar, text='Guardar PDF…', style='Primary.TButton', command=lambda: self.guard(save)).pack(side='left', padx=8)
            def cleanup(event):
                if event.widget is win:
                    win.request_id += 1
                    if self.executor._shutdown:
                        temporary.cleanup()
                    else:
                        self.executor.submit(temporary.cleanup)
            win.bind('<Destroy>', cleanup, add='+')
            self.status.set('Vista previa lista. Revisa el contenido antes de exportar.')
        self.background(generate, done)

    def settings(self, parent):
        tabs = ttk.Notebook(parent)
        tabs.pack(fill='both', expand=True)
        from app.general_ui import GeneralSettings
        general = GeneralSettings(tabs, self)
        tabs.add(general, text='General')
        tabs.bind('<<NotebookTabChanged>>', lambda event: general.refresh(), add='+')
        appearance = AppearanceEditor(tabs, self)
        tabs.add(appearance, text='Apariencia')
        data_page = ttk.Frame(tabs, padding=20)
        tabs.add(data_page, text='Datos y respaldos')
        ttk.Label(data_page, text='Ubicación activa', style='Section.TLabel').pack(anchor='w')
        ttk.Label(data_page, text=str(self.store.root), wraplength=760).pack(fill='x', pady=10)
        backup_info = ttk.Label(data_page, wraplength=760, style='Subtitle.TLabel')
        backup_info.pack(fill='x', pady=10)
        def refresh_data():
            backup = self.store.read('config/last_backup.json', {})
            backup_info.configure(text=('Último respaldo verificado: '+display_date(backup['created_at'])+'\n'+backup['path']+f"\n{backup['files']} archivos" if backup else 'Todavía no hay un respaldo verificado registrado.'))
        ttk.Button(data_page, text='Exportar y respaldar', command=lambda: self.show('Exportar y respaldar')).pack(anchor='w', pady=10)
        tabs.bind('<<NotebookTabChanged>>', lambda event: refresh_data(), add='+')
        parent.refresh = refresh_data
        refresh_data()
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
        if self.auth.current['role'] == 'admin':
            from app.attachments import CATEGORIES
            categories,_ = field(identity.body,'Categorías de documentos · separadas por coma',', '.join(self.store.read('config/attachment_categories.json',CATEGORIES)))
            def save_categories():
                self.auth.require('admin')
                values = list(dict.fromkeys(s.strip() for s in categories.get().split(',') if s.strip()))
                if not values or len(values)>30 or any(len(s)>60 for s in values):
                    raise DataError('Define entre 1 y 30 categorías de hasta 60 caracteres.')
                self.store.write('config/attachment_categories.json',values)
                self.status.set('Categorías guardadas. Se usarán al abrir una sección de documentos.')
            ttk.Button(identity.body,text='Guardar categorías',command=lambda:self.guard(save_categories)).pack(anchor='w',pady=8)
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
        from app.profiles import ProfileEditor
        profile = ProfileEditor(tabs, self)
        tabs.add(profile, text='Mi perfil')
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
        def profile():
            if tree.selection():
                from app.profiles import ProfileEditor
                uid = tree.selection()[0]
                self.mount('perfil:'+uid, lambda container: ProfileEditor(container, self, uid))
        ttk.Button(parent, text='Editar perfil y avatar', command=profile).pack(side='left', padx=8)
        refresh()

    def about(self, parent):
        from app.version import VERSION
        import struct
        self.heading(parent, 'Acerca de', self.identity.values['app_name'])
        self.brand(parent).pack(anchor='w', pady=12)
        ttk.Label(parent, text='TresVizo', font=('Segoe UI Semibold', 27)).pack(anchor='w')
        ttk.Label(parent, text=f'Versión {VERSION} · {struct.calcsize("P")*8} bits').pack(anchor='w', pady=8)
        ttk.Label(parent, text='Registro de pacientes y consultas · Almacenamiento local', style='Subtitle.TLabel').pack(anchor='w', pady=12)
        ttk.Button(parent, text=self.identity.values['website_text']+' ↗', style='Link.TButton', command=lambda: self.guard(self.identity.open_website)).pack(anchor='w')
        ttk.Label(parent, text='Datos y configuración:\n'+str(self.store.root), wraplength=780).pack(anchor='w', pady=20)

    def exports(self, parent):
        self.heading(parent, 'Exportar y respaldar', 'Las exportaciones contienen información sensible. Elige una ubicación bajo tu control.')
        def patients():
            from app.export_ui import export_patients
            export_patients(self)
        ttk.Button(parent, text='Exportar pacientes · CSV / JSON', command=patients, style='Primary.TButton').pack(anchor='w', pady=10)
        if self.auth.current['role'] == 'admin':
            from app.import_ui import ImportWindow
            ttk.Button(parent, text='Importar pacientes CSV · mapear y revisar…', command=lambda: ImportWindow(self)).pack(anchor='w', pady=10)
            def backup():
                destination = filedialog.asksaveasfilename(parent=self, defaultextension='.zip', initialfile='respaldo-'+date.today().isoformat()+'.zip', filetypes=[('Respaldo ZIP', '*.zip')])
                if destination:
                    self.background(lambda: self.transfer.backup(destination), lambda _: self.status.set('Respaldo creado y verificado.'))
            ttk.Button(parent, text='Crear respaldo completo verificado', command=backup).pack(anchor='w', pady=10)
            def restore():
                source = filedialog.askopenfilename(parent=self, filetypes=[('Respaldo ZIP', '*.zip')])
                if not source:
                    return
                folder = filedialog.askdirectory(parent=self, title='Carpeta donde crear una copia restaurada')
                if not folder:
                    return
                destination = Path(folder)/('clinica-restaurada-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
                def done(path):
                    self.status.set('Copia restaurada y verificada en '+str(path)+' · la clínica activa sigue en '+str(self.store.root))
                    def open_copy():
                        import subprocess, sys
                        root = Path(__file__).resolve().parents[1]
                        command = [sys.executable] + ([] if getattr(sys,'frozen',False) else [str(root/'main.py')]) + ['--data-dir',str(path)]
                        subprocess.Popen(command,cwd=root,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    ttk.Button(parent,text='Abrir copia restaurada',command=open_copy).pack(anchor='w',pady=8)
                self.background(lambda:self.transfer.restore(source,destination),done)
            ttk.Button(parent,text='Restaurar respaldo en una carpeta separada…',command=restore).pack(anchor='w',pady=10)
            def integrity():
                def done(report):
                    messagebox.showinfo('Integridad de archivos',f"{report['documents']} documentos registrados\n{len(report['missing'])} archivos ausentes\n{len(report['unreferenced'])} originales sin referencia\n{len(report['pending'])} archivos en preparación\n\nLos archivos se conservan para revisión y recuperación.",parent=self)
                self.background(self.attachments.integrity_report,done)
            ttk.Button(parent,text='Revisar integridad de archivos',command=integrity).pack(anchor='w',pady=8)
            ttk.Label(parent, text='Incluye datos, configuración, adjuntos y avatares.\nUna copia en el mismo disco no protege frente a la pérdida del equipo.', wraplength=750).pack(anchor='w', pady=10)

    def check_idle(self):
        self.check_day()
        if self.auth.current and not self.locked:
            minutes = self.store.read('config/security.json', {'idle_minutes': 10})['idle_minutes']
            if time.monotonic()-self.last_activity >= minutes*60:
                self.lock_session()
        self.after(1000, self.check_idle)

    def check_day(self):
        today = date.today()
        if today == self.day_key:
            return
        if self.locked:
            return
        self.day_key = today
        if self.auth.current and not self.locked:
            page = getattr(self, 'pages', {}).get(getattr(self, 'current_page', ''))
            if page and hasattr(page, 'day_changed'):
                page.day_changed()
            elif page and self.current_page == 'Inicio':
                page.refresh()

    def logout(self, force=False):
        # Ocultar inmediatamente todas las ventanas, incluso si falla el guardado.
        self.withdraw()
        if not self.locked:
            self.session_generation += 1
        self.locked = True
        windows = [w for w in self.winfo_children() if isinstance(w, tk.Toplevel)]
        for win in windows:
            win.withdraw()
        capture = getattr(self, 'active_capture', None)
        if capture and capture.winfo_exists():
            capture.grab_release()
            if hasattr(capture, 'persist_pending'):
                try:
                    capture.persist_pending()
                except (ValueError, OSError):
                    self.reauthenticate_hidden()
                    return
        if any(not task.done() for task in self.pending):
            self.after(50, lambda: self.logout(force))
            return
        failed = False
        for win, save, state in self.editors:
            if win.winfo_exists() and (state['dirty'] or capture and getattr(capture, 'owner', None) is win):
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
                if win.winfo_exists() and isinstance(win, tk.Toplevel):
                    win.deiconify()
            capture = getattr(self, 'active_capture', None)
            if capture and capture.winfo_exists():
                capture.deiconify()
                capture.grab_set()
            self.activity()
            self.locked = False
        ttk.Button(cover, text='Desbloquear', command=lambda: self.guard(unlock)).pack(pady=16)
        self.theme._walk(cover)

    def close(self):
        if any(not task.done() for task in self.pending):
            self.status.set('Espera a que termine la operación de archivos antes de cerrar.')
            self.after(100, self.close)
            return
        capture = getattr(self, 'active_capture', None)
        if capture and capture.winfo_exists() and hasattr(capture, 'persist_pending'):
            if not self.guard(capture.persist_pending):
                return
        for win, save, state in self.editors:
            if win.winfo_exists() and (state['dirty'] or capture and getattr(capture, 'owner', None) is win) and not self.guard(save):
                return
        if self.auth.current:
            self.auth.logout()
        self.executor.shutdown(wait=True, cancel_futures=True)
        self.instance.close()
        for timer in self.tk.call('after','info'):
            self.tk.call('after','cancel',timer)
        self.destroy()
