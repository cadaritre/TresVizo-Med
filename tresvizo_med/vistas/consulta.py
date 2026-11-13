"""Consulta SOAP: editor con autoguardado y capturas laterales, revisión, finalización, adendas y conflictos."""
import json

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from tvplataforma import cuentas

from ..dominio.clinical_models import encounter_sections, medication_text
from ..dominio.consultation_state import CAPTURE_NAMES, COLLECTIONS, ConsultationDraft, measurement_summary
from ..dominio.editing_state import merge_draft
from ..dominio.errores import DataError
from ..formato import consulta_a_dict
from ..formularios import consulta as form_consulta
from ..formularios.consulta import TIPOS_CAPTURA, campos_captura, leer_captura, leer_soap, solo_soap
from ..formularios.paciente import edad_texto
from ..models import Consulta
from ..servicios import NoEncontrado, PermisoDenegado, VersionConflict, borradores, consultas, documentos
from .comun import es_htmx, redirigir, vista_med

CLAVE_CONFLICTO = 'med_conflicto_'
ORDEN_CAPTURAS = {'vitals': 'vitals', 'medication': 'prescriptions', 'study': 'study_orders', 'diagnosis': 'diagnoses'}


def _editable(actor, c):
    return c.estado == Consulta.Estado.BORRADOR and c.doctor_id == actor.cuenta_id and not c.archivada and actor.es_medico


def _para_editar(request, identificador):
    c = consultas.obtener(request.actor, identificador)
    if not _editable(request.actor, c):
        raise PermisoDenegado('Esta consulta ya no se puede editar.')
    return c


def _guardar_borrador(actor, draft, revision):
    return consultas.guardar(actor, draft.snapshot(), revision)


def _resumenes(draft):
    datos = draft.data
    return {
        'diagnosticos': [{'id': r['id'], 'texto': r['name']} for r in datos['diagnoses']],
        'signos': [{'id': r['id'], 'texto': measurement_summary(r)} for r in sorted(datos['vitals'], key=lambda g: g.get('at', ''))],
        'medicamentos': [{'id': r['id'], 'texto': medication_text(r), 'revisar': bool(r.get('needs_review'))} for r in datos['prescriptions']],
        'estudios': [{'id': r['id'], 'texto': r['name']+' · '+r.get('status', 'Sin estado') + (('\n'+r['notes']) if r.get('notes') else '')}
                     for r in datos['study_orders']],
        'pendientes': [{'tipo': p['kind'], 'id': p['id'], 'nombre': CAPTURE_NAMES.get(p['kind'], 'Captura')} for p in draft.pending.values()
                       if p['kind'] in TIPOS_CAPTURA],
    }


def _contexto_editor(request, c, draft=None, errores=None):
    d = consulta_a_dict(c)
    draft = draft or ConsultationDraft(d)
    paciente = c.paciente
    alergias = [r.get('substance') for r in paciente.datos.get('allergy_records', []) if r.get('substance')]
    soap = solo_soap(d)
    abrir_url = _url_abrir(c, request.GET.get('abrir', ''))
    return {'abrir_url': abrir_url, 'c': c, 'p': paciente, 'd': d, 'edad': edad_texto(paciente_dict_basico(paciente)), 'alergias': alergias,
            'estado_alergias': paciente.datos.get('allergy_status', 'No interrogado'),
            'encabezado': form_consulta.campos_encabezado(d['attended_at'], d.get('type', 'General'), (errores or {}).get('header', '')),
            'textos': form_consulta.campos_texto(d), 'resumenes': _resumenes(draft), 'base': json.dumps(soap, ensure_ascii=False),
            'tipos_captura': TIPOS_CAPTURA, 'abrir': request.GET.get('abrir', ''), 'errores': errores or {}}


def _url_abrir(c, valor):
    """Enlace de «Revisar y finalizar» a una captura: ``tipo`` o ``tipo/identificador``."""
    tipo, _, item = valor.partition('/')
    if tipo not in TIPOS_CAPTURA:
        return ''
    return reverse('med:captura_item', args=[c.id, tipo, item]) if item else reverse('med:captura', args=[c.id, tipo])


def paciente_dict_basico(p):
    d = {}
    if p.nacimiento:
        d['birth_date'] = p.nacimiento.isoformat()
    if p.edad_aproximada:
        d['approx_age'] = p.edad_aproximada
    return d


def _contexto_lectura(request, c):
    d = consulta_a_dict(c)
    actor = request.actor
    autores = cuentas.nombres({c.doctor_id, *[a['actor'] for a in d['addenda']]})
    secciones = encounter_sections(d, autores)
    puede_anular = (c.doctor_id == actor.cuenta_id and actor.es_medico) or actor.es_admin
    return {'c': c, 'p': c.paciente, 'd': d, 'secciones': secciones, 'doctor': autores.get(c.doctor_id, ''),
            'puede_anular': puede_anular, 'puede_adenda': actor.es_medico, 'edad': edad_texto(paciente_dict_basico(c.paciente)),
            'alergias': [r.get('substance') for r in c.paciente.datos.get('allergy_records', []) if r.get('substance')],
            'documentos': documentos.listar(actor, c.paciente_id, c.id) if c.paciente_id else []}


@vista_med('admin', 'medico')
def consulta(request, consulta):
    c = consultas.obtener(request.actor, consulta)
    if _editable(request.actor, c):
        return render(request, 'med/consulta/editor.html', _contexto_editor(request, c))
    return render(request, 'med/consulta/lectura.html', _contexto_lectura(request, c))


def _estado(c, base):
    return {'revision': c.revision, 'base': json.dumps(base, ensure_ascii=False)}


def _indicador(request, c, base, estado=200, error=''):
    return render(request, 'med/parciales/_guardado.html',
                  {'hora': timezone.localtime(c.updated_at), 'estado_editor': _estado(c, base), 'error': error}, status=estado)


def _aplicar_soap(draft, local):
    for clave in form_consulta.TEXTOS:
        draft.data[clave] = local[clave]
    draft.data['type'] = local['type']
    draft.data['attended_at'] = local['attended_at']


def _conflicto(request, c, local, base, remoto):
    request.session[CLAVE_CONFLICTO+str(c.id)] = {'local': local, 'base': base}
    return redirigir(request, reverse('med:conflicto', args=[c.id]))


@vista_med('medico', metodos=('POST',))
def guardar(request, consulta):
    """Autoguardado (HTMX, 900 ms / 5 s) y guardado explícito (Ctrl+S, «Revisar y finalizar»)."""
    c = _para_editar(request, consulta)
    d = consulta_a_dict(c)
    try:
        local = leer_soap(request.POST, d['attended_at'])
    except DataError as error:
        return render(request, 'med/parciales/_guardado.html', {'error': str(error), 'estado_editor': _estado(c, solo_soap(d))}, status=422)
    try:
        revision = int(request.POST.get('revision', c.revision))
        base = json.loads(request.POST.get('base') or 'null') or solo_soap(d)
    except (ValueError, TypeError):
        raise Http404 from None
    draft = ConsultationDraft(d)
    _aplicar_soap(draft, local)
    try:
        if revision == c.revision and solo_soap(d) == local:
            guardada = c
        else:
            guardada = _guardar_borrador(request.actor, draft, revision)
    except VersionConflict as error:
        remoto = error.current
        fusion, conflictos = merge_draft(base, local, solo_soap(remoto))
        if conflictos:
            return _conflicto(request, c, local, base, remoto)
        # Dos pestañas sin campos en común: se combinan sin pérdida.
        draft = ConsultationDraft(remoto)
        _aplicar_soap(draft, {**local, **fusion})
        guardada = _guardar_borrador(request.actor, draft, remoto['revision'])
        local = {**local, **fusion}
    if not es_htmx(request):
        return redirect('med:revisar' if request.POST.get('ir') == 'revisar' else 'med:consulta', consulta=c.id)
    return _indicador(request, guardada, solo_soap(consulta_a_dict(guardada, adendas=False)))


@vista_med('medico', metodos=('GET', 'POST'))
def conflicto(request, consulta):
    """Diferencias por campo entre mi captura y la versión guardada en otra pestaña."""
    c = _para_editar(request, consulta)
    guardado = request.session.get(CLAVE_CONFLICTO+str(c.id))
    if not guardado:
        return redirect('med:consulta', consulta=c.id)
    remoto = consulta_a_dict(c)
    fusion, conflictos = merge_draft(guardado['base'], guardado['local'], solo_soap(remoto))
    if request.method == 'POST':
        for clave in conflictos:
            eleccion = request.POST.get('campo_'+clave)
            if eleccion not in ('local', 'remoto'):
                messages.error(request, 'Elige una versión para cada campo en conflicto.')
                return redirect('med:conflicto', consulta=c.id)
            fusion[clave] = conflictos[clave][eleccion if eleccion == 'local' else 'remote']
        draft = ConsultationDraft(remoto)
        _aplicar_soap(draft, {**solo_soap(remoto), **fusion})
        _guardar_borrador(request.actor, draft, c.revision)
        request.session.pop(CLAVE_CONFLICTO+str(c.id), None)
        messages.success(request, 'Se combinaron las dos versiones de la consulta.')
        return redirect('med:consulta', consulta=c.id)
    etiquetas = {**form_consulta.ROTULOS_TEXTO, 'type': 'Tipo de consulta', 'attended_at': 'Fecha y hora de atención'}
    filas = [{'clave': k, 'etiqueta': etiquetas.get(k, k), 'local': v['local'], 'remoto': v['remote']} for k, v in conflictos.items()]
    return render(request, 'med/consulta/conflicto.html', {'c': c, 'p': c.paciente, 'filas': filas})


# --- Capturas laterales ---------------------------------------------------------------------------------------

def _panel(request, c, draft, tipo, identificador, valores, pendiente, errores=None, estado=200):
    catalogo = borradores.catalogo(request.actor) if tipo == 'medication' else None
    favoritos = [f for f in (catalogo or []) if request.actor.cuenta_id in f['favorites']]
    return render(request, 'med/consulta/_panel_captura.html', {
        'c': c, 'tipo': tipo, 'rotulo': TIPOS_CAPTURA[tipo], 'item': identificador, 'pendiente': pendiente,
        'existe': any(r['id'] == identificador for r in draft.data.get(COLLECTIONS[tipo], [])),
        'campos': campos_captura(tipo, valores, catalogo, errores), 'error': (errores or {}).get('general', ''),
        'favoritos': favoritos, 'catalogo': catalogo or []}, status=estado)


def _respuesta_cambio(request, c, draft):
    """Cierra el panel y refresca resúmenes y revisión (cambios fuera de banda de HTMX)."""
    return render(request, 'med/consulta/_cambio.html', {
        'c': c, 'resumenes': _resumenes(draft), 'estado_editor': _estado(c, solo_soap(consulta_a_dict(c, adendas=False))),
        'hora': timezone.localtime(c.updated_at)})


@vista_med('medico', metodos=('GET', 'POST'))
def captura(request, consulta, tipo, item=None):
    if tipo not in TIPOS_CAPTURA:
        raise Http404
    c = _para_editar(request, consulta)
    draft = ConsultationDraft(consulta_a_dict(c))
    identificador, valores, pendiente = draft.initial(tipo, item)
    if request.method == 'GET':
        if tipo == 'medication' and request.GET.get('de') and not pendiente:
            plantilla = next((f for f in borradores.catalogo(request.actor) if f['id'] == request.GET['de']), None)
            if plantilla:
                valores = {'name': plantilla['name'], 'ingredient': plantilla['ingredient'],
                           'presentation': plantilla['presentation'], 'strength': plantilla['strength']}
        return _panel(request, c, draft, tipo, identificador, valores, pendiente)
    identificador = item or request.POST.get('item') or identificador
    accion = request.POST.get('accion', 'aplicar')
    existente = next((r for r in draft.data.get(COLLECTIONS[tipo], []) if r['id'] == identificador), None)
    if accion == 'descartar':
        draft.discard(tipo, identificador)
        guardada = _guardar_borrador(request.actor, draft, c.revision)
        return _respuesta_cambio(request, guardada, ConsultationDraft(consulta_a_dict(guardada)))
    try:
        entrada = leer_captura(tipo, request.POST, existente)
    except DataError as error:
        if accion == 'pendiente':
            return HttpResponse(status=204)
        return _panel(request, c, draft, tipo, identificador, {}, False, {'general': str(error)}, 422)
    if accion == 'pendiente':
        draft.remember(tipo, identificador, entrada)
        guardada = _guardar_borrador(request.actor, draft, c.revision)
        respuesta = render(request, 'med/parciales/_guardado.html', {
            'hora': timezone.localtime(guardada.updated_at),
            'estado_editor': _estado(guardada, solo_soap(consulta_a_dict(guardada, adendas=False)))})
        respuesta['HX-Reswap'] = 'none'  # solo se actualiza el indicador; el formulario sigue abierto
        return respuesta
    extras = {k: entrada.pop(k) for k in ('al_catalogo', 'favorito') if k in entrada}
    try:
        draft.apply(tipo, identificador, entrada)
    except DataError as error:
        campo_error = 'name' if tipo in ('diagnosis', 'study', 'medication') and 'nombre' in str(error).lower() else 'general'
        return _panel(request, c, draft, tipo, identificador, {**entrada, **extras}, False, {campo_error: str(error), 'general': str(error)}, 422)
    guardada = _guardar_borrador(request.actor, draft, c.revision)
    if tipo == 'medication' and (extras.get('al_catalogo') or extras.get('favorito')):
        try:
            borradores.guardar_catalogo(request.actor, entrada, bool(extras.get('favorito')))
        except DataError:
            pass
    return _respuesta_cambio(request, guardada, ConsultationDraft(consulta_a_dict(guardada)))


@vista_med('medico', metodos=('POST',))
def quitar(request, consulta, tipo, item):
    if tipo not in TIPOS_CAPTURA:
        raise Http404
    c = _para_editar(request, consulta)
    draft = ConsultationDraft(consulta_a_dict(c))
    draft.remove(tipo, item)
    guardada = _guardar_borrador(request.actor, draft, c.revision)
    return _respuesta_cambio(request, guardada, ConsultationDraft(consulta_a_dict(guardada)))


# --- Revisar, finalizar y estados ------------------------------------------------------------------------------

@vista_med('medico')
def revisar(request, consulta):
    c = _para_editar(request, consulta)
    draft = ConsultationDraft(consulta_a_dict(c))
    pendientes = []
    for clave, texto in draft.problems():
        destino = reverse('med:consulta', args=[c.id])
        if clave in ('reason', 'plan'):
            destino += '#'+clave
        elif clave == 'diagnosis':
            destino += '?abrir=diagnosis'
        elif ':' in clave and clave.split(':')[0] in TIPOS_CAPTURA:
            destino += '?abrir='+clave.replace(':', '/')
        pendientes.append({'texto': texto, 'enlace': destino})
    return render(request, 'med/consulta/revisar.html', {'c': c, 'p': c.paciente, 'pendientes': pendientes,
                                                          'secciones': encounter_sections(draft.snapshot())})


@vista_med('medico', metodos=('POST',))
def finalizar(request, consulta):
    c = _para_editar(request, consulta)
    draft = ConsultationDraft(consulta_a_dict(c))
    try:
        _guardar_borrador_final(request.actor, draft, c.revision)
    except VersionConflict:
        messages.error(request, 'La consulta cambió en otra pestaña. Revísala antes de finalizar.')
        return redirect('med:consulta', consulta=c.id)
    except DataError as error:
        messages.error(request, str(error))
        return redirect('med:revisar', consulta=c.id)
    messages.success(request, 'Consulta finalizada.')
    return redirect('med:consulta', consulta=c.id)


def _guardar_borrador_final(actor, draft, revision):
    return consultas.guardar(actor, draft.snapshot(final=True), revision)


def _volver(request, c):
    return redirect('med:consulta', consulta=c.id)


@vista_med('admin', 'medico', metodos=('POST',))
def adenda(request, consulta):
    c = consultas.obtener(request.actor, consulta)
    try:
        consultas.agregar_adenda(request.actor, c.id, request.POST.get('motivo', ''), request.POST.get('contenido', ''))
        messages.success(request, 'Adenda agregada.')
    except PermisoDenegado:
        raise
    except DataError as error:
        messages.error(request, str(error))
    return _volver(request, c)


@vista_med('admin', 'medico', metodos=('POST',))
def anular(request, consulta):
    c = consultas.obtener(request.actor, consulta)
    try:
        consultas.anular(request.actor, c.id, request.POST.get('motivo', ''))
        messages.success(request, 'Consulta anulada. Queda en el expediente y no cuenta en las estadísticas.')
    except PermisoDenegado:
        raise
    except DataError as error:
        messages.error(request, str(error))
    return _volver(request, c)


@vista_med('admin', 'medico', metodos=('POST',))
def restaurar(request, consulta):
    c = consultas.obtener(request.actor, consulta)
    try:
        consultas.restaurar(request.actor, c.id, request.POST.get('motivo', ''))
        messages.success(request, 'Consulta restaurada.')
    except PermisoDenegado:
        raise
    except DataError as error:
        messages.error(request, str(error))
    return _volver(request, c)


@vista_med('medico', metodos=('POST',))
def papelera(request, consulta):
    c = consultas.obtener(request.actor, consulta)
    recuperar = request.POST.get('accion') == 'restaurar'
    try:
        consultas.papelera(request.actor, c.id, request.POST.get('motivo') or 'Retirado por el responsable', recuperar)
    except DataError as error:
        messages.error(request, str(error))
        return _volver(request, c)
    messages.success(request, 'Borrador recuperado.' if recuperar else 'Borrador retirado a la papelera.')
    return redirect('med:expediente', paciente=c.paciente_id)
