from pathlib import Path
import sys
import webbrowser
from PIL import Image, ImageTk
from app.themes import DEFAULT_IDENTITY, validate_url, color
from app.storage import DataError
import shutil
import uuid

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent)) / 'assets'


class Identity:
    def __init__(self, store, auth):
        self.store, self.auth = store, auth
        self.values = {**DEFAULT_IDENTITY, **store.read('config/identity.json', {})}

    def save(self, values):
        self.auth.require('admin')
        data = {**self.values, **values}
        validate_url(data['website'])
        for key in ('app_name', 'clinic_name', 'website_text'):
            if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > 120:
                raise DataError('Completa los nombres y el texto visible (máximo 120 caracteres).')
        for key in ('document_primary', 'document_text'):
            color(data[key])
        self.store.write('config/identity.json', data)
        self.values = data
        self.auth.audit('actualizar_identidad', 'clinica')

    def open_website(self):
        if not webbrowser.open(validate_url(self.values['website']), new=2):
            raise DataError('No se pudo abrir el navegador predeterminado.')

    def set_clinic_logo(self, source):
        self.auth.require('admin')
        path = Path(source)
        if path.stat().st_size > 10_000_000:
            raise DataError('El logo de la clínica debe ser menor de 10 MB.')
        with Image.open(path) as image:
            if image.format not in ('PNG', 'JPEG'):
                raise DataError('Elige una imagen PNG o JPEG.')
            image.verify()
        destination = self.store.root / 'config' / ('clinic-logo-'+str(uuid.uuid4())+path.suffix.lower())
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        self.save({'clinic_logo': str(destination)})


def logo_photo(size=80, dark=False):
    path = ASSETS / ('tresvizo_medico_oscuro.png' if dark else 'tresvizo_medico.png')
    if not path.exists():
        path = ASSETS / 'tresvizo_medico.png'
    image = Image.open(path).convert('RGBA')
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    return ImageTk.PhotoImage(image)
