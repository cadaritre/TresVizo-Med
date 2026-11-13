"""Datos sintéticos compartidos por las pruebas de dominio. Nada clínico real."""
import uuid

import pytest


def make_patient(name='Paciente sintético', number=1, **extra):
    return {'id': str(uuid.uuid4()), 'name': name, 'file_number': f'RC-{number:06d}', **extra}


def make_encounter(patient_id, doctor_id, attended_at='2026-09-10T10:00:00', status='Finalizada', **extra):
    return {'id': str(uuid.uuid4()), 'patient_id': patient_id, 'doctor_id': doctor_id, 'status': status,
            'attended_at': attended_at, 'reason': 'Motivo', 'assessment': 'Gastritis', 'plan': 'Reposo',
            'type': 'General', 'vitals': [], 'prescriptions': [], **extra}


@pytest.fixture
def doctor():
    return str(uuid.uuid4())
