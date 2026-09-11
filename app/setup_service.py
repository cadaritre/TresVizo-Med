"""Alta inicial atómica de la clínica, identidad y administrador."""
import uuid
from app.services import password_hash, now
from app.storage import DataError
from app.branding import APP_MARK


def create_clinic(auth, identity, *, clinic_name, name, username, password, master_password,
                  logo_source=None, use_clinic_icon=True):
    if not all(value.strip() for value in (clinic_name, name, username)):
        raise DataError('Completa el nombre de la clínica, del administrador y su usuario.')
    credential = password_hash(password)
    recovery = password_hash(master_password)
    data = {**identity.values, 'clinic_name': clinic_name.strip(), 'use_clinic_icon': bool(use_clinic_icon)}
    identity.validate(data)
    with auth.store.lock:
        if auth.users():
            raise DataError('Esta clínica ya está configurada. Inicia sesión con tu perfil.')
        data.update(identity.prepare_clinic_logo(logo_source or APP_MARK))
        uid, audit_id = str(uuid.uuid4()), str(uuid.uuid4())
        user = {'schema_version': 1, 'id': uid, 'name': name.strip(), 'username': username.strip(),
                'role': 'admin', 'active': True, 'password': credential, 'created_at': now()}
        auth.store.transaction({f'data/users/{uid}.json': user, 'config/identity.json': data,
            'config/recovery.json': {'schema_version': 1, 'password': recovery, 'updated_at': now()},
            f'data/audit/{audit_id}.json': {'schema_version': 1, 'id': audit_id, 'actor': uid,
                'action': 'crear_clinica', 'target': 'clinica', 'at': now()}})
        identity.values = data
    return uid
