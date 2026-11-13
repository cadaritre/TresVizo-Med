"""Estadísticas de consultas (periodo, doctor, tipo, diagnóstico, nuevos y recurrentes, edades, sexo).

Portado de ``Clinic.statistics`` del escritorio como función pura: recibe las consultas visibles para quien
pregunta y los pacientes, y calcula sin tocar almacenamiento ni permisos. Quien llama decide qué doctor puede
consultar cada persona.
"""
from collections import Counter
from datetime import date, timedelta

from .texto import normalized, now

AGE_BANDS = (('0–5', 6), ('6–17', 18), ('18–39', 40), ('40–64', 65))


def age_band(birth_date, attended_day):
    if not birth_date:
        return 'Desconocida'
    birth, at = date.fromisoformat(birth_date), date.fromisoformat(attended_day)
    age = at.year-birth.year-((at.month, at.day) < (birth.month, birth.day))
    for label, limit in AGE_BANDS:
        if age < limit:
            return label
    return '65+'


def calculate(encounters, patients, start, end, doctor, consultation_type='', diagnosis='', patient_group='Todos'):
    """``encounters``: consultas visibles (incluye borradores propios); ``patients``: todos, archivados incluidos;
    ``doctor``: id del doctor o ``'*'`` para toda la clínica."""
    all_rows = [r for r in encounters if r['status'] == 'Finalizada' and (doctor == '*' or r['doctor_id'] == doctor)]
    rows = [r for r in all_rows if start <= r['attended_at'][:10] <= end]
    previous = {r['patient_id'] for r in all_rows if r['attended_at'][:10] < start}
    if consultation_type:
        rows = [r for r in rows if normalized(r.get('type', 'General')) == normalized(consultation_type)]
    if diagnosis:
        rows = [r for r in rows if normalized(diagnosis) in normalized(r.get('assessment', ''))]
    if patient_group == 'Nuevos':
        rows = [r for r in rows if r['patient_id'] not in previous]
    elif patient_group == 'Recurrentes':
        rows = [r for r in rows if r['patient_id'] in previous]
    unique = {r['patient_id'] for r in rows}
    counts = Counter(r['patient_id'] for r in rows)
    diagnoses = Counter(d for r in rows for d in set(normalized(d) for d in r.get('assessment', '').split(';') if d.strip()))
    activity = Counter(r['attended_at'][:10] for r in rows)
    types = Counter(r.get('type', 'General') or 'General' for r in rows)
    reasons = Counter(normalized(r.get('reason', '')) or 'No registrado' for r in rows)
    by_id = {p['id']: p for p in patients}
    ages, sexes = Counter(), Counter()
    for r in rows:
        patient = by_id.get(r['patient_id'], {})
        sexes[patient.get('sex', 'No especificado')] += 1
        ages[age_band(patient.get('birth_date'), r['attended_at'][:10])] += 1
    drafts = [r for r in encounters if r['status'] == 'Borrador' and (doctor == '*' or r['doctor_id'] == doctor)]
    span = (date.fromisoformat(end)-date.fromisoformat(start)).days+1
    prior_start = (date.fromisoformat(start)-timedelta(days=span)).isoformat()
    prior_end = (date.fromisoformat(start)-timedelta(days=1)).isoformat()
    prior_rows = [r for r in all_rows if prior_start <= r['attended_at'][:10] <= prior_end]
    prior_patients = {r['patient_id'] for r in all_rows if r['attended_at'][:10] < prior_start}
    if consultation_type:
        prior_rows = [r for r in prior_rows if normalized(r.get('type', 'General')) == normalized(consultation_type)]
    if diagnosis:
        prior_rows = [r for r in prior_rows if normalized(diagnosis) in normalized(r.get('assessment', ''))]
    if patient_group != 'Todos':
        prior_rows = [r for r in prior_rows if (r['patient_id'] in prior_patients) == (patient_group == 'Recurrentes')]
    prior_count = len(prior_rows)
    return {'consultations': len(rows), 'patients': len(unique), 'new': len(unique-previous),
            'recurrent': len(unique & previous), 'days': len(activity), 'average': len(rows)/len(activity) if activity else 0,
            'diagnoses': dict(diagnoses.most_common()), 'activity': dict(sorted(activity.items())),
            'frequency': dict(counts.most_common()), 'start': start, 'end': end, 'doctor': doctor,
            'types': dict(types), 'reasons': dict(reasons.most_common()), 'ages': dict(ages), 'sexes': dict(sexes),
            'drafts': len(drafts), 'no_diagnosis': sum(not r.get('assessment', '').strip() for r in rows),
            'previous': prior_count, 'difference': len(rows)-prior_count,
            'variation': (len(rows)-prior_count)/prior_count*100 if prior_count else None,
            'previous_start': prior_start, 'previous_end': prior_end,
            'filters': {'type': consultation_type, 'diagnosis': diagnosis, 'patient_group': patient_group}, 'updated_at': now()}
