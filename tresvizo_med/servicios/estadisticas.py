"""Estadísticas de consultas con los permisos de Med: cada médico las suyas, el administrador las de toda la clínica."""
from ..dominio import estadisticas as dominio
from ..dominio.errores import DataError
from ..formato import consulta_a_dict
from ..models import Paciente
from .consultas import visibles
from .errores import PermisoDenegado


def calcular(actor, inicio, fin, doctor=None, tipo='', diagnostico='', grupo='Todos'):
    """``doctor``: cuenta de un médico, ``'*'`` para toda la clínica, o ``None`` para las propias."""
    doctor = actor.cuenta_id if doctor is None else doctor
    if doctor != actor.cuenta_id and not actor.es_admin:
        raise PermisoDenegado('Solo el administrador consulta las estadísticas de otros médicos.')
    if grupo not in ('Todos', 'Nuevos', 'Recurrentes'):
        raise DataError('Grupo de pacientes no admitido.')
    filas = [consulta_a_dict(c, adendas=False) for c in visibles(actor)]
    pacientes = [{'id': str(p.id), 'sex': p.sexo, 'birth_date': p.nacimiento.isoformat() if p.nacimiento else None}
                 for p in Paciente.objects.only('id', 'sexo', 'nacimiento')]
    for p in pacientes:
        if not p['sex']:
            del p['sex']
        if not p['birth_date']:
            del p['birth_date']
    return dominio.calculate(filas, pacientes, inicio, fin, doctor, tipo, diagnostico, grupo)
