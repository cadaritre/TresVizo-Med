"""Pacientes: búsqueda, alta con borrador privado, expediente, edición, archivo y evolución."""
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from ..dominio.clinical_models import VITALS, age_label
from ..dominio.errores import DataError
from ..formato import consulta_a_dict, paciente_a_dict
from ..formularios import paciente as form_paciente
from ..formularios.campos import fila_nueva
from ..graficas import serie_para
from ..models import BorradorAlta, Clinica, Consulta, Documento
from ..servicios import VersionConflict, borradores, consultas, documentos, pacientes, profesionales
from .comun import TODOS, es_htmx, redirigir, vista_med
from .documentos import contexto_gestor

MEDICIONES = [('blood_pressure', 'Presión arterial'), *[(k, v[0]) for k, v in VITALS.items() if k not in ('systolic', 'diastolic')], ('bmi', 'IMC')]
PERIODOS = [('30', '30 días'), ('90', '90 días'), ('365', 'Un año'), ('todo', 'Todo')]
PESTANAS = [('resumen', 'Resumen'), ('consultas', 'Consultas'), ('documentos', 'Documentos'), ('evolucion', 'Evolución')]


@vista_med(*TODOS)
def inicio(request):
    """Primera vez: quien administra la clínica la configura (nombre, logo, enlace y preferencias de documentos)."""
    if request.actor.es_admin and not Clinica.obtener().configurada:
        return redirect('med:identidad')
    return redirect('med:pacientes')


@vista_med(*TODOS)
def buscar(request):
    consulta = request.GET.get('q', '').strip()
    modo = request.GET.get('modo', 'Activos')
    try:
        pagina = int(request.GET.get('pagina', 0))
    except ValueError:
        pagina = 0
    try:
        filas, total, actual = pacientes.buscar(request.actor, consulta, modo, pagina)
    except DataError:
        raise Http404 from None
    for fila in filas:
        fila['edad'] = form_paciente.edad_texto(fila)
    consulta_qs = {'q': consulta, 'modo': modo}
    contexto = {'filas': filas, 'total': total, 'pagina': actual, 'q': consulta, 'modo': modo, 'modos': pacientes.MODOS,
                'hay_anterior': actual > 0, 'hay_siguiente': (actual+1)*100 < total,
                'anterior': urlencode({**consulta_qs, 'pagina': actual-1}), 'siguiente': urlencode({**consulta_qs, 'pagina': actual+1})}
    plantilla = 'med/pacientes/_resultados.html' if es_htmx(request) and request.headers.get('HX-Target') == 'resultados' \
        else 'med/pacientes/buscar.html'
    return render(request, plantilla, contexto)


@vista_med(*TODOS)
def en_curso(request):
    actor = request.actor
    altas = [{'borrador': b, 'nombre': b.contenido.get('name') or 'Sin nombre', 'edicion': bool(b.paciente)} for b in borradores.propios(actor)]
    consultas_en_curso = [] if not actor.es_medico else [
        {'consulta': c, 'paciente': c.paciente} for c in consultas.visibles(actor).filter(
            estado=Consulta.Estado.BORRADOR, doctor_id=actor.cuenta_id).select_related('paciente').order_by('-updated_at')]
    return render(request, 'med/pacientes/en_curso.html', {'altas': altas, 'consultas': consultas_en_curso})


# --- Alta y edición con borrador privado --------------------------------------------------------------------------

@vista_med(*TODOS)
def alta_nueva(request):
    """Abre un borrador nuevo y vacío."""
    borrador = borradores.guardar_borrador(request.actor, {})
    return redirect('med:alta', borrador=borrador.id)


@vista_med(*TODOS, metodos=('POST',))
def editar(request, paciente):
    """Edita un paciente: reutiliza el borrador abierto del mismo paciente o crea uno con sus datos."""
    persona = pacientes.obtener(request.actor, paciente)
    existente = borradores.propios(request.actor).filter(paciente=persona.id).first()
    if existente is None:
        existente = borradores.guardar_borrador(request.actor, paciente_a_dict(persona), paciente_id=persona.id,
                                                revision_origen=persona.revision)
    return redirect('med:alta', borrador=existente.id)


def _borrador_propio(request, borrador):
    try:
        return borradores.propios(request.actor).get(pk=borrador)
    except BorradorAlta.DoesNotExist:
        raise Http404 from None


def _contexto_alta(request, b, datos=None, errores=None, duplicados=None, conflicto=None):
    datos = b.contenido if datos is None else datos
    persona = None
    if b.paciente:
        persona = pacientes.Paciente.objects.filter(pk=b.paciente).first()
    return {**contexto_gestor(request, 'borrador', b.id), 'borrador': b, 'edicion': persona, 'campos': form_paciente.campos_personales(datos, errores),
            'colecciones': form_paciente.colecciones(datos), 'errores': errores or {}, 'duplicados': duplicados or [],
            'conflicto': conflicto, 'foto': datos.get('photo_attachment_id', ''), 'puede_atender': request.actor.es_medico}


@vista_med(*TODOS)
def alta(request, borrador):
    b = _borrador_propio(request, borrador)
    return render(request, 'med/pacientes/alta.html', _contexto_alta(request, b))


def _payload(request, b):
    base = {k: v for k, v in b.contenido.items() if k not in form_paciente.CLAVE_DATOS.values()}
    return form_paciente.payload_desde_post(request.POST, base)


@vista_med(*TODOS, metodos=('POST',))
def alta_guardar(request, borrador):
    """Autoguardado del borrador privado (HTMX). Responde el indicador «Guardado»."""
    b = _borrador_propio(request, borrador)
    payload = _payload(request, b)
    if payload != b.contenido:
        b = borradores.guardar_borrador(request.actor, payload, b.id, b.paciente, b.revision_origen)
    return render(request, 'med/parciales/_guardado.html', {'hora': timezone.localtime(b.updated_at)})


@vista_med(*TODOS, metodos=('POST',))
def alta_registrar(request, borrador):
    b = _borrador_propio(request, borrador)
    payload = _payload(request, b)
    b = borradores.guardar_borrador(request.actor, payload, b.id, b.paciente, b.revision_origen)
    errores = form_paciente.validar(payload)
    if errores:
        return render(request, 'med/pacientes/alta.html', _contexto_alta(request, b, payload, errores), status=422)
    confirmado = request.POST.get('confirmar_duplicado') == '1'
    if not confirmado:
        duplicados = pacientes.posibles_duplicados(payload, excluir=b.paciente)
        if duplicados:
            return render(request, 'med/pacientes/alta.html', _contexto_alta(request, b, payload, duplicados=duplicados), status=409)
    completo = {**payload, 'photo_attachment_id': payload.get('photo_attachment_id', '')}
    if b.paciente:
        actual = pacientes.obtener(request.actor, b.paciente)
        completo = {**paciente_a_dict(actual), **completo}
    try:
        persona = borradores.registrar(request.actor, b.id, completo)
    except VersionConflict as error:
        return render(request, 'med/pacientes/alta.html', _contexto_alta(request, b, payload, conflicto=error.current), status=409)
    except DataError as error:
        return render(request, 'med/pacientes/alta.html', _contexto_alta(request, b, payload, {'general': str(error)}), status=422)
    if request.POST.get('comenzar') == '1' and request.actor.es_medico:
        consulta, _ = consultas.iniciar(request.actor, persona.id)
        return redirect('med:consulta', consulta=consulta.id)
    messages.success(request, f'Paciente {persona.nombre} guardado ({persona.folio}).')
    return redirect('med:expediente', paciente=persona.id)


@vista_med(*TODOS, metodos=('POST',))
def alta_descartar(request, borrador):
    b = _borrador_propio(request, borrador)
    destino = reverse('med:expediente', args=[b.paciente]) if b.paciente else reverse('med:pacientes')
    borradores.descartar(request.actor, b.id)
    messages.info(request, 'Borrador descartado.')
    return redirect(destino)


@vista_med(*TODOS)
def fila(request, coleccion):
    """Una fila en blanco para «Agregar» (HTMX)."""
    try:
        datos = form_paciente.fila_en_blanco(coleccion)
    except KeyError:
        raise Http404 from None
    return render(request, 'med/parciales/_fila.html', {'fila': datos, 'quitar': True})


# --- Expediente -------------------------------------------------------------------------------------------------

def _contexto_expediente(request, persona):
    datos = paciente_a_dict(persona)
    alergias = [r for r in datos.get('allergy_records', []) if r.get('substance')]
    return {'p': persona, 'd': datos, 'edad': form_paciente.edad_texto(datos), 'alergias': alergias,
            'estado_alergias': datos.get('allergy_status', 'No interrogado'), 'pestanas': PESTANAS}


@vista_med(*TODOS)
def expediente(request, paciente):
    persona = pacientes.obtener(request.actor, paciente)
    pestana = request.GET.get('pestana', 'resumen')
    if pestana not in dict(PESTANAS):
        pestana = 'resumen'
    from tvplataforma import hosts
    from tvplataforma.modulos import modulo
    contexto = {**_contexto_expediente(request, persona), 'pestana': pestana,
                'enlace': hosts.url_de(modulo('med'), reverse('med:expediente', args=[persona.id]))}
    deshacer = request.session.pop('med_deshacer', None)
    if deshacer and Consulta.objects.filter(pk=deshacer, paciente=persona, estado=Consulta.Estado.BORRADOR, archivada=True,
                                            doctor_id=request.actor.cuenta_id).exists():
        contexto['deshacer_consulta'] = deshacer
    if pestana == 'resumen':
        d = contexto['d']
        contexto['historias'] = [(t, d.get('histories', {}).get(k, {})) for k, t in form_paciente.HISTORIAS
                                 if d.get('histories', {}).get(k, {}).get('notes') or
                                 d.get('histories', {}).get(k, {}).get('status') not in (None, '', 'No registrado')]
        recientes = consultas.visibles(request.actor).filter(paciente=persona, archivada=False).exclude(estado=Consulta.Estado.BORRADOR).order_by('-atendida_en')[:1]
        contexto['ultima'] = {'c': recientes[0], 'doctor': profesionales.nombre(recientes[0].doctor_id)} if recientes else None
        contexto['heredado'] = {k: v for k, v in d.get('legacy', {}).items() if v}
    elif pestana == 'consultas':
        filas = list(consultas.visibles(request.actor).filter(paciente=persona).order_by('-atendida_en'))
        nombres = profesionales.nombres({c.doctor_id for c in filas})
        borrador = next((c for c in filas if c.estado == Consulta.Estado.BORRADOR and c.doctor_id == request.actor.cuenta_id), None)
        contexto.update(consultas=[{'c': c, 'doctor': nombres.get(c.doctor_id, '')} for c in filas], borrador=borrador)
    elif pestana == 'documentos':
        contexto.update(contexto_gestor(request, 'paciente', persona.id))
    else:
        contexto.update(_contexto_evolucion(request, persona))
    return render(request, 'med/pacientes/expediente.html', contexto)


@vista_med(*TODOS, metodos=('POST',))
def archivar(request, paciente):
    restaurar = request.POST.get('accion') == 'restaurar'
    persona = pacientes.archivar(request.actor, paciente, request.POST.get('motivo', ''), restaurar)
    messages.success(request, 'Paciente restaurado.' if restaurar else 'Paciente archivado.')
    return redirect('med:expediente', paciente=persona.id)


@vista_med('medico', metodos=('POST',))
def atender(request, paciente):
    consulta, _ = consultas.iniciar(request.actor, paciente)
    return redirect('med:consulta', consulta=consulta.id)


# --- Evolución --------------------------------------------------------------------------------------------------

def _contexto_evolucion(request, persona):
    medicion = request.GET.get('medicion', 'blood_pressure')
    periodo = request.GET.get('periodo', '365')
    if medicion not in dict(MEDICIONES):
        medicion = 'blood_pressure'
    if periodo not in dict(PERIODOS):
        periodo = '365'
    claves = ['systolic', 'diastolic'] if medicion == 'blood_pressure' else [medicion]
    desde = '' if periodo == 'todo' else (timezone.localdate()-timedelta(days=int(periodo))).isoformat()
    series = []
    for clave in claves:
        finales = [p for p in borradores.evolucion(request.actor, persona.id, clave) if p['at'][:10] >= desde]
        provisionales = [p for p in borradores.puntos_provisionales(request.actor, persona.id, clave) if p['at'][:10] >= desde]
        etiqueta = VITALS[clave][0] if clave in VITALS else 'IMC'
        series.append({'clave': clave, 'etiqueta': etiqueta, 'finales': finales, 'provisionales': provisionales})
    nombres = profesionales.nombres({p['doctor_id'] for s in series for p in s['finales']})
    tabla = sorted(({'at': p['at'], 'medicion': s['etiqueta'], 'valor': p['value'], 'unidad': p['unit'], 'contexto': p['context'],
                     'estado': 'Consulta finalizada', 'doctor': nombres.get(p['doctor_id'], '')}
                    for s in series for p in s['finales']), key=lambda f: f['at'], reverse=True)
    tabla += [{'at': p['at'], 'medicion': s['etiqueta'], 'valor': p['value'], 'unidad': p['unit'], 'contexto': p['context'],
               'estado': 'Borrador', 'doctor': ''} for s in series for p in s['provisionales']]
    tabla.sort(key=lambda f: f['at'], reverse=True)
    return {'mediciones': MEDICIONES, 'medicion': medicion, 'periodos': PERIODOS, 'periodo': periodo,
            'grafica': serie_para(series), 'tabla_evolucion': tabla,
            'leyenda_series': [{'n': i, 'etiqueta': s['etiqueta']} for i, s in enumerate(series, 1)] if len(series) > 1 else []}


@vista_med(*TODOS)
def evolucion(request, paciente):
    """Fragmento de la pestaña Evolución (HTMX) o la página completa."""
    persona = pacientes.obtener(request.actor, paciente)
    contexto = {**_contexto_expediente(request, persona), 'pestana': 'evolucion', **_contexto_evolucion(request, persona)}
    if es_htmx(request):
        return render(request, 'med/pacientes/_evolucion.html', contexto)
    return render(request, 'med/pacientes/expediente.html', contexto)
