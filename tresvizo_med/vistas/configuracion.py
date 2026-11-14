"""Configuración: apariencia (temas), identidad de la clínica, doctores y perfil propio."""
import json
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from tvplataforma import cuentas, hosts
from tvplataforma.temas import TOKENS

from ..dominio import themes
from ..dominio.errores import DataError
from ..models import Clinica, Profesional
from ..servicios import PermisoDenegado, apariencia, clinica
from .comun import TODOS, vista_med

ETIQUETAS_TOKENS = [(k, v) for k, v in themes.COLORS.items()]


@vista_med(*TODOS)
def hub(request):
    return render(request, 'med/configuracion/hub.html', {'perfil_url': reverse('med:perfil')})


# --- Apariencia ----------------------------------------------------------------------------------------------------

def _tokens_de(post, base=None):
    return {k: (post.get('c_'+k) or post.get(k) or (base or {}).get(k, '')).strip().upper() for k in TOKENS}


def _contexto_apariencia(request, editor=None):
    actor = request.actor
    lista = apariencia.listar()
    activo = apariencia.clave_activa(actor)
    perfil = Profesional.para(actor.cuenta_id)
    return {'temas': [{'clave': k, 'nombre': v['name'], 'tokens': v['tokens'], 'personalizado': 'owner' in v,
                       'mio': v.get('owner') == actor.cuenta_id, 'dlg': f'dlg-eliminar-{i}', 'puede_editar': 'owner' in v and (actor.es_admin or v.get('owner') == actor.cuenta_id)}
                      for i, (k, v) in enumerate(lista.items())],
            'activo': activo, 'hereda': perfil.hereda_tema, 'clinica': Clinica.obtener().tema_clinica, 'editor': editor,
            'etiquetas': ETIQUETAS_TOKENS}


def _editor(base_clave, nombre='', tokens=None, problemas=None, clave=''):
    base = apariencia.listar().get(base_clave) or apariencia.listar()['Clínico']
    t = tokens or base['tokens']
    return {'nombre': nombre, 'tokens': [(k, etiqueta, t[k]) for k, etiqueta in ETIQUETAS_TOKENS], 'problemas': problemas or [], 'base': base_clave, 'clave': clave}


@vista_med(*TODOS)
def apariencia_pagina(request):
    editor = _editor(request.GET.get('base', 'Clínico')) if 'base' in request.GET else None
    return render(request, 'med/configuracion/apariencia.html', _contexto_apariencia(request, editor))


@vista_med(*TODOS, metodos=('POST',))
def apariencia_aplicar(request):
    try:
        apariencia.aplicar(request.actor, request.POST.get('clave', ''), hereda=request.POST.get('hereda') == 'on',
                           clinica=request.POST.get('ambito') == 'clinica')
        messages.success(request, 'Tema aplicado.')
    except PermisoDenegado:
        raise
    except DataError as exc:
        messages.error(request, str(exc))
    return redirect('med:apariencia')


@vista_med(*TODOS, metodos=('POST',))
def apariencia_verificar(request):
    """Contraste en vivo mientras se edita (HTMX)."""
    try:
        problemas = apariencia.problemas(_tokens_de(request.POST))
        error = ''
    except (DataError, ValueError) as exc:
        problemas, error = [], str(exc)
    return render(request, 'med/configuracion/_contraste.html', {'problemas': problemas, 'error': error})


@vista_med(*TODOS, metodos=('POST',))
def apariencia_guardar(request):
    nombre = request.POST.get('nombre', '')
    tokens = _tokens_de(request.POST)
    clave = request.POST.get('clave', '')
    try:
        if request.POST.get('accion') == 'reparar':
            tokens = apariencia.reparar(tokens)
            return render(request, 'med/configuracion/apariencia.html', _contexto_apariencia(request, _editor(request.POST.get('base', 'Clínico'), nombre, tokens, clave=clave)))
        tema = apariencia.guardar_tema(request.actor, nombre, tokens)
        messages.success(request, 'Tema guardado.')
        return redirect('med:apariencia')
    except (DataError, ValueError) as exc:
        problemas = apariencia.problemas(tokens) if not isinstance(exc, ValueError) and 'contraste' in str(exc) else [str(exc)]
        messages.error(request, str(exc))
        return render(request, 'med/configuracion/apariencia.html', _contexto_apariencia(request, _editor(request.POST.get('base', 'Clínico'), nombre, tokens, problemas, clave)), status=422)


@vista_med(*TODOS, metodos=('POST',))
def apariencia_tema(request, clave):
    accion = request.POST.get('accion')
    try:
        if accion == 'renombrar':
            apariencia.renombrar(request.actor, clave, request.POST.get('nombre', ''))
            messages.success(request, 'Tema renombrado.')
        elif accion == 'eliminar':
            apariencia.eliminar(request.actor, clave)
            messages.success(request, 'Tema eliminado.')
        else:
            raise Http404
    except PermisoDenegado:
        raise
    except DataError as exc:
        messages.error(request, str(exc))
    return redirect('med:apariencia')


@vista_med(*TODOS)
def apariencia_exportar(request, clave):
    try:
        datos = apariencia.exportar(clave)
    except KeyError:
        raise Http404 from None
    respuesta = HttpResponse(json.dumps(datos, ensure_ascii=False, indent=2), content_type='application/json')
    respuesta['Content-Disposition'] = f'attachment; filename="tema-{datos["name"]}.json"'
    return respuesta


@vista_med(*TODOS, metodos=('POST',))
def apariencia_importar(request):
    archivo = request.FILES.get('archivo')
    try:
        if archivo is None:
            raise DataError('Elige un archivo de tema (.json).')
        apariencia.importar(request.actor, archivo.read())
        messages.success(request, 'Tema importado.')
    except DataError as exc:
        messages.error(request, str(exc))
    return redirect('med:apariencia')


# --- Identidad de la clínica -------------------------------------------------------------------------------------

CAMPOS_IDENTIDAD = ('app_name', 'clinic_name', 'contact', 'website', 'website_text', 'document_primary', 'document_text')


@vista_med('admin', metodos=('GET', 'POST'))
def identidad(request):
    fila = Clinica.obtener()
    error = ''
    if request.method == 'POST':
        valores = {k: request.POST.get(k, '').strip() for k in CAMPOS_IDENTIDAD}
        valores['document_website'] = request.POST.get('document_website') == 'on'
        valores['document_app_brand'] = request.POST.get('document_app_brand') == 'on'
        try:
            clinica.guardar_identidad(request.actor, valores, int(request.POST.get('revision', fila.revision)))
            logo = request.FILES.get('logo')
            if logo is not None:
                clinica.guardar_logo(request.actor, logo.read())
            elif request.POST.get('quitar_logo') == 'on':
                clinica.quitar_logo(request.actor)
            messages.success(request, 'Identidad de la clínica guardada.')
            return redirect('med:identidad')
        except (DataError, KeyError, ValueError) as exc:
            error = str(exc) or 'Revisa los datos.'
            fila.identidad = {**fila.valores(), **valores}
    return render(request, 'med/configuracion/identidad.html', {'fila': fila, 'v': fila.valores(), 'error': error,
                                                                 'primera_vez': not fila.configurada}, status=422 if error else 200)


@vista_med(*TODOS)
def logo(request):
    fila = Clinica.obtener()
    ruta = Path(settings.TV_MED_ARCHIVOS)/fila.logo_ruta if fila.logo_ruta else None
    if not ruta or not ruta.is_file():
        raise Http404
    respuesta = FileResponse(ruta.open('rb'), content_type='image/png')
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta


# --- Doctores y perfil -----------------------------------------------------------------------------------------

@vista_med('admin')
def doctores(request):
    """Perfiles profesionales de la clínica. Altas, bajas y roles se hacen en el portal, solo el propietario."""
    personas = {p.id: p for rol in ('medico', 'admin') for p in cuentas.con_rol('med', rol)}
    perfiles = {p.cuenta_id: p for p in Profesional.objects.filter(cuenta_id__in=personas)}
    filas = [{'persona': p, 'perfil': perfiles.get(i)} for i, p in sorted(personas.items(), key=lambda t: t[1].nombre.lower())]
    return render(request, 'med/configuracion/doctores.html', {'filas': filas, 'portal': hosts.url_portal('/')})


def _perfil_contexto(request, cuenta_id):
    perfil = Profesional.para(cuenta_id)
    return {'perfil': perfil, 'cuenta': cuenta_id, 'propio': cuenta_id == request.actor.cuenta_id, 'avatares': clinica.AVATARES,
            'nombre_portal': cuentas.nombre(cuenta_id), 'cuenta_url': hosts.url_portal(settings.TV_URL_CUENTA)}


@vista_med(*TODOS, metodos=('GET', 'POST'))
def perfil(request, cuenta=None):
    cuenta_id = request.actor.cuenta_id if cuenta is None else cuenta
    if cuenta_id != request.actor.cuenta_id:
        request.actor.exigir_admin()
    if request.method == 'POST':
        try:
            valores = {'nombre_visible': request.POST.get('nombre_visible', '').strip(), 'cedula': request.POST.get('cedula', '').strip(),
                       'especialidad': request.POST.get('especialidad', '').strip(), 'reducir_movimiento': request.POST.get('reducir_movimiento') == 'on'}
            if request.actor.es_admin and request.POST.get('campo_activo') == '1':
                valores['activo'] = request.POST.get('activo') == 'on'
            clinica.guardar_perfil(request.actor, cuenta_id, **valores)
            foto = request.FILES.get('foto')
            if foto is not None:
                clinica.guardar_foto_perfil(request.actor, cuenta_id, foto.read())
            elif request.POST.get('avatar'):
                clinica.elegir_avatar(request.actor, cuenta_id, request.POST['avatar'])
            messages.success(request, 'Perfil guardado.')
        except PermisoDenegado:
            raise
        except DataError as exc:
            messages.error(request, str(exc))
            return render(request, 'med/configuracion/perfil.html', _perfil_contexto(request, cuenta_id), status=422)
        return redirect('med:perfil') if cuenta is None else redirect('med:perfil_de', cuenta=cuenta)
    return render(request, 'med/configuracion/perfil.html', _perfil_contexto(request, cuenta_id))


@vista_med(*TODOS)
def perfil_foto(request, cuenta):
    """Foto o avatar de una persona (cualquier integrante de Med puede verlas)."""
    perfil = Profesional.objects.filter(cuenta_id=cuenta).first()
    if perfil is None or not perfil.avatar or perfil.avatar == 'initials':
        raise Http404
    if perfil.avatar == 'photo':
        ruta = Path(settings.TV_MED_ARCHIVOS)/perfil.foto_ruta if perfil.foto_ruta else None
    else:
        ruta = Path(__file__).resolve().parents[1]/'static'/'med'/'img'/'avatares'/(perfil.avatar+'.png')
        if perfil.avatar not in clinica.AVATARES:
            ruta = None
    if not ruta or not ruta.is_file():
        raise Http404
    respuesta = FileResponse(ruta.open('rb'), content_type='image/png')
    respuesta['X-Content-Type-Options'] = 'nosniff'
    return respuesta
