from pathlib import Path
import pytest
from pypdf import PdfReader
from app.documents import create_pdf
from app.themes import DEFAULT_IDENTITY
from app.transfer import safe_csv


def test_long_pdf_pages_and_brand_opt_in(tmp_path):
    path = tmp_path/'long.pdf'
    text = 'Texto sintético de prueba con acentos: atención, evolución, presión. ' * 220
    create_pdf(path, DEFAULT_IDENTITY, 'Consulta de prueba', [('Evolución', text)], 'Doctora sintética', 'Paciente sintético')
    pdf = PdfReader(path)
    joined = '\n'.join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) > 2
    assert 'tresvizo.com' not in joined
    assert 'TresVizo' not in joined
    assert 'Paciente sintético' in joined
    assert all(f'Página {i}' in page.extract_text() for i, page in enumerate(pdf.pages, 1))
    create_pdf(path, {**DEFAULT_IDENTITY, 'document_website': True, 'document_app_brand': True}, 'Prueba', [('Nota', 'Sintética')])
    joined = PdfReader(path).pages[0].extract_text()
    assert 'tresvizo.com' in joined and 'TresVizo' in joined


@pytest.mark.parametrize('value', ['=1+1', '+cmd', '-1', '@SUM(A1)', '   =HYPERLINK("bad")'])
def test_csv_formula_protection(value):
    assert safe_csv(value).startswith("'")
