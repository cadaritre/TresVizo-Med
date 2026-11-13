"""Limpieza diaria de lo que Med deja a medias (la ejecuta ``manage.py tv_limpiar``; ``Modulo.limpiezas`` de tvplataforma 1.1.2).

* archivos subidos que nunca se asociaron a un expediente, consulta o borrador, ni se incorporaron (72 h, ``TV_SUBIDAS_HORAS``);
* preparaciones de documentos abandonadas por un fallo a media copia (1 día);
* PDF (24 h) y descargas ZIP (24 h) generados por tareas.
"""
import time
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from tvplataforma import ajustes

from .db import atomico
from .models import ColaDocumentos

HORAS_PDF = 24
HORAS_DESCARGAS = 24
HORAS_PREPARACION = 24


def _viejo(ruta, horas):
    return ruta.is_file() and ruta.stat().st_mtime < time.time()-horas*3600


def subidas_huerfanas():
    """Borra los archivos de «subidos» (y de las colas de destino) con más de 72 h sin incorporarse. Devuelve cuántos."""
    horas = ajustes.valor('TV_SUBIDAS_HORAS')
    limite = timezone.now()-timedelta(hours=horas)
    borrados = 0
    with atomico():
        for cola in ColaDocumentos.objects.select_for_update().filter(actualizado__lt=limite):
            quedan, quitadas = [], []
            for fila in cola.filas:
                ruta = Path(fila.get('path', ''))
                if not ruta.is_file() or _viejo(ruta, horas):
                    quitadas.append(ruta)
                else:
                    quedan.append(fila)
            if len(quedan) != len(cola.filas):
                cola.filas = quedan
                cola.save(update_fields=['filas'])
            for ruta in quitadas:
                ruta.unlink(missing_ok=True)
                borrados += 1
    return borrados


def temporales():
    """Preparaciones abandonadas, PDF y descargas vencidos. Devuelve cuántos archivos borró."""
    raiz = Path(settings.TV_MED_ARCHIVOS)
    borrados = 0
    for carpeta, horas in ((raiz/'documentos'/'preparacion', HORAS_PREPARACION), (raiz/'pdf', HORAS_PDF), (raiz/'descargas', HORAS_DESCARGAS)):
        if not carpeta.is_dir():
            continue
        for ruta in carpeta.rglob('*'):
            if _viejo(ruta, horas):
                ruta.unlink(missing_ok=True)
                borrados += 1
    return borrados
