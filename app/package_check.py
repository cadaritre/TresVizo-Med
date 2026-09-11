"""Verificación explícita del paquete sin abrir ni modificar datos de la clínica."""
from pathlib import Path
import struct
import tempfile
import traceback
from app.storage import atomic_json
from app.version import VERSION


def run_check(report):
    result = {'version': VERSION, 'bits': struct.calcsize('P')*8, 'ok': False, 'checks': []}
    app = None
    try:
        with tempfile.TemporaryDirectory(prefix='tresvizo-package-check-') as folder:
            from app.main_window import Application
            from app.branding import ASSETS
            from PIL import Image
            from reportlab.pdfgen import canvas
            import pypdfium2
            app = Application(folder)
            app.withdraw()
            app.update()
            assert app.tk.call('package', 'present', 'tkdnd')
            assert app.brand_icon_set
            result['checks'].extend(['tkinter', 'tkdnd', 'login', 'icono'])
            if __import__('sys').platform == 'win32':
                import ctypes
                from app.branding import APP_USER_MODEL_ID
                assert app.windows_identity_registered
                identifier = ctypes.c_void_p()
                shell = ctypes.WinDLL('shell32')
                shell.GetCurrentProcessExplicitAppUserModelID.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
                assert shell.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(identifier)) == 0
                try:
                    assert ctypes.wstring_at(identifier) == APP_USER_MODEL_ID
                finally:
                    release = ctypes.WinDLL('ole32').CoTaskMemFree
                    release.argtypes = [ctypes.c_void_p]
                    release(identifier)
                user32 = ctypes.WinDLL('user32')
                send = user32.SendMessageW
                send.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
                send.restype = ctypes.c_ssize_t
                class_icon = getattr(user32, 'GetClassLongPtrW', user32.GetClassLongW)
                class_icon.argtypes = [ctypes.c_void_p, ctypes.c_int]
                class_icon.restype = ctypes.c_size_t
                handle = int(app.frame(), 16)
                assert send(handle, 0x007F, 0, 0) or class_icon(handle, -34)
                assert send(handle, 0x007F, 1, 0) or class_icon(handle, -14)
                result['checks'].extend(['identidad_barra_tareas', 'iconos_ventana_pequeno_grande'])
            uid = app.auth.create_user('Doctor sintético del paquete', 'package-test', 'Sintetica-paquete-12345')
            app.login_screen()
            app.update()
            assert app.login_page.selected['id'] == uid
            assert uid in app.login_page.cards
            result['checks'].append('seleccion_medicos')
            with Image.open(ASSETS/'clinica.ico') as logo:
                assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= logo.ico.sizes()
            pdf = Path(folder)/'prueba.pdf'
            document = canvas.Canvas(str(pdf))
            document.drawString(40, 800, 'Documento sintetico de verificacion')
            document.save()
            with pypdfium2.PdfDocument(pdf) as pages:
                page = pages[0]
                bitmap = page.render(scale=0.5)
                assert bitmap.width > 0
                bitmap.close()
                page.close()
            result['checks'].extend(['pdf_exportacion', 'pdf_vista_previa'])
            app.close()
            app = None
        result['ok'] = True
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        if app is not None:
            app.close()
    atomic_json(Path(report), result)
    return 0 if result['ok'] else 1
