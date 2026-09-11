"""Recuperación explícita, sin entrar a una sesión mediante la clave maestra."""
from tkinter import ttk
from app.components import field
from app.consultation_tools import fit_window
from app.storage import DataError


def recovery_dialog(app, user=None):
    changing = user is None
    if changing:
        app.auth.require('admin')
    win = app.window('Contraseña maestra' if changing else 'Recuperar acceso')
    fit_window(win, app, 640, 560)
    body = ttk.Frame(win, padding=24)
    body.pack(fill='both', expand=True)
    title = 'Configurar recuperación de la clínica' if changing else 'Restablecer acceso de '+user['name']
    ttk.Label(body, text=title, style='Section.TLabel', wraplength=560).pack(fill='x', pady=(0, 8))
    current, first = field(body, 'Tu contraseña de administrador' if changing else 'Contraseña maestra de la clínica', secret=True)
    password, _ = field(body, 'Nueva contraseña maestra · mínimo 8 caracteres' if changing else 'Nueva contraseña del médico · mínimo 8 caracteres', secret=True)
    confirmation, _ = field(body, 'Confirmar nueva contraseña', secret=True)
    notice = ttk.Label(body, style='Subtitle.TLabel', wraplength=560)
    notice.pack(fill='x', pady=12)
    notice.configure(text='Guarda la contraseña maestra en un lugar seguro.' if changing else 'Se conservarán pacientes, consultas, documentos y preferencias. Después inicia sesión con tu nueva contraseña.')
    def save():
        try:
            if password.get() != confirmation.get():
                raise DataError('Las contraseñas no coinciden.')
            if changing:
                app.auth.set_recovery_password(password.get(), current.get())
            else:
                app.auth.reset_password(user['id'], current.get(), password.get())
        except (ValueError, OSError) as exc:
            notice.configure(text=str(exc), style='error.TLabel')
            return
        for variable in (current, password, confirmation):
            variable.set('')
        win.destroy()
        app.status.set('Contraseña maestra configurada.' if changing else 'Contraseña restablecida. Inicia sesión con tu nueva contraseña.')
        if not changing and hasattr(app, 'login_page'):
            page = app.login_page
            page.password.set('')
            page.error.set('Contraseña restablecida. Ya puedes iniciar sesión.')
            page.error_label.configure(style='success.TLabel')
            page.error_label.pack(fill='x', before=page.submit, pady=8)
            page.entry.focus_set()
    ttk.Button(body, text='Guardar contraseña maestra' if changing else 'Restablecer contraseña', style='Primary.TButton', command=save).pack(anchor='e', pady=10)
    first.focus_set()
    app.theme._walk(win)
    return win
