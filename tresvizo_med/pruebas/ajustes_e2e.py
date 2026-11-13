"""Ajustes para las pruebas de punta a punta (Playwright): las de la app más los estáticos que sirve el servidor en vivo."""
from .ajustes import *  # noqa: F403

INSTALLED_APPS = ["django.contrib.staticfiles", *INSTALLED_APPS]  # noqa: F405
STATIC_URL = "/static/"
