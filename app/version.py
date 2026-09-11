"""Versión pública: incrementar antes de publicar un instalador diferente."""
VERSION = '1.0.1'


def version_tuple(value=VERSION):
    import re
    if not isinstance(value, str) or not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', value):
        raise ValueError('La versión debe tener tres números: mayor.menor.corrección.')
    parts = tuple(map(int, value.split('.')))
    if any(n > limit for n, limit in zip(parts, (255, 255, 65535))):
        raise ValueError('La versión supera los límites de Windows Installer.')
    return parts
