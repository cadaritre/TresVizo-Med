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
