"""Tareas de Med (cola ``med``): PDF de receta y resumen, PDF de estadísticas, paquete del expediente y exportación completa.

Reciben identificadores, nunca datos (contrato §6). El trabajador no tiene petición: la persona se reconstruye por su id.
"""
from django.contrib.auth import get_user_model
from tvplataforma.middleware import urlconf_de
from tvplataforma.tareas import progreso, tarea

from .servicios import Actor, exportaciones, pdf


def _actor(usuario_id):
    return Actor.de(get_user_model().objects.get(pk=usuario_id))


def _ruta(nombre, *args):
    from django.urls import reverse
    return reverse(f'med:{nombre}', args=args, urlconf=urlconf_de('med'))


@tarea(cola='med')
def pdf_consulta(consulta_id, usuario_id, tipo):
    identificador, _ = pdf.crear_pdf_consulta(_actor(usuario_id), consulta_id, tipo, progreso)
    progreso(1, 'Listo')
    return {'mensaje': 'El PDF está listo.', 'url': _ruta('pdf', identificador), 'etiqueta': 'Ver el PDF'}


@tarea(cola='med')
def pdf_estadisticas(usuario_id, filtros):
    identificador, _ = pdf.crear_pdf_estadisticas(_actor(usuario_id), filtros, progreso)
    progreso(1, 'Listo')
    return {'mensaje': 'El PDF está listo.', 'url': _ruta('pdf', identificador), 'etiqueta': 'Ver el PDF'}


@tarea(cola='med')
def paquete_expediente(paciente_id, usuario_id, documentos, consulta_id=None):
    identificador = exportaciones.crear_paquete_expediente(_actor(usuario_id), paciente_id, documentos, consulta_id, progreso)
    progreso(1, 'Listo')
    return {'mensaje': 'El paquete del expediente está listo.', 'url': _ruta('descarga', identificador), 'etiqueta': 'Descargar el paquete'}


@tarea(cola='med')
def exportacion_completa(usuario_id):
    identificador = exportaciones.crear_exportacion_completa(_actor(usuario_id), progreso)
    progreso(1, 'Listo')
    return {'mensaje': 'La exportación de la clínica está lista.', 'url': _ruta('descarga', identificador), 'etiqueta': 'Descargar la exportación'}
