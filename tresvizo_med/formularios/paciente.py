"""Alta y edición de paciente: campos, colecciones y paso entre el formulario y el diccionario del escritorio."""
import re
from datetime import date

from ..dominio.clinical_models import MED_FIELDS, age_label, validate_medications
from ..dominio.errores import DataError
from .campos import cadena, campo, campos_de_fila, leer_coleccion

SEXOS = ['Masculino', 'Femenino']
ESTADOS_ALERGIA = ['No interrogado', 'Desconocido', 'Sin alergias conocidas', 'Alergias registradas']
GRAVEDAD = ['No documentada', 'Leve', 'Moderada', 'Grave']
HISTORIAS = [('personal', 'Antecedentes personales'), ('family', 'Antecedentes familiares'), ('surgical', 'Cirugías'),
             ('hospital', 'Hospitalizaciones'), ('other', 'Otros antecedentes')]
ESTADOS_HISTORIA = ['No registrado', 'Desconocido', 'Sin antecedentes declarados', 'Antecedentes registrados']
OPCIONES_MED = {'dose_unit': ['mg', 'g', 'mcg', 'mL', 'tableta', 'cápsula', 'gota', 'UI', 'inhalación'],
                'route': ['Oral', 'Tópica', 'Inhalada', 'Intravenosa', 'Intramuscular', 'Subcutánea', 'Oftálmica', 'Ótica'],
                'frequency_kind': ['Cada N horas', 'Veces al día', 'Horarios', 'Pauta personalizada', 'Según necesidad'],
                'duration_unit': ['días', 'semanas', 'meses'], 'status': ['Activo', 'Suspendido', 'Completado']}
TIPOS_MED = {'start': 'fecha', 'end': 'fecha', 'instructions': 'area', 'dose': 'numero', 'duration': 'numero', 'quantity': 'numero'}

ESQUEMAS = {
    'phones': [('number', 'Número, prefijo o extensión', 'telefono', None),
               ('type', 'Tipo', 'seleccion', ['Principal', 'Móvil', 'Casa', 'Trabajo', 'Otro'])],
    'allergies': [('substance', 'Sustancia', 'texto', None), ('reaction', 'Reacción documentada', 'texto', None),
                  ('severity', 'Gravedad documentada', 'seleccion', GRAVEDAD), ('date', 'Fecha conocida', 'fecha', None),
                  ('notes', 'Observaciones', 'area', None)],
    'problems': [('name', 'Problema', 'texto', None), ('status', 'Estado', 'seleccion', ['Activo', 'Resuelto', 'En estudio']),
                 ('date', 'Fecha conocida', 'fecha', None), ('notes', 'Observaciones', 'area', None)],
    'medications': [(clave, etiqueta, TIPOS_MED.get(clave, 'seleccion' if clave in OPCIONES_MED else 'texto'),
                     OPCIONES_MED.get(clave)) for clave, etiqueta in MED_FIELDS],
}
# Colección → clave en el diccionario del paciente
CLAVE_DATOS = {'phones': 'phones', 'allergies': 'allergy_records', 'problems': 'problem_records',
               'medications': 'medication_records'}
ROTULOS = {'phones': 'Teléfonos', 'allergies': 'Alergias', 'problems': 'Problemas activos', 'medications': 'Medicamentos habituales'}
VALORES_FIJOS = {'phones': {'type': 'Principal'}, 'allergies': {'severity': 'No documentada'}, 'problems': {'status': 'Activo'},
                 'medications': {'status': 'Activo', 'frequency_kind': 'Cada N horas', 'duration_unit': 'días'}}


def payload_desde_post(post, base=None):
    """Diccionario con el esquema del paciente a partir del formulario. No valida: sirve para el borrador."""
    datos = dict(base or {})
    for clave in ('name', 'preferred_name', 'sex', 'email', 'address', 'administrative', 'clinical_notes', 'allergy_status'):
        datos[clave] = cadena(post, clave)
    desconocida = post.get('birth_unknown') == 'on'
    datos['birth_unknown'] = desconocida
    datos['birth_date'] = '' if desconocida else cadena(post, 'birth_date')
    datos['approx_age'] = {'value': cadena(post, 'approx_value'), 'unit': cadena(post, 'approx_unit') or 'años',
                           'at': cadena(post, 'approx_at')} if desconocida and cadena(post, 'approx_value') else {}
    datos['emergency_contact'] = {k: cadena(post, 'emergency_'+k) for k in ('name', 'relationship', 'phone', 'guardian', 'guardian_relation')}
    for coleccion, clave in CLAVE_DATOS.items():
        claves = [c[0] for c in ESQUEMAS[coleccion]]
        datos[clave] = leer_coleccion(post, coleccion, claves)
    datos['histories'] = {k: {'status': cadena(post, f'hist_{k}_status') or 'No registrado', 'notes': cadena(post, f'hist_{k}_notes')}
                          for k, _ in HISTORIAS}
    datos['phone'] = next((p['number'] for p in datos['phones'] if p['number']), '')
    return datos


def validar(datos, confirmar_duplicado=False):
    """Errores por campo para registrar el paciente; vacío si todo está bien."""
    errores = {}
    if not datos.get('name', '').strip():
        errores['name'] = 'El nombre del paciente es obligatorio.'
    if datos.get('birth_date'):
        try:
            if date.fromisoformat(datos['birth_date']) > date.today():
                raise ValueError()
        except ValueError:
            errores['birth_date'] = 'Usa una fecha válida que no sea futura.'
    if datos.get('email') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', datos['email']):
        errores['email'] = 'Revisa el formato del correo electrónico.'
    if datos.get('allergy_records') and datos.get('allergy_status') == 'Sin alergias conocidas':
        errores['allergy_status'] = 'Hay alergias registradas: cambia el estado o quítalas.'
    try:
        validate_medications(datos.get('medication_records', []))
    except DataError as error:
        errores['medications'] = str(error)
    return errores


def campos_personales(datos, errores=None):
    errores = errores or {}
    d = datos or {}
    aprox = d.get('approx_age') or {}
    desconocida = d.get('birth_unknown', bool(aprox.get('value')))

    def c(nombre, etiqueta, tipo='texto', **extra):
        return campo(nombre, etiqueta, d.get(nombre, ''), tipo, error=errores.get(nombre, ''), **extra)
    return {
        'nombre': c('name', 'Nombre completo', requerido=True), 'preferido': c('preferred_name', 'Nombre preferido'),
        'nacimiento': c('birth_date', 'Fecha de nacimiento', 'fecha'),
        'sexo': c('sex', 'Sexo', 'seleccion', opciones=SEXOS),
        'desconocida': campo('birth_unknown', 'Fecha de nacimiento desconocida', bool(desconocida), 'casilla'),
        'aprox_valor': campo('approx_value', 'Edad aproximada', aprox.get('value', ''), 'numero'),
        'aprox_unidad': campo('approx_unit', 'Unidad de edad', aprox.get('unit', 'años'), 'seleccion', ['años', 'meses', 'días']),
        'aprox_fecha': campo('approx_at', 'Fecha de referencia', aprox.get('at') or date.today().isoformat(), 'fecha'),
        'estado_alergias': c('allergy_status', 'Estado de alergias', 'seleccion', opciones=ESTADOS_ALERGIA),
        'correo': c('email', 'Correo electrónico', 'correo'), 'direccion': c('address', 'Dirección', 'area'),
        'administrativas': c('administrative', 'Notas administrativas · visibles para doctores autorizados', 'area'),
        'clinicas': c('clinical_notes', 'Notas clínicas', 'area'),
        'emergencia': [campo('emergency_'+k, etiqueta, (d.get('emergency_contact') or {}).get(k, ''), 'texto')
                       for k, etiqueta in (('name', 'Contacto de emergencia'), ('relationship', 'Relación declarada'),
                                           ('phone', 'Teléfono'), ('guardian', 'Tutor o responsable (opcional)'),
                                           ('guardian_relation', 'Relación del responsable'))],
        'historias': [{'clave': k, 'titulo': t,
                       'estado': campo(f'hist_{k}_status', 'Estado de la información',
                                       (d.get('histories') or {}).get(k, {}).get('status', 'No registrado'), 'seleccion', ESTADOS_HISTORIA),
                       'notas': campo(f'hist_{k}_notes', 'Descripción', (d.get('histories') or {}).get(k, {}).get('notes', ''), 'area')}
                      for k, t in HISTORIAS],
        'edad': edad_texto(d),
    }


def edad_texto(datos):
    try:
        return age_label({k: v for k, v in datos.items() if k in ('birth_date', 'approx_age')} if datos else {})
    except ValueError:
        return 'Fecha pendiente de completar'


def colecciones(datos):
    """Para dibujar: ``[{'nombre','rotulo','esquema','filas':[campos_de_fila…]}]``."""
    resultado = []
    for nombre in ('phones', 'allergies', 'problems', 'medications'):
        filas = (datos or {}).get(CLAVE_DATOS[nombre]) or []
        resultado.append({'nombre': nombre, 'rotulo': ROTULOS[nombre],
                          'filas': [campos_de_fila(nombre, ESQUEMAS[nombre], f) for f in filas]})
    return resultado


def fila_en_blanco(nombre):
    if nombre not in ESQUEMAS:
        raise KeyError(nombre)
    return campos_de_fila(nombre, ESQUEMAS[nombre], VALORES_FIJOS.get(nombre, {}))
