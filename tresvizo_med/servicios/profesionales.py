"""Nombre visible de los médicos: el del perfil profesional («Dra. Ana Muñoz») y, si falta, el de la cuenta del portal."""
from tvplataforma import cuentas

from ..models import Profesional


def nombres(ids):
    """``{cuenta_id: nombre visible}`` con una consulta al perfil y otra a las cuentas (solo las que no tienen nombre propio)."""
    ids = {int(i) for i in ids if i is not None}
    visibles = dict(Profesional.objects.filter(cuenta_id__in=ids).exclude(nombre_visible='').values_list('cuenta_id', 'nombre_visible'))
    faltan = ids-set(visibles)
    return {**cuentas.nombres(faltan), **visibles} if faltan else visibles


def nombre(cuenta_id):
    return nombres([cuenta_id]).get(int(cuenta_id), cuentas.DESCONOCIDA) if cuenta_id is not None else cuentas.DESCONOCIDA


def firma(cuenta_id):
    """Datos con los que un médico firma sus documentos: ``name``, ``cedula`` y ``specialty``."""
    perfil = Profesional.objects.filter(cuenta_id=cuenta_id).first()
    return {'name': nombre(cuenta_id), 'cedula': perfil.cedula if perfil else '', 'specialty': perfil.especialidad if perfil else ''}
