"""Limpieza diaria: subidas huérfanas, preparaciones, PDF y descargas vencidos."""
import os
import time
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.utils import timezone
from tvplataforma.subidas.destinos import ArchivoSubido, destinos_registrados

from tresvizo_med import limpieza
from tresvizo_med.models import ColaDocumentos
from tresvizo_med.servicios import Actor, documentos, pacientes
from .conftest import datos_paciente

pytestmark = pytest.mark.django_db(databases=['default', 'med'])


def envejecer(ruta, horas):
    antes = time.time()-horas*3600
    os.utime(ruta, (antes, antes))


@pytest.fixture
def medico(fabrica_actor):
    return Actor.de(fabrica_actor('medico'))


def subir(medico, imagen, nombre='a.png'):
    origen = imagen(nombre)
    archivo = ArchivoSubido(ruta=origen, nombre=nombre, tipo='image/png', tamano=origen.stat().st_size, sha256='x')
    return documentos.registrar_subida(medico, archivo)


def test_la_limpieza_esta_declarada_en_el_modulo_y_tv_limpiar_la_ejecuta(medico, imagen, capsys):
    from tvplataforma.modulos import modulo
    assert 'tresvizo_med.limpieza.subidas_huerfanas' in modulo('med').limpiezas
    fila = subir(medico, imagen)
    ColaDocumentos.objects.filter(profesional_id=medico.cuenta_id).update(actualizado=timezone.now()-timedelta(hours=100))
    envejecer(fila['path'], 100)
    call_command('tv_limpiar')
    salida = capsys.readouterr().out
    assert 'med: tresvizo_med.limpieza.subidas_huerfanas -> 1' in salida and not Path(fila['path']).exists()


def test_solo_se_borran_las_subidas_de_mas_de_72_horas(medico, imagen):
    vieja, reciente = subir(medico, imagen, 'vieja.png'), subir(medico, imagen, 'reciente.png')
    envejecer(vieja['path'], 80)
    ColaDocumentos.objects.update(actualizado=timezone.now()-timedelta(hours=80))
    assert limpieza.subidas_huerfanas() == 1
    assert not Path(vieja['path']).exists() and Path(reciente['path']).exists()
    assert [f['id'] for f in documentos.subidos(medico)] == [reciente['id']]


def test_una_subida_reciente_o_ya_incorporada_no_se_toca(medico, imagen):
    paciente = pacientes.guardar(medico, datos_paciente('Ana'))
    fila = subir(medico, imagen)
    documentos.asociar(medico, fila['id'], paciente=paciente.id)
    documento = documentos.incorporar(medico, fila['id'], paciente=paciente.id)
    ColaDocumentos.objects.update(actualizado=timezone.now()-timedelta(hours=200))
    assert limpieza.subidas_huerfanas() == 0
    assert documentos.ruta_verificada(medico, documento.id).is_file()


def test_una_fila_cuyo_archivo_ya_no_existe_se_retira(medico, imagen):
    fila = subir(medico, imagen)
    Path(fila['path']).unlink()
    ColaDocumentos.objects.update(actualizado=timezone.now()-timedelta(hours=100))
    limpieza.subidas_huerfanas()
    assert documentos.subidos(medico) == []


def test_temporales_vencidos(medico, settings):
    raiz = Path(settings.TV_MED_ARCHIVOS)
    archivos = {raiz/'pdf'/'1'/'a.pdf': 30, raiz/'pdf'/'1'/'b.pdf': 2, raiz/'descargas'/'1'/'c.zip': 30, raiz/'documentos'/'preparacion'/'d.png': 30}
    for ruta, horas in archivos.items():
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(b'x')
        envejecer(ruta, horas)
    assert limpieza.temporales() == 3
    assert (raiz/'pdf'/'1'/'b.pdf').exists() and not (raiz/'pdf'/'1'/'a.pdf').exists()
