"""Estáticos en producción: cada URL sale de su propio {% static %} (nombre con hash); nada la deriva de otra ni escribe /static/."""
import json
import re
from pathlib import Path

import pytest
from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from django.core.management import call_command
from django.test import modify_settings

from tresvizo_med.servicios import Actor, documentos, pacientes
from .conftest import datos_paciente, reverse_med as reverse

pytestmark = pytest.mark.django_db(databases=['default', 'med'])
APP = Path(__file__).resolve().parents[1]


class AlmacenComoProduccion(ManifestStaticFilesStorage):
    manifest_strict = False


def test_ninguna_plantilla_ni_js_escribe_static_ni_arma_rutas_de_estaticos():
    """Herramientas tuvo el error del trabajador de MapLibre derivado de otra URL: aquí cada archivo llega por su atributo."""
    for ruta in [*APP.glob('templates/**/*.html'), *APP.glob('static/med/*.js'), *APP.glob('**/*.py')]:
        if 'pruebas' in ruta.parts:
            continue
        texto = ruta.read_text(encoding='utf-8')
        assert '/static/' not in texto, ruta
        assert not re.search(r"\{% static '[^']*/' %\}", texto), ruta  # nunca una carpeta + un nombre
    js = (APP/'static/med/med-pdf.js').read_text()
    assert 'import(raiz.dataset.lib)' in js and 'workerSrc = raiz.dataset.worker' in js  # biblioteca y trabajador, cada uno con su URL


def test_visor_pdf_con_biblioteca_y_trabajador_con_hash(cliente_med, settings, tmp_path, imagen):
    from reportlab.pdfgen import canvas
    cliente = cliente_med('medico', username='dra')
    actor = Actor.de(cliente.usuario)
    p = pacientes.guardar(actor, datos_paciente('Ana Muñoz'))
    ruta = tmp_path/'r.pdf'
    c = canvas.Canvas(str(ruta)); c.drawString(72, 720, 'Prueba'); c.showPage(); c.save()
    doc = documentos.agregar(actor, ruta, paciente=p.id, categoria='Laboratorio', titulo='Resultado')
    with modify_settings(INSTALLED_APPS={'append': 'django.contrib.staticfiles'}):
        settings.STATIC_ROOT = str(tmp_path/'estaticos')
        settings.STORAGES = {**settings.STORAGES, 'staticfiles': {'BACKEND': f'{__name__}.AlmacenComoProduccion'}}
        call_command('collectstatic', '--noinput', verbosity=0)
        manifiesto = json.loads((tmp_path/'estaticos'/'staticfiles.json').read_text())['paths']
        html = cliente.get(reverse('med:visor', args=[doc.id])).content.decode()
    for archivo in ('med/vendor/pdfjs/pdf.min.mjs', 'med/vendor/pdfjs/pdf.worker.min.mjs', 'med/med-pdf.js', 'med/med.css'):
        con_hash = manifiesto[archivo]
        assert con_hash != archivo and f'/static/{con_hash}"' in html
        assert (tmp_path/'estaticos'/con_hash).is_file()
    sin_hash = [u for u in re.findall(r'(?:src|href|data-lib|data-worker)="(/static/[^"]+)"', html) if not re.search(r'\.[0-9a-f]{12}\.', u)]
    assert sin_hash == []
