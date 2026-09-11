"""Inspección local con datos temporales, sin cuentas en la distribución."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main_window import Application

with tempfile.TemporaryDirectory(prefix='registro-clinico-qa-') as directory:
    app = Application(directory)
    uid = app.auth.create_user('Doctora de demostración', 'demo', 'Solo-Pruebas-12345')
    app.auth.login(uid, 'Solo-Pruebas-12345')
    app.identity.save({'clinic_name': 'Clínica · vista de prueba'})
    app.shell()
    app.show('Configuración')
    app.mainloop()
