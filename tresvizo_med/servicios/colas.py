"""Cola de archivos elegidos y aún no incorporados, por profesional y destino (``attachment_queues`` del escritorio)."""
from copy import deepcopy

from django.utils import timezone

from ..models import ColaDocumentos


def clave_destino(paciente=None, consulta=None, borrador=None):
    for nombre, valor in (('paciente', paciente), ('consulta', consulta), ('borrador', borrador)):
        if valor:
            return f'{nombre}:{valor}'
    raise ValueError('Destino de documentos inválido.')


def cargar(actor, **destino):
    fila = ColaDocumentos.objects.filter(profesional_id=actor.cuenta_id, destino=clave_destino(**destino)).first()
    return None if fila is None else deepcopy(fila.filas)


def guardar(actor, filas, **destino):
    clave = clave_destino(**destino)
    existente = ColaDocumentos.objects.filter(profesional_id=actor.cuenta_id, destino=clave).first()
    if existente is None and not filas:
        return
    if existente and existente.filas == filas:
        return
    ColaDocumentos.objects.update_or_create(profesional_id=actor.cuenta_id, destino=clave,
                                            defaults={'filas': deepcopy(filas), 'actualizado': timezone.now()})


def cargar_ediciones(actor, **destino):
    fila = ColaDocumentos.objects.filter(profesional_id=actor.cuenta_id, destino=clave_destino(**destino)).first()
    return None if fila is None else deepcopy(fila.ediciones)


def guardar_ediciones(actor, pendientes, **destino):
    clave = clave_destino(**destino)
    pendientes = {k: deepcopy(v) for k, v in pendientes.items() if v.get('kind') == 'document_metadata'}
    existente = ColaDocumentos.objects.filter(profesional_id=actor.cuenta_id, destino=clave).first()
    if (existente is None and not pendientes) or (existente and existente.ediciones == pendientes):
        return
    ColaDocumentos.objects.update_or_create(profesional_id=actor.cuenta_id, destino=clave,
                                            defaults={'ediciones': pendientes, 'actualizado': timezone.now()})
