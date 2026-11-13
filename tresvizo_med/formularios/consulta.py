"""Consulta SOAP: encabezado, campos de texto y capturas laterales (signos vitales, medicamento, estudio, diagnóstico)."""
from django.utils import timezone

from ..dominio.clinical_models import MED_FIELDS, VITALS, local_date
from ..dominio.consultation_state import attention_time
from ..dominio.errores import DataError
from .campos import cadena, campo
from .paciente import OPCIONES_MED, TIPOS_MED

TIPOS_CONSULTA = ['General', 'Control', 'Urgencia', 'Primera vez']
ESTADOS_ESTUDIO = ['Solicitado', 'Pendiente', 'Recibido']
CONTEXTO_GLUCOSA = ['No especificado', 'Ayuno', 'Posprandial', 'Aleatoria']
TEXTOS = ('reason', 'subjective', 'objective', 'assessment_notes', 'plan')
CAMPOS_SOAP = (*TEXTOS, 'type', 'attended_at')
ROTULOS_TEXTO = {'reason': 'Motivo de consulta', 'subjective': 'Síntomas y evolución', 'objective': 'Exploración física',
                 'assessment_notes': 'Notas de valoración', 'plan': 'Indicaciones y plan'}
TIPOS_CAPTURA = {'vitals': 'Signos vitales', 'medication': 'Medicamento', 'study': 'Estudio', 'diagnosis': 'Diagnóstico'}


def solo_soap(d):
    """Subconjunto de campos que se fusionan a tres vías cuando hay dos pestañas."""
    return {k: d.get(k, '') for k in CAMPOS_SOAP}


def leer_soap(post, atendida):
    """Campos de texto y encabezado enviados por el formulario; ``atendida`` es el ``attended_at`` guardado."""
    valores = {k: str(post.get(k, '')).strip() if k not in ('subjective', 'objective', 'assessment_notes', 'plan', 'reason')
               else str(post.get(k, '')).replace('\r\n', '\n').strip() for k in TEXTOS}
    valores['type'] = cadena(post, 'type') or 'General'
    valores['attended_at'] = attention_time({'date': cadena(post, 'date'), 'time': cadena(post, 'time')}, atendida)
    return valores


def campos_encabezado(atendida, tipo, error=''):
    return [campo('date', 'Fecha de atención', atendida[:10], 'fecha', error=error),
            campo('time', 'Hora', atendida[11:16], 'hora'),
            campo('type', 'Tipo de consulta', tipo or 'General', 'seleccion', TIPOS_CONSULTA)]


def campos_texto(datos):
    return {k: campo(k, ROTULOS_TEXTO[k], datos.get(k, ''), 'area') for k in TEXTOS}


# --- Capturas ------------------------------------------------------------------------------------------------

def campos_captura(tipo, valores, catalogo=None, errores=None):
    """Campos del panel lateral para ``tipo`` con los ``valores`` actuales (de un registro o de una captura pendiente)."""
    errores = errores or {}
    v = valores or {}
    if tipo == 'diagnosis':
        return [campo('name', 'Diagnóstico', v.get('name', ''), error=errores.get('name', ''), requerido=True, autofoco=True)]
    if tipo == 'study':
        return [campo('name', 'Estudio', v.get('name', ''), error=errores.get('name', ''), requerido=True, autofoco=True),
                campo('status', 'Estado', v.get('status', 'Solicitado'), 'seleccion', ESTADOS_ESTUDIO),
                campo('notes', 'Indicaciones / resultado recibido', v.get('notes', ''), 'area')]
    if tipo == 'medication':
        lista = [r['name'] for r in (catalogo or [])]
        campos = []
        for clave, etiqueta in MED_FIELDS:
            valor = v.get(clave, {'status': 'Activo', 'frequency_kind': 'Cada N horas', 'duration_unit': 'días'}.get(clave, ''))
            tipo_campo = TIPOS_MED.get(clave, 'seleccion' if clave in OPCIONES_MED else 'texto')
            campos.append(campo(clave, etiqueta, valor, tipo_campo, OPCIONES_MED.get(clave), errores.get(clave, ''),
                                requerido=clave == 'name', lista=lista if clave == 'name' else None, autofoco=clave == 'name'))
        campos.append(campo('al_catalogo', 'Guardar en el catálogo de la clínica', bool(v.get('al_catalogo')), 'casilla'))
        campos.append(campo('favorito', 'Marcar como favorito mío', bool(v.get('favorito')), 'casilla'))
        return campos
    if tipo == 'vitals':
        valores_v = v.get('values', {})
        at = v.get('at') or timezone.localtime().isoformat(timespec='seconds')
        campos = [campo('date', 'Fecha', at[:10], 'fecha'), campo('time', 'Hora', at[11:16], 'hora')]
        for clave, (etiqueta, unidades) in VITALS.items():
            item = valores_v.get(clave, {})
            campos.append(campo('v_'+clave, etiqueta, item.get('value', ''), 'numero' if clave != 'pain' else 'numero',
                                error=errores.get(clave, ''), unidad_nombre='u_'+clave, unidades=list(unidades),
                                unidad=item.get('unit', unidades[0]), vital=True))
        campos.append(campo('context', 'Contexto de glucosa', v.get('context', 'No especificado'), 'seleccion', CONTEXTO_GLUCOSA))
        return campos
    raise KeyError(tipo)


def leer_captura(tipo, post, previo=None):
    """Valores de la captura a partir del formulario; ``previo`` es el registro que se edita (para conservar su hora)."""
    if tipo == 'diagnosis':
        return {'name': cadena(post, 'name')}
    if tipo == 'study':
        return {'name': cadena(post, 'name'), 'status': cadena(post, 'status') or 'Solicitado', 'notes': cadena(post, 'notes')}
    if tipo == 'medication':
        valores = {clave: cadena(post, clave) for clave, _ in MED_FIELDS}
        valores['al_catalogo'] = post.get('al_catalogo') == 'on'
        valores['favorito'] = post.get('favorito') == 'on'
        return valores
    if tipo == 'vitals':
        base = (previo or {}).get('at') or timezone.localtime().isoformat(timespec='seconds')
        try:
            local_date(cadena(post, 'date'))
            at = attention_time({'date': cadena(post, 'date'), 'time': cadena(post, 'time')}, base)
        except DataError:
            raise DataError('Revisa la fecha y la hora (HH:MM).') from None
        valores = {}
        for clave, (_, unidades) in VITALS.items():
            valor = cadena(post, 'v_'+clave)
            if valor:
                valores[clave] = {'value': valor, 'unit': cadena(post, 'u_'+clave) or unidades[0]}
        return {'at': at, 'context': cadena(post, 'context') or 'No especificado', 'values': valores}
    raise KeyError(tipo)
