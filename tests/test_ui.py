import tkinter as tk
from unittest.mock import patch
import pytest
from tkinter import ttk
from app.ui_theme import ThemeManager
from app.themes import BUILTINS
from app.components import Chart, DatePicker
from app.main_window import Application

pytestmark = pytest.mark.desktop


def test_windows_taskbar_identity_and_inherited_window_icons(tmp_path):
    import os
    if os.name != 'nt':
        pytest.skip('La identidad de la barra de tareas pertenece a Windows.')
    import ctypes
    from app.branding import APP_USER_MODEL_ID, ASSETS
    from PIL import Image
    app = Application(tmp_path)
    try:
        assert app.windows_identity_registered
        identifier = ctypes.c_void_p()
        get_id = ctypes.WinDLL('shell32').GetCurrentProcessExplicitAppUserModelID
        get_id.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        get_id.restype = ctypes.c_long
        assert get_id(ctypes.byref(identifier)) == 0
        try:
            assert ctypes.wstring_at(identifier) == APP_USER_MODEL_ID
        finally:
            free = ctypes.WinDLL('ole32').CoTaskMemFree
            free.argtypes = [ctypes.c_void_p]
            free(identifier)
        with Image.open(ASSETS / 'tresvizo_medico.ico') as ico:
            assert {(16,16), (32,32), (48,48), (256,256)} <= ico.ico.sizes()
        dialog = tk.Toplevel(app)
        app.theme._walk(dialog)
        app.update()
        send = ctypes.WinDLL('user32').SendMessageW
        send.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        send.restype = ctypes.c_ssize_t
        user32 = ctypes.WinDLL('user32')
        class_icon = getattr(user32, 'GetClassLongPtrW', user32.GetClassLongW)
        class_icon.argtypes = [ctypes.c_void_p, ctypes.c_int]
        class_icon.restype = ctypes.c_size_t
        for window in (app, dialog):
            hwnd = int(window.frame(), 16)
            # Windows recurre al icono de la clase para los diálogos que lo heredan.
            assert send(hwnd, 0x007F, 0, 0) or class_icon(hwnd, -34), 'La ventana necesita un icono pequeño.'
            assert send(hwnd, 0x007F, 1, 0) or class_icon(hwnd, -14), 'La ventana necesita un icono grande.'
        dialog.destroy()
    finally:
        app.close()


def test_icon_only_actions_keep_tooltips_keyboard_and_theme_state(tmp_path):
    from app.profiles import ProfileEditor
    app = Application(tmp_path)
    try:
        uid = app.auth.create_user('Doctora de prueba', 'prueba', 'Sintetica-12345')
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        for label, button in app.nav_buttons.items():
            assert str(button.cget('compound')) == 'left'
            assert button.tooltip.text == label == button.action_label
        patients = app.nav_buttons['Pacientes']
        patients.focus_force()
        app.update()
        patients.event_generate('<KeyPress-space>')
        app.after(550, app.quit)
        app.mainloop()
        assert app.current_page == 'Pacientes'
        assert str(patients.cget('style')) == 'Active.Nav.TButton'
        for name, palette in BUILTINS.items():
            app.theme.apply(palette)
            assert patients.icon == app.icons.photo('users', int(18*app.ui_scale), app.theme.tokens['on_selection'])
            images = tuple(map(str, patients.cget('image')))
            assert 'disabled' in images and 'pressed' in images and 'active' in images
        focus = app.focus_get()
        patients.tooltip.show()
        app.update_idletasks()
        assert patients.tooltip.window.winfo_viewable()
        assert app.focus_get() == focus
        patients.tooltip.hide()
        app.show('Mi perfil')
        profile = next(w for w in app.pages['Mi perfil'].winfo_children() if isinstance(w, ProfileEditor))
        for button in profile.avatar_buttons.values():
            assert str(button.cget('compound')) == 'none'
            assert button.tooltip.text
        profile.avatar_buttons['gato'].invoke()
        assert str(profile.avatar_buttons['gato'].cget('style')) == 'Active.Nav.TButton'
        assert sum(str(b.cget('style')) == 'Active.Nav.TButton' for b in profile.avatar_buttons.values()) == 1
        for future in list(app.pending):
            future.result(timeout=10)
    finally:
        app.close()


def test_live_theme_preserves_widgets_text_cursor_selection_focus():
    root = tk.Tk()
    try:
        theme = ThemeManager(root)
        theme.apply(BUILTINS['Clínico'])
        entry = ttk.Entry(root)
        entry.pack()
        entry.insert(0, 'Borrador con acentos áéíóú')
        entry.icursor(7)
        entry.selection_range(1, 4)
        root.update()
        entry.focus_force()
        root.update()
        top = tk.Toplevel(root)
        text = tk.Text(top)
        text.pack()
        text.insert('1.0', 'Texto clínico sintético sin guardar')
        chart = Chart(root, theme, {'Lunes': 4})
        chart.pack()
        entry.focus_force()
        root.update()
        original = (str(entry), entry.get(), entry.index('insert'), root.focus_get(), text.get('1.0', 'end'))
        for name, palette in BUILTINS.items():
            theme.apply(palette)
            root.update_idletasks()
            assert (str(entry), entry.get(), entry.index('insert'), root.focus_get(), text.get('1.0', 'end')) == original
            assert entry.selection_present()
            assert text.cget('background').upper() == palette['surface']
            assert chart.cget('background').upper() == palette['surface']
            assert top.winfo_exists()
    finally:
        root.destroy()


def test_all_screens_session_change_and_private_drafts(tmp_path):
    app = Application(tmp_path)
    try:
        first = app.auth.create_user('Doctora uno', 'uno', 'Sintetica-12345')
        app.auth.login(first, 'Sintetica-12345')
        second = app.auth.create_user('Doctor dos', 'dos', 'Sintetica-12345')
        app.shell()
        patient = app.clinic.save('patients', {'name': 'Paciente de prueba'})
        draft = app.clinic.save('encounters', {'patient_id': patient['id'], 'status': 'Borrador', 'attended_at': '2026-09-10T09:00:00-06:00'})
        for page in ('Inicio', 'Pacientes', 'Consultas', 'Más opciones', 'Mis estadísticas', 'Exportar y respaldar', 'Configuración', 'Acerca de'):
            app.show(page)
            app.update_idletasks()
        for future in list(app.pending):
            future.result(timeout=10)
        app.appearance.apply('Azul profundo')
        app.theme.apply(app.appearance.tokens())
        app.logout()
        assert app.auth.current is None
        assert app.theme.tokens['background'] == BUILTINS['Clínico']['background']
        app.auth.login(second, 'Sintetica-12345')
        assert draft['id'] not in [r['id'] for r in app.clinic.list('encounters')]
        assert app.appearance.active_key() == 'Clínico'
        app.shell()
        for future in list(app.pending):
            future.result(timeout=10)
    finally:
        app.close()


@pytest.mark.parametrize('scale', [1, 1.25, 1.5, 2])
def test_editor_actions_remain_in_window_at_tk_scaling(tmp_path, scale):
    original_init = tk.Tk.__init__
    def init(root, *args, **kwargs):
        original_init(root, *args, **kwargs)
        root.tk.call('tk', 'scaling', scale*96/72)
    with patch.object(tk.Tk, '__init__', init):
        app = Application(tmp_path)
    try:
        uid = app.auth.create_user('Doctora de prueba', 'prueba', 'Sintetica-12345')
        app.auth.login(uid, 'Sintetica-12345')
        app.shell()
        app.show('Configuración')
        app.update_idletasks()
        def widgets(widget):
            for child in widget.winfo_children():
                yield child
                yield from widgets(child)
        from app.appearance_ui import AppearanceEditor
        appearance = next(w for w in widgets(app) if isinstance(w, AppearanceEditor))
        buttons = [w for w in widgets(appearance) if isinstance(w, ttk.Button) and w.cget('text') in
                   ('Aplicar cambios', 'Cancelar cambios')]
        assert len(buttons) == 2
        for button in buttons:
            assert button.winfo_rootx() >= app.winfo_rootx()
            assert button.winfo_rootx()+button.winfo_width() <= app.winfo_rootx()+app.winfo_width()
            assert button.winfo_rooty()+button.winfo_height() <= app.winfo_rooty()+app.winfo_height()
        for future in list(app.pending):
            future.result(timeout=10)
    finally:
        app.close()
