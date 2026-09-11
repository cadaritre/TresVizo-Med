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
            with Image.open(ASSETS/'tresvizo_medico.ico') as logo:
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
