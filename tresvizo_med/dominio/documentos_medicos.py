"""PDF de receta médica y de resumen de consulta con composición de documento profesional (carta, formato mexicano).

La identidad (logo, nombre y contacto) es de la clínica; el médico firma y se identifica con nombre, cédula y
especialidad. Un borrador o una consulta anulada se marcan con una franja y una marca de agua en cada página.
Reglas puras: no importan Django.
"""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as lienzo
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, PageTemplate, Paragraph,
                                Spacer, Table, TableStyle)

from .documents import APP_MARK, FUENTES, register_font
from .presentacion import ABREVIATURAS, medicamento, signos_ordenados

NEGRITA = 'LiberationSans-Bold'
ANCHO, ALTO = LETTER
MARGEN = 42
ANCHO_UTIL = ANCHO-2*MARGEN
MARGEN_SUPERIOR, MARGEN_INFERIOR = 34, 58
ESTADOS = {
    'Borrador': ('BORRADOR', 'Consulta todavía sin finalizar: este documento no es válido.', '#FFF2CE', '#714B00'),
    'Anulada': ('ANULADA', 'Consulta anulada: este documento no es válido.', '#FDEBEC', '#9E182C'),
}
ROTULOS_SIGNOS_RECETA = ('pressure', 'heart_rate', 'temperature', 'oxygen', 'weight', 'height')


def registrar_fuentes():
    nombre = register_font()
    if NEGRITA not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(NEGRITA, str(FUENTES/'LiberationSans-Bold.ttf')))
        pdfmetrics.registerFontFamily(nombre, normal=nombre, bold=NEGRITA, italic=nombre, boldItalic=NEGRITA)
    return nombre


def _mezcla(a, b, cantidad):
    return '#'+''.join(f'{round(int(a[i:i+2], 16)*(1-cantidad)+int(b[i:i+2], 16)*cantidad):02X}' for i in (1, 3, 5))


def _p(texto, estilo):
    return Paragraph(escape(str(texto)).replace('\n', '<br/>'), estilo)


class Estilos:
    def __init__(self, identidad):
        fuente = registrar_fuentes()
        self.primario = identidad['document_primary']
        self.texto = identidad['document_text']
        self.tenue = _mezcla(self.texto, '#FFFFFF', .38)
        self.fino = _mezcla(self.texto, '#FFFFFF', .78)
        self.fondo = _mezcla(self.primario, '#FFFFFF', .94)

        def estilo(nombre, **kw):
            base = dict(fontName=fuente, fontSize=10, leading=14, textColor=colors.HexColor(self.texto))
            return ParagraphStyle(nombre, **{**base, **kw})
        self.cuerpo = estilo('cuerpo')
        self.cuerpo_largo = estilo('largo', leading=15)
        self.clinica = estilo('clinica', fontName=NEGRITA, fontSize=16, leading=19, textColor=colors.HexColor(self.primario))
        self.contacto = estilo('contacto', fontSize=8.5, leading=11.5, textColor=colors.HexColor(self.tenue))
        self.medico = estilo('medico', fontName=NEGRITA, fontSize=11.5, leading=14.5, alignment=TA_RIGHT, textColor=colors.HexColor(self.primario))
        self.medico_dato = estilo('medico_dato', fontSize=9, leading=12, alignment=TA_RIGHT)
        self.titulo = estilo('titulo', fontName=NEGRITA, fontSize=13, leading=16, textColor=colors.HexColor(self.primario))
        self.rotulo = estilo('rotulo', fontName=NEGRITA, fontSize=8.5, leading=11, textColor=colors.HexColor(self.primario))
        self.etiqueta = estilo('etiqueta', fontSize=7.5, leading=9.5, textColor=colors.HexColor(self.tenue))
        self.valor = estilo('valor', fontSize=10.5, leading=13)
        self.valor_fuerte = estilo('valor_fuerte', fontName=NEGRITA, fontSize=11.5, leading=14)
        self.medicamento = estilo('medicamento', fontName=NEGRITA, fontSize=11.5, leading=15)
        self.posologia = estilo('posologia', fontSize=10.5, leading=15)
        self.nota = estilo('nota', fontSize=9, leading=12.5, textColor=colors.HexColor(self.tenue))
        self.numero = estilo('numero', fontName=NEGRITA, fontSize=13, leading=16, textColor=colors.HexColor(self.primario))
        self.firma = estilo('firma', alignment=TA_CENTER, fontSize=9.5, leading=12.5)
        self.firma_nombre = estilo('firma_nombre', alignment=TA_CENTER, fontName=NEGRITA, fontSize=10.5, leading=13.5)


HUECO_FIRMA = 18


class Cierre(Flowable):
    """Últimos bloques del documento junto con la firma: la firma nunca queda sola en una hoja. En la receta se ancla
    al borde inferior de la hoja; en el resumen sigue al contenido."""

    def __init__(self, contenido, firma, anclar):
        super().__init__()
        self.contenido, self.firma, self.anclar = contenido, firma, anclar

    def wrap(self, ancho, alto):
        self.ancho = ancho
        self.alturas = [c.wrap(ancho, 10000)[1] for c in self.contenido]
        self.ancho_firma, self.alto_firma = self.firma.wrap(ancho, 10000)
        necesario = sum(self.alturas)+HUECO_FIRMA+self.alto_firma
        self.alto = max(alto, necesario) if self.anclar else necesario
        return ancho, self.alto

    def draw(self):
        y = self.alto
        for c, h in zip(self.contenido, self.alturas):
            y -= h
            c.drawOn(self.canv, 0, y)
        self.firma.drawOn(self.canv, self.ancho-self.ancho_firma, 0 if self.anclar else y-HUECO_FIRMA-self.alto_firma)


def _con_firma(historia, firma, anclar):
    """Saca del final de ``historia`` el último bloque (con su rótulo, que va «pegado») para formar el cierre con la firma.
    Un último bloque muy alto se deja en el flujo y la firma va sola."""
    cola = []
    if historia and historia[-1].wrap(ANCHO_UTIL, 10000)[1] <= 300:
        cola.insert(0, historia.pop())
        while historia and getattr(historia[-1], 'tv_pegado', False):
            cola.insert(0, historia.pop())
    return [*historia, Cierre(cola, firma, anclar)]


def _encabezado(identidad, medico, e):
    """Logo, nombre y contacto de la clínica a la izquierda; nombre, especialidad y cédula del médico a la derecha."""
    izquierda = [_p(identidad['clinic_name'], e.clinica)]
    if identidad.get('contact'):
        izquierda.append(_p(identidad['contact'], e.contacto))
    logo = identidad.get('clinic_logo')
    if logo and Path(logo).is_file():
        from PIL import Image as PILImage
        with PILImage.open(logo) as imagen:
            w, h = imagen.size
        escala = min(120/w, 58/h)
        celda = Table([[Image(logo, width=w*escala, height=h*escala), izquierda]], colWidths=[w*escala+12, ANCHO_UTIL*.62-w*escala-12])
        celda.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                   ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
        izquierda = celda
    derecha = [_p(medico['name'], e.medico)]
    if medico.get('specialty'):
        derecha.append(_p(medico['specialty'], e.medico_dato))
    if medico.get('cedula'):
        derecha.append(_p('Cédula profesional '+medico['cedula'], e.medico_dato))
    tabla = Table([[izquierda, derecha]], colWidths=[ANCHO_UTIL*.62, ANCHO_UTIL*.38])
    tabla.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                               ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                               ('LINEBELOW', (0, 0), (-1, 0), 1.6, colors.HexColor(e.primario))]))
    return tabla


def _franja_estado(estado, e):
    if estado not in ESTADOS:
        return []
    marca, aviso, fondo, texto = ESTADOS[estado]
    estilo = ParagraphStyle('estado', parent=e.cuerpo, fontName=NEGRITA, fontSize=9.5, leading=13, textColor=colors.HexColor(texto))
    tabla = Table([[Paragraph(f'{marca} · <font name="{registrar_fuentes()}">{escape(aviso)}</font>', estilo)]], colWidths=[ANCHO_UTIL])
    tabla.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(fondo)), ('LEFTPADDING', (0, 0), (-1, -1), 10),
                               ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
    return [Spacer(1, 8), tabla]


def _celda(etiqueta, valor, e, fuerte=False):
    return [_p(etiqueta.upper(), e.etiqueta), _p(valor or '—', e.valor_fuerte if fuerte else e.valor)]


def _bloque_paciente(paciente, fecha, signos, e):
    columnas = [ANCHO_UTIL*.42, ANCHO_UTIL*.2, ANCHO_UTIL*.18, ANCHO_UTIL*.2]
    filas = [[_celda('Paciente', paciente['name'], e, True), _celda('Edad', paciente.get('age', ''), e),
              _celda('Sexo', paciente.get('sex', ''), e), _celda('Fecha', fecha, e)]]
    estilo = [('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(e.fondo)), ('BOX', (0, 0), (-1, -1), .6, colors.HexColor(e.fino)),
              ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 6),
              ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]
    linea = [_celda('Expediente', paciente.get('folio', ''), e), _celda('Alergias', paciente.get('allergies', ''), e), '', '']
    filas.append(linea)
    estilo += [('SPAN', (1, 1), (-1, 1)), ('LINEABOVE', (0, 1), (-1, 1), .4, colors.HexColor(e.fino))]
    if signos:
        filas.append([_celda('Signos vitales', signos, e), '', '', ''])
        estilo += [('SPAN', (0, 2), (-1, 2)), ('LINEABOVE', (0, 2), (-1, 2), .4, colors.HexColor(e.fino))]
    tabla = Table(filas, colWidths=columnas)
    tabla.setStyle(TableStyle(estilo))
    return tabla


def _rotulo(texto, e):
    """Rótulo de sección: sus separadores y él mismo van «pegados» al flujo siguiente (``tv_pegado``)."""
    partes = [Spacer(1, 12), Paragraph(escape(texto.upper()), e.rotulo), Spacer(1, 3)]
    for parte in partes:
        parte.tv_pegado = True
    return partes


def _linea_fina(e):
    tabla = Table([['']], colWidths=[ANCHO_UTIL], rowHeights=[1])
    tabla.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), .5, colors.HexColor(e.fino))]))
    tabla.tv_pegado = True
    return tabla


def _medicamentos(filas, e):
    """Cada medicamento numerado: nombre y concentración, posología en una frase, cantidad a surtir e indicaciones."""
    flujo = []
    for numero, fila in enumerate(filas, 1):
        m = medicamento(fila)
        texto = [_p(m['titulo'], e.medicamento), _p(m['posologia'], e.posologia)]
        if m['surtir']:
            texto.append(_p('Surtir: '+m['surtir'], e.nota))
        if m['indicaciones']:
            texto.append(_p('Indicaciones: '+m['indicaciones'], e.nota))
        tabla = Table([[_p(f'{numero}.', e.numero), texto]], colWidths=[24, ANCHO_UTIL-24])
        tabla.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                   ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                                   ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor(e.fino))]))
        flujo.append(tabla)
    return flujo


def _firma(medico, e, rotulo='Firma del médico'):
    """Línea de firma con nombre, cédula y especialidad del médico responsable."""
    lineas = [_p(medico['name'], e.firma_nombre)]
    if medico.get('cedula'):
        lineas.append(_p('Cédula profesional '+medico['cedula'], e.firma))
    if medico.get('specialty'):
        lineas.append(_p(medico['specialty'], e.firma))
    lineas.append(_p(rotulo, ParagraphStyle('rot_firma', parent=e.firma, fontSize=7.5, textColor=colors.HexColor(e.tenue))))
    ancho = 230
    tabla = Table([[''], *[[x] for x in lineas]], colWidths=[ancho], rowHeights=[46]+[None]*len(lineas))
    tabla.setStyle(TableStyle([('LINEBELOW', (0, 0), (0, 0), .8, colors.HexColor(e.texto)), ('TOPPADDING', (0, 1), (-1, 1), 5),
                               ('TOPPADDING', (0, 2), (-1, -1), 0), ('BOTTOMPADDING', (0, 1), (-1, -1), 0)]))
    return tabla


def _lienzo(identidad, estado, e):
    """Lienzo con pie en todas las hojas («Página n de N»), marca de agua del estado y marca opcional de la app."""
    fuente = registrar_fuentes()
    marca = ESTADOS.get(estado)

    class Lienzo(lienzo.Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.paginas = []

        def showPage(self):
            self.paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self.paginas)
            for estado_pagina in self.paginas:
                self.__dict__.update(estado_pagina)
                self.pie(total)
                super().showPage()
            super().save()

        def pie(self, total):
            self.saveState()
            self.setStrokeColor(colors.HexColor(e.fino))
            self.setLineWidth(.5)
            self.line(MARGEN, 44, ANCHO-MARGEN, 44)
            self.setFont(fuente, 8)
            self.setFillColor(colors.HexColor(e.tenue))
            x = MARGEN
            if identidad.get('document_app_brand'):
                self.drawImage(str(APP_MARK), x, 26, width=14, height=14, mask='auto')
                self.drawString(x+19, 30, 'TresVizo · '+identidad['app_name'])
                x += 19+pdfmetrics.stringWidth('TresVizo · '+identidad['app_name'], fuente, 8)+14
            if identidad.get('document_website'):
                self.drawString(x, 30, identidad['website_text']+' · '+identidad['website'])
            self.drawRightString(ANCHO-MARGEN, 30, f'Página {self._pageNumber} de {total}')
            self.restoreState()
    return Lienzo, marca


def _marca_de_agua(marca):
    def dibujar(c, doc):
        if not marca:
            return
        c.saveState()
        c.setFillColor(colors.HexColor(marca[3]))
        c.setFillAlpha(.09)
        c.setFont(NEGRITA, 96)
        c.translate(ANCHO/2, ALTO/2)
        c.rotate(42)
        c.drawCentredString(0, 0, marca[0])
        c.restoreState()
    return dibujar


def _construir(ruta, identidad, titulo, historia, estado, medico):
    e = Estilos(identidad)
    Lienzo, marca = _lienzo(identidad, estado, e)
    documento = BaseDocTemplate(str(ruta), pagesize=LETTER, leftMargin=MARGEN, rightMargin=MARGEN, topMargin=MARGEN_SUPERIOR,
                                bottomMargin=MARGEN_INFERIOR, title=titulo, author='', creator=identidad['app_name'])
    marco = Frame(MARGEN, MARGEN_INFERIOR, ANCHO_UTIL, ALTO-MARGEN_SUPERIOR-MARGEN_INFERIOR, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0, id='pagina')
    documento.addPageTemplates([PageTemplate(id='hoja', frames=[marco], onPage=_marca_de_agua(marca))])
    documento.build(historia, canvasmaker=Lienzo)


def _cabecera(identidad, medico, titulo, estado, paciente, fecha, signos, e):
    historia = [_encabezado(identidad, medico, e), *_franja_estado(estado, e), Spacer(1, 12),
                Paragraph(escape(titulo.upper()), e.titulo), Spacer(1, 7), _bloque_paciente(paciente, fecha, signos, e)]
    return historia


def _signos_de_receta(grupos):
    if not grupos:
        return ''
    ultimo = sorted(grupos, key=lambda g: g.get('at', ''))[-1]
    return ' · '.join(f'{ABREVIATURAS[c]} {t}' for c, _, t in signos_ordenados(ultimo) if c in ROTULOS_SIGNOS_RECETA)


def crear_receta(ruta, identidad, datos):
    """Receta e indicaciones. ``datos``: ``estado``, ``fecha`` (dd/mm/aaaa), ``paciente`` (name, folio, age, sex, allergies),
    ``medico`` (name, specialty, cedula), ``diagnostico``, ``medicamentos`` (filas de la consulta), ``plan``, ``seguimiento``
    y ``signos`` (tomas de signos vitales)."""
    e = Estilos(identidad)
    medico = datos['medico']
    historia = _cabecera(identidad, medico, 'Receta médica', datos['estado'], datos['paciente'], datos['fecha'],
                         _signos_de_receta(datos.get('signos')), e)
    if datos.get('diagnostico'):
        historia += [*_rotulo('Diagnóstico', e), _p(datos['diagnostico'], e.cuerpo_largo)]
    historia += [*_rotulo('Rp. Tratamiento', e), _linea_fina(e), *_medicamentos(datos['medicamentos'], e)]
    if datos.get('plan'):
        historia += [*_rotulo('Indicaciones generales', e), _p(datos['plan'], e.cuerpo_largo)]
    if datos.get('seguimiento'):
        historia += [*_rotulo('Próxima cita', e), _p(datos['seguimiento'], e.cuerpo_largo)]
    historia = _con_firma(historia, _firma(medico, e), anclar=True)
    _construir(ruta, identidad, 'Receta médica', historia, datos['estado'], medico)


def _tabla_signos(grupos, e):
    flujo = []
    for grupo in sorted(grupos, key=lambda g: g.get('at', '')):
        pares = [(r, t) for _, r, t in signos_ordenados(grupo)]
        if not pares:
            continue
        celdas = [[_p(r.upper(), e.etiqueta), _p(t, e.valor)] for r, t in pares]
        filas = [celdas[i:i+4] for i in range(0, len(celdas), 4)]
        filas = [f+[['']]*(4-len(f)) for f in filas]
        tabla = Table(filas, colWidths=[ANCHO_UTIL/4]*4)
        tabla.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                                   ('TOPPADDING', (0, 0), (-1, -1), 0)]))
        if len(grupos) > 1:
            flujo.append(_p(grupo['_fecha'], e.nota))
        flujo.append(tabla)
    return flujo


def crear_resumen(ruta, identidad, datos):
    """Resumen de consulta: mismo encabezado y firma que la receta. ``secciones`` son ``(título, texto)`` de la nota sin
    adendas; «Signos vitales» y «Medicamentos» se dibujan con ``signos`` (tomas) y ``medicamentos`` (filas) cuando los hay;
    ``adendas`` son bloques con fecha, autor, motivo y contenido."""
    from .clinical_models import display_date
    e = Estilos(identidad)
    medico = datos['medico']
    historia = _cabecera(identidad, medico, 'Resumen de consulta', datos['estado'], datos['paciente'], datos['fecha'], '', e)
    for titulo, texto in datos['secciones']:
        if titulo == 'Signos vitales' and datos.get('signos'):
            grupos = [{**g, '_fecha': display_date(g['at'])} for g in datos['signos']]
            historia += [*_rotulo(titulo, e), *_tabla_signos(grupos, e)]
        elif titulo == 'Medicamentos' and datos.get('medicamentos'):
            historia += [*_rotulo(titulo, e), _linea_fina(e), *_medicamentos(datos['medicamentos'], e)]
        else:
            historia += [*_rotulo(titulo, e), _p(texto, e.cuerpo_largo)]
    if datos.get('adendas'):
        historia += _adendas(datos['adendas'], e)
    historia = _con_firma(historia, _firma(medico, e, 'Médico responsable'), anclar=False)
    _construir(ruta, identidad, 'Resumen de consulta', historia, datos['estado'], medico)


def _adendas(adendas_, e):
    flujo = [*_rotulo('Adendas', e), _linea_fina(e)]
    for a in adendas_:
        cabecera = _p(f"{a['fecha']} · {a['autor']}", e.nota)
        cuerpo = [cabecera, _p(a['motivo'], ParagraphStyle('motivo_adenda', parent=e.cuerpo, fontName=NEGRITA)), _p(a['contenido'], e.cuerpo_largo)]
        tabla = Table([[cuerpo]], colWidths=[ANCHO_UTIL])
        tabla.setStyle(TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                                   ('LINEBELOW', (0, 0), (-1, -1), .4, colors.HexColor(e.fino))]))
        flujo.append(tabla)
    return flujo
