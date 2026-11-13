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


def serie_para(series):
    """SVG de una o más series. Los puntos de consultas finalizadas van rellenos; los del borrador, huecos."""
    puntos = [(s_i, p, False) for s_i, s in enumerate(series) for p in s['finales']] + \
             [(s_i, p, True) for s_i, s in enumerate(series) for p in s['provisionales']]
    if not puntos:
        return ''
    xs = [_fecha(p['at']) for _, p, _ in puntos]
    ys = [p['value'] for _, p, _ in puntos]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    relleno = (y1-y0)*.15 or max(abs(y1)*.1, 1)
    y0, y1 = y0-relleno, y1+relleno
    ex = _escala(x0, x1, MARGEN['izq'], ANCHO-MARGEN['der'])
    ey = _escala(y0, y1, ALTO-MARGEN['inf'], MARGEN['sup'])
    partes = [f'<svg class="med-grafica" viewBox="0 0 {ANCHO} {ALTO}" role="img" '
              f'aria-label="Evolución: {escape(", ".join(s["etiqueta"] for s in series))}. Los valores exactos están en la tabla.">']
    for k in range(5):
        valor = y0+(y1-y0)*k/4
        y = ey(valor)
        partes.append(f'<line class="med-grafica__rejilla" x1="{MARGEN["izq"]}" x2="{ANCHO-MARGEN["der"]}" y1="{y:.1f}" y2="{y:.1f}"/>')
        partes.append(f'<text class="med-grafica__eje" x="{MARGEN["izq"]-6}" y="{y+4:.1f}" text-anchor="end">{valor:.0f}</text>')
    for fecha in sorted({p['at'][:10] for _, p, _ in puntos})[:: max(1, len({p['at'][:10] for _, p, _ in puntos})//5)]:
        x = ex(_fecha(fecha+'T00:00:00'))
        partes.append(f'<text class="med-grafica__eje" x="{x:.1f}" y="{ALTO-14}" text-anchor="middle">{escape(fecha[8:10]+"/"+fecha[5:7])}</text>')
    for i, serie in enumerate(series):
        ordenados = sorted(serie['finales']+serie['provisionales'], key=lambda p: p['at'])
        if len(ordenados) > 1:
            trazo = ' '.join(f'{ex(_fecha(p["at"])):.1f},{ey(p["value"]):.1f}' for p in ordenados)
            partes.append(f'<polyline class="med-grafica__linea med-serie-{i+1}" points="{trazo}"/>')
    for i, p, provisional in puntos:
        clase = f'med-grafica__punto med-serie-{i+1}'+(' med-grafica__punto--hueco' if provisional else '')
        partes.append(f'<circle class="{clase}" cx="{ex(_fecha(p["at"])):.1f}" cy="{ey(p["value"]):.1f}" r="5">'
                      f'<title>{escape(series[i]["etiqueta"])}: {p["value"]:.6g} {escape(p["unit"])} · {escape(p["at"][:10])}'
                      f'{" · borrador" if provisional else ""}</title></circle>')
    partes.append('</svg>')
    return mark_safe(''.join(partes))
