"""Regresión «Paracetamol8»: lo que se teclea nunca cae en otro campo.

Causa: htmx enfoca los [autofocus] del contenido nuevo en su fase «settle», un temporizador después de insertarlo. Si en ese
intervalo la persona ya pasó a otro campo (o el equipo va lento y el temporizador se retrasa), el foco saltaba al nombre del
medicamento y la frecuencia «8» terminaba en él. Ahora el foco se da en el mismo instante en que llega el contenido y nunca se
mueve si ya se escribe en un campo. Para que el intervalo sea grande y la prueba determinista, se alarga la fase «settle» a
900 ms (como un teléfono lento) y en Chromium se frena además la CPU.

``MOTOR=webkit`` corre las mismas pruebas en WebKit (fixture ``navegador`` de conftest); ``VUELTAS=30`` repite la captura rápida.
"""
import os

import pytest
from playwright.sync_api import expect

from tresvizo_med.servicios import Actor, consultas, pacientes
from .conftest import guardado

pytestmark = pytest.mark.django_db(transaction=True, databases=['default', 'med'])
MOTOR = os.environ.get('MOTOR', 'chromium')
VUELTAS = int(os.environ.get('VUELTAS', '3'))


def abrir_consulta(fabrica_sesion, lenta=True):
    s = fabrica_sesion('medico', username='dra')
    actor = Actor.de(s.usuario)
    p = pacientes.guardar(actor, {'name': 'Ana Muñoz'})
    c, _ = consultas.iniciar(actor, p.id)
    pagina = s.ir(f'/consultas/{c.id}/')
    if MOTOR == 'chromium':
        s.contexto.new_cdp_session(pagina).send('Emulation.setCPUThrottlingRate', {'rate': 4})
    if lenta:
        pagina.evaluate('htmx.config.defaultSettleDelay = 900')  # intervalo largo entre insertar y «settle»
    return pagina


@pytest.mark.parametrize('tipo, otro, texto', [('medication', 'input[name=frequency]', '88888888'),
                                               ('medication', 'input[name=dose]', '1234567'),
                                               ('study', 'textarea[name=notes]', 'Ayuno de doce horas'),
                                               ('vitals', 'input[name=v_diastolic]', '8080808')])
def test_escribir_en_otro_campo_justo_al_abrir_la_captura(fabrica_sesion, tipo, otro, texto):
    pagina = abrir_consulta(fabrica_sesion)
    pagina.locator(f'#resumenes button[hx-get*="/{tipo}/"], #campo-diagnosis button[hx-get*="/{tipo}/"]').first.click()
    campo = pagina.locator(f'#captura {otro}')
    campo.wait_for()
    campo.click()
    pagina.keyboard.type(texto, delay=120)  # 120 ms por tecla: atraviesa la fase «settle» de 900 ms
    expect(campo).to_have_value(texto)
    expect(campo).to_be_focused()
    if tipo != 'vitals':
        expect(pagina.locator('#captura input[name=name]')).to_have_value('')


@pytest.mark.parametrize('vuelta', range(VUELTAS))
def test_captura_rapida_de_medicamento_sin_teclas_perdidas_ni_cruzadas(fabrica_sesion, vuelta):
    pagina = abrir_consulta(fabrica_sesion)
    pagina.locator('#resumenes button[hx-get*="/medication/"]').first.click()
    nombre = pagina.locator('#captura input[name=name]')
    expect(nombre).to_be_focused()  # el nombre recibe el foco al abrir, sin esperar a «settle»
    pagina.keyboard.type('Paracetamol', delay=25)
    pagina.locator('#captura input[name=dose]').click()
    pagina.keyboard.type('1', delay=25)
    pagina.select_option('#captura select[name=dose_unit]', 'tableta')
    pagina.select_option('#captura select[name=route]', 'Oral')
    pagina.locator('#captura input[name=frequency]').click()
    pagina.keyboard.type('8', delay=25)
    pagina.wait_for_timeout([0, 400, 1100][vuelta % 3])  # con y sin el guardado de fondo de la captura (900 ms)
    expect(nombre).to_have_value('Paracetamol')
    expect(pagina.locator('#captura input[name=frequency]')).to_have_value('8')
    pagina.click('#captura button[value=aplicar]')
    expect(pagina.locator('#resumenes')).to_contain_text('Paracetamol')
    resumen = pagina.locator('#resumenes').inner_text()
    assert 'Paracetamol8' not in resumen and 'Cada 8 horas' in resumen, resumen


def test_un_error_de_validacion_lleva_el_foco_al_campo_que_falta(fabrica_sesion):
    pagina = abrir_consulta(fabrica_sesion, lenta=False)
    pagina.locator('#resumenes button[hx-get*="/medication/"]').first.click()
    pagina.locator('#captura input[name=dose]').fill('1')
    pagina.click('#captura button[value=aplicar]')
    expect(pagina.locator('#captura input[name=name][aria-invalid=true]')).to_be_focused()


def test_una_subida_que_termina_no_borra_lo_que_se_escribe_en_otro_documento(fabrica_sesion, tmp_path):
    from PIL import Image
    s = fabrica_sesion('medico', username='dra')
    p = pacientes.guardar(Actor.de(s.usuario), {'name': 'Ana Muñoz'})
    pagina = s.ir(f'/pacientes/{p.id}/?pestana=documentos')
    archivos = []
    for n in range(2):
        ruta = tmp_path/f'placa{n}.png'
        Image.new('RGB', (64 + n, 40), '#3a7').save(ruta)
        archivos.append(str(ruta))
    pagina.locator('tv-subida input[type=file]').first.set_input_files(archivos[0])
    expect(pagina.locator('#cola-docs form')).to_have_count(1, timeout=15000)
    titulo = pagina.locator('#cola-docs form [name=titulo]').first
    titulo.fill('Radiografía de tórax, proyección')
    titulo.focus()
    pagina.locator('tv-subida input[type=file]').first.set_input_files(archivos[1])  # la cola se vuelve a pintar al terminar
    expect(pagina.locator('#cola-docs form')).to_have_count(2, timeout=15000)
    expect(titulo).to_have_value('Radiografía de tórax, proyección')
    pagina.keyboard.type(' lateral')
    expect(titulo).to_have_value('Radiografía de tórax, proyección lateral')
