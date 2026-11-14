"""PDF, validación de archivos y activos de marca (portado de test_documents/test_branding)."""
import io
import uuid
import zipfile

import pytest
from PIL import Image
from pypdf import PdfReader

from tresvizo_med.dominio import attachments
from tresvizo_med.dominio.documents import APP_MARK, FUENTES, create_pdf
from tresvizo_med.dominio.errores import DataError
from tresvizo_med.dominio.themes import DEFAULT_IDENTITY

STATIC = APP_MARK.parent


def test_long_pdf_pages_and_brand_opt_in(tmp_path):
    path = tmp_path/'long.pdf'
    text = 'Texto sintético de prueba con acentos: atención, evolución, presión. ' * 220
    create_pdf(path, DEFAULT_IDENTITY, 'Consulta de prueba', [('Evolución', text)], 'Doctora sintética', 'Paciente sintético')
    pdf = PdfReader(path)
    joined = '\n'.join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) > 2
    assert 'tresvizo.com' not in joined and 'TresVizo' not in joined
    assert 'Paciente sintético' in joined and 'atención, evolución, presión' in joined
    assert all(f'Página {i}' in page.extract_text() for i, page in enumerate(pdf.pages, 1))
    create_pdf(path, {**DEFAULT_IDENTITY, 'document_website': True, 'document_app_brand': True}, 'Prueba', [('Nota', 'Sintética')])
    joined = PdfReader(path).pages[0].extract_text()
    assert 'tresvizo.com' in joined and 'TresVizo' in joined


def test_pdf_embeds_liberation_sans_on_every_platform(tmp_path):
    path = tmp_path/'fuente.pdf'
    create_pdf(path, DEFAULT_IDENTITY, 'Título', [('Sección', 'Contenido ñ')])
    fonts = {str(f.get_object().get('/BaseFont')) for page in PdfReader(path).pages
             for f in page['/Resources']['/Font'].values()}
    assert any('LiberationSans' in f for f in fonts)
    assert (FUENTES/'LICENCIA-LiberationSans.txt').is_file()


def test_pdf_with_clinic_logo(tmp_path):
    logo = tmp_path/'logo.png'
    Image.new('RGBA', (300, 100), 'blue').save(logo)
    create_pdf(tmp_path/'l.pdf', {**DEFAULT_IDENTITY, 'clinic_logo': str(logo)}, 'T', [('S', 'C')])
    assert len(PdfReader(tmp_path/'l.pdf').pages) == 1


def image_file(path, fmt='PNG', size=(40, 30)):
    Image.new('RGB', size, 'white').save(path, fmt)
    return path


def test_validate_accepts_real_content(tmp_path):
    assert attachments.validate(image_file(tmp_path/'a.png')) == 'image/png'
    assert attachments.validate(image_file(tmp_path/'a.jpg', 'JPEG')) == 'image/jpeg'
    pdf = tmp_path/'a.pdf'
    create_pdf(pdf, DEFAULT_IDENTITY, 'T', [('S', 'C')])
    assert attachments.validate(pdf) == 'application/pdf'
    docx = tmp_path/'a.docx'
    with zipfile.ZipFile(docx, 'w') as z:
        z.writestr('[Content_Types].xml', '<x/>')
        z.writestr('word/document.xml', '<x/>')
    assert attachments.validate(docx).endswith('wordprocessingml.document')


def test_validate_rejects_mismatches_and_damage(tmp_path):
    jpeg_named_png = tmp_path/'falso.png'
    image_file(jpeg_named_png, 'JPEG')
    (tmp_path/'vacio.png').write_bytes(b'')
    (tmp_path/'roto.pdf').write_bytes(b'%PDF-1.4 roto')
    (tmp_path/'texto.txt').write_text('hola')
    macro = tmp_path/'macro.docx'
    with zipfile.ZipFile(macro, 'w') as z:
        z.writestr('[Content_Types].xml', '<x/>')
        z.writestr('word/document.xml', '<x/>')
        z.writestr('word/vbaProject.bin', 'x')
    (tmp_path/'noimg.jpg').write_bytes(b'no es imagen')
    for name in ('falso.png', 'vacio.png', 'roto.pdf', 'texto.txt', 'macro.docx', 'noimg.jpg'):
        with pytest.raises(DataError):
            attachments.validate(tmp_path/name)


def test_validate_rejects_oversized_images(tmp_path, monkeypatch):
    monkeypatch.setattr(attachments, 'MAX_PIXELS', 100)
    with pytest.raises(DataError):
        attachments.validate(image_file(tmp_path/'grande.png', size=(20, 20)))


def test_operation_identifier_is_deterministic_per_target():
    actor, target = str(uuid.uuid4()), {'patient_id': 'p', 'encounter_id': None, 'draft_id': None}
    first = attachments.operation_identifier(actor, target, 'op1')
    assert first == attachments.operation_identifier(actor, target, 'op1')
    assert first != attachments.operation_identifier(actor, target, 'op2')
    assert first != attachments.operation_identifier(actor, {**target, 'patient_id': 'q'}, 'op1')


def test_clean_update_filters_and_validates():
    assert attachments.clean_update({'title': 'Nuevo', 'sha256': 'x', 'archived': True}) == {'title': 'Nuevo', 'archived': True}
    for bad in ({'title': '  '}, {'document_date': '2026-13-01'}):
        with pytest.raises(DataError):
            attachments.clean_update(bad)


def test_thumbnail_keeps_aspect_ratio(tmp_path):
    out = attachments.make_thumbnail(image_file(tmp_path/'g.png', size=(400, 200)), tmp_path/'t'/'g.png', 160)
    with Image.open(out) as thumb:
        assert thumb.size == (160, 80)


def test_transparency_of_brand_assets():
    for name in ('tresvizo_medico.png', 'tresvizo_medico_compacto.png', 'tresvizo_medico_oscuro.png',
                 'tresvizo_medico_principal_claro.png', 'tresvizo_medico_principal_oscuro.png', 'clinica_cruz.png'):
        with Image.open(STATIC/name) as image:
            assert image.mode == 'RGBA'
            assert image.getchannel('A').getextrema() == (0, 255)


def test_avatars_and_icons_ship_with_the_package():
    assert len(list((STATIC/'avatares').glob('*.png'))) == 16
    assert (STATIC.parent/'iconos'/'LICENSE.txt').is_file() and list((STATIC.parent/'iconos').glob('*.svg'))


# --- Receta y resumen (UX-MED-05) ------------------------------------------------------------------------------

def _datos_receta(**extra):
    return {'estado': 'Finalizada', 'fecha': '10/09/2026',
            'paciente': {'name': 'Ana Muñoz', 'folio': 'RC-000001', 'age': '35 años', 'sex': 'Femenino', 'allergies': 'Penicilina'},
            'medico': {'name': 'Dra. Ana Prueba', 'cedula': '123456', 'specialty': 'Medicina general'},
            'diagnostico': 'Gastritis', 'plan': 'Reposo', 'seguimiento': '', 'signos': [],
            'medicamentos': [{'name': 'Omeprazol', 'strength': '20 mg', 'dose': '1', 'dose_unit': 'cápsula', 'route': 'Oral',
                              'frequency_kind': 'Cada N horas', 'frequency': '24', 'duration': '14', 'duration_unit': 'días'}], **extra}


def test_receta_tiene_encabezado_paciente_medicamentos_y_firma(tmp_path):
    from tresvizo_med.dominio.documentos_medicos import crear_receta
    logo = tmp_path/'logo.png'
    Image.new('RGBA', (300, 100), 'blue').save(logo)
    crear_receta(tmp_path/'r.pdf', {**DEFAULT_IDENTITY, 'clinic_name': 'Clínica Norte', 'contact': 'Tel. 555 1111', 'clinic_logo': str(logo)}, _datos_receta())
    pdf = PdfReader(tmp_path/'r.pdf')
    texto = pdf.pages[0].extract_text()
    assert len(pdf.pages) == 1 and pdf.pages[0].mediabox.width == 612  # carta
    for esperado in ('Clínica Norte', 'Tel. 555 1111', 'Dra. Ana Prueba', 'Cédula profesional 123456', 'Medicina general', 'Ana Muñoz', '35 años',
                     '10/09/2026', 'Penicilina', 'Gastritis', 'Omeprazol 20 mg', 'Tomar 1 cápsula por vía oral cada 24 horas durante 14 días.', 'Firma del médico'):
        assert esperado in texto, esperado
    assert texto.index('Omeprazol') < texto.index('Firma del médico')


@pytest.mark.parametrize('estado, marca', [('Borrador', 'BORRADOR'), ('Anulada', 'ANULADA')])
def test_receta_marca_borrador_y_anulada(tmp_path, estado, marca):
    from tresvizo_med.dominio.documentos_medicos import crear_receta
    crear_receta(tmp_path/'r.pdf', DEFAULT_IDENTITY, _datos_receta(estado=estado))
    assert marca in PdfReader(tmp_path/'r.pdf').pages[0].extract_text()
    crear_receta(tmp_path/'f.pdf', DEFAULT_IDENTITY, _datos_receta())
    texto = PdfReader(tmp_path/'f.pdf').pages[0].extract_text()
    assert 'BORRADOR' not in texto and 'ANULADA' not in texto


@pytest.mark.parametrize('n_signos', [1, 2, 3, 5])
def test_resumen_con_signos_que_no_llenan_la_ultima_fila(tmp_path, n_signos):
    # Con signos que no son múltiplo de 4, la última fila de la tabla se rellenaba con [''] y el resumen fallaba en el trabajador
    # («'str' object has no attribute 'wrapOn'»): la doctora pulsaba «Resumen» y no salía nada. Encontrado en el ensayo por la pila real.
    from tresvizo_med.dominio.documentos_medicos import crear_resumen
    valores = {'systolic': {'value': '118', 'unit': 'mmHg'}, 'diastolic': {'value': '76', 'unit': 'mmHg'},
               'heart_rate': {'value': '72', 'unit': 'lpm'}, 'oxygen': {'value': '97', 'unit': '%'},
               'weight': {'value': '70', 'unit': 'kg'}, 'glucose': {'value': '100', 'unit': 'mg/dL'}}
    orden = [('systolic', 'diastolic'), ('heart_rate',), ('oxygen',), ('weight',), ('glucose',)][:n_signos]
    elegidos = {k: valores[k] for grupo in orden for k in grupo}
    datos = {**_datos_receta(), 'secciones': [('Motivo de consulta', 'Tos seca'), ('Signos vitales', ''), ('Medicamentos', '')],
             'signos': [{'at': '2026-09-10T10:00:00', 'values': elegidos}], 'adendas': []}
    crear_resumen(tmp_path/'s.pdf', DEFAULT_IDENTITY, datos)
    texto = PdfReader(tmp_path/'s.pdf').pages[0].extract_text()
    assert 'PRESIÓN ARTERIAL' in texto and '118/76 mmHg' in texto and 'Omeprazol' in texto


def test_posologia_en_lenguaje_de_receta():
    from tresvizo_med.dominio.presentacion import medicamento
    base = {'name': 'Paracetamol', 'strength': '500 mg', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral'}
    assert medicamento({**base, 'frequency_kind': 'Veces al día', 'frequency': '3', 'duration': '5', 'duration_unit': 'días'})['posologia'] == \
        'Tomar 1 tableta por vía oral 3 veces al día durante 5 días.'
    assert medicamento({**base, 'frequency_kind': 'Cada N horas', 'frequency': '8', 'as_needed': True, 'as_needed_reason': 'dolor'})['posologia'] == \
        'Tomar 1 tableta por vía oral cada 8 horas. Solo si es necesario: dolor.'
    crema = medicamento({'name': 'Hidrocortisona', 'strength': '1 %', 'presentation': 'Crema', 'dose': '1', 'dose_unit': 'g', 'route': 'Tópica',
                         'frequency_kind': 'Cada N horas', 'frequency': '12', 'quantity': '30', 'quantity_unit': 'g'})
    assert crema['titulo'] == 'Hidrocortisona 1 %, crema' and crema['posologia'].startswith('Aplicar 1 g por vía tópica cada 12 horas') and crema['surtir'] == '30 g'


def test_signos_en_orden_clinico_y_presion_en_una_linea():
    from tresvizo_med.dominio.presentacion import signos_ordenados
    grupo = {'at': '2026-09-10T10:00:00', 'values': {
        'height': {'value': '165', 'unit': 'cm'}, 'oxygen': {'value': '97', 'unit': '%'}, 'weight': {'value': '70', 'unit': 'kg'},
        'glucose': {'value': '100', 'unit': 'mg/dL'}, 'diastolic': {'value': '73', 'unit': 'mmHg'}, 'systolic': {'value': '157', 'unit': 'mmHg'},
        'heart_rate': {'value': '72', 'unit': 'lpm'}}, 'bmi': 25.7}
    filas = signos_ordenados(grupo)
    assert [r for _, r, _ in filas] == ['Presión arterial', 'Frecuencia cardiaca', 'Saturación de oxígeno', 'Peso', 'Estatura', 'IMC', 'Glucosa']
    assert filas[0][2] == '157/73 mmHg'
