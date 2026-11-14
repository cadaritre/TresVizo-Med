"""PDF por tareas, estadísticas, exportaciones, importación CSV, paquete del expediente y exportación completa."""
import csv
import io
import json
import re
import zipfile

import pytest
from pypdf import PdfReader

from tresvizo_med.dominio import transfer
from tresvizo_med.models import LoteImportacion, Paciente
from tresvizo_med.servicios import Actor, consultas, documentos, exportaciones, pacientes
from tresvizo_med.servicios import pdf as servicio_pdf
from .conftest import datos_consulta, datos_paciente
from .conftest import reverse_med as reverse

pytestmark = pytest.mark.django_db(databases=['default', 'med'])
HTMX = {'HTTP_HX_REQUEST': 'true'}
MEDICAMENTO = {'name': 'Paracetamol', 'strength': '500 mg', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral', 'frequency': '8',
               'frequency_kind': 'Cada N horas', 'instructions': 'Con alimentos'}


@pytest.fixture
def web(cliente_med):
    cliente = cliente_med('medico', username='dra')
    cliente.actor = Actor.de(cliente.usuario)
    return cliente


@pytest.fixture
def admin(cliente_med):
    cliente = cliente_med('admin', username='jefa')
    cliente.actor = Actor.de(cliente.usuario)
    return cliente


@pytest.fixture
def paciente(web):
    return pacientes.guardar(web.actor, datos_paciente('Ana Muñoz', birth_date='1990-05-01', sex='Femenino', phone='5551234'))


@pytest.fixture
def final(web, paciente):
    return consultas.guardar(web.actor, datos_consulta(paciente, 'Finalizada', prescriptions=[MEDICAMENTO], reason='Dolor de cabeza',
                                                       assessment='Migraña', plan='Reposo e hidratación'))


def texto_pdf(ruta):
    return '\n'.join(p.extract_text() for p in PdfReader(ruta).pages)


# --- PDF ------------------------------------------------------------------------------------------------------------

def generar(web, consulta, tipo):
    return web.post(reverse('med:pdf_consulta', args=[consulta.id, tipo]), **HTMX)


def test_pdf_de_receta_con_identidad_doctor_y_liberation_sans(web, final):
    from tresvizo_med.servicios import clinica
    admin_actor = Actor.de(web.usuario)  # el médico de la prueba no es admin: la identidad se guarda con superusuario
    from django.contrib.auth import get_user_model
    jefe = get_user_model().objects.create_user('jefe', password='x', is_superuser=True)
    clinica.guardar_identidad(Actor.de(jefe), {'clinic_name': 'Clínica Sur', 'contact': 'Tel. 555 0000'})
    clinica.guardar_perfil(admin_actor, admin_actor.cuenta_id, nombre_visible='Dra. Ana Prueba', cedula='123456', especialidad='Medicina general')
    r = generar(web, final, 'receta')
    html = r.content.decode()
    assert r.status_code == 200 and 'El PDF está listo' in html and 'Ver el PDF' in html
    enlace = html.split('href="')[1].split('"')[0]
    pagina = web.get(enlace)
    assert pagina.status_code == 200 and 'pdf.min.mjs' in pagina.content.decode()
    archivo = web.get(enlace+'archivo/')
    assert archivo['Content-Type'] == 'application/pdf' and 'inline' in archivo['Content-Disposition']
    ruta = next((servicio_pdf.carpeta_pdf(web.usuario.pk)).glob('*.pdf'))
    texto = texto_pdf(ruta)
    for esperado in ('RECETA MÉDICA', 'Clínica Sur', 'Tel. 555 0000', 'Ana Muñoz', '10/09/2026', 'Dra. Ana Prueba',
                     'Cédula profesional 123456', 'Medicina general', 'Paracetamol 500 mg', 'Tomar 1 tableta por vía oral cada 8 horas',
                     'Con alimentos', 'Reposo e hidratación', 'Migraña', 'Página 1 de 1'):
        assert esperado in texto, esperado
    assert re.search(r'\d+ años', texto) and 'Femenino' in texto  # edad y sexo del paciente
    fuentes = {str(f.get_object().get('/BaseFont')) for p in PdfReader(ruta).pages for f in p['/Resources']['/Font'].values()}
    assert any('LiberationSans' in f for f in fuentes)


def test_pdf_de_resumen_incluye_adendas_y_estado(web, final):
    consultas.agregar_adenda(web.actor, final.id, 'Aclaración', 'Texto de la adenda')
    generar(web, final, 'resumen')
    texto = texto_pdf(next(servicio_pdf.carpeta_pdf(web.usuario.pk).glob('*.pdf')))
    assert 'RESUMEN DE CONSULTA' in texto and 'Dolor de cabeza' in texto and 'ADENDAS' in texto and 'Texto de la adenda' in texto
    assert 'Aclaración' in texto and 'Médico responsable' in texto and 'Paracetamol 500 mg' in texto
    assert 'BORRADOR' not in texto and 'ANULADA' not in texto


def test_pdf_de_borrador_y_de_consulta_anulada_se_marcan(web, paciente):
    borrador = consultas.guardar(web.actor, datos_consulta(paciente, prescriptions=[MEDICAMENTO]))
    generar(web, borrador, 'receta')
    assert 'BORRADOR' in texto_pdf(next(servicio_pdf.carpeta_pdf(web.usuario.pk).glob('*.pdf')))
    anulada = consultas.anular(web.actor, consultas.guardar(web.actor, datos_consulta(paciente, 'Finalizada', prescriptions=[MEDICAMENTO])).id, 'Duplicada')
    generar(web, anulada, 'receta')
    assert any('ANULADA' in texto_pdf(p) for p in servicio_pdf.carpeta_pdf(web.usuario.pk).glob('*.pdf'))


def test_pdf_de_receta_con_muchos_medicamentos_firma_en_la_ultima_hoja(web, paciente):
    filas = [{**MEDICAMENTO, 'name': f'Medicamento {n}', 'instructions': 'Indicación larga. '*8} for n in range(1, 15)]
    consulta = consultas.guardar(web.actor, datos_consulta(paciente, 'Finalizada', prescriptions=filas))
    generar(web, consulta, 'receta')
    paginas = PdfReader(next(servicio_pdf.carpeta_pdf(web.usuario.pk).glob('*.pdf'))).pages
    assert len(paginas) >= 2
    assert 'Firma del médico' in paginas[-1].extract_text() and 'Firma del médico' not in paginas[0].extract_text()
    assert 'Medicamento 14' in paginas[-1].extract_text() or 'Medicamento 14' in paginas[-2].extract_text()
    assert all(f'Página {n} de {len(paginas)}' in p.extract_text() for n, p in enumerate(paginas, 1))


def test_receta_sin_medicamentos_falla_con_mensaje_y_tipo_invalido_es_404(web, final, paciente):
    sin = consultas.guardar(web.actor, datos_consulta(paciente, 'Finalizada'))
    with pytest.raises(Exception, match='no tiene medicamentos'):
        generar(web, sin, 'receta')
    assert web.post(reverse('med:pdf_consulta', args=[final.id, 'otro'])).status_code == 404


def test_los_pdf_son_privados_de_quien_los_genero_y_un_borrador_ajeno_no_se_genera(web, cliente_med, final, paciente):
    generar(web, final, 'resumen')
    identificador = next(servicio_pdf.carpeta_pdf(web.usuario.pk).glob('*.pdf')).stem
    otro = cliente_med('medico', username='otro')
    assert otro.get(reverse('med:pdf', args=[identificador])).status_code == 404
    assert otro.get(reverse('med:pdf_archivo', args=[identificador])).status_code == 404
    borrador = consultas.guardar(web.actor, datos_consulta(paciente))
    assert otro.post(reverse('med:pdf_consulta', args=[borrador.id, 'resumen'])).status_code == 404


def test_pdf_anterior_a_24_horas_se_limpia(web, final):
    import os
    import time
    generar(web, final, 'resumen')
    viejo = next(servicio_pdf.carpeta_pdf(web.usuario.pk).glob('*.pdf'))
    os.utime(viejo, (time.time()-90000, time.time()-90000))
    generar(web, final, 'resumen')
    assert not viejo.exists() and len(list(servicio_pdf.carpeta_pdf(web.usuario.pk).glob('*.pdf'))) == 1


# --- Estadísticas ---------------------------------------------------------------------------------------------------

def test_estadisticas_calculan_y_exportan_con_la_instantanea_de_filtros(web, paciente, final):
    r = web.get(reverse('med:estadisticas'), {'desde': '2026-09-01', 'hasta': '2026-09-30', 'grupo': 'Todos'})
    html = r.content.decode()
    assert r.status_code == 200 and 'migrana' in html and '<svg' in html and 'Periodo previo' in html
    assert 'desde=2026-09-01' in html and 'estadisticas/csv' in html and 'Generar PDF' in html and 'Calculado con los filtros' in html
    cuerpo = web.get(reverse('med:estadisticas_csv'), {'desde': '2026-09-01', 'hasta': '2026-09-30'}).content.decode('utf-8-sig')
    filas = list(csv.reader(io.StringIO(cuerpo)))
    assert filas[0] == ['seccion', 'clave', 'valor'] and ['resumen', 'consultations', '1'] in filas and ['diagnoses', 'migrana', '1'] in filas
    r = web.post(reverse('med:estadisticas_pdf'), {'desde': '2026-09-01', 'hasta': '2026-09-30'}, **HTMX)
    assert 'El PDF está listo' in r.content.decode()
    assert 'Estadísticas de consulta' in texto_pdf(next(servicio_pdf.carpeta_pdf(web.usuario.pk).glob('*.pdf')))


def test_estadisticas_validan_fechas_y_respetan_permisos(web, admin, final):
    assert 'anterior o igual' in web.get(reverse('med:estadisticas'), {'desde': '2026-10-01', 'hasta': '2026-09-01'}).content.decode()
    assert web.get(reverse('med:estadisticas'), {'desde': '2026-09-01', 'hasta': '2026-09-30', 'doctor': '*'}).status_code == 403
    assert web.get(reverse('med:estadisticas_csv'), {'desde': 'mal', 'hasta': '2026-09-30'}).status_code == 422
    html = admin.get(reverse('med:estadisticas'), {'desde': '2026-09-01', 'hasta': '2026-09-30', 'doctor': '*'}).content.decode()
    assert 'Toda la clínica' in html and '<strong>1</strong>Consultas' in html
    assert 'Médico' in admin.get(reverse('med:estadisticas')).content.decode()


# --- Exportaciones --------------------------------------------------------------------------------------------------

def test_exportar_pacientes_csv_y_json_por_alcance(web, admin, paciente, final, cliente_med):
    otro_paciente = pacientes.guardar(admin.actor, datos_paciente('=Otro paciente'))
    csv_medico = web.get(reverse('med:exportar_pacientes')).content.decode('utf-8-sig')
    assert 'Ana Muñoz' in csv_medico and 'Otro paciente' not in csv_medico  # un médico exporta los suyos
    csv_admin = admin.get(reverse('med:exportar_pacientes')).content.decode('utf-8-sig')
    assert "'=Otro paciente" in csv_admin and 'Ana Muñoz' in csv_admin  # el admin, los de la clínica, con protección de fórmulas
    assert list(csv.reader(io.StringIO(csv_admin)))[0] == ['id', 'file_number', 'name', 'birth_date', 'phone', 'email']
    js = json.loads(admin.get(reverse('med:exportar_pacientes'), {'formato': 'json', 'ids': str(otro_paciente.id)}).content)
    assert js['schema_version'] == 1 and [p['name'] for p in js['patients']] == ['=Otro paciente']
    assert admin.get(reverse('med:exportar_pacientes'), {'formato': 'xml'}).status_code == 422
    assert admin.get(reverse('med:exportar_pacientes'), {'ids': 'no-es-uuid'}).status_code == 404
    assert 'attachment' in web.get(reverse('med:exportar_pacientes'))['Content-Disposition']


def test_exportar_consultas_mismas_columnas_que_el_escritorio(web, admin, paciente, final):
    consultas.guardar(web.actor, datos_consulta(paciente, reason='Mi borrador', attended_at='2026-09-11T10:00:00-06:00'))
    cuerpo = web.get(reverse('med:exportar_consultas'), {'desde': '2026-09-01', 'hasta': '2026-09-30'}).content.decode('utf-8-sig')
    filas = list(csv.DictReader(io.StringIO(cuerpo)))
    assert list(filas[0]) == list(transfer.CONSULTATION_FIELDS) and len(filas) == 1
    assert filas[0]['patient_name'] == 'Ana Muñoz' and filas[0]['reason'] == 'Dolor de cabeza' and filas[0]['doctor_name']
    assert json.loads(filas[0]['prescriptions_json'])[0]['name'] == 'Paracetamol'
    con_borradores = web.get(reverse('med:exportar_consultas'), {'borradores': '1'}).content.decode('utf-8-sig')
    assert 'Mi borrador' in con_borradores
    assert web.get(reverse('med:exportar_consultas'), {'doctor': '*'}).status_code == 403
    assert web.get(reverse('med:exportar_consultas'), {'desde': '2026-10-01', 'hasta': '2026-09-01'}).status_code == 422
    assert 'Dolor de cabeza' in admin.get(reverse('med:exportar_consultas'), {'doctor': '*'}).content.decode('utf-8-sig')
    assert 'Mi borrador' not in admin.get(reverse('med:exportar_consultas'), {'doctor': '*', 'borradores': '1'}).content.decode('utf-8-sig')


def test_paquete_del_expediente_con_manifiesto_y_documentos_verificados(web, paciente, final, imagen):
    x = documentos.agregar(web.actor, imagen(), paciente=paciente.id, categoria='Estudio')
    pagina = web.get(reverse('med:paquete', args=[paciente.id])).content.decode()
    assert 'Paquete del expediente' in pagina and str(x.id) in pagina
    r = web.post(reverse('med:paquete', args=[paciente.id]), {'documento': [str(x.id)]}, **HTMX)
    html = r.content.decode()
    assert 'Descargar el paquete' in html
    enlace = html.split('href="')[1].split('"')[0]
    descarga = web.get(enlace)
    assert descarga['Content-Type'] == 'application/zip' and 'attachment' in descarga['Content-Disposition']
    z = zipfile.ZipFile(io.BytesIO(b''.join(descarga.streaming_content)))
    manifiesto = json.loads(z.read('manifest.json'))
    assert manifiesto['kind'] == 'patient-export' and manifiesto['schema_version'] == 2 and f'documentos/{x.id}.png' in manifiesto['files']
    assert json.loads(z.read('expediente.json'))['patient']['name'] == 'Ana Muñoz'
    import hashlib
    assert all(hashlib.sha256(z.read(n)).hexdigest() == h for n, h in manifiesto['files'].items())


def test_paquete_rechaza_documentos_de_otro_paciente(web, paciente, imagen):
    otro = pacientes.guardar(web.actor, datos_paciente('Otro'))
    ajeno = documentos.agregar(web.actor, imagen(), paciente=otro.id)
    r = web.post(reverse('med:paquete', args=[paciente.id]), {'documento': [str(ajeno.id)]}, **HTMX)
    assert 'Descargar el paquete' in r.content.decode()  # lo ajeno se ignora: no está en la lista de este paciente
    with pytest.raises(Exception, match='otro destino'):
        exportaciones.crear_paquete_expediente(web.actor, paciente.id, [ajeno.id])


def test_exportacion_completa_en_formato_de_respaldo_del_escritorio(web, admin, paciente, final, imagen):
    from tresvizo_med.servicios import borradores
    documentos.agregar(web.actor, imagen(), paciente=paciente.id)
    consultas.agregar_adenda(web.actor, final.id, 'Aclaración', 'Texto')
    borradores.guardar_catalogo(web.actor, {'name': 'Paracetamol', 'strength': '500 mg'}, favorito=True)
    assert web.post(reverse('med:exportacion_completa')).status_code == 403
    r = admin.post(reverse('med:exportacion_completa'), **HTMX)
    enlace = r.content.decode().split('href="')[1].split('"')[0]
    ruta = exportaciones.ruta_descarga(admin.actor, enlace.strip('/').split('/')[-1])
    manifiesto = transfer.verify_backup(ruta)  # el mismo verificador del escritorio: CRC, manifiesto v1, rutas y hashes
    z = zipfile.ZipFile(ruta)
    nombres = set(z.namelist())
    assert {'manifest.json', 'config/schema.json', 'config/identity.json', 'config/appearance.json'} <= nombres
    assert f'data/patients/{paciente.id}.json' in nombres and f'data/encounters/{final.id}.json' in nombres
    paciente_json = json.loads(z.read(f'data/patients/{paciente.id}.json'))
    consulta_json = json.loads(z.read(f'data/encounters/{final.id}.json'))
    assert paciente_json['file_number'] == 'RC-000001' and consulta_json['status'] == 'Finalizada' and consulta_json['addenda'][0]['content'] == 'Texto'
    assert consulta_json['doctor_id'] == exportaciones.uuid_de_cuenta(web.actor.cuenta_id)
    adjunto = next(n for n in nombres if n.startswith('data/attachments/'))
    ruta_original = json.loads(z.read(adjunto))['path']
    assert ruta_original in nombres and ruta_original.startswith('attachments/originals/')
    assert any(n.startswith('data/users/') for n in nombres) and any(n.startswith('data/medication_catalog/') for n in nombres)
    assert manifiesto['schema_version'] == 1 and len(manifiesto['files']) == len(nombres)-1
    transfer.loads_strict(z.read('config/appearance.json'))
    from tresvizo_med.dominio.themes import validate_appearance_state
    validate_appearance_state(json.loads(z.read('config/appearance.json')))


def test_las_descargas_son_privadas(web, admin, paciente, cliente_med):
    r = admin.post(reverse('med:exportacion_completa'), **HTMX)
    identificador = r.content.decode().split('href="')[1].split('"')[0].strip('/').split('/')[-1]
    assert web.get(reverse('med:descarga', args=[identificador])).status_code == 404
    assert admin.get(reverse('med:descarga', args=[identificador])).status_code == 200


def test_pagina_exportar_segun_el_rol(web, admin):
    assert 'Exportación completa' not in web.get(reverse('med:exportar')).content.decode()
    assert 'Exportación completa' in admin.get(reverse('med:exportar')).content.decode()


# --- Importar CSV ------------------------------------------------------------------------------------------------------

def csv_bytes(filas, delimitador=';'):
    flujo = io.StringIO(newline='')
    csv.writer(flujo, delimiter=delimitador).writerows(filas)
    return ('﻿'+flujo.getvalue()).encode('utf-8')


def subir_csv(admin, contenido, nombre='pacientes.csv', delimitador=';'):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return admin.post(reverse('med:importar'), {'archivo': SimpleUploadedFile(nombre, contenido), 'delimitador': delimitador})


ENTRADA = [['Nombre', 'Nacimiento', 'Correo', 'Tel'], ['María; Luz\nPrueba', '1980-01-02', '', ''], ['Nombre inválido', '31/02/2020', 'invalido', ''],
           ['ANA MUNOZ', '', '', ''], ['Luis Pérez', '', 'luis@correo.mx', '5559999']]


def test_importacion_de_punta_a_punta_con_mapeo_vista_previa_y_duplicados(web, admin, paciente):
    r = subir_csv(admin, csv_bytes(ENTRADA))
    lote = LoteImportacion.objects.get()
    assert r['Location'] == reverse('med:importar_mapear', args=[lote.id]) and lote.conteos['filas'] == 4
    pagina = admin.get(r['Location']).content.decode()
    assert 'Mapear columnas' in pagina and '4 filas' in pagina
    r = admin.post(reverse('med:importar_mapear', args=[lote.id]), {'name': 'Nombre', 'birth_date': 'Nacimiento', 'email': 'Correo', 'phone': 'Tel'})
    assert r['Location'] == reverse('med:importar_previa', args=[lote.id])
    previa = admin.get(r['Location']).content.decode()
    assert '3 válidas' in previa and '1 con errores' in previa and 'Nombre coincidente' in previa and 'Es una persona distinta' in previa
    assert Paciente.objects.count() == 1  # la vista previa no escribe pacientes
    # Un duplicado sin confirmar frena todo el lote.
    r = admin.post(reverse('med:importar_previa', args=[lote.id]), {'fila': ['2', '4', '5']}, follow=True)
    assert 'confirma que corresponde a una persona distinta' in r.content.decode() and Paciente.objects.count() == 1
    r = admin.post(reverse('med:importar_previa', args=[lote.id]), {'fila': ['2', '4', '5'], 'duplicado': ['4']})
    assert r['Location'] == reverse('med:importar_recibo', args=[lote.id])
    assert Paciente.objects.count() == 4
    folios = sorted(Paciente.objects.values_list('folio', flat=True))
    assert len(set(folios)) == 4 and folios[0] == 'RC-000001'  # la secuencia puede dejar huecos si un lote se revierte
    maria = Paciente.objects.get(nombre__startswith='María')
    assert maria.nombre == 'María; Luz\nPrueba' and maria.datos['provenance']['import_batch'] == str(lote.id)
    assert 'Se importaron 3 pacientes' in admin.get(r['Location']).content.decode()
    # Repetir la confirmación no duplica nada.
    admin.post(reverse('med:importar_previa', args=[lote.id]), {'fila': ['2', '4', '5'], 'duplicado': ['4']})
    assert Paciente.objects.count() == 4


def test_importacion_rechaza_archivos_y_mapeos_invalidos_y_es_solo_del_admin(web, admin):
    assert web.get(reverse('med:importar')).status_code == 403
    assert 'Elige un archivo' in admin.post(reverse('med:importar'), {}, follow=True).content.decode()
    assert 'CSV UTF-8' in admin.get(subir_csv(admin, b'x', 'datos.zip', ',')['Location']).content.decode()
    r = subir_csv(admin, csv_bytes(ENTRADA), 'datos.json')
    assert 'CSV UTF-8' in admin.get(r['Location']).content.decode() and not LoteImportacion.objects.exists()
    r = subir_csv(admin, csv_bytes(ENTRADA))
    lote = LoteImportacion.objects.get()
    r = admin.post(reverse('med:importar_mapear', args=[lote.id]), {'birth_date': 'Nacimiento'}, follow=True)
    assert 'Mapea Nombre' in r.content.decode()
    assert admin.get(reverse('med:importar_previa', args=[lote.id])).status_code == 302
    assert web.get(reverse('med:importar_mapear', args=[lote.id])).status_code == 403


def test_importacion_detecta_pacientes_nuevos_desde_la_vista_previa(web, admin):
    subir_csv(admin, csv_bytes([['Nombre'], ['Persona Nueva']]))
    lote = LoteImportacion.objects.get()
    admin.post(reverse('med:importar_mapear', args=[lote.id]), {'name': 'Nombre'})
    pacientes.guardar(web.actor, datos_paciente('Alguien más'))  # cambia la base entre la vista previa y la confirmación
    r = admin.post(reverse('med:importar_previa', args=[lote.id]), {'fila': ['2']}, follow=True)
    assert 'cambiaron desde la vista previa' in r.content.decode() and Paciente.objects.count() == 1


def test_las_pantallas_ofrecen_los_pdf_y_el_paquete(web, final, paciente):
    lectura = web.get(reverse('med:consulta', args=[final.id])).content.decode()
    assert 'Receta e indicaciones' in lectura and 'Resumen de consulta' in lectura
    borrador = consultas.guardar(web.actor, datos_consulta(paciente))
    assert 'Receta (borrador)' in web.get(reverse('med:revisar', args=[borrador.id])).content.decode()
    assert 'Paquete del expediente' in web.get(reverse('med:expediente', args=[paciente.id])).content.decode()
