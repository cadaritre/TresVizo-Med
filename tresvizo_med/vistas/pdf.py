"""PDF (receta, resumen, estadísticas) generados por tareas, vista previa con PDF.js y descargas de ZIP."""
from django.http import FileResponse
from django.shortcuts import render

from ..servicios import consultas, exportaciones
from .comun import TODOS, vista_med

TIPOS = {'receta': 'Receta e indicaciones', 'resumen': 'Resumen de consulta'}


def estado_tarea(request, tarea, titulo):
    """Página (o fragmento HTMX) con el avance de una tarea; al terminar muestra el enlace al resultado."""
    plantilla = 'med/parciales/_tarea.html' if request.headers.get('HX-Request') == 'true' else 'med/tarea.html'
    return render(request, plantilla, {'tarea': tarea, 'titulo': titulo})


@vista_med('admin', 'medico', metodos=('POST',))
def pdf_consulta(request, consulta, tipo):
    from .. import tareas
    if tipo not in TIPOS:
        from django.http import Http404
        raise Http404
    consultas.obtener(request.actor, consulta)  # 404 para un borrador ajeno, antes de encolar
    tarea = tareas.pdf_consulta.encolar(str(consulta), request.user.pk, tipo, usuario=request.user)
    return estado_tarea(request, tarea, TIPOS[tipo])


@vista_med(*TODOS)
def pdf(request, documento):
    """Vista previa del PDF con PDF.js."""
    exportaciones.ruta_pdf(request.actor, documento)
    return render(request, 'med/pdf.html', {'pdf_id': documento})


@vista_med(*TODOS)
def pdf_archivo(request, documento):
    ruta = exportaciones.ruta_pdf(request.actor, documento)
    respuesta = FileResponse(ruta.open('rb'), content_type='application/pdf', filename='documento.pdf')
    respuesta['Content-Disposition'] = 'inline; filename="documento.pdf"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@vista_med(*TODOS)
def descarga(request, documento):
    ruta = exportaciones.ruta_descarga(request.actor, documento)
    nombre = f'tresvizo-med-{documento}.zip'
    respuesta = FileResponse(ruta.open('rb'), as_attachment=True, filename=nombre, content_type='application/zip')
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta
