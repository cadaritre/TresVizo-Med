"""Migración, evolución, catálogo y estadísticas (portado de test_redesign/test_hardening)."""
import pytest

from tresvizo_med.dominio import care, estadisticas
from tresvizo_med.dominio.clinical_models import validate_vitals
from tresvizo_med.dominio.errores import DataError
from .conftest import make_encounter, make_patient


def test_migration_is_idempotent_and_preserves_clinical_text():
    patient = {'id': 'p', 'name': 'Paciente previo', 'allergies': 'Texto clínico sin interpretar', 'medications': 'Texto original'}
    first = care.migrate_record(patient)
    assert first['legacy'] == {'allergies': 'Texto clínico sin interpretar', 'medications': 'Texto original'}
    assert first['schema_version'] == 2 and first['archived'] is False
    assert care.migrate_record(first) == first
    assert 'legacy' not in patient and patient.get('schema_version') is None


def test_migration_rejects_future_versions():
    care.check_schema_version(1)
    care.check_schema_version(2)
    with pytest.raises(DataError):
        care.check_schema_version(3)


def vitals_at(moment, systolic):
    return validate_vitals([{'at': moment, 'values': {'systolic': {'value': systolic, 'unit': 'mmHg'},
                                                      'weight': {'value': '70', 'unit': 'kg'}, 'height': {'value': '175', 'unit': 'cm'}}}])[0]


def test_evolution_counts_only_finalized_non_archived_encounters_of_the_patient(doctor):
    pid = 'paciente'
    rows = [make_encounter(pid, doctor, vitals=[vitals_at('2026-09-02T10:00:00', '130')]),
            make_encounter(pid, doctor, vitals=[vitals_at('2026-09-01T10:00:00', '120')]),
            make_encounter(pid, doctor, status='Borrador', vitals=[vitals_at('2026-09-03T10:00:00', '999')]),
            make_encounter(pid, doctor, archived=True, vitals=[vitals_at('2026-09-04T10:00:00', '998')]),
            make_encounter('otro', doctor, vitals=[vitals_at('2026-09-05T10:00:00', '997')])]
    points = care.evolution_points(rows, pid, 'systolic')
    assert [p['value'] for p in points] == [120, 130]
    assert [p['at'][:10] for p in points] == ['2026-09-01', '2026-09-02']
    assert care.evolution_points(rows, pid, 'bmi')[0]['unit'] == 'kg/m²'


def test_catalog_reuses_identifier_and_accumulates_favorites():
    first = care.catalog_item({'name': 'Paracetamol', 'strength': '500 mg'}, [], 'doc1', favorite=True)
    again = care.catalog_item({'name': ' paracetamol', 'strength': '500 mg'}, [first], 'doc2', favorite=True)
    assert again['id'] == first['id'] and set(again['favorites']) == {'doc1', 'doc2'}
    other = care.catalog_item({'name': 'Paracetamol', 'strength': '1 g'}, [first], 'doc1')
    assert other['id'] != first['id'] and other['favorites'] == []
    assert [r['name'] for r in care.filter_catalog([first, other], 'PARACETAMOL')] == ['Paracetamol', 'Paracetamol']
    with pytest.raises(DataError):
        care.catalog_item({'name': '  '}, [], 'doc1')


def stats_fixture(doctor):
    ana = make_patient('Ana', 1, birth_date='1990-05-01', sex='Mujer')
    luis = make_patient('Luis', 2, birth_date='2020-01-01', sex='Hombre')
    other = '00000000-0000-0000-0000-000000000009'
    rows = [make_encounter(ana['id'], doctor, '2026-08-20T09:00:00'),
            make_encounter(ana['id'], doctor, '2026-09-10T10:00:00', assessment='Gastritis; Reflujo'),
            make_encounter(luis['id'], doctor, '2026-09-12T11:00:00', assessment='', type='Control'),
            make_encounter(ana['id'], other, '2026-09-13T11:00:00'),
            make_encounter(luis['id'], doctor, '2026-09-14T11:00:00', status='Borrador'),
            make_encounter(luis['id'], doctor, '2026-09-15T11:00:00', status='Anulada')]
    return rows, [ana, luis]


def test_statistics_period_new_versus_recurrent_and_drafts(doctor):
    rows, patients = stats_fixture(doctor)
    result = estadisticas.calculate(rows, patients, '2026-09-01', '2026-09-30', doctor)
    assert result['consultations'] == 2 and result['patients'] == 2
    assert result['new'] == 1 and result['recurrent'] == 1
    assert result['drafts'] == 1 and result['no_diagnosis'] == 1
    assert result['diagnoses'] == {'gastritis': 1, 'reflujo': 1}
    assert result['ages'] == {'18–39': 1, '6–17': 1} and result['sexes'] == {'Mujer': 1, 'Hombre': 1}
    assert result['previous'] == 1 and result['difference'] == 1 and result['variation'] == 100.0
    assert result['previous_start'] == '2026-08-02' and result['previous_end'] == '2026-08-31'


def test_statistics_filters_and_clinic_scope(doctor):
    rows, patients = stats_fixture(doctor)
    everyone = estadisticas.calculate(rows, patients, '2026-09-01', '2026-09-30', '*')
    assert everyone['consultations'] == 3
    assert estadisticas.calculate(rows, patients, '2026-09-01', '2026-09-30', doctor, consultation_type='control')['consultations'] == 1
    assert estadisticas.calculate(rows, patients, '2026-09-01', '2026-09-30', doctor, diagnosis='GASTRITIS')['consultations'] == 1
    assert estadisticas.calculate(rows, patients, '2026-09-01', '2026-09-30', doctor, patient_group='Nuevos')['consultations'] == 1
    assert estadisticas.calculate(rows, patients, '2026-09-01', '2026-09-30', doctor, patient_group='Recurrentes')['consultations'] == 1
    anuladas = [r for r in rows if r['status'] == 'Anulada']
    assert anuladas and estadisticas.calculate(anuladas, patients, '2026-09-01', '2026-09-30', doctor)['consultations'] == 0


def test_age_bands():
    assert estadisticas.age_band('', '2026-09-01') == 'Desconocida'
    day = '2026-09-01'
    assert [estadisticas.age_band(b, day) for b in ('2021-09-02', '2021-09-01', '2009-09-01', '1990-01-01', '1970-01-01', '1950-01-01')] == \
        ['0–5', '0–5', '6–17', '18–39', '40–64', '65+']
