"""Campos y colecciones repetibles que se dibujan con ``parciales/_campo.html`` y ``_coleccion.html``.

Un campo es un diccionario (``nombre``, ``etiqueta``, ``valor``, ``tipo``, ``opciones``…). Las colecciones
(teléfonos, alergias, problemas, medicamentos habituales) se envían como ``<coleccion>__<id-de-fila>__<clave>``.
"""
import uuid

SEP = '__'
HTML = {'texto': 'text', 'fecha': 'date', 'numero': 'text', 'correo': 'email', 'hora': 'time', 'telefono': 'tel',
        'fechahora': 'datetime-local'}


def campo(nombre, etiqueta, valor='', tipo='texto', opciones=None, error='', ayuda='', requerido=False, **extra):
    """``tipo``: texto, fecha, numero, area, seleccion, casilla, correo, hora, fechahora o telefono."""
    return {'html': HTML.get(tipo, 'text'), 'nombre': nombre, 'etiqueta': etiqueta, 'valor': '' if valor is None else valor, 'tipo': tipo,
            'opciones': opciones or [], 'error': error, 'ayuda': ayuda, 'requerido': requerido, **extra}


def cadena(post, nombre, por_omision=''):
    return str(post.get(nombre, por_omision) or '').strip()


def leer_coleccion(post, nombre, claves):
    """Filas ``[{'id', clave: valor…}]`` en el orden en que llegaron; descarta las filas completamente vacías."""
    filas, orden = {}, []
    prefijo = nombre+SEP
    for llave in post.keys():
        if not llave.startswith(prefijo):
            continue
        resto = llave[len(prefijo):].split(SEP)
        if len(resto) != 2 or resto[1] not in claves:
            continue
        if resto[0] not in filas:
            filas[resto[0]] = {}
            orden.append(resto[0])
        filas[resto[0]][resto[1]] = cadena(post, llave)
    resultado = []
    for identificador in orden:
        fila = filas[identificador]
        if any(fila.get(c) for c in claves if c not in ('status', 'severity', 'type', 'frequency_kind', 'duration_unit')):
            resultado.append({'id': identificador, **{c: fila.get(c, '') for c in claves}})
    return resultado


def fila_nueva():
    return str(uuid.uuid4())


def campos_de_fila(coleccion, esquema, fila=None):
    """Campos de una fila de colección; ``esquema`` es una lista ``(clave, etiqueta, tipo, opciones)``."""
    fila = fila or {}
    identificador = fila.get('id') or fila_nueva()
    return {'id': identificador, 'coleccion': coleccion, 'campos': [
        campo(f'{coleccion}{SEP}{identificador}{SEP}{clave}', etiqueta, fila.get(clave, ''), tipo, opciones)
        for clave, etiqueta, tipo, opciones in esquema]}
