"""Primer inicio: identidad visible y acceso de la clínica."""
import tkinter as tk
from tkinter import ttk, filedialog
from PIL import Image
from app.components import ScrollFrame, field
from app.branding import APP_MARK, photo_from_path
from app.setup_service import create_clinic
from app.storage import DataError


class SetupPage(ScrollFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.logo_source = None
        self.variables = {}
        self.outer = ttk.Frame(self.body, padding=28)
        self.outer.pack(fill='x', expand=True)
        app.brand(self.outer, size=68).pack(anchor='w')
        ttk.Label(self.outer, text='Tu clínica, lista para atender', style='Title.TLabel').pack(anchor='w', pady=(12, 6))
        self.progress = ttk.Label(self.outer, style='Subtitle.TLabel')
        self.progress.pack(anchor='w', pady=(0, 18))
        self.identity_page = ttk.Frame(self.outer)
        self.access_page = ttk.Frame(self.outer)
        self.variables['clinic_name'], _ = field(self.identity_page, 'Nombre de la clínica')
        ttk.Label(self.identity_page, text='Logo e icono de tu clínica', style='Section.TLabel').pack(anchor='w', pady=(18, 8))
        self.preview = ttk.Label(self.identity_page)
        self.preview.pack(anchor='w')
        self.logo_label = ttk.Label(self.identity_page, style='Subtitle.TLabel')
        self.logo_label.pack(anchor='w', pady=6)
        self.set_preview(APP_MARK)
        choices = ttk.Frame(self.identity_page)
        choices.pack(fill='x', pady=8)
        ttk.Button(choices, text='Cruz azul y turquesa', command=self.default_logo).pack(side='left', padx=(0, 8))
        ttk.Button(choices, text='Elegir mi logo…', command=self.choose_logo).pack(side='left')
        self.use_icon = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.identity_page, text='Usar este logo también como icono de las ventanas', variable=self.use_icon).pack(anchor='w', pady=8)
        ttk.Label(self.identity_page, text='Puedes elegir PNG, JPG o ICO. Esta identidad se usará en los documentos de tu clínica y podrás cambiarla en Configuración.', wraplength=690, style='Subtitle.TLabel').pack(fill='x', pady=8)
        ttk.Button(self.identity_page, text='Continuar →', style='Primary.TButton', command=self.next).pack(anchor='e', pady=16)
        for key, label, secret in (
            ('name', 'Nombre del administrador', False), ('username', 'Usuario', False),
            ('password', 'Contraseña · mínimo 8 caracteres', True),
            ('confirmation', 'Confirmar contraseña', True),
            ('master_password', 'Contraseña maestra de recuperación · mínimo 8 caracteres', True),
            ('master_confirmation', 'Confirmar contraseña maestra', True)):
            self.variables[key], _ = field(self.access_page, label, secret=secret)
        ttk.Label(self.access_page, text='La contraseña maestra permite restablecer el acceso de los médicos. Guárdala en un lugar seguro; no se muestra después de configurar la clínica.', wraplength=690, style='Subtitle.TLabel').pack(fill='x', pady=12)
        buttons = ttk.Frame(self.access_page)
        buttons.pack(fill='x', pady=14)
        ttk.Button(buttons, text='← Identidad', command=lambda: self.show_step(1)).pack(side='left')
        self.submit = ttk.Button(buttons, text='Crear clínica y entrar', style='Primary.TButton', command=self.submit_setup)
        self.submit.pack(side='right')
        self.error = ttk.Label(self.outer, style='error.TLabel', wraplength=690)
        self.show_step(1)

    def show_step(self, step):
        self.identity_page.pack_forget()
        self.access_page.pack_forget()
        (self.identity_page if step == 1 else self.access_page).pack(fill='x')
        self.progress.configure(text='1 de 2 · Identidad de la clínica' if step == 1 else '2 de 2 · Administrador y recuperación')
        self.canvas.yview_moveto(0)

    def set_preview(self, path):
        self.preview.image = photo_from_path(path, 104, self.app)
        self.preview.configure(image=self.preview.image)
        self.logo_label.configure(text='Cruz azul y turquesa' if path == APP_MARK else 'Logo propio seleccionado')

    def default_logo(self):
        self.logo_source = None
        self.set_preview(APP_MARK)

    def choose_logo(self):
        path = filedialog.askopenfilename(parent=self, filetypes=[('Logo o icono', '*.png *.jpg *.jpeg *.ico')])
        if not path:
            return
        try:
            from pathlib import Path
            if Path(path).stat().st_size > 10_000_000:
                raise DataError('El archivo debe ser menor de 10 MB.')
            with Image.open(path) as image:
                if image.format not in ('PNG', 'JPEG', 'ICO') or image.width*image.height > 20_000_000:
                    raise DataError('Elige PNG, JPG o ICO de hasta 20 megapíxeles.')
            self.set_preview(path)
            self.logo_source = path
            self.error.pack_forget()
        except (ValueError, OSError) as exc:
            self.show_error(str(exc))

    def show_error(self, text):
        self.error.configure(text=text)
        self.error.pack(fill='x', pady=8)

    def next(self):
        if not self.variables['clinic_name'].get().strip():
            self.show_error('Escribe el nombre de tu clínica.')
            return
        self.error.pack_forget()
        self.show_step(2)

    def submit_setup(self):
        values = {key: var.get() for key, var in self.variables.items()}
        if values.pop('confirmation') != values['password'] or values.pop('master_confirmation') != values['master_password']:
            self.show_error('Las contraseñas y sus confirmaciones deben coincidir.')
            return
        self.submit.state(['disabled'])
        try:
            uid = create_clinic(self.app.auth, self.app.identity, **values, logo_source=self.logo_source, use_clinic_icon=self.use_icon.get())
            self.app.auth.login(uid, values['password'])
        except (ValueError, OSError) as exc:
            self.submit.state(['!disabled'])
            self.show_error(str(exc))
            return
        for key in ('password', 'confirmation', 'master_password', 'master_confirmation'):
            self.variables[key].set('')
        self.app.refresh_identity()
        self.app.shell()
