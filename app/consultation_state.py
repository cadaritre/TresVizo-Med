"""Borrador de consulta y capturas temporales independientes de Tk."""
from copy import deepcopy
from datetime import datetime
import uuid

from app.clinical_models import (local_date, display_date, validate_medications,
                                 validate_vitals, VITALS)
from app.storage import DataError

COLLECTIONS = {'vitals': 'vitals', 'medication': 'prescriptions',
               'diagnosis': 'diagnoses', 'study': 'study_orders'}
CAPTURE_NAMES = {'vitals': 'Signos vitales', 'medication': 'Medicamento',
                 'diagnosis': 'Diagnóstico', 'study': 'Estudio',
                 'header': 'Fecha, hora y tipo', 'followup': 'Seguimiento', 'document_metadata': 'Detalles del documento'}


def attention_time(fields, previous=''):
    day = local_date(fields.get('date', ''))
    clock = fields.get('time', '').strip()
    if not day or len(clock) != 5:
        raise DataError('Revisa la fecha y la hora (HH:MM).')
    try:
        stamp = datetime.strptime(day+'T'+clock, '%Y-%m-%dT%H:%M')
        if previous and previous[:16] == stamp.isoformat()[:16]:
            return previous
        if previous:
            stamp = stamp.replace(tzinfo=datetime.fromisoformat(previous).tzinfo)
        return stamp.isoformat()
    except ValueError as exc:
        raise DataError('Revisa la fecha y la hora (HH:MM).') from exc


def measurement_summary(group):
    values = group.get('values', {})
    parts = []
    if 'systolic' in values or 'diastolic' in values:
        parts.append('Presión: '+str(values.get('systolic', {}).get('value', 'sin sistólica'))+
                     ' / '+str(values.get('diastolic', {}).get('value', 'sin diastólica'))+' mmHg')
    for key, item in values.items():
        if key not in ('systolic', 'diastolic'):
            parts.append(VITALS.get(key, (key,))[0]+': '+str(item['value'])+' '+item['unit'])
    if group.get('bmi') is not None:
        parts.append('IMC: '+str(group['bmi'])+' kg/m²')
    if 'glucose' in values:
        parts.append('Glucosa: '+group.get('context', 'No especificado'))
    return display_date(group.get('at', ''))+'\n'+' · '.join(parts)


class ConsultationDraft:
    def __init__(self, record):
        self.record = deepcopy(record)
        self.data = deepcopy(record)
        self.legacy_assessment = record.get('assessment', '') if not record.get('diagnoses') else ''
        self.pending = {}
        self.queue = []
        self.selected_take = None
        self.generation = 0
        self.legacy_state = {}
        for field in COLLECTIONS.values():
            self.data.setdefault(field, [])
            for row in self.data[field]:
                row.setdefault('id', str(uuid.uuid4()))
        saved = deepcopy(record.get('editor_state', {}))
        self.section_state = saved.get('sections', {})
        if saved.get('version') == 3:
            self.pending = saved.get('pending', {})
            self.legacy_state = saved.get('legacy_unmapped', {})
            self.selected_take = saved.get('selected_take')
        else:
            self._recover_legacy(saved)
        self.queue = saved.get('attachment_queue', [])
        for item in self.queue:
            if item.get('status') != 'Guardado':
                item['status'] = 'Pendiente de copia / reintento'
        self.data.pop('editor_state', None)

    def _recover_legacy(self, saved):
        # Conservar campos ajenos a esta versión sin interpretar contenido clínico.
        self.legacy_state = {k: v for k, v in saved.items() if k not in
                             ('header', 'followup', 'diagnoses', 'medications', 'studies', 'vitals', 'attachment_queue')}
        for old, kind in [('diagnoses', 'diagnosis'), ('medications', 'medication'), ('studies', 'study')]:
            state = saved.get(old, {})
            rows = deepcopy(state.get('rows', self.data[COLLECTIONS[kind]]))
            valid = []
            for row in rows:
                row.setdefault('id', str(uuid.uuid4()))
                try:
                    self.validate(kind, row)
                    valid.append(row)
                except ValueError:
                    self.remember(kind, row['id'], row)
            self.data[COLLECTIONS[kind]] = valid
            if state.get('pending') is not None:
                index = state.get('index')
                original = rows[index] if isinstance(index, int) and 0 <= index < len(rows) else {}
                self.remember(kind, original.get('id', str(uuid.uuid4())), {**original, **state['pending']})
        vital = saved.get('vitals', {})
        if any(str(v).strip() for v in vital.get('values', {}).values()):
            self.remember('vitals', vital.get('id', str(uuid.uuid4())), vital)
        for kind in ('header', 'followup'):
            raw = saved.get(kind)
            if not raw:
                continue
            try:
                normalized = self.validate(kind, raw)
                existing = self.data.get('followup', {}) if kind == 'followup' else {
                    'attended_at': self.data['attended_at'], 'type': self.data.get('type', 'General')}
                if normalized != existing:
                    self.remember(kind, kind, raw)
            except ValueError:
                self.remember(kind, kind, raw)

    @staticmethod
    def key(kind, identifier):
        return kind+':'+identifier

    def remember(self, kind, identifier, values):
        self.pending[self.key(kind, identifier)] = {
            'kind': kind, 'id': identifier, 'values': deepcopy(values)}
        self.generation += 1

    def discard(self, kind, identifier):
        self.pending.pop(self.key(kind, identifier), None)
        self.generation += 1

    def initial(self, kind, identifier=None):
        if identifier is None:
            pending = next((p for p in self.pending.values() if p['kind'] == kind), None)
            if pending:
                return pending['id'], deepcopy(pending['values']), True
        identifier = identifier or (kind if kind in ('header', 'followup') else str(uuid.uuid4()))
        pending = self.pending.get(self.key(kind, identifier))
        if pending:
            return identifier, deepcopy(pending['values']), True
        if kind == 'header':
            value = {'date': self.data['attended_at'][:10], 'time': self.data['attended_at'][11:16],
                     'type': self.data.get('type', 'General')}
        elif kind == 'followup':
            value = deepcopy(self.data.get('followup', {}))
        else:
            value = deepcopy(next((r for r in self.data[COLLECTIONS[kind]] if r['id'] == identifier), {}))
        return identifier, value, False

    def validate(self, kind, values):
        row = deepcopy(values)
        if kind == 'header':
            return {'attended_at': attention_time(row, self.data['attended_at']), 'type': row.get('type', '').strip()}
        if kind == 'followup':
            row['date'] = local_date(row.get('date', ''))
            if bool(row['date']) != bool(row.get('reason', '').strip()):
                raise DataError('Completa fecha y motivo del seguimiento, o deja ambos vacíos.')
            return row
        if kind == 'vitals':
            if not row.get('values'):
                raise DataError('Registra al menos una medición.')
            return validate_vitals([row])[0]
        if kind == 'medication':
            return validate_medications([row])[0]
        if not row.get('name', '').strip():
            raise DataError('Escribe el nombre del '+('diagnóstico' if kind == 'diagnosis' else 'estudio')+'.')
        return row

    def apply(self, kind, identifier, values):
        # Validar antes de modificar listas o quitar una recuperación pendiente.
        existing = next((r for r in self.data.get(COLLECTIONS.get(kind), []) if r['id'] == identifier), {})
        item = self.validate(kind, {**existing, **deepcopy(values)})
        if kind in COLLECTIONS:
            item['id'] = identifier
            rows = self.data[COLLECTIONS[kind]]
            index = next((i for i, r in enumerate(rows) if r['id'] == identifier), None)
            if index is None:
                rows.append(item)
            else:
                rows[index] = item
            if kind == 'vitals':
                self.selected_take = identifier
        elif kind == 'header':
            self.data.update(item)
        else:
            self.data[kind] = item
        self.discard(kind, identifier)

    def remove(self, kind, identifier):
        self.data[COLLECTIONS[kind]] = [r for r in self.data[COLLECTIONS[kind]] if r['id'] != identifier]
        self.discard(kind, identifier)

    def problems(self):
        result = []
        for field, label in [('reason', 'motivo'), ('plan', 'plan e indicaciones')]:
            if not self.data.get(field, '').strip():
                result.append((field, 'Completa el '+label+'.'))
        if not self.data['diagnoses'] and not self.legacy_assessment.strip():
            result.append(('diagnosis', 'Añade un diagnóstico o revisa la valoración heredada.'))
        for item in self.data['prescriptions']:
            try:
                validate_medications([item], final=True)
            except ValueError as exc:
                result.append(('medication:'+item['id'], str(exc)))
        for key, item in self.pending.items():
            result.append((key, CAPTURE_NAMES.get(item['kind'], 'Captura')+' pendiente de aplicar o descartar.'))
        if any(r.get('status') != 'Guardado' for r in self.queue):
            result.append(('documents', 'Incorpora o retira explícitamente los archivos pendientes.'))
        return result

    def snapshot(self, final=False):
        if final and self.problems():
            raise DataError(self.problems()[0][1])
        data = deepcopy(self.data)
        data.update(id=self.record['id'], revision=self.record.get('revision'), status='Finalizada' if final else 'Borrador')
        data['assessment'] = '; '.join(r['name'] for r in data['diagnoses']) or self.legacy_assessment
        if not final:
            data['editor_state'] = {'version': 3, 'pending': deepcopy(self.pending),
                                    'attachment_queue': deepcopy(self.queue), 'selected_take': self.selected_take,
                                    'legacy_unmapped': deepcopy(self.legacy_state), 'sections': dict(self.section_state)}
        return data

    def saved(self, record):
        self.record = deepcopy(record)
        self.data.update({k: deepcopy(v) for k, v in record.items() if k not in ('editor_state',)})
