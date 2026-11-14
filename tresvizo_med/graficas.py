"""Gráfica de evolución en SVG generada en el servidor. Sin estilos en línea: los colores vienen de clases del CSS."""
from datetime import datetime

from django.utils.html import escape
from django.utils.safestring import mark_safe

ANCHO, ALTO = 640, 280
MARGEN = {'izq': 52, 'der': 16, 'sup': 16, 'inf': 40}


def _fecha(texto):
    return datetime.fromisoformat(texto[:19]).timestamp()


def _escala(minimo, maximo, a, b):
    if maximo == minimo:
        return lambda v: (a+b)/2
    return lambda v: a+(v-minimo)/(maximo-minimo)*(b-a)


ESTRECHO = {'ancho': 300, 'alto': 250, 'margen': {'izq': 38, 'der': 12, 'sup': 14, 'inf': 34}, 'marcas_y': 4, 'marcas_x': 3}
AMPLIO = {'ancho': ANCHO, 'alto': ALTO, 'margen': MARGEN, 'marcas_y': 5, 'marcas_x': 5}


def _dia_mes(fecha):
    return fecha[8:10]+'/'+fecha[5:7]


def _fecha_completa(fecha):
    return fecha[8:10]+'/'+fecha[5:7]+'/'+fecha[:4]


def _svg_serie(series, puntos, formato, variante):
    ancho, alto, margen = formato['ancho'], formato['alto'], formato['margen']
    xs = [_fecha(p['at']) for _, p, _ in puntos]
    ys = [p['value'] for _, p, _ in puntos]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    relleno = (y1-y0)*.15 or max(abs(y1)*.1, 1)
    y0, y1 = y0-relleno, y1+relleno
    ex = _escala(x0, x1, margen['izq'], ancho-margen['der'])
    ey = _escala(y0, y1, alto-margen['inf'], margen['sup'])
    nombres = escape(", ".join(s["etiqueta"] for s in series))
    partes = [f'<svg class="med-grafica med-grafica--{variante}" viewBox="0 0 {ancho} {alto}" role="img" '
              f'aria-label="Evolución: {nombres}. Los valores exactos están en la tabla.">']
    marcas = formato['marcas_y']
    for k in range(marcas):
        valor = y0+(y1-y0)*k/(marcas-1)
        y = ey(valor)
        partes.append(f'<line class="med-grafica__rejilla" x1="{margen["izq"]}" x2="{ancho-margen["der"]}" y1="{y:.1f}" y2="{y:.1f}"/>')
        partes.append(f'<text class="med-grafica__eje" x="{margen["izq"]-6}" y="{y+4:.1f}" text-anchor="end">{valor:.0f}</text>')
    dias = sorted({p['at'][:10] for _, p, _ in puntos})
    for fecha in dias[:: max(1, -(-len(dias)//formato['marcas_x']))]:
        partes.append(f'<text class="med-grafica__eje" x="{ex(_fecha(fecha+"T00:00:00")):.1f}" y="{alto-12}" text-anchor="middle">{_dia_mes(fecha)}</text>')
    for i, serie in enumerate(series):
        ordenados = sorted(serie['finales']+serie['provisionales'], key=lambda p: p['at'])
        if len(ordenados) > 1:
            trazo = ' '.join(f'{ex(_fecha(p["at"])):.1f},{ey(p["value"]):.1f}' for p in ordenados)
            partes.append(f'<polyline class="med-grafica__linea med-serie-{i+1}" points="{trazo}"/>')
    for i, p, provisional in puntos:
        clase = f'med-grafica__punto med-serie-{i+1}'+(' med-grafica__punto--hueco' if provisional else '')
        x, y = ex(_fecha(p["at"])), ey(p["value"])
        titulo = (f'<title>{escape(series[i]["etiqueta"])}: {p["value"]:.6g} {escape(p["unit"])} · {_fecha_completa(p["at"][:10])}'
                  f'{" · borrador" if provisional else ""}</title>')
        if i % 2:  # la segunda serie con cuadros: no depende solo del color
            partes.append(f'<rect class="{clase}" x="{x-5:.1f}" y="{y-5:.1f}" width="10" height="10">{titulo}</rect>')
        else:
            partes.append(f'<circle class="{clase}" cx="{x:.1f}" cy="{y:.1f}" r="5">{titulo}</circle>')
    partes.append('</svg>')
    return ''.join(partes)


def serie_para(series):
    """SVG de una o más series. Los puntos de consultas finalizadas van rellenos; los del borrador, huecos. Se dibujan dos
    versiones (amplia y estrecha, de texto legible en teléfono) y el CSS muestra la que corresponde al ancho."""
    puntos = [(s_i, p, False) for s_i, s in enumerate(series) for p in s['finales']] + \
             [(s_i, p, True) for s_i, s in enumerate(series) for p in s['provisionales']]
    if not puntos:
        return ''
    return mark_safe(_svg_serie(series, puntos, AMPLIO, 'amplia')+_svg_serie(series, puntos, ESTRECHO, 'estrecha'))


def barras(valores, ancho=ANCHO, alto=200):
    """Barras por día (``{'2026-09-10': 3, …}``) para la actividad del periodo. Los números exactos van en la tabla."""
    if not valores:
        return ''
    items = sorted(valores.items())
    maximo = max(v for _, v in items) or 1
    sitio = (ancho-MARGEN['izq']-MARGEN['der'])/len(items)
    grueso = min(28, sitio*.7)
    partes = [f'<svg class="med-grafica" viewBox="0 0 {ancho} {alto}" role="img" aria-label="Consultas por día; el máximo es {maximo}.">']
    base = alto-MARGEN['inf']
    marcas = min(5, maximo+1)  # con máximos chicos, una marca por número entero (no «1, 1, 0, 0, 0»)
    for k in range(marcas):
        y = base-(base-MARGEN['sup'])*k/(marcas-1)
        partes.append(f'<line class="med-grafica__rejilla" x1="{MARGEN["izq"]}" x2="{ancho-MARGEN["der"]}" y1="{y:.1f}" y2="{y:.1f}"/>')
        partes.append(f'<text class="med-grafica__eje" x="{MARGEN["izq"]-6}" y="{y+4:.1f}" text-anchor="end">{maximo*k/(marcas-1):.0f}</text>')
    paso = max(1, len(items)//8)
    for i, (dia, valor) in enumerate(items):
        x = MARGEN['izq']+sitio*i+(sitio-grueso)/2
        altura = (base-MARGEN['sup'])*valor/maximo
        partes.append(f'<rect class="med-grafica__barra" x="{x:.1f}" y="{base-altura:.1f}" width="{grueso:.1f}" height="{altura:.1f}"><title>{escape(dia)}: {valor}</title></rect>')
        if i % paso == 0:
            partes.append(f'<text class="med-grafica__eje" x="{x+grueso/2:.1f}" y="{alto-14}" text-anchor="middle">{escape(dia[8:10]+"/"+dia[5:7])}</text>')
    partes.append('</svg>')
    return mark_safe(''.join(partes))
