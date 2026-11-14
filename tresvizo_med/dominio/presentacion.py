"""Presentación clínica para pantalla y PDF (orden de signos, posología en lenguaje de receta, adendas aparte).

Solo de la versión web: no cambia ``clinical_models`` (que conserva la paridad con el escritorio).
"""
from .clinical_models import VITALS, display_date

# Orden clínico fijo de los signos vitales: presión, frecuencias, temperatura, saturación, medidas, glucosa y dolor.
ORDEN_SIGNOS = ('pressure', 'heart_rate', 'respiratory_rate', 'temperature', 'oxygen', 'weight', 'height', 'bmi', 'glucose', 'pain')
ROTULOS_SIGNOS = {'pressure': 'Presión arterial', 'bmi': 'IMC'}
ABREVIATURAS = {'pressure': 'T/A', 'heart_rate': 'FC', 'respiratory_rate': 'FR', 'temperature': 'Temp.', 'oxygen': 'SatO₂',
                'weight': 'Peso', 'height': 'Talla', 'bmi': 'IMC', 'glucose': 'Glucosa', 'pain': 'Dolor'}


def _numero(valor):
    """«72.0» → «72»; deja intacto lo que no es un número."""
    texto = str(valor).strip()
    try:
        numero = float(texto.replace(',', '.'))
    except ValueError:
        return texto
    return str(int(numero)) if numero == int(numero) and '.' not in texto and ',' not in texto else texto


def signos_ordenados(grupo):
    """``[(clave, rótulo, texto)]`` de una toma de signos vitales en orden clínico; la presión va en una sola línea
    («157/73 mmHg»)."""
    valores = grupo.get('values', {})
    salida = {}
    if 'systolic' in valores or 'diastolic' in valores:
        sistolica = _numero(valores.get('systolic', {}).get('value', '—'))
        diastolica = _numero(valores.get('diastolic', {}).get('value', '—'))
        salida['pressure'] = f'{sistolica}/{diastolica} mmHg'
    for clave, item in valores.items():
        if clave in VITALS and clave not in ('systolic', 'diastolic'):
            texto = f"{_numero(item['value'])} {item['unit']}".strip()
            if clave == 'glucose' and grupo.get('context'):
                texto += f" ({grupo['context'].lower()})"
            salida[clave] = texto
    if grupo.get('bmi') is not None:
        salida['bmi'] = f"{grupo['bmi']} kg/m²"
    return [(c, ROTULOS_SIGNOS.get(c) or VITALS[c][0], salida[c]) for c in ORDEN_SIGNOS if c in salida]


def signos_texto(grupo):
    """Toma de signos vitales como texto de varias líneas: fecha y una línea por medición."""
    return '\n'.join([display_date(grupo['at']), *[f'{rotulo}: {texto}' for _, rotulo, texto in signos_ordenados(grupo)]])


FRECUENCIAS_DE_UNA = {'Cada N horas': 'cada hora', 'Veces al día': 'una vez al día'}
VERBOS = {'Oral': 'Tomar', 'Tópica': 'Aplicar', 'Inhalada': 'Inhalar', 'Oftálmica': 'Aplicar', 'Ótica': 'Aplicar'}


def _frecuencia(fila):
    tipo, valor = fila.get('frequency_kind', ''), str(fila.get('frequency', '')).strip()
    if tipo == 'Según necesidad' and not valor:
        return 'según necesidad'
    if not valor:
        return ''
    if tipo in FRECUENCIAS_DE_UNA and _numero(valor) == '1':
        return FRECUENCIAS_DE_UNA[tipo]
    if tipo == 'Cada N horas':
        return f'cada {_numero(valor)} horas'
    if tipo == 'Veces al día':
        return f'{_numero(valor)} veces al día'
    if tipo == 'Horarios':
        return f'a las {valor}'
    return valor


def medicamento(fila):
    """Partes de un medicamento para una receta: ``titulo`` («Losartán 50 mg, tableta»), ``posologia`` («Tomar 1 tableta
    por vía oral cada 12 horas durante 10 días.»), ``surtir`` («30 tabletas») y ``indicaciones``."""
    titulo = ' '.join(filter(None, [fila.get('name', '').strip(), str(fila.get('strength', '')).strip()]))
    if fila.get('presentation'):
        titulo += f", {fila['presentation'].strip().lower()}"
    ruta = fila.get('route', '').strip()
    dosis = ' '.join(filter(None, [_numero(fila['dose']) if fila.get('dose') else '', fila.get('dose_unit', '')])).strip()
    pasos = [VERBOS.get(ruta, 'Administrar'), dosis, f'por vía {ruta.lower()}' if ruta else '', _frecuencia(fila)]
    if fila.get('duration'):
        pasos.append(f"durante {_numero(fila['duration'])} {fila.get('duration_unit', 'días')}".strip())
    posologia = ' '.join(p for p in pasos if p)+'.'
    if fila.get('as_needed'):
        motivo = fila.get('as_needed_reason', '').strip()
        posologia += ' Solo si es necesario' + (f': {motivo}.' if motivo else '.')
    surtir = ' '.join(filter(None, [_numero(fila['quantity']) if fila.get('quantity') else '', fila.get('quantity_unit', '')])).strip()
    return {'titulo': titulo, 'posologia': posologia, 'surtir': surtir, 'indicaciones': fila.get('instructions', '').strip()}


def seccion_nota(registro):
    """Secciones de la nota (sin adendas) para la lectura y el resumen: ``[(título, texto)]`` solo con contenido y con
    los signos vitales en orden clínico."""
    from .clinical_models import encounter_sections
    secciones = encounter_sections({**registro, 'addenda': []})
    signos = '\n\n'.join(signos_texto(g) for g in registro.get('vitals', []))
    return [(t, signos if t == 'Signos vitales' else c) for t, c in secciones if c]


def adendas(registro, autores):
    """Adendas como bloques: ``[{'fecha', 'autor', 'motivo', 'contenido'}]`` en el orden en que se agregaron."""
    return [{'fecha': display_date(a['at']), 'autor': (autores or {}).get(a['actor'], 'Doctor registrado'),
             'motivo': a.get('reason', ''), 'contenido': a.get('content', '')} for a in registro.get('addenda', [])]
