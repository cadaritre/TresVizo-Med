"""Documentos: subida reanudable, cola de archivos por destino, lista con filtros, visor y versiones."""
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from ..dominio.errores import DataError
from ..models import BorradorAlta, Consulta, Documento, Paciente
from ..servicios import NoEncontrado, PermisoDenegado, VersionConflict, documentos, profesionales
from .comun import TODOS, es_htmx, vista_med

TIPOS_DESTINO = ('paciente', 'consulta', 'borrador')
EN_LINEA = ('image/png', 'image/jpeg', 'application/pdf')


def _destino(tipo, identificador):
    if tipo not in TIPOS_DESTINO:
        raise Http404
    return {tipo: identificador}


def contexto_gestor(request, tipo, identificador, error='', permitir=None, filtros=None):
    """Contexto de ``_gestor.html``: lista y cola de un destino."""
    actor = request.actor
    destino = _destino(tipo, identificador)
    filtros = filtros or {}
    paciente_id = identificador if tipo == 'paciente' else None
    if tipo == 'consulta':
        paciente_id = Consulta.objects.values_list('paciente_id', flat=True).filter(pk=identificador).first()
    kwargs = {'paciente': paciente_id, 'consulta': identificador if tipo == 'consulta' else None,
              'borrador': identificador if tipo == 'borrador' else None}
    lista = documentos.listar(actor, **kwargs, archivados=bool(filtros.get('archivados')))
    lista = documentos.filtrar(lista, filtros.get('q', ''), filtros.get('categoria', ''))
    finalizada = tipo == 'consulta' and Consulta.objects.filter(pk=identificador).exclude(estado='Borrador').exists()
    return {'tipo': tipo, 'identificador': identificador, 'lista': lista, 'cola': documentos.cola(actor, **kwargs),
            'categorias': documentos.CATEGORIAS, 'filtros': filtros, 'error': error, 'finalizada': finalizada,
            'puede_subir': actor.es_medico, 'limite': settings.TV_MED_LIMITE_DOCUMENTO,
            'permitir': permitir or {}}


def _kwargs(tipo, identificador):
    destino = _destino(tipo, identificador)
    if tipo == 'consulta':
        paciente = Consulta.objects.values_list('paciente_id', flat=True).filter(pk=identificador).first()
        return {'paciente': paciente, 'consulta': identificador}
    return {'paciente' if tipo == 'paciente' else 'borrador': destino[tipo]}


@vista_med(*TODOS)
def gestor(request, tipo, identificador):
    return render(request, 'med/documentos/_gestor.html', contexto_gestor(request, tipo, identificador))


@vista_med(*TODOS)
def lista(request, tipo, identificador):
    filtros = {'q': request.GET.get('q', ''), 'categoria': request.GET.get('categoria', ''), 'archivados': request.GET.get('archivados') == '1'}
    return render(request, 'med/documentos/_lista.html', contexto_gestor(request, tipo, identificador, filtros=filtros))


@vista_med('medico', metodos=('POST',))
def asociar(request, tipo, identificador):
    """Una subida terminada pasa a la cola del destino. La llama ``med.js`` al recibir ``tv-subida:listo``."""
    fila = request.POST.get('subido', '')
    try:
        documentos.asociar(request.actor, fila, reemplaza=request.POST.get('reemplaza') or None, **_kwargs(tipo, identificador))
        error = ''
    except NoEncontrado:
        raise
    except DataError as exc:
        error = str(exc)
    return render(request, 'med/documentos/_cola_y_lista.html', contexto_gestor(request, tipo, identificador, error))


@vista_med('medico', metodos=('POST',))
def incorporar(request, tipo, identificador, fila):
    fila = str(fila)
    post = request.POST
    try:
        documentos.incorporar(request.actor, fila, categoria=post.get('categoria') or 'Otro documento', titulo=post.get('titulo', ''),
                              notas=post.get('notas', ''), fecha=post.get('fecha', ''), motivo=post.get('motivo', ''),
                              permitir_duplicado=post.get('permitir_duplicado') == 'on', **_kwargs(tipo, identificador))
        error, permitir = '', {}
    except NoEncontrado:
        raise
    except PermisoDenegado:
        raise
    except DataError as exc:
        error, permitir = str(exc), {fila: 'idéntico' in str(exc)}
    contexto = contexto_gestor(request, tipo, identificador, error, permitir)
    contexto['fila_error'] = fila if error else ''
    return render(request, 'med/documentos/_cola_y_lista.html', contexto)


@vista_med('medico', metodos=('POST',))
def retirar(request, tipo, identificador, fila):
    documentos.retirar(request.actor, fila, **_kwargs(tipo, identificador))
    return render(request, 'med/documentos/_cola_y_lista.html', contexto_gestor(request, tipo, identificador))


# --- Un documento ---------------------------------------------------------------------------------------------

@vista_med(*TODOS)
def visor(request, documento):
    fila = documentos.obtener(request.actor, documento)
    cadena = documentos.versiones(request.actor, fila)
    contexto = {'x': fila, 'versiones': cadena, 'p': fila.paciente, 'autor': profesionales.nombre(fila.doctor_id),
                'es_imagen': fila.mime.startswith('image/'), 'es_pdf': fila.mime == 'application/pdf', 'categorias': documentos.CATEGORIAS,
                'es_foto': bool(fila.paciente_id and fila.paciente.foto_documento == fila.id), 'puede_editar': request.actor.es_medico or request.actor.es_admin,
                'finalizada': bool(fila.consulta_id and fila.consulta.estado != 'Borrador'),
                'gestor_destino': ('consulta', fila.consulta_id) if fila.consulta_id else ('paciente', fila.paciente_id) if fila.paciente_id else ('borrador', fila.borrador_id)}
    return render(request, 'med/documentos/visor.html', contexto)


@vista_med(*TODOS)
def archivo(request, documento):
    """Descarga el original tras verificar su integridad; ``?en_linea=1`` lo muestra en el visor (solo imágenes y PDF)."""
    fila = documentos.obtener(request.actor, documento)
    try:
        ruta = documentos.ruta_verificada(request.actor, documento)
    except DataError as exc:  # archivo ausente o alterado: el registro se conserva para recuperación
        return HttpResponse(str(exc), status=409, content_type='text/plain; charset=utf-8')
    en_linea = request.GET.get('en_linea') == '1' and fila.mime in EN_LINEA
    respuesta = FileResponse(ruta.open('rb'), as_attachment=not en_linea, filename=fila.nombre_original, content_type=fila.mime)
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@vista_med(*TODOS)
def miniatura(request, documento):
    try:
        ruta = documentos.miniatura(request.actor, documento)
    except DataError:
        raise Http404 from None
    if ruta is None:
        raise Http404
    respuesta = FileResponse(Path(ruta).open('rb'), content_type='image/png')
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


@vista_med('admin', 'medico', metodos=('POST',))
def editar(request, documento):
    post = request.POST
    fila = documentos.obtener(request.actor, documento)
    valores = {'title': post.get('titulo', ''), 'category': post.get('categoria', ''), 'notes': post.get('notas', ''),
               'document_date': post.get('fecha', '')}
    if post.get('accion') in ('archivar', 'restaurar'):
        valores = {'archived': post.get('accion') == 'archivar'}
    try:
        documentos.actualizar(request.actor, fila.id, valores, int(post.get('revision', fila.revision)), post.get('motivo', ''))
        messages.success(request, 'Documento actualizado.')
    except VersionConflict:
        messages.error(request, 'El documento cambió en otra pestaña. Revisa los datos y vuelve a intentarlo.')
    except PermisoDenegado:
        raise
    except (DataError, ValueError) as exc:
        messages.error(request, str(exc))
    return redirect('med:visor', documento=fila.id)


@vista_med('admin', 'medico', metodos=('POST',))
def foto(request, documento):
    fila = documentos.obtener(request.actor, documento)
    try:
        documentos.foto_de_paciente(request.actor, fila.paciente_id, fila.id)
        messages.success(request, 'Esta imagen es ahora la foto del paciente.')
    except PermisoDenegado:
        raise
    except DataError as exc:
        messages.error(request, str(exc))
    return redirect('med:visor', documento=fila.id)


@vista_med('medico')
def panel_consulta(request, consulta):
    """Panel lateral de documentos de una consulta (HTMX)."""
    c = Consulta.objects.filter(pk=consulta).first()
    if c is None:
        raise Http404
    return render(request, 'med/documentos/_panel.html', {**contexto_gestor(request, 'consulta', consulta), 'c': c})
