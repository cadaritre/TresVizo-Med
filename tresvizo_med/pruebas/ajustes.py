"""Ajustes para correr las pruebas de la app solas (contrato tvplataforma §3.8)."""
from tvplataforma.pruebas.ajustes import *  # noqa: F403

INSTALLED_APPS += ["tresvizo_med"]  # noqa: F405
DATABASES = bases_de_prueba(med=True)  # noqa: F405
DATABASE_ROUTERS = ["tvplataforma.pruebas.EnrutadorMed"]
ROOT_URLCONF = "tresvizo_med.pruebas.urls"
TV_MED_ARCHIVOS = carpeta_temporal()  # noqa: F405
