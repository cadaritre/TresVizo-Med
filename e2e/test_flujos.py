"""Recorridos principales de Med en escritorio (1280×800): búsqueda, alta, consulta, finalizar, adenda, documentos, PDF, estadísticas y exportar."""
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tresvizo_med.dominio.documents import create_pdf
from tresvizo_med.dominio.themes import DEFAULT_IDENTITY
from tresvizo_med.models import Consulta, Paciente
from tresvizo_med.servicios import consultas, pacientes
from .conftest import guardado

pytestmark = pytest.mark.django_db(transaction=True, databases=['default', 'med'])
MEDICAMENTO = {'name': 'Paracetamol', 'strength': '500 mg', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral', 'frequency': '8', 'frequency_kind': 'Cada N horas'}


def paciente(actor, nombre='Ana Muñoz', **extra):
    return pacientes.guardar(actor, {'name': nombre, 'birth_date': '1990-05-01', 'phone': '5551234', **extra})


def finalizada(actor, p, **extra):
    return consultas.guardar(actor, {'patient_id': str(p.id), 'status': 'Finalizada', 'attended_at': '2026-09-10T10:15:23-06:00', 'type': 'General',
                                     'reason': 'Dolor de cabeza', 'assessment': 'Migraña', 'plan': 'Reposo', **extra})


def test_busqueda_con_atajos_y_resultados_en_tarjetas(medico, actor):
    for nombre in ('Ana Muñoz', 'Luis Pérez', 'María Núñez'):
        paciente(actor, nombre)
    pagina = medico.ir('/pacientes/')
    expect(pagina.locator('[data-resultado]')).to_have_count(3)
    pagina.locator('#q').click()  # la búsqueda de la página ya tiene el foco al entrar
    pagina.keyboard.type('nunez')
    expect(pagina.locator('[data-resultado]')).to_have_count(1)
    expect(pagina.locator('[data-resultado]')).to_contain_text('María Núñez')
    pagina.wait_for_url(re.compile(r'q=nunez'))  # la búsqueda se conserva en la URL
    pagina.keyboard.press('ArrowDown')
    pagina.keyboard.press('Enter')
    pagina.wait_for_url(re.compile(r'/pacientes/[0-9a-f-]{36}/'))
    expect(pagina.locator('h1')).to_contain_text('María Núñez')
    # La paleta del armazón (Ctrl+K) también busca pacientes, solo de Med, y abre el expediente
    pagina.keyboard.press('Control+k')
    pagina.keyboard.type('luis')
    resultado = pagina.locator('[data-tv-ir^="/pacientes/"]', has_text='Luis Pérez')
    expect(resultado).to_be_visible()
    expect(resultado).not_to_contain_text('55')  # sin teléfono en la paleta
    resultado.click()
    pagina.wait_for_url(re.compile(r'/pacientes/[0-9a-f-]{36}/'))
    expect(pagina.locator('h1')).to_contain_text('Luis Pérez')


def test_alta_con_borrador_que_sobrevive_a_recargar_y_comienza_la_consulta(medico, actor):
    pagina = medico.ir('/pacientes/nuevo/')
    pagina.fill('#id_name', 'Luis Pérez')
    pagina.select_option('#id_sex', 'Masculino')
    pagina.locator('summary', has_text='Contacto').first.click()
    pagina.locator('#filas-phones ~ button').click()
    expect(pagina.locator('#filas-phones [data-fila]')).to_have_count(1)
    pagina.locator('#filas-phones input[name$="__number"]').fill('5550001')
    from tresvizo_med.models import BorradorAlta
    for _ in range(40):  # el borrador se guarda 900 ms después de dejar de escribir
        if BorradorAlta.objects.get().contenido.get('phone') == '5550001':
            break
        pagina.wait_for_timeout(250)
    assert BorradorAlta.objects.get().contenido['phone'] == '5550001'
    pagina.reload()
    expect(pagina.locator('#id_name')).to_have_value('Luis Pérez')
    expect(pagina.locator('#filas-phones input[name$="__number"]')).to_have_value('5550001')
    pagina.click('button[name=comenzar][value="1"]')
    pagina.wait_for_url(re.compile(r'/consultas/[0-9a-f-]{36}/'))
    expect(pagina.locator('h1')).to_contain_text('Luis Pérez')
    expect(pagina.locator('.med-estado--borrador')).to_be_visible()
    assert Paciente.objects.get().folio.startswith('RC-') and Consulta.objects.get().estado == 'Borrador'


def test_consulta_completa_hasta_finalizar_y_lectura(medico, actor):
    p = paciente(actor, allergy_records=[{'substance': 'Penicilina'}], allergy_status='Alergias registradas')
    c, _ = consultas.iniciar(actor, p.id)
    pagina = medico.ir(f'/consultas/{c.id}/')
    expect(pagina.locator('.med-alergias')).to_contain_text('Penicilina')
    pagina.fill('#id_reason', 'Dolor de cabeza desde ayer')
    guardado(pagina)
    # Signos vitales en el panel lateral
    pagina.locator('#resumenes button[hx-get*="/vitals/"]').first.click()
    pagina.fill('input[name=v_systolic]', '120')
    pagina.fill('input[name=v_diastolic]', '80')
    pagina.click('#captura button[value=aplicar]')
    expect(pagina.locator('#resumenes')).to_contain_text('Presión: 120 / 80 mmHg')
    expect(pagina.locator('#panel')).to_be_empty()
    # Medicamento
    pagina.locator('#resumenes button[hx-get*="/medication/"]').first.click()
    pagina.fill('input[name=name]', 'Paracetamol')
    pagina.fill('input[name=dose]', '1')
    pagina.select_option('select[name=dose_unit]', 'tableta')
    pagina.select_option('select[name=route]', 'Oral')
    pagina.fill('input[name=frequency]', '8')
    pagina.click('#captura button[value=aplicar]')
    expect(pagina.locator('#resumenes')).to_contain_text('Paracetamol')
    # Diagnóstico y plan
    pagina.click('#campo-diagnosis >> text=Agregar diagnóstico')
    pagina.fill('input[name=name]', 'Migraña')
    pagina.click('#captura button[value=aplicar]')
    expect(pagina.locator('#diagnosticos')).to_contain_text('Migraña')
    pagina.fill('#id_plan', 'Reposo e hidratación')
    guardado(pagina)
    # Ctrl+Enter abre la revisión
    pagina.keyboard.press('Control+Enter')
    pagina.wait_for_url(re.compile(r'/revisar/'))
    expect(pagina.locator('.tv-alerta--exito')).to_contain_text('Todo listo')
    pagina.click('button:has-text("Finalizar consulta")')
    pagina.wait_for_url(re.compile(r'/consultas/[0-9a-f-]{36}/$'))
    expect(pagina.locator('.med-estado--finalizada')).to_be_visible()
    expect(pagina.locator('.med-lectura')).to_contain_text('Migraña')
    c.refresh_from_db()
    assert c.estado == 'Finalizada' and c.motivo == 'Dolor de cabeza desde ayer' and c.contenido['prescriptions'][0]['name'] == 'Paracetamol'
    assert pagina.locator('#id_reason').count() == 0  # ya no es editable


def test_adenda_anulacion_y_restauracion(medico, actor):
    p = paciente(actor)
    c = finalizada(actor, p)
    pagina = medico.ir(f'/consultas/{c.id}/')
    pagina.locator('summary', has_text='Agregar adenda').click()
    pagina.fill('#adenda-motivo', 'Aclaración')
    pagina.fill('#adenda-contenido', 'El paciente refiere mejoría.')
    pagina.click('button:has-text("Agregar adenda")')
    expect(pagina.locator('.med-adendas')).to_contain_text('El paciente refiere mejoría.')
    c.refresh_from_db()
    assert c.motivo == 'Dolor de cabeza' and c.adendas.count() == 1  # la consulta no cambió; la adenda se agregó
    pagina.locator('summary', has_text='Anular consulta').click()
    pagina.fill('#anular-motivo', 'Duplicada')
    pagina.click('button:has-text("Anular")')
    expect(pagina.locator('.tv-alerta--aviso')).to_contain_text('Consulta anulada')
    pagina.locator('summary', has_text='Restaurar consulta').click()
    pagina.fill('#anular-motivo', 'Error de captura')
    pagina.click('button:has-text("Restaurar") >> nth=-1')
    expect(pagina.locator('.med-estado--finalizada')).to_be_visible()
    assert [a.tipo for a in c.adendas.all()] == ['adenda', 'anulacion', 'restauracion']


def test_dos_pestanas_editando_el_mismo_campo_piden_decidir_y_no_pierden_nada(medico, actor):
    p = paciente(actor)
    c, _ = consultas.iniciar(actor, p.id)
    a = medico.ir(f'/consultas/{c.id}/')
    b = medico.contexto.new_page()
    b.goto(medico.servidor+f'/consultas/{c.id}/')
    b.fill('#id_reason', 'Versión B')
    guardado(b)
    a.fill('#id_reason', 'Versión A')
    a.wait_for_url(re.compile(r'/conflicto/'))
    expect(a.locator('.med-conflicto')).to_contain_text('Versión A')
    expect(a.locator('.med-conflicto')).to_contain_text('Versión B')
    a.check('input[name=campo_reason][value=local]')
    a.click('text=Combinar y continuar')
    a.wait_for_url(re.compile(r'/consultas/[0-9a-f-]{36}/$'))
    expect(a.locator('#id_reason')).to_have_value('Versión A')


def archivo_png(tmp_path, nombre='placa.png'):
    from PIL import Image
    ruta = tmp_path/nombre
    Image.new('RGB', (320, 200), '#3a7').save(ruta)
    return ruta


def test_documentos_subida_reanudable_cola_visor_de_imagen_y_pdf(medico, actor, tmp_path):
    p = paciente(actor)
    pagina = medico.ir(f'/pacientes/{p.id}/?pestana=documentos')
    pagina.locator('tv-subida input[type=file]').first.set_input_files(str(archivo_png(tmp_path)))
    formulario = pagina.locator('#cola-docs form')
    expect(formulario).to_have_count(1, timeout=15000)
    formulario.locator('[name=titulo]').fill('Radiografía de tórax')
    formulario.locator('[name=categoria]').select_option('Laboratorio')
    formulario.locator('button[type=submit]').click()
    expect(pagina.locator('#lista-docs')).to_contain_text('Radiografía de tórax')
    expect(pagina.locator('#cola-docs form')).to_have_count(0)
    # Visor de imagen con zoom
    pagina.locator('#lista-docs a >> text=Radiografía de tórax').click()
    imagen = pagina.locator('[data-zoom-imagen]')
    expect(imagen).to_be_visible()
    pagina.wait_for_function("() => document.querySelector('[data-zoom-imagen]').naturalWidth > 0")
    pagina.click('[data-zoom-mas]')
    assert 'scale(1.25)' in imagen.get_attribute('style')
    # PDF por páginas
    pdf = tmp_path/'carta.pdf'
    create_pdf(pdf, DEFAULT_IDENTITY, 'Carta de referencia', [('Resumen', 'Texto de la carta. ' * 400)])
    pagina.goto(medico.servidor+f'/pacientes/{p.id}/?pestana=documentos')
    pagina.locator('tv-subida input[type=file]').first.set_input_files(str(pdf))
    pagina.locator('#cola-docs form [name=titulo]').fill('Carta de referencia')
    pagina.locator('#cola-docs form button[type=submit]').click()
    pagina.locator('#lista-docs a >> text=Carta de referencia').first.click()
    pagina.wait_for_selector('canvas.med-pdf__pagina--lista', timeout=15000)
    assert pagina.locator('canvas.med-pdf__pagina').count() >= 2


def test_pdf_de_receta_con_vista_previa(medico, actor):
    p = paciente(actor)
    c = finalizada(actor, p, prescriptions=[MEDICAMENTO])
    pagina = medico.ir(f'/consultas/{c.id}/')
    pagina.click('button:has-text("Receta")')
    pagina.wait_for_url('**/pdf/**', timeout=15000)  # la vista previa se abre sola al terminar
    pagina.wait_for_selector('canvas.med-pdf__pagina--lista', timeout=15000)
    assert pagina.locator('canvas.med-pdf__pagina').count() == 1
    assert pagina.evaluate("() => document.querySelector('canvas').width") > 200


def test_estadisticas_y_exportaciones_con_descargas(medico, actor, tmp_path):
    p = paciente(actor)
    finalizada(actor, p)
    pagina = medico.ir('/estadisticas/')
    pagina.click('summary:has-text("Filtros")')  # los filtros avanzados se abren a pedido; el periodo rápido está siempre a la vista
    pagina.fill('#desde', '2026-09-01')
    pagina.fill('#hasta', '2026-09-30')
    pagina.click('text=Calcular')
    expect(pagina.locator('.med-numero').first).to_contain_text('1')
    expect(pagina.locator('svg.med-grafica:visible')).to_be_visible()
    with pagina.expect_download() as descarga:
        pagina.click('text=Descargar CSV')
    contenido = Path(descarga.value.path()).read_text(encoding='utf-8-sig')
    assert 'resumen,consultations,1' in contenido and 'diagnoses,Migraña,1' in contenido
    pagina.fill('#desde', '2026-08-01')  # al cambiar los filtros, las exportaciones se ocultan hasta recalcular
    expect(pagina.locator('.med-exportar')).to_be_hidden()
    pagina.goto(medico.servidor+'/exportar/')
    with pagina.expect_download() as descarga:
        pagina.click('text=Descargar pacientes')
    assert 'Ana Muñoz' in Path(descarga.value.path()).read_text(encoding='utf-8-sig')
    with pagina.expect_download() as descarga:
        pagina.click('text=Descargar consultas (CSV)')
    assert 'Dolor de cabeza' in Path(descarga.value.path()).read_text(encoding='utf-8-sig')


def test_bloquear_oculta_el_contenido_y_la_contrasena_lo_reabre(medico, actor):
    paciente(actor)
    pagina = medico.ir('/pacientes/')
    pagina.click('summary[aria-label="Menú de la cuenta"]')
    pagina.click('button:has-text("Bloquear Med")')
    pagina.wait_for_url(re.compile(r'/desbloquear/'))
    assert 'Ana Muñoz' not in pagina.content()
    pagina.goto(medico.servidor+'/pacientes/')
    pagina.wait_for_url(re.compile(r'/desbloquear/'))
    pagina.fill('#password', 'incorrecta')
    pagina.click('button:has-text("Desbloquear")')
    expect(pagina.locator('.tv-alerta--error')).to_contain_text('no coincide')
    pagina.fill('#password', 'clave-de-prueba')
    pagina.click('button:has-text("Desbloquear")')
    expect(pagina.locator('[data-resultado]')).to_have_count(1)


def test_suspender_a_un_medico_lo_saca_en_la_siguiente_peticion(medico, actor, roles):
    pagina = medico.ir('/pacientes/')
    expect(pagina.locator('h1')).to_contain_text('Pacientes')
    roles.revocar(medico.usuario, 'med')
    respuesta = pagina.goto(medico.servidor+'/pacientes/')
    assert respuesta.status == 404
