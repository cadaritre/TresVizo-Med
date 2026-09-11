from pathlib import Path
import sys
import webbrowser
from PIL import Image, ImageTk
from app.themes import DEFAULT_IDENTITY, validate_url, color
from app.storage import DataError
import uuid

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'assets'
APP_USER_MODEL_ID = 'TresVizo.Med.Desktop'
APP_ICON = ASSETS / 'clinica.ico'
APP_MARK = ASSETS / 'clinica_cruz.png'
APP_TILE = ASSETS / 'clinica_icono.png'


def register_windows_identity():
    """Separar la aplicación del anfitrión Python antes de crear ventanas."""
    import os
    if os.name != 'nt':
        return False
    import ctypes
    try:
        register = ctypes.WinDLL('shell32').SetCurrentProcessExplicitAppUserModelID
        register.argtypes = [ctypes.c_wchar_p]
        register.restype = ctypes.c_long
        return register(APP_USER_MODEL_ID) >= 0
    except (AttributeError, OSError):
        return False


def set_window_icon(window, default=False):
    identity = getattr(window._root(), 'identity', None)
    values = identity.values if identity else {}
    custom = values.get('clinic_icon') if values.get('use_clinic_icon') else None
    icon = Path(custom) if custom and Path(custom).is_file() else APP_ICON
    window.logo = photo_from_path(icon, 96, master=window)
    window.iconphoto(default, window.logo)
    if sys.platform == 'win32' and icon.exists():
        if default:
            window.iconbitmap(default=str(icon))
        window.iconbitmap(str(icon))
    window.brand_icon_set = True
    window.brand_icon_path = str(icon)


class Identity:
    def __init__(self, store, auth):
        self.store, self.auth = store, auth
        self.values = {**DEFAULT_IDENTITY, **store.read('config/identity.json', {})}

    def save(self, values):
        self.auth.require('admin')
        data = {**self.values, **values}
        self.validate(data)
        self.store.write('config/identity.json', data)
        self.values = data
        self.auth.audit('actualizar_identidad', 'clinica')

    @staticmethod
    def validate(data):
        validate_url(data['website'])
        for key in ('app_name', 'clinic_name', 'website_text'):
            if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > 120:
                raise DataError('Completa los nombres y el texto visible (máximo 120 caracteres).')
        for key in ('document_primary', 'document_text'):
            color(data[key])

    def open_website(self):
        if not webbrowser.open(validate_url(self.values['website']), new=2):
            raise DataError('No se pudo abrir el navegador predeterminado.')

    def set_clinic_logo(self, source):
        self.auth.require('admin')
        self.save(self.prepare_clinic_logo(source))

    def prepare_clinic_logo(self, source):
        """Validar y normalizar una copia local; nunca referenciar la imagen externa."""
        path = Path(source)
        if path.stat().st_size > 10_000_000:
            raise DataError('El logo de la clínica debe ser menor de 10 MB.')
        with Image.open(path) as image:
            if image.format not in ('PNG', 'JPEG', 'ICO') or image.width*image.height > 20_000_000:
                raise DataError('Elige PNG, JPEG o ICO de hasta 20 megapíxeles.')
            normalized = image.convert('RGBA')
            normalized.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        destination = self.store.root / 'config' / ('clinic-logo-'+str(uuid.uuid4())+'.png')
        destination.parent.mkdir(parents=True, exist_ok=True)
        normalized.save(destination)
        tile = Image.new('RGBA', (256, 256))
        normalized.thumbnail((240, 240), Image.Resampling.LANCZOS)
        tile.alpha_composite(normalized, ((256-normalized.width)//2, (256-normalized.height)//2))
        icon = destination.with_suffix('.ico')
        tile.save(icon, sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
        return {'clinic_logo': str(destination), 'clinic_icon': str(icon)}


def logo_photo(size=80, dark=False, master=None):
    return photo_from_path(APP_TILE if dark else APP_MARK, size, master)


def photo_from_path(path, size=80, master=None):
    with Image.open(path) as source:
        image = source.convert('RGBA')
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image, master=master)
