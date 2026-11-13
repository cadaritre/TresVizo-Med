"""Exportaciones, importación de pacientes desde CSV, paquete del expediente y exportación completa."""
import uuid

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from tvplataforma import cuentas

from ..dominio.errores import DataError
from ..models import Documento, LoteImportacion
from ..servicios import exportaciones, importacion, pacientes
from .comun import TODOS, vista_med
from .pdf import estado_tarea


@vista_med(*TODOS)
def exportar(request):
    actor = request.actor
    return render(request, 'med/exportar.html', {
        'medicos': cuentas.con_rol('med', 'medico') if actor.es_admin else [], 'q': request.GET.get('q', ''),
        'modo': request.GET.get('modo', 'Activos'), 'modos': pacientes.MODOS})


def _descarga(cuerpo, nombre, tipo):
    respuesta = HttpResponse(cuerpo, content_type=tipo)
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


def _ids(texto):
    if not texto:
        return None
    try:
        return [uuid.UUID(t) for t in texto.split(',') if t]
    except ValueError:
        raise Http404 from None


@vista_med(*TODOS)
def exportar_pacientes(request):
    try:
        cuerpo, nombre, tipo = exportaciones.exportar_pacientes(
            request.actor, request.GET.get('formato', 'csv'), request.GET.get('q', ''), request.GET.get('modo', 'Activos'), _ids(request.GET.get('ids', '')))
    except DataError as exc:
        return HttpResponse(str(exc), status=422, content_type='text/plain; charset=utf-8')
    return _descarga(cuerpo, nombre, tipo)


@vista_med(*TODOS)
def exportar_consultas(request):
    doctor = request.GET.get('doctor', '')
    doctor = '*' if doctor == '*' else int(doctor) if doctor.isdigit() else None
    try:
        cuerpo, nombre, _ = exportaciones.exportar_consultas(request.actor, request.GET.get('desde', ''), request.GET.get('hasta', ''),
                                                              doctor, request.GET.get('borradores') == '1', _ids(request.GET.get('ids', '')))
    except DataError as exc:
        if 'administrador' in str(exc):
            raise
        return HttpResponse(str(exc), status=422, content_type='text/plain; charset=utf-8')
    return _descarga(cuerpo, nombre, 'text/csv; charset=utf-8')


@vista_med('admin', metodos=('POST',))
def exportacion_completa(request):
    from .. import tareas
    tarea = tareas.exportacion_completa.encolar(request.user.pk, usuario=request.user)
    return estado_tarea(request, tarea, 'Exportación completa de la clínica')


@vista_med(*TODOS, metodos=('GET', 'POST'))
def paquete(request, paciente):
    """Elige documentos (y opcionalmente una consulta) y genera el ZIP del expediente con una tarea."""
    from .. import tareas
    from ..servicios import documentos
    persona = pacientes.obtener(request.actor, paciente)
    lista = [d for d in documentos.listar(request.actor, persona.id, archivados=True)]
    if request.method == 'POST':
        elegidos = [i for i in request.POST.getlist('documento') if i in {str(d.id) for d in lista}]
        tarea = tareas.paquete_expediente.encolar(str(persona.id), request.user.pk, elegidos, request.POST.get('consulta') or None,
                                                  usuario=request.user)
        return estado_tarea(request, tarea, 'Paquete del expediente')
    return render(request, 'med/paquete.html', {'p': persona, 'documentos': lista})


# --- Importar pacientes desde CSV --------------------------------------------------------------------------------

CAMPOS_IMPORTACION = [('name', 'Nombre (obligatorio)'), ('birth_date', 'Fecha de nacimiento (AAAA-MM-DD)'), ('phone', 'Teléfono'), ('email', 'Correo')]


@vista_med('admin', metodos=('GET', 'POST'))
def importar(request):
    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        if archivo is None:
            messages.error(request, 'Elige un archivo CSV.')
            return redirect('med:importar')
        try:
            lote = importacion.leer(request.actor, archivo.read(), archivo.name, request.POST.get('delimitador', ','))
        except DataError as exc:
            messages.error(request, str(exc))
            return redirect('med:importar')
        return redirect('med:importar_mapear', lote=lote.id)
    return render(request, 'med/importar.html', {})


@vista_med('admin', metodos=('GET', 'POST'))
def importar_mapear(request, lote):
    registro = _lote_ensayo(request, lote)
    columnas = registro.recibo['fuente']['columns']
    if request.method == 'POST':
        mapeo = {clave: request.POST.get(clave, '') for clave, _ in CAMPOS_IMPORTACION}
        try:
            importacion.vista_previa(request.actor, registro.id, mapeo)
        except DataError as exc:
            messages.error(request, str(exc))
            return redirect('med:importar_mapear', lote=registro.id)
        return redirect('med:importar_previa', lote=registro.id)
    sugerido = {clave: next((c for c in columnas if c.strip().lower() == clave), '') for clave, _ in CAMPOS_IMPORTACION}
    return render(request, 'med/importar_mapear.html', {'lote': registro, 'columnas': columnas, 'campos': CAMPOS_IMPORTACION,
                                                          'sugerido': registro.recibo.get('mapeo') or sugerido,
                                                          'muestra': registro.recibo['fuente']['rows'][:3]})


def _lote_ensayo(request, lote):
    request.actor.exigir_admin()
    registro = LoteImportacion.objects.filter(pk=lote, tipo=LoteImportacion.Tipo.CSV).first()
    if registro is None:
        raise Http404
    return registro


@vista_med('admin', metodos=('GET', 'POST'))
def importar_previa(request, lote):
    registro = _lote_ensayo(request, lote)
    if registro.estado == LoteImportacion.Estado.CONFIRMADO:
        return redirect('med:importar_recibo', lote=registro.id)
    if 'filas' not in registro.recibo:
        return redirect('med:importar_mapear', lote=registro.id)
    if request.method == 'POST':
        elegidas = {int(n) for n in request.POST.getlist('fila') if n.isdigit()}
        aceptadas = {int(n) for n in request.POST.getlist('duplicado') if n.isdigit()}
        try:
            importacion.importar(request.actor, registro.id, elegidas, aceptadas)
        except DataError as exc:
            messages.error(request, str(exc))
            return redirect('med:importar_previa', lote=registro.id)
        return redirect('med:importar_recibo', lote=registro.id)
    return render(request, 'med/importar_previa.html', {'lote': registro, 'filas': registro.recibo['filas'], 'conteos': registro.conteos})


@vista_med('admin')
def importar_recibo(request, lote):
    registro = _lote_ensayo(request, lote)
    if registro.estado != LoteImportacion.Estado.CONFIRMADO:
        return redirect('med:importar_previa', lote=registro.id)
    return render(request, 'med/importar_recibo.html', {'lote': registro})
