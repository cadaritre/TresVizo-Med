from unittest.mock import patch

import pytest

from app.main_window import Application
from app.themes import BUILTINS

pytestmark = pytest.mark.desktop


@pytest.fixture
def login_app(tmp_path):
    app = Application(tmp_path)
    first = app.auth.create_user('Dra. Elena Martínez', 'elena', 'Sintetica-local-12345')
    app.auth.login(first, 'Sintetica-local-12345')
    for index in range(10):
        uid = app.auth.create_user('Doctor de prueba '+str(index), 'doctor'+str(index), 'Sintetica-local-12345')
        app.profiles.save(uid, {'specialty': 'Pediatría' if index < 3 else 'Medicina general'})
    app.auth.logout()
    app.login_screen()
    app.update()
    yield app
    app.close()


def test_filtered_profiles_page_by_results_and_clear_hidden_credentials(login_app):
    page = login_app.login_page
    page.password.set('Captura sintética')
    page.visible.set(True)
    page.toggle_password()
    page.turn(1)
    assert len(page.cards) == 5
    page.query.set('pediatria')
    login_app.update()
    assert page.page == 0 and len(page.cards) == 3
    assert page.selected is None and page.password.get() == ''
    assert not page.visible.get() and page.entry.cget('show') == '•'
    assert page.submit.instate(['disabled'])
    page.query.set('no existe')
    login_app.update()
    assert not page.cards and page.empty.winfo_ismapped()
    page.query.set('elena')
    page.choose_result()
    login_app.update()
    assert page.selected['username'] == 'elena'
    assert not page.submit.instate(['disabled'])


def test_login_feedback_and_success_keep_authentication_service(login_app):
    page = login_app.login_page
    page.login()
    assert page.entry.instate(['invalid']) and 'Escribe' in page.error.get()
    assert login_app.auth.current is None
    page.password.set('Sintetica-local-12345')
    page.login()
    assert login_app.auth.current['username'] == 'elena'
    assert login_app.current_page == 'Pacientes'
    assert page.password.get() == ''


@pytest.mark.parametrize('scale,width,height', [(1, 1366, 768), (1, 940, 640), (1.5, 1366, 768), (2, 1366, 768)])
def test_login_resizes_without_losing_selection_password_or_theme(login_app, scale, width, height):
    app = login_app
    app.ui_scale = scale
    app.tk.call('tk', 'scaling', scale*96/72)
    app.geometry(f'{width}x{height}')
    app.login_screen()
    page = app.login_page
    page.password.set('Texto pendiente sintético')
    app.update()
    selected = page.selected['id']
    for palette in (BUILTINS['Clínico'], BUILTINS['Azul profundo']):
        app.theme.apply(palette)
        app.update()
        assert page.selected['id'] == selected and page.password.get() == 'Texto pendiente sintético'
        assert page.outer.winfo_width() <= page.canvas.winfo_width()
        assert page.access.winfo_rootx()+page.access.winfo_width() <= app.winfo_rootx()+app.winfo_width()
    page.reveal_access()
    app.update()
    assert page.entry.winfo_rooty() >= page.canvas.winfo_rooty()
    assert page.submit.winfo_rooty()+page.submit.winfo_height() <= page.canvas.winfo_rooty()+page.canvas.winfo_height()
