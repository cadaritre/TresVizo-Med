"""Estadísticas de consultas con los permisos de Med: cada médico las suyas, el administrador las de toda la clínica."""
from collections import Counter

from ..dominio import estadisticas as dominio
from ..dominio.errores import DataError
from ..dominio.texto import normalized
from ..formato import consulta_a_dict
from ..models import Paciente
from .consultas import visibles
from .errores import PermisoDenegado


ORDEN_EDADES = [etiqueta for etiqueta, _ in dominio.AGE_BANDS]+['65+', 'Desconocida']


def _formas_originales(filas, campo, separador=None):
    """``{texto normalizado: forma más frecuente tal como se escribió}``: el recuento agrupa sin acentos ni mayúsculas, pero
    se muestra «Hipertensión arterial sistémica», no «hipertension arterial sistemica»."""
    formas = {}
    for fila in filas:
        textos = str(fila.get(campo) or '').split(separador) if separador else [str(fila.get(campo) or '')]
        for texto in textos:
            texto = ' '.join(texto.split())
            if texto:
                formas.setdefault(normalized(texto), Counter())[texto] += 1
    return {clave: cuentas.most_common(1)[0][0] for clave, cuentas in formas.items()}


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
    datos = dominio.calculate(filas, pacientes, inicio, fin, doctor, tipo, diagnostico, grupo)
    for seccion, campo, separador in (('diagnoses', 'assessment', ';'), ('reasons', 'reason', None)):
        originales = _formas_originales(filas, campo, separador)
        datos[seccion] = {originales.get(clave, clave): valor for clave, valor in datos[seccion].items()}
    datos['ages'] = {k: datos['ages'][k] for k in sorted(datos['ages'], key=lambda e: ORDEN_EDADES.index(e) if e in ORDEN_EDADES else 99)}
    return datos
