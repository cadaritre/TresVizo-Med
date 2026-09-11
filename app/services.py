"""Servicios de sesión y expediente; las pantallas no escriben archivos clínicos."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, date, timedelta
from collections import Counter
import hashlib
import hmac
import secrets
import time
import uuid
import unicodedata
from app.storage import DataError


def now():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', value.casefold()) if not unicodedata.combining(c)).split())


def password_hash(password):
    if len(password) < 10:
        raise DataError('La contraseña debe contener al menos 10 caracteres.')
    salt = secrets.token_bytes(16)
    return {'algorithm': 'scrypt', 'n': 16384, 'r': 8, 'p': 1,
            'salt': salt.hex(), 'hash': hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()}


def password_matches(password, saved):
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(saved['salt']), n=saved['n'], r=saved['r'], p=saved['p'])
    return hmac.compare_digest(value.hex(), saved['hash'])


class Auth:
    def __init__(self, store):
        self.store, self.current = store, None
        self.failures = {}

    def users(self):
        return [{k: v for k, v in u.items() if k != 'password'} for u in self.store.records('users')]

    def require(self, role=None):
        if not self.current:
            raise DataError('Inicia sesión para continuar.')
        current = self.store.read(f"data/users/{self.current['id']}.json")
        if not current or not current['active'] or (role and current['role'] != role):
            raise DataError('Esta operación requiere permisos de administrador activo.')
        return self.current

    def audit(self, action, target):
        identifier = str(uuid.uuid4())
        self.store.write(f'data/audit/{identifier}.json', {'schema_version': 1, 'id': identifier,
            'actor': self.current['id'] if self.current else None, 'action': action, 'target': target, 'at': now()})

    def create_user(self, name, username, password, role='doctor'):
        with self.store.lock:
            users = self.users()
            if users:
                self.require('admin')
            else:
                role = 'admin'
            if role not in ('admin', 'doctor') or not name.strip() or not username.strip():
                raise DataError('Completa nombre, usuario y rol válido.')
            if any(u['username'].casefold() == username.strip().casefold() for u in users):
                raise DataError('El nombre de usuario ya existe.')
            identifier = str(uuid.uuid4())
            record = {'schema_version': 1, 'id': identifier, 'name': name.strip(), 'username': username.strip(),
                      'role': role, 'active': True, 'password': password_hash(password), 'created_at': now()}
            self.store.write(f'data/users/{identifier}.json', record)
            self.audit('crear_usuario', identifier)
            return identifier

    def login(self, identifier, password):
        failed, until = self.failures.get(identifier, (0, 0))
        if time.monotonic() < until:
            raise DataError(f'Espera {int(until-time.monotonic())+1} segundos antes de volver a intentar.')
        user = self.store.read(f'data/users/{identifier}.json')
        if not user or not user['active'] or not password_matches(password, user['password']):
            failed += 1
            self.failures[identifier] = (failed, time.monotonic() + min(120, 2**min(failed, 7)))
            raise DataError('Usuario o contraseña incorrectos. Se ha aplicado una espera de seguridad.')
        self.current = {k: v for k, v in user.items() if k != 'password'}
        self.failures.pop(identifier, None)
        self.audit('inicio_sesion', identifier)
        return self.current

    def logout(self):
        if self.current:
            try:
                self.audit('cierre_sesion', self.current['id'])
            finally:
                self.current = None

    def update_user(self, identifier, active=None, password=None):
        actor = self.require()
        if identifier != actor['id'] or active is not None:
            self.require('admin')
        with self.store.lock:
            u = self.store.read(f'data/users/{identifier}.json')
            if not u:
                raise DataError('No existe el doctor.')
            if active is False and u['role'] == 'admin' and sum(x['active'] and x['role'] == 'admin' for x in self.users()) <= 1:
                raise DataError('No puedes desactivar al último administrador activo.')
            if active is not None:
                u['active'] = bool(active)
            if password is not None:
                u['password'] = password_hash(password)
            self.store.write(f'data/users/{identifier}.json', u)
            self.audit('actualizar_usuario', identifier)


class Clinic:
    def __init__(self, store, auth):
        self.store, self.auth = store, auth
        self._patient_index = None

    def search_patients(self, query='', mode='Activos', page=0, page_size=100):
        self.auth.require()
        generation = self.store.generation('patients')
        if self._patient_index is None or self._patient_index[0] != generation:
            patients = self.list('patients', True)
            index = []
            for row in patients:
                text = normalized(' '.join(str(row.get(key, '')) for key in ('name', 'preferred_name', 'file_number', 'phone')))
                summary = {key: deepcopy(row.get(key)) for key in ('id', 'name', 'file_number', 'birth_date', 'approx_age', 'phone', 'archived') if key in row}
                index.append((normalized(row['name']), text, summary))
            index.sort(key=lambda item: (item[0], item[2]['file_number']))
            if self.store.generation('patients') == generation:
                self._patient_index = generation, index
        else:
            index = self._patient_index[1]
        terms = normalized(query).split()
        rows = [row for _, text, row in index if all(term in text for term in terms) and
                (mode == 'Todos' or bool(row.get('archived')) == (mode == 'Archivados'))]
        current = min(max(0, page), max(0, (len(rows)-1)//page_size))
        return deepcopy(rows[current*page_size:(current+1)*page_size]), len(rows), current

    def list(self, kind, include_archived=False):
        actor = self.auth.require()
        if kind not in ('patients','encounters','appointments','followups'):
            raise DataError('Tipo de registro clínico no admitido.')
        data = self.store.records(kind)
        if kind == 'encounters':
            data = [r for r in data if r['status'] != 'Borrador' or r['doctor_id'] == actor['id']]
        if not include_archived:
            data = [r for r in data if not r.get('archived')]
        return data

    def save(self, kind, record, revision=None, related=None):
        actor = self.auth.require()
        if kind not in ('patients', 'encounters', 'appointments', 'followups'):
            raise DataError('Tipo de registro no admitido.')
        record = deepcopy(record)
        with self.store.lock:
            identifier = record.get('id', str(uuid.uuid4()))
            uuid.UUID(identifier)
            path = f'data/{kind}/{identifier}.json'
            previous = self.store.read(path)
            if previous and previous['revision'] != revision:
                from app.editing_state import VersionConflict
                raise VersionConflict(previous)
            if previous and kind in ('encounters', 'appointments', 'followups'):
                linked = kind == 'encounters' or previous.get('encounter_id')
                if linked and record.get('patient_id') != previous.get('patient_id'):
                    raise DataError('Este registro ya está vinculado a una consulta y conserva su paciente original.')
                for relation in ('encounter_id', 'appointment_id'):
                    if previous.get(relation) and record.get(relation) != previous[relation]:
                        raise DataError('La relación con la atención original debe conservarse.')
            if kind == 'patients':
                if not record.get('name', '').strip():
                    raise DataError('El nombre del paciente es obligatorio.')
                if record.get('birth_date'):
                    try:
                        if date.fromisoformat(record['birth_date']) > date.today():
                            raise ValueError()
                    except ValueError as exc:
                        raise DataError('Nacimiento inválido. Usa AAAA-MM-DD y una fecha no futura.') from exc
                record['file_number'] = previous['file_number'] if previous else f'RC-{len(self.store.records(kind))+1:06d}'
                if record.get('birth_date') and record.get('approx_age', {}).get('value') not in ('', None):
                    raise DataError('Elige fecha de nacimiento o edad aproximada.')
                if record.get('allergy_records') and record.get('allergy_status') == 'Sin alergias conocidas':
                    raise DataError('Revisa las alergias registradas antes de declarar ausencia de alergias.')
                photo_id = record.get('photo_attachment_id')
                if photo_id:
                    try:
                        photo_path = f'data/attachments/{uuid.UUID(photo_id)}.json'
                    except (ValueError, TypeError, AttributeError) as exc:
                        raise DataError('Foto del paciente inválida.') from exc
                    photo = (related or {}).get(photo_path) or self.store.read(photo_path)
                    if not photo or photo.get('patient_id') != identifier or photo.get('draft_id') or not photo.get('mime', '').startswith('image/'):
                        raise DataError('La foto debe ser una imagen incorporada al expediente de este paciente.')
                if previous:
                    record['archived'] = previous.get('archived', False)
            if kind == 'encounters':
                if previous and (previous['doctor_id'] != actor['id'] or previous['status'] != 'Borrador'):
                    raise DataError('Solo el responsable puede editar su borrador. Usa una adenda para consultas finalizadas.')
                if record.get('status') not in ('Borrador', 'Finalizada'):
                    raise DataError('Estado de consulta inválido.')
                if record['status'] == 'Finalizada' and not all(record.get(k, '').strip() for k in ('reason', 'assessment', 'plan')):
                    raise DataError('Para finalizar completa motivo, impresión diagnóstica y plan.')
                if record['status'] == 'Finalizada':
                    if record.get('editor_state', {}).get('pending'):
                        raise DataError('Resuelve las capturas sin aplicar antes de finalizar.')
                    from app.attachments import Attachments
                    attachments = Attachments(self.store, self.auth, self)
                    if previous:
                        queue = attachments.load_queue(patient_id=record['patient_id'], encounter_id=identifier, draft_id=None) or []
                        if any(row['status'] != 'Guardado' for row in queue):
                            raise DataError('Hay archivos seleccionados sin incorporar. Incorpóralos o retira su selección antes de finalizar.')
                try:
                    datetime.fromisoformat(record['attended_at'])
                except (ValueError, KeyError) as exc:
                    raise DataError('Fecha de atención inválida.') from exc
                record['doctor_id'] = previous['doctor_id'] if previous else actor['id']
                record['captured_by'] = previous['captured_by'] if previous else actor['id']
                record.setdefault('addenda', [])
                from app.clinical_models import validate_vitals, validate_medications
                record['vitals'] = validate_vitals(record.get('vitals', []))
                record['prescriptions'] = validate_medications(record.get('prescriptions', []), record['status'] == 'Finalizada')
                record['archived'] = previous.get('archived', False) if previous else False
                if record['archived']:
                    raise DataError('Restaura el borrador antes de editarlo.')
            if kind in ('encounters', 'appointments', 'followups'):
                pid = record.get('patient_id', '')
                try:
                    uuid.UUID(pid)
                except ValueError as exc:
                    raise DataError('Selecciona un paciente válido.') from exc
                patient = self.store.read(f'data/patients/{pid}.json')
                if not patient:
                    raise DataError('El paciente ya no existe.')
                if patient.get('archived') and not previous:
                    raise DataError('Reactiva el expediente antes de iniciar una atención.')
            if kind in ('appointments', 'followups'):
                record['doctor_id'] = previous['doctor_id'] if previous else actor['id']
                if previous and previous['doctor_id'] != actor['id']:
                    self.auth.require('admin')
                try:
                    datetime.fromisoformat(record['due_at'])
                except (ValueError, KeyError) as exc:
                    raise DataError('Fecha inválida. Usa AAAA-MM-DD HH:MM.') from exc
            record.update(schema_version=2, id=identifier, revision=(previous['revision']+1 if previous else 1),
                          created_at=previous['created_at'] if previous else now(),
                          created_by=previous['created_by'] if previous else actor['id'], updated_at=now(), updated_by=actor['id'])
            audit_id = str(uuid.uuid4())
            related = deepcopy(related or {})
            # Agenda y seguimientos retirados: conservar relaciones históricas sin programar ni modificar tareas.
            self.store.transaction({**(related or {}), path: record, f'data/audit/{audit_id}.json': {'id': audit_id, 'actor': actor['id'], 'action': f'guardar_{kind}', 'target': identifier, 'at': now()}})
            return record

    def attend(self, appointment_id):
        actor = self.auth.require()
        with self.store.lock:
            path = f'data/appointments/{uuid.UUID(appointment_id)}.json'
            appointment = self.store.read(path)
            if not appointment or appointment['doctor_id'] != actor['id']:
                raise DataError('La cita debe estar asignada al doctor activo para iniciar su atención.')
            identifier = appointment.get('encounter_id') or str(uuid.uuid5(uuid.UUID(appointment_id), 'encounter'))
            encounter = self.store.read(f'data/encounters/{identifier}.json')
            if encounter:
                if encounter['patient_id'] != appointment['patient_id'] or encounter['doctor_id'] != actor['id']:
                    raise DataError('La asociación de esta cita requiere revisión.')
                return encounter
            if appointment['status'] in ('Cancelada', 'No asistió', 'Atendida'):
                raise DataError('Esta cita está cerrada. Revisa su estado antes de atender.')
            appointment.update(encounter_id=identifier, status='En consulta', revision=appointment['revision']+1,
                               updated_at=now(), updated_by=actor['id'])
            appointment.setdefault('lifecycle', []).append({'at': now(), 'actor': actor['id'], 'action': 'iniciar_consulta', 'encounter_id': identifier})
            return self.save('encounters', {'id': identifier, 'patient_id': appointment['patient_id'], 'appointment_id': appointment_id,
                'status': 'Borrador', 'attended_at': now(), 'reason': appointment.get('reason', '')}, related={path: appointment})

    def archive(self, kind, identifier, reason, restore=False, revision=None):
        actor = self.auth.require('admin' if kind == 'patients' else None)
        if kind not in ('patients', 'encounters') or not reason.strip():
            raise DataError('Indica el motivo de la operación.')
        with self.store.lock:
            path = f'data/{kind}/{uuid.UUID(identifier)}.json'
            row = self.store.read(path)
            if not row:
                raise DataError('No existe el registro.')
            if revision is not None and row['revision'] != revision:
                raise DataError('El registro cambió. Actualiza antes de continuar.')
            if kind == 'encounters':
                if row['status'] == 'Anulada' and restore:
                    if row['doctor_id'] != actor['id']:
                        self.auth.require('admin')
                    row.update(status='Finalizada', revision=row['revision']+1, updated_at=now(), updated_by=actor['id'])
                    row.setdefault('addenda', []).append({'id': str(uuid.uuid4()), 'actor': actor['id'], 'at': now(), 'reason': reason, 'content': 'Consulta restaurada: '+reason})
                    aid = str(uuid.uuid4())
                    self.store.transaction({path: row, f'data/audit/{aid}.json': {'id': aid, 'actor': actor['id'], 'at': now(), 'action': 'restaurar_consulta', 'target': identifier}})
                    return row
                if row['status'] == 'Finalizada' and not restore:
                    return self.addendum(identifier, reason, 'Consulta anulada: '+reason, annul=True)
                if row['status'] != 'Borrador' or row['doctor_id'] != actor['id']:
                    raise DataError('Solo puedes retirar o restaurar tus propios borradores.')
            row.update(archived=not restore, revision=row['revision']+1, updated_at=now(), updated_by=actor['id'])
            row.setdefault('lifecycle', []).append({'actor': actor['id'], 'at': now(), 'reason': reason, 'action': 'restaurar' if restore else 'archivar'})
            aid = str(uuid.uuid4())
            self.store.transaction({path: row,f'data/audit/{aid}.json':{'id':aid,'actor':actor['id'],'at':now(),'action':'restaurar' if restore else 'archivar','target':identifier}})
            return row

    def addendum(self, identifier, reason, content, annul=False):
        actor = self.auth.require()
        if not reason.strip() or not content.strip():
            raise DataError('Escribe contenido y motivo de la adenda.')
        with self.store.lock:
            path = f'data/encounters/{identifier}.json'
            record = self.store.read(path)
            if not record or record['status'] != 'Finalizada':
                raise DataError('Solo se pueden agregar adendas a consultas finalizadas.')
            if annul and actor['id'] != record['doctor_id']:
                self.auth.require('admin')
            record['addenda'].append({'id': str(uuid.uuid4()), 'actor': actor['id'], 'at': now(), 'reason': reason, 'content': content})
            if annul:
                record['status'] = 'Anulada'
            record['revision'] += 1
            aid = str(uuid.uuid4())
            self.store.transaction({path:record,f'data/audit/{aid}.json':{'id':aid,'actor':actor['id'],'at':now(),'action':'anular_consulta' if annul else 'agregar_adenda','target':identifier}})

    def statistics(self, start, end, doctor=None, consultation_type='', diagnosis='', patient_group='Todos'):
        actor = self.auth.require()
        doctor = doctor or actor['id']
        if doctor != actor['id']:
            self.auth.require('admin')
        all_rows = [r for r in self.list('encounters') if r['status'] == 'Finalizada' and (doctor == '*' or r['doctor_id'] == doctor)]
        rows = [r for r in all_rows if start <= r['attended_at'][:10] <= end]
        unique = {r['patient_id'] for r in rows}
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
        patients = {p['id']: p for p in self.list('patients', include_archived=True)}
        ages, sexes = Counter(), Counter()
        for r in rows:
            patient = patients.get(r['patient_id'], {})
            sexes[patient.get('sex', 'No especificado')] += 1
            birth = patient.get('birth_date')
            if not birth:
                ages['Desconocida'] += 1
            else:
                birth, at = date.fromisoformat(birth), date.fromisoformat(r['attended_at'][:10])
                age = at.year-birth.year-((at.month, at.day) < (birth.month, birth.day))
                ages['0–5' if age < 6 else '6–17' if age < 18 else '18–39' if age < 40 else '40–64' if age < 65 else '65+'] += 1
        drafts = [r for r in self.list('encounters') if r['status'] == 'Borrador' and (doctor == '*' or r['doctor_id'] == doctor)]
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
