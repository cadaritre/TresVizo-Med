"""Utilidades de texto y tiempo comunes a las reglas clínicas."""
from datetime import datetime
import unicodedata


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def normalized(value):
    """Minúsculas, sin acentos y con espacios colapsados; base de la búsqueda de pacientes."""
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c)).split())
