"""Vista del acceso con perfiles ficticios en una carpeta temporal."""
import argparse
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main_window import Application

parser = argparse.ArgumentParser()
parser.add_argument('--width', type=int, default=1366)
parser.add_argument('--height', type=int, default=768)
parser.add_argument('--theme', default='Clínico')
parser.add_argument('--scale', type=float, default=1)
parser.add_argument('--seconds', type=int, default=180)
args = parser.parse_args()

with tempfile.TemporaryDirectory(prefix='tresvizo-acceso-') as directory:
    app = Application(directory)
    first = app.auth.create_user('Dra. Elena Martínez', 'elena', 'Sintetica-local-12345')
    app.auth.login(first, 'Sintetica-local-12345')
    app.profiles.save(first, {'avatar': 'zorro', 'specialty': 'Medicina general'})
    for name, username, avatar, specialty in [
            ('Dr. Andrés Rivera', 'andres', 'oso', 'Medicina interna'),
            ('Dra. Sofía Hernández', 'sofia', 'buho', 'Pediatría'),
            ('Dr. Gabriel Torres', 'gabriel', 'koala', 'Medicina general')]:
        uid = app.auth.create_user(name, username, 'Sintetica-local-12345')
        app.profiles.save(uid, {'avatar': avatar, 'specialty': specialty})
    app.identity.save({'clinic_name': 'Clínica de demostración · datos ficticios'})
    app.auth.logout()
    app.ui_scale = args.scale
    app.tk.call('tk', 'scaling', args.scale*96/72)
    app.geometry(f'{args.width}x{args.height}')
    app.login_screen()
    app.theme.apply(app.appearance.list()[args.theme]['tokens'])
    app.title('TresVizo Med · vista de acceso · datos ficticios')
    app.after(args.seconds*1000, app.close)
    app.mainloop()
