"""Estadísticas: periodo, doctor, tipo, diagnóstico, nuevos y recurrentes, comparación y exportación con instantánea de filtros."""
from datetime import date
from urllib.parse import urlencode

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from tvplataforma import cuentas

from ..dominio.errores import DataError
from ..graficas import barras
from ..servicios import estadisticas, exportaciones
from .comun import TODOS, vista_med
from .pdf import estado_tarea

GRUPOS = ('Todos', 'Nuevos', 'Recurrentes')


def filtros_de(datos):
    hoy = timezone.localdate()
    doctor = datos.get('doctor', '')
    return {'inicio': datos.get('desde') or hoy.replace(day=1).isoformat(), 'fin': datos.get('hasta') or hoy.isoformat(),
            'doctor': '*' if doctor == '*' else int(doctor) if str(doctor).isdigit() else None, 'tipo': datos.get('tipo', '').strip(),
            'diagnostico': datos.get('diagnostico', '').strip(), 'grupo': datos.get('grupo', 'Todos')}


def _validar(f):
    for clave in ('inicio', 'fin'):
        try:
            date.fromisoformat(f[clave])
        except ValueError:
            raise DataError('Revisa las fechas del periodo.') from None
    if f['inicio'] > f['fin']:
        raise DataError('La fecha inicial debe ser anterior o igual a la final.')
    if f['grupo'] not in GRUPOS:
        raise DataError('Grupo de pacientes no admitido.')


def _quien(actor, doctor):
    if doctor == '*':
        return 'Toda la clínica'
    return cuentas.nombre(doctor if doctor is not None else actor.cuenta_id)


@vista_med(*TODOS)
def pagina(request):
    actor = request.actor
    filtros = filtros_de(request.GET)
    error, datos = '', None
    if 'desde' in request.GET or 'hasta' in request.GET:
        try:
            _validar(filtros)
            datos = estadisticas.calcular(actor, filtros['inicio'], filtros['fin'], filtros['doctor'], filtros['tipo'],
                                          filtros['diagnostico'], filtros['grupo'])
        except DataError as exc:
            if 'administrador' in str(exc):
                raise
            error = str(exc)
    instantanea = urlencode({'desde': filtros['inicio'], 'hasta': filtros['fin'], 'doctor': '' if filtros['doctor'] is None else filtros['doctor'],
                             'tipo': filtros['tipo'], 'diagnostico': filtros['diagnostico'], 'grupo': filtros['grupo']})
    contexto = {'filtros': filtros, 'error': error, 'datos': datos, 'instantanea': instantanea, 'grupos': GRUPOS,
                'medicos': cuentas.con_rol('med', 'medico') if actor.es_admin else [], 'quien': _quien(actor, filtros['doctor'])}
    if datos:
        contexto.update(grafica=barras(datos['activity']), tablas=[
            ('Diagnósticos más frecuentes', list(datos['diagnoses'].items())[:15]), ('Tipos de consulta', list(datos['types'].items())),
            ('Motivos más frecuentes', list(datos['reasons'].items())[:15]), ('Edades', list(datos['ages'].items())),
            ('Sexo', list(datos['sexes'].items()))])
    return render(request, 'med/estadisticas.html', contexto)


@vista_med(*TODOS)
def csv(request):
    filtros = filtros_de(request.GET)
    try:
        _validar(filtros)
    except DataError as exc:
        return HttpResponse(str(exc), status=422, content_type='text/plain; charset=utf-8')
    datos = estadisticas.calcular(request.actor, filtros['inicio'], filtros['fin'], filtros['doctor'], filtros['tipo'],
                                  filtros['diagnostico'], filtros['grupo'])
    cuerpo, nombre = exportaciones.estadisticas_csv(datos, _quien(request.actor, filtros['doctor']))
    respuesta = HttpResponse(cuerpo, content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return respuesta


@vista_med(*TODOS, metodos=('POST',))
def pdf(request):
    from .. import tareas
    filtros = filtros_de(request.POST)
    try:
        _validar(filtros)
    except DataError as exc:
        return HttpResponse(str(exc), status=422, content_type='text/plain; charset=utf-8')
    estadisticas.calcular(request.actor, filtros['inicio'], filtros['fin'], filtros['doctor'])  # permisos antes de encolar
    tarea = tareas.pdf_estadisticas.encolar(request.user.pk, filtros, usuario=request.user)
    return estado_tarea(request, tarea, 'PDF de estadísticas')
