"""Contenido de los PDF de receta, resumen de consulta y estadísticas (se dibujan con ``dominio.documents.create_pdf``)."""
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from ..dominio.clinical_models import age_label, display_date
from ..dominio.documents import create_pdf
from ..dominio.documentos_medicos import crear_receta, crear_resumen
from ..dominio.errores import DataError
from ..dominio.presentacion import adendas, seccion_nota
from ..formato import consulta_a_dict, paciente_a_dict
from ..models import Clinica
from . import consultas, estadisticas, profesionales

HORAS_VIGENCIA = 24


def carpeta_pdf(cuenta_id):
    return Path(settings.TV_MED_ARCHIVOS)/'pdf'/str(cuenta_id)


def identidad():
    """Identidad de impresión de la clínica con la ruta absoluta de su logo (la apariencia de cada doctor nunca cambia
    los documentos)."""
    clinica = Clinica.obtener()
    datos = dict(clinica.valores())
    logo = Path(settings.TV_MED_ARCHIVOS)/clinica.logo_ruta if clinica.logo_ruta else None
    datos['clinic_logo'] = str(logo) if logo and logo.is_file() else ''
    return datos


def texto_doctor(cuenta_id):
    """Línea de responsable de los PDF genéricos (estadísticas): nombre, cédula y especialidad."""
    datos = profesionales.firma(cuenta_id)
    extras = [x for x in ('Cédula '+datos['cedula'] if datos['cedula'] else '', datos['specialty']) if x]
    return ' · '.join([datos['name'], *extras])


def limpiar_vencidos(cuenta_id):
    limite = timezone.now()-timedelta(hours=HORAS_VIGENCIA)
    carpeta = carpeta_pdf(cuenta_id)
    if carpeta.is_dir():
        for ruta in carpeta.glob('*.pdf'):
            if ruta.stat().st_mtime < limite.timestamp():
                ruta.unlink(missing_ok=True)


def _datos_documento(consulta, d, firmante):
    paciente = consulta.paciente
    datos_paciente = paciente.datos
    alergias = ', '.join(r['substance'] for r in datos_paciente.get('allergy_records', []) if r.get('substance'))
    if not alergias and datos_paciente.get('allergy_status') == 'Sin alergias conocidas':
        alergias = 'Sin alergias conocidas'
    alergias = alergias or 'No registradas'
    atendida = timezone.localtime(consulta.atendida_en)
    return {'estado': consulta.estado, 'doctor_id': consulta.doctor_id, 'medico': firmante,
            'paciente': {'name': paciente.nombre, 'folio': paciente.folio, 'sex': paciente.sexo,
                         'age': edad_en_pdf(paciente_a_dict(paciente), atendida.date()), 'allergies': alergias},
            'fecha': atendida.strftime('%d/%m/%Y'), 'fecha_hora': atendida.strftime('%d/%m/%Y %H:%M')}


def edad_en_pdf(datos, al):
    """Edad en la fecha de la consulta; la aproximada se marca con «≈»."""
    if datos.get('birth_date'):
        return age_label(datos, al)
    aproximada = datos.get('approx_age', {})
    if aproximada.get('value') not in ('', None):
        return f"≈ {aproximada['value']} {aproximada.get('unit', 'años')}"
    return ''


def _seguimiento(d):
    seguimiento = d.get('followup', {})
    if not seguimiento.get('date'):
        return ''
    return ' · '.join(x for x in (display_date(seguimiento['date']), seguimiento.get('reason', '')) if x)


def crear_pdf_consulta(actor, consulta_id, tipo, progreso=lambda f, m='': None):
    """Genera el PDF de una consulta visible para ``actor`` y devuelve ``(identificador, ruta)``."""
    if tipo not in ('receta', 'resumen'):
        raise DataError('Tipo de PDF no admitido.')
    consulta = consultas.obtener(actor, consulta_id)
    progreso(.2, 'Reuniendo los datos')
    d = consulta_a_dict(consulta)
    if tipo == 'receta' and not d.get('prescriptions'):
        raise DataError('La consulta no tiene medicamentos para la receta.')
    autores = profesionales.nombres({d['doctor_id'], *[a['actor'] for a in d['addenda']]})
    datos = _datos_documento(consulta, d, profesionales.firma(consulta.doctor_id))
    limpiar_vencidos(actor.cuenta_id)
    identificador = uuid.uuid4()
    ruta = carpeta_pdf(actor.cuenta_id)/f'{identificador}.pdf'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    progreso(.5, 'Armando el documento')
    if tipo == 'receta':
        crear_receta(ruta, identidad(), {**datos, 'diagnostico': d.get('assessment', ''), 'medicamentos': d['prescriptions'],
                                         'plan': d.get('plan', ''), 'seguimiento': _seguimiento(d), 'signos': d.get('vitals', [])})
    else:
        secciones = [(t, c) for t, c in seccion_nota(d) if t != 'Atención']
        crear_resumen(ruta, identidad(), {**datos, 'fecha': datos['fecha_hora'], 'secciones': secciones, 'signos': d.get('vitals', []),
                                          'medicamentos': d.get('prescriptions', []), 'adendas': adendas(d, autores)})
    return identificador, ruta


def secciones_estadisticas(datos):
    def tabla(diccionario, limite=15):
        return '\n'.join(f'{clave}: {valor}' for clave, valor in list(diccionario.items())[:limite]) or 'Sin datos'
    previo = f"{datos['previous']} consultas ({datos['previous_start']} a {datos['previous_end']})"
    variacion = 'sin periodo previo para comparar' if datos['variation'] is None else f"{datos['variation']:+.1f} %"
    filtros = datos['filters']
    return [
        ('Periodo', f"{datos['start']} a {datos['end']}"),
        ('Filtros', f"Tipo: {filtros['type'] or 'todos'} · Diagnóstico: {filtros['diagnosis'] or 'todos'} · Pacientes: {filtros['patient_group']}"),
        ('Resumen', f"Consultas: {datos['consultations']}\nPacientes: {datos['patients']} ({datos['new']} nuevos, {datos['recurrent']} recurrentes)\n"
                    f"Días con actividad: {datos['days']} · Promedio por día: {datos['average']:.1f}\nBorradores: {datos['drafts']} · Sin diagnóstico: {datos['no_diagnosis']}"),
        ('Comparación con el periodo previo', f"{previo}\nDiferencia: {datos['difference']:+d} · Variación: {variacion}"),
        ('Diagnósticos más frecuentes', tabla(datos['diagnoses'])), ('Tipos de consulta', tabla(datos['types'])),
        ('Motivos más frecuentes', tabla(datos['reasons'])), ('Edades', tabla(datos['ages'])), ('Sexo', tabla(datos['sexes'])),
    ]


def crear_pdf_estadisticas(actor, filtros, progreso=lambda f, m='': None):
    progreso(.2, 'Calculando')
    datos = estadisticas.calcular(actor, filtros['inicio'], filtros['fin'], filtros.get('doctor'), filtros.get('tipo', ''),
                                  filtros.get('diagnostico', ''), filtros.get('grupo', 'Todos'))
    limpiar_vencidos(actor.cuenta_id)
    identificador = uuid.uuid4()
    ruta = carpeta_pdf(actor.cuenta_id)/f'{identificador}.pdf'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    progreso(.6, 'Armando el documento')
    quien = 'Toda la clínica' if datos['doctor'] == '*' else texto_doctor(datos['doctor'])
    create_pdf(ruta, identidad(), 'Estadísticas de consulta', secciones_estadisticas(datos), quien, '')
    return identificador, ruta
