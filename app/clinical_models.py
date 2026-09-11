"""Datos clínicos estructurados y presentación independiente de Tk."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from copy import deepcopy
import uuid
from app.storage import DataError

VITALS = {
    'systolic': ('Presión sistólica', ('mmHg',)),
    'diastolic': ('Presión diastólica', ('mmHg',)),
    'heart_rate': ('Frecuencia cardiaca', ('lpm',)),
    'respiratory_rate': ('Frecuencia respiratoria', ('rpm',)),
    'temperature': ('Temperatura', ('°C', '°F')),
    'oxygen': ('Saturación de oxígeno', ('%',)),
    'weight': ('Peso', ('kg', 'lb')),
    'height': ('Estatura', ('cm', 'm', 'in')),
    'glucose': ('Glucosa', ('mg/dL', 'mmol/L')),
    'pain': ('Dolor referido', ('0–10',)),
}
MED_FIELDS = [('name', 'Medicamento'), ('ingredient', 'Principio activo'),
              ('presentation', 'Presentación'), ('strength', 'Concentración'),
              ('dose', 'Dosis'), ('dose_unit', 'Unidad de dosis'), ('route', 'Vía'), ('status', 'Estado'),
              ('frequency_kind', 'Tipo de frecuencia'), ('frequency', 'Intervalo, veces, horarios o pauta'),
              ('duration', 'Duración'), ('duration_unit', 'Unidad de duración'),
              ('start', 'Inicio'), ('end', 'Fin'),
              ('quantity', 'Cantidad a dispensar'), ('quantity_unit', 'Unidad a dispensar'),
              ('instructions', 'Indicaciones adicionales')]

def numeric(value, label, minimum=None, maximum=None):
    try:
        result = Decimal(str(value).strip().replace(',', '.'))
        if not result.is_finite() or (minimum is not None and result < minimum) or (maximum is not None and result > maximum):
            raise InvalidOperation()
        return float(result)
    except (InvalidOperation, ValueError):
        raise DataError(f'{label}: escribe una cantidad válida con su unidad.')

def local_date(value):
    if not value:
        return ''
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise DataError('Fecha inválida. Usa día/mes/año.')

def display_date(value):
    if not value:
        return 'Sin fecha'
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime('%d/%m/%Y %H:%M') if 'T' in value or ' ' in value else dt.strftime('%d/%m/%Y')
    except ValueError:
        return value

def age_label(patient, at=None):
    if patient.get('birth_date'):
        birth, current = date.fromisoformat(patient['birth_date']), at or date.today()
        months = (current.year-birth.year)*12+current.month-birth.month-(current.day < birth.day)
        if months >= 24:
            return f'{months//12} años'
        if months >= 1:
            return f'{months} meses'
        return f'{(current-birth).days} días'
    approx = patient.get('approx_age', {})
    if approx.get('value') not in ('', None):
        return f"≈ {approx['value']} {approx.get('unit', 'años')} · al {display_date(approx.get('at', ''))}"
    return 'Edad no registrada'

def normalize_measurement(key, value, unit):
    value = numeric(value, VITALS[key][0])
    if unit not in VITALS[key][1]:
        raise DataError('Unidad de medición inválida.')
    if key in ('oxygen', 'pain') and not 0 <= value <= (100 if key == 'oxygen' else 10):
        raise DataError('El valor está fuera de la escala seleccionada.')
    if key != 'temperature' and value < 0:
        raise DataError('La medición no admite cantidades negativas.')
    if key in ('weight', 'height') and value <= 0:
        raise DataError('Peso y estatura deben ser mayores que cero.')
    if key == 'temperature' and unit == '°F':
        return (value-32)*5/9, '°C'
    if key == 'weight' and unit == 'lb':
        return value*0.45359237, 'kg'
    if key == 'height':
        return value*({'cm': 1, 'm': 100, 'in': 2.54}[unit]), 'cm'
    if key == 'glucose' and unit == 'mmol/L':
        return value*18.0182, 'mg/dL'
    return value, unit

def validate_vitals(groups):
    result = deepcopy(groups)
    for group in result:
        datetime.fromisoformat(group['at'])
        group.setdefault('id', str(uuid.uuid4()))
        for key, item in group.get('values', {}).items():
            if key not in VITALS:
                raise DataError('Medición desconocida.')
            val, unit = normalize_measurement(key, item['value'], item['unit'])
            item.update(normalized_value=val, normalized_unit=unit)
        values = group.get('values', {})
        group.pop('bmi', None)
        if 'weight' in values and 'height' in values:
            group['bmi'] = round(values['weight']['normalized_value']/(values['height']['normalized_value']/100)**2, 2)
    return result

def validate_medications(rows, final=False):
    result = deepcopy(rows)
    for row in result:
        row.setdefault('id', str(uuid.uuid4()))
        if not row.get('name', '').strip():
            raise DataError('Escribe el nombre del medicamento.')
        for key in ('dose', 'duration', 'quantity'):
            if row.get(key):
                numeric(row[key], key, minimum=0)
        if row.get('frequency_kind') in ('Cada N horas', 'Veces al día') and row.get('frequency'):
            if numeric(row['frequency'], 'Frecuencia', minimum=0) == 0:
                raise DataError('La frecuencia debe ser mayor que cero.')
        for key in ('start', 'end'):
            if row.get(key):
                row[key] = local_date(row[key])
        if row.get('start') and row.get('end') and row['end'] < row['start']:
            raise DataError('El fin del tratamiento precede a su inicio.')
        if final and (row.get('needs_review') or not all(row.get(k) for k in ('dose', 'dose_unit', 'route', 'frequency'))):
            raise DataError(f"Revisa dosis, unidad, vía y frecuencia de {row['name']}.")
    return result

def medication_text(row):
    parts = [row.get('name', ''), ' '.join(filter(None, [row.get('presentation'), row.get('strength')]))]
    parts += [f"{row.get('dose', '')} {row.get('dose_unit', '')}".strip(), row.get('route', '')]
    freq = row.get('frequency', '')
    kind = row.get('frequency_kind', '')
    parts += [('Cada '+freq+' horas') if kind == 'Cada N horas' else (freq+' veces al día') if kind == 'Veces al día' else freq]
    parts += [f"{row.get('duration', '')} {row.get('duration_unit', '')}".strip() if row.get('duration') else '']
    if row.get('as_needed'):
        parts.append('Según necesidad: '+row.get('as_needed_reason', ''))
    return ' · '.join(p for p in parts if p)

def encounter_sections(record, authors=None):
    sections = [('Atención', display_date(record.get('attended_at', ''))),
                ('Motivo', record.get('reason', '')), ('Síntomas y evolución', record.get('subjective', '')),
                ('Exploración física', record.get('objective', ''))]
    measures = []
    for group in record.get('vitals', []):
        measures.append(display_date(group['at']))
        measures.extend(f"{VITALS[k][0]}: {v['value']} {v['unit']}" for k, v in group['values'].items())
        if group.get('bmi'):
            measures.append(f"IMC: {group['bmi']} kg/m²")
    sections += [('Signos vitales', '\n'.join(measures)), ('Diagnósticos', record.get('assessment', '')),
                 ('Valoración clínica', record.get('assessment_notes', '')),
                 ('Plan e indicaciones', record.get('plan', ''))]
    meds = [medication_text(m)+'\n'+m.get('instructions', '') for m in record.get('prescriptions', [])]
    if record.get('medications'):
        meds.append('Texto heredado: '+record['medications'])
    sections += [('Medicamentos', '\n\n'.join(meds)), ('Estudios', '\n'.join(r['name']+' · '+r.get('status', '')+('\n'+r['notes'] if r.get('notes') else '') for r in record.get('study_orders', [])) or record.get('studies', ''))]
    followup = record.get('followup', {})
    if followup.get('date'):
        sections.append(('Seguimiento', display_date(followup['date'])+' · '+followup.get('reason', '')))
    for item in record.get('addenda', []):
        author = (authors or {}).get(item['actor'], 'Doctor registrado')
        sections.append(('Adenda · '+display_date(item['at']), item['reason']+'\n'+item['content']+'\nAutor: '+author))
    return sections
