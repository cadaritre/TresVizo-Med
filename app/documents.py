"""PDF paginado con identidad y paleta de impresión independientes de la UI."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from app.branding import ASSETS


def create_pdf(path, identity, title, sections, doctor='', patient=''):
    font_path = Path('C:/Windows/Fonts/segoeui.ttf')
    font_name = 'Helvetica'
    if font_path.exists():
        font_name = 'SegoeUI'
        if font_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    text_style = ParagraphStyle('Body', fontName=font_name, fontSize=10, leading=15,
                               textColor=colors.HexColor(identity['document_text']), spaceAfter=10)
    heading = ParagraphStyle('Heading', parent=text_style, fontSize=17, leading=22,
                             textColor=colors.HexColor(identity['document_primary']), spaceBefore=12)
    subheading = ParagraphStyle('Section', parent=heading, fontSize=12, leading=17)
    story = []
    clinic_logo = identity.get('clinic_logo')
    if clinic_logo and Path(clinic_logo).is_file():
        from PIL import Image as PILImage
        with PILImage.open(clinic_logo) as image:
            w, h = image.size
        scale = min(120/w, 65/h)
        story.append(Image(clinic_logo, width=w*scale, height=h*scale, hAlign='LEFT'))
    def paragraph(value, style=text_style):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)
    story.extend([paragraph(identity['clinic_name'], heading), paragraph(identity.get('contact', '')), paragraph(title, heading)])
    if patient:
        story.append(paragraph('Paciente: '+patient))
    if doctor:
        story.append(paragraph('Doctor responsable: '+doctor))
    for label, content in sections:
        story.extend([paragraph(label, subheading), paragraph(content or 'No registrado')])
    if identity.get('document_app_brand'):
        story.append(Spacer(1, 12))
        story.append(Image(str(ASSETS/'tresvizo_medico.png'), width=34, height=39, hAlign='LEFT'))
        story.append(paragraph('TresVizo · '+identity['app_name']))
    if identity.get('document_website'):
        story.append(paragraph(identity['website_text']+' · '+identity['website']))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor(identity['document_text']))
        canvas.drawRightString(A4[0]-48, 28, f'Página {doc.page}')
        canvas.restoreState()
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=48, rightMargin=48, topMargin=36,
                      bottomMargin=48, title=title, author='', creator=identity['app_name']).build(story, onFirstPage=footer, onLaterPages=footer)
