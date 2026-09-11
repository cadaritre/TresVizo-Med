import tkinter as tk
from unittest.mock import patch
import pytest
from tkinter import ttk
from app.ui_theme import ThemeManager
from app.themes import BUILTINS
from app.components import Chart, DatePicker
from app.main_window import Application


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
        for page in ('Inicio', 'Pacientes', 'Consultas', 'Agenda', 'Seguimientos', 'Mis estadísticas', 'Exportar y respaldar', 'Configuración', 'Acerca de'):
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
        buttons = [w for w in widgets(app) if isinstance(w, ttk.Button) and w.cget('text') in
                   ('Aplicar cambios', 'Cancelar cambios', 'Guardar con nombre', 'Restablecer Clínico')]
        assert len(buttons) == 4
        for button in buttons:
            assert button.winfo_rootx() >= app.winfo_rootx()
            assert button.winfo_rootx()+button.winfo_width() <= app.winfo_rootx()+app.winfo_width()
            assert button.winfo_rooty()+button.winfo_height() <= app.winfo_rooty()+app.winfo_height()
        for future in list(app.pending):
            future.result(timeout=10)
    finally:
        app.close()
