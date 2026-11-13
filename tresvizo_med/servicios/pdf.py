"""Contenido de los PDF de receta, resumen de consulta y estadísticas (se dibujan con ``dominio.documents.create_pdf``)."""
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from tvplataforma import cuentas

from ..dominio.clinical_models import encounter_sections, medication_text
from ..dominio.documents import create_pdf
from ..dominio.errores import DataError
from ..dominio.texto import normalized
from ..formato import consulta_a_dict, paciente_a_dict
from ..models import Clinica, Profesional
from . import consultas, estadisticas

HORAS_VIGENCIA = 24
ROTULOS_ESTADO = {'Borrador': 'BORRADOR · ', 'Anulada': 'ANULADA · ', 'Finalizada': ''}


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
    perfil = Profesional.objects.filter(cuenta_id=cuenta_id).first()
    nombre = (perfil.nombre_visible if perfil and perfil.nombre_visible else '') or cuentas.nombre(cuenta_id)
    extras = []
    if perfil and perfil.cedula:
        extras.append('Cédula '+perfil.cedula)
    if perfil and perfil.especialidad:
        extras.append(perfil.especialidad)
    return ' · '.join([nombre, *extras])


def limpiar_vencidos(cuenta_id):
    limite = timezone.now()-timedelta(hours=HORAS_VIGENCIA)
    carpeta = carpeta_pdf(cuenta_id)
    if carpeta.is_dir():
        for ruta in carpeta.glob('*.pdf'):
            if ruta.stat().st_mtime < limite.timestamp():
                ruta.unlink(missing_ok=True)


def _secciones_consulta(actor, consulta, tipo):
    d = consulta_a_dict(consulta)
    autores = cuentas.nombres({d['doctor_id'], *[a['actor'] for a in d['addenda']]})
    prefijo = ROTULOS_ESTADO.get(consulta.estado, '')
    nota = [('Estado', 'Consulta todavía sin finalizar.')] if consulta.estado == 'Borrador' else \
        [('Estado', 'Consulta anulada: no es válida.')] if consulta.estado == 'Anulada' else []
    if tipo == 'receta':
        if not d.get('prescriptions'):
            raise DataError('La consulta no tiene medicamentos para la receta.')
        medicamentos = '\n\n'.join(medication_text(m)+('\n'+m['instructions'] if m.get('instructions') else '') for m in d['prescriptions'])
        secciones = [*nota, ('Fecha de atención', encounter_sections(d)[0][1]), ('Diagnóstico', d.get('assessment', '')),
                     ('Medicamentos', medicamentos), ('Indicaciones', d.get('plan', ''))]
        return prefijo+'Receta e indicaciones', secciones, d, autores
    secciones = [*nota, *[(t, c) for t, c in encounter_sections(d, autores) if c]]
    return prefijo+'Resumen de consulta', secciones, d, autores


def crear_pdf_consulta(actor, consulta_id, tipo, progreso=lambda f, m='': None):
    """Genera el PDF de una consulta visible para ``actor`` y devuelve ``(identificador, ruta)``."""
    if tipo not in ('receta', 'resumen'):
        raise DataError('Tipo de PDF no admitido.')
    consulta = consultas.obtener(actor, consulta_id)
    progreso(.2, 'Reuniendo los datos')
    titulo, secciones, d, autores = _secciones_consulta(actor, consulta, tipo)
    paciente = consulta.paciente
    limpiar_vencidos(actor.cuenta_id)
    identificador = uuid.uuid4()
    ruta = carpeta_pdf(actor.cuenta_id)/f'{identificador}.pdf'
    ruta.parent.mkdir(parents=True, exist_ok=True)
    progreso(.5, 'Armando el documento')
    create_pdf(ruta, identidad(), titulo, secciones, texto_doctor(consulta.doctor_id), f'{paciente.nombre} · {paciente.folio}')
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
