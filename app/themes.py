"""Tokens, contraste y preferencias de apariencia. Sin dependencias de Tk."""
from __future__ import annotations
from copy import deepcopy
import re
import uuid
from urllib.parse import urlsplit
from app.storage import DataError, read_json, atomic_json

COLORS = {
    'primary': 'Color principal', 'accent': 'Color de acento',
    'background': 'Fondo general', 'surface': 'Tarjetas y paneles',
    'header': 'Barra superior', 'sidebar': 'Navegación lateral',
    'text': 'Texto principal', 'muted': 'Texto secundario',
    'border': 'Bordes y separadores', 'button': 'Botones principales',
    'secondary': 'Botones secundarios', 'selection': 'Selección', 'focus': 'Foco',
    **{f'chart{i}': f'Gráficas · serie {i}' for i in range(1, 7)},
}
BASE = dict(zip(COLORS, ['#0066CC', '#087B86', '#F5F5F7', '#FFFFFF', '#FFFFFF', '#EFEFF2',
                       '#1D1D1F', '#626269', '#85858B', '#0066CC', '#EFEFF2', '#E8F1FC', '#0066CC',
                       '#086A8C', '#197653', '#8055A1', '#9A6200', '#A24468', '#4269A6']))
BUILTINS = {
    'Clínico': BASE,
    'TresVizo': {**BASE, 'accent': '#0A79A4', 'primary': '#173B5F'},
    'Verde suave': {**BASE, 'primary': '#245B4B', 'header': '#FFFFFF', 'sidebar': '#EAF1ED',
                    'background': '#F1F8F4', 'button': '#276E54', 'accent': '#276E54', 'secondary': '#DEEFE5'},
    'Azul profundo': {**BASE, 'background': '#101D2E', 'surface': '#1C2D42', 'header': '#132239',
                     'sidebar': '#132239', 'text': '#F0F6FC', 'muted': '#B9CDDD', 'border': '#8197AE',
                     'primary': '#A7D8FF', 'accent': '#69CBD0', 'button': '#70C7EA', 'secondary': '#304861',
                     'selection': '#416185', 'focus': '#70C7EA', 'chart1': '#70C7EA', 'chart2': '#76DBAD',
                     'chart3': '#C5A0EA', 'chart4': '#EBC576', 'chart5': '#F29AB9', 'chart6': '#9FB5FF'},
    'Neutro': {**BASE, 'primary': '#414A52', 'header': '#FFFFFF', 'sidebar': '#EFEFF2',
               'background': '#F5F5F3', 'accent': '#59636C', 'button': '#505A63', 'secondary': '#E4E7E8'},
}
SEMANTIC = {'error_bg': '#FDEBEC', 'error_fg': '#9E182C', 'warning_bg': '#FFF2CE',
            'warning_fg': '#714B00', 'success_bg': '#E1F4E8', 'success_fg': '#185631'}
DEFAULT_IDENTITY = {'app_name': 'Registro Clínico', 'clinic_name': 'Mi clínica', 'clinic_logo': '',
                    'clinic_icon': '', 'use_clinic_icon': False,
                    'contact': '', 'website': 'https://www.tresvizo.com/', 'website_text': 'tresvizo.com',
                    'document_website': False, 'document_app_brand': False,
                    'document_primary': '#07356F', 'document_text': '#263746'}


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise DataError('Usa un color hexadecimal completo: #RRGGBB.')
    return value.upper()


def luminance(value):
    rgb = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    return sum(a*b for a, b in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    x, y = sorted((luminance(a), luminance(b)))
    return (y + .05) / (x + .05)


def on(bg):
    return max(('#FFFFFF', '#000000'), key=lambda fg: contrast(fg, bg))


def mix(a, b, amount):
    return '#' + ''.join(f'{round(int(a[i:i+2], 16)*(1-amount)+int(b[i:i+2], 16)*amount):02X}' for i in (1, 3, 5))


def readable(fg, bg, minimum=4.5):
    if contrast(fg, bg) >= minimum:
        return fg
    target = on(bg)
    for n in range(1, 101):
        candidate = mix(fg, target, n/100)
        if contrast(candidate, bg) >= minimum:
            return candidate
    return target


def validate_tokens(tokens):
    if not isinstance(tokens, dict) or set(tokens) != set(COLORS):
        raise DataError('La paleta debe contener exactamente todos los tokens de color admitidos.')
    return {key: color(value) for key, value in tokens.items()}


def validate_theme(data):
    if not isinstance(data, dict) or set(data) != {'schema_version', 'name', 'tokens'} or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise DataError('Formato de tema incompatible. Se requiere schema_version 1, name y tokens.')
    name = data['name']
    if not isinstance(name, str) or not name.strip() or len(name) > 60 or any(ord(c) < 32 for c in name):
        raise DataError('El nombre del tema debe tener entre 1 y 60 caracteres sin controles.')
    return {'schema_version': 1, 'name': name.strip(), 'tokens': validate_tokens(data['tokens'])}


def issues(t):
    found = []
    for fg in ('text', 'muted', 'primary', 'accent'):
        for bg in ('background', 'surface'):
            ratio = contrast(t[fg], t[bg])
            if ratio < 4.5:
                found.append(f'{COLORS[fg]} sobre {COLORS[bg]}: {ratio:.2f}:1 (mínimo 4.5:1).')
    for fg in ('border', 'focus'):
        for bg in ('background', 'surface'):
            if contrast(t[fg], t[bg]) < 3:
                found.append(f'{COLORS[fg]} sobre {COLORS[bg]}: contraste menor que 3:1.')
    for key in (f'chart{i}' for i in range(1, 7)):
        if contrast(t[key], t['surface']) < 3:
            found.append(f'{COLORS[key]}: contraste menor que 3:1 en paneles.')
    return found


def repair(t):
    t = deepcopy(t)
    # Si dos superficies tienen luminancias incompatibles, aproximarlas permite texto común.
    for fg, minimum in [('text', 4.5), ('muted', 4.5), ('primary', 4.5), ('accent', 4.5), ('border', 3), ('focus', 3)]:
        candidates = [mix(t[fg], end, n/100) for end in ('#FFFFFF', '#000000') for n in range(101)]
        valid = [v for v in candidates if all(contrast(v, t[b]) >= minimum for b in ('surface', 'background'))]
        if not valid:
            t['background'] = t['surface']
            valid = [readable(t[fg], t['surface'], minimum)]
        t[fg] = valid[0]
    for i in range(1, 7):
        t[f'chart{i}'] = readable(t[f'chart{i}'], t['surface'], 3)
    return t


def derived(tokens):
    t = {**validate_tokens(tokens), **SEMANTIC}
    t['separator'] = mix(t['surface'], t['text'], .13)
    t['surface_secondary'] = mix(t['surface'], t['background'], .6)
    for key in ('header', 'sidebar', 'button', 'secondary', 'selection'):
        t[f'on_{key}'] = on(t[key])
        for state, amount in [('hover', .10), ('pressed', .19), ('disabled', .48)]:
            t[f'{key}_{state}'] = mix(t[key], t['surface'] if state == 'disabled' else on(t[key]), amount)
            t[f'on_{key}_{state}'] = on(t[f'{key}_{state}'])
    return t


def validate_url(url):
    if not isinstance(url, str) or any(c.isspace() for c in url):
        raise DataError('La dirección web no puede contener espacios.')
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or '\\' in url:
            raise ValueError()
        _ = parsed.port
    except ValueError as exc:
        raise DataError('Introduce una dirección HTTP o HTTPS válida, sin credenciales.') from exc
    return url


class Appearance:
    def __init__(self, store, auth):
        self.store, self.auth = store, auth
        self.state = store.read('config/appearance.json', {'schema_version': 1, 'clinic': 'Clínico', 'custom': {}, 'users': {}, 'owners': {}})
        self.validate_state(self.state)

    @staticmethod
    def validate_state(state):
        if not isinstance(state, dict) or set(state) != {'schema_version', 'clinic', 'custom', 'users', 'owners'} or type(state['schema_version']) is not int or state['schema_version'] != 1:
            raise DataError('Configuración de apariencia inválida; no se ha reemplazado.')
        if not isinstance(state['custom'], dict) or not isinstance(state['users'], dict) or not isinstance(state['clinic'], str):
            raise DataError('Preferencias inválidas.')
        for key, theme in state['custom'].items():
            validate_theme(theme)
            if key in BUILTINS:
                raise DataError('Identificador de tema inválido.')
        if not isinstance(state['owners'], dict) or set(state['owners']) != set(state['custom']):
            raise DataError('Propietarios de temas inválidos.')
        for owner in state['owners'].values():
            try:
                uuid.UUID(owner)
            except (ValueError, TypeError, AttributeError) as exc:
                raise DataError('Propietario inválido.') from exc
        keys = set(BUILTINS) | set(state['custom'])
        if state['clinic'] not in keys:
            raise DataError('No existe el tema general de la clínica.')
        for uid, value in state['users'].items():
            try:
                uuid.UUID(uid)
            except (ValueError, TypeError, AttributeError) as exc:
                raise DataError('Identificador de doctor inválido.') from exc
            if not isinstance(value, dict) or set(value) != {'inherit', 'theme'} or type(value['inherit']) is not bool or not isinstance(value['theme'], str) or value['theme'] not in keys:
                raise DataError('Preferencia de doctor inválida.')

    def commit(self, state):
        self.validate_state(state)
        self.store.write('config/appearance.json', state)
        self.state = state

    def list(self):
        return {**{k: {'name': k, 'tokens': v} for k, v in BUILTINS.items()}, **deepcopy(self.state['custom'])}

    def active_key(self):
        user = self.auth.current
        pref = self.state['users'].get(user['id'], {}) if user else {}
        return self.state['clinic'] if pref.get('inherit', True) else pref['theme']

    def tokens(self):
        return deepcopy(self.list()[self.active_key()]['tokens'])

    def save_theme(self, name, tokens):
        self.auth.require()
        data = validate_theme({'schema_version': 1, 'name': name, 'tokens': tokens})
        if data['name'].casefold() == 'personalizada':
            raise DataError('Elige un nombre propio para distinguir el tema del editor Personalizada.')
        if any(t['name'].casefold() == data['name'].casefold() for t in self.list().values()):
            raise DataError('Ya existe un tema con ese nombre.')
        key = str(uuid.uuid4())
        state = deepcopy(self.state)
        state['custom'][key] = data
        state['owners'][key] = self.auth.current['id']
        self.commit(state)
        return key

    def rename(self, key, name):
        self.require_owner(key)
        if key not in self.state['custom']:
            raise DataError('Las paletas prediseñadas no se pueden renombrar.')
        data = validate_theme({**self.state['custom'][key], 'name': name})
        if any(k != key and t['name'].casefold() == data['name'].casefold() for k, t in self.list().items()):
            raise DataError('Ya existe un tema con ese nombre.')
        state = deepcopy(self.state)
        state['custom'][key] = data
        self.commit(state)

    def delete(self, key):
        self.require_owner(key)
        if key not in self.state['custom']:
            raise DataError('Solo se pueden eliminar temas personalizados.')
        if key == self.state['clinic'] or any(p['theme'] == key for p in self.state['users'].values()):
            raise DataError('El tema está en uso. Cambia primero las preferencias que lo utilizan.')
        state = deepcopy(self.state)
        del state['custom'][key]
        del state['owners'][key]
        self.commit(state)

    def require_owner(self, key):
        actor = self.auth.require()
        if actor['role'] != 'admin' and self.state['owners'].get(key) != actor['id']:
            raise DataError('Solo puedes modificar tus temas personalizados.')

    def apply(self, key, inherit=False, clinic=False):
        user = self.auth.require('admin' if clinic else None)
        state = deepcopy(self.state)
        if clinic:
            state['clinic'] = key
        else:
            state['users'][user['id']] = {'inherit': bool(inherit), 'theme': key}
        self.commit(state)

    def import_theme(self, path):
        if path.stat().st_size > 64_000:
            raise DataError('El tema excede el máximo de 64 KB.')
        data = validate_theme(read_json(path))
        return self.save_theme(data['name'], data['tokens'])

    def export_theme(self, path, key):
        self.auth.require()
        data = self.list()[key]
        atomic_json(path, validate_theme({'schema_version': 1, **data}))
