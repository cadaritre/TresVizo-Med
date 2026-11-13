"""Signos vitales, medicamentos, tiempos, conflictos y consulta (portado de test_redesign/test_hardening)."""
import pytest

from tresvizo_med.dominio.clinical_models import (VITALS, age_label, encounter_sections, medication_text,
                                                  validate_medications, validate_vitals)
from tresvizo_med.dominio.consultation_state import ConsultationDraft, attention_time, measurement_summary
from tresvizo_med.dominio.editing_state import VersionConflict, merge_draft
from tresvizo_med.dominio.errores import DataError
from tresvizo_med.dominio.texto import normalized

MEDICATION = {'name': 'Producto sintético', 'strength': 'concentración de prueba', 'dose': '2', 'dose_unit': 'tableta',
              'route': 'Oral', 'frequency_kind': 'Cada N horas', 'frequency': '12'}


def test_measurement_units_and_medication_structure():
    result = validate_vitals([{'at': '2026-09-10T10:00:00', 'values': {
        'weight': {'value': '154.3235835', 'unit': 'lb'}, 'height': {'value': '1,75', 'unit': 'm'},
        'temperature': {'value': '98.6', 'unit': '°F'}}}])[0]
    assert result['bmi'] == 22.86
    assert result['values']['temperature']['normalized_value'] == pytest.approx(37)
    assert 'oxygen' not in result['values']
    with pytest.raises(DataError):
        validate_vitals([{'at': '2026-09-10T10:00:00', 'values': {'oxygen': {'value': '101', 'unit': '%'}}}])
    assert validate_medications([MEDICATION], True)[0]['dose'] == '2'
    with pytest.raises(DataError):
        validate_medications([{**MEDICATION, 'needs_review': True}], True)


@pytest.mark.parametrize('values', [
    {'weight': {'value': '0', 'unit': 'kg'}}, {'weight': {'value': '-1', 'unit': 'kg'}},
    {'pain': {'value': '11', 'unit': '0–10'}}, {'systolic': {'value': 'abc', 'unit': 'mmHg'}},
    {'systolic': {'value': '120', 'unit': 'kg'}}, {'sueño': {'value': '1', 'unit': 'h'}}])
def test_invalid_vitals_are_rejected(values):
    with pytest.raises(DataError):
        validate_vitals([{'at': '2026-09-10T10:00:00', 'values': values}])


def test_every_vital_has_units():
    assert set(VITALS) == {'systolic', 'diastolic', 'heart_rate', 'respiratory_rate', 'temperature', 'oxygen',
                           'weight', 'height', 'glucose', 'pain'}


def test_medication_rules():
    with pytest.raises(DataError):
        validate_medications([{**MEDICATION, 'frequency': '0'}])
    with pytest.raises(DataError):
        validate_medications([{**MEDICATION, 'start': '2026-09-10', 'end': '2026-09-01'}])
    with pytest.raises(DataError):
        validate_medications([{'name': ' '}])
    assert medication_text(MEDICATION).endswith('Cada 12 horas')


def test_temporal_semantics():
    stamp = '2026-09-10T10:15:23-06:00'
    assert attention_time({'date': '10/09/2026', 'time': '10:15'}, stamp) == stamp
    assert attention_time({'date': '11/09/2026', 'time': '10:30'}, stamp) == '2026-09-11T10:30:00-06:00'
    for bad in ({'date': '31/02/2026', 'time': '10:00'}, {'date': '10/09/2026', 'time': '25:00'}, {'date': '', 'time': '10:00'}):
        with pytest.raises(DataError):
            attention_time(bad, stamp)


def test_three_way_conflict_merges_without_loss():
    stamp = '2026-09-10T10:15:23-06:00'
    base = {'id': 'x', 'revision': 1, 'attended_at': stamp, 'reason': 'Base'}
    remote = {**base, 'revision': 2, 'reason': 'Remoto', 'plan': 'Plan remoto'}
    local = {**base, 'reason': 'Local', 'subjective': 'Nota local'}
    merged, conflicts = merge_draft(base, local, remote)
    assert set(conflicts) == {'reason'}
    assert merged['plan'] == 'Plan remoto' and merged['subjective'] == 'Nota local'
    assert local['reason'] == 'Local' and remote['reason'] == 'Remoto'
    assert conflicts['reason'] == {'local': 'Local', 'remote': 'Remoto'}
    error = VersionConflict(remote)
    assert error.current == remote and error.current is not remote


def test_encounter_sections_include_addenda_with_authors():
    record = {'attended_at': '2026-09-10T10:15:00', 'reason': 'Dolor', 'assessment': 'Gastritis', 'plan': 'Reposo',
              'prescriptions': [MEDICATION], 'addenda': [{'actor': 'a1', 'at': '2026-09-11T08:00:00', 'reason': 'Aclaración',
                                                          'content': 'Texto'}]}
    sections = dict(encounter_sections(record, {'a1': 'Dra. Prueba'}))
    assert sections['Motivo'] == 'Dolor' and 'Producto sintético' in sections['Medicamentos']
    assert any(label.startswith('Adenda') and 'Dra. Prueba' in text for label, text in encounter_sections(record, {'a1': 'Dra. Prueba'}))


def test_age_label_and_normalized_search_text():
    assert age_label({'birth_date': '2020-01-15'}, __import__('datetime').date(2026, 1, 14)).startswith('5')
    assert normalized('  María   NÚÑEZ ') == 'maria nunez'


def draft_record():
    return {'id': '11111111-1111-1111-1111-111111111111', 'revision': 1, 'attended_at': '2026-09-10T10:15:23-06:00',
            'reason': '', 'plan': '', 'type': 'General'}


def test_consultation_draft_pending_and_final_review():
    draft = ConsultationDraft(draft_record())
    draft.remember('vitals', 'v1', {'values': {'weight': {'value': '70', 'unit': 'kg'}}})
    assert any(key == 'vitals:v1' for key, _ in draft.problems())
    draft.apply('vitals', 'v1', {'at': '2026-09-10T10:15:23-06:00', 'values': {'weight': {'value': '70', 'unit': 'kg'}}})
    draft.apply('diagnosis', 'd1', {'name': 'Gastritis'})
    draft.data.update(reason='Dolor', plan='Reposo')
    assert not draft.problems()
    final = draft.snapshot(final=True)
    assert final['status'] == 'Finalizada' and final['assessment'] == 'Gastritis'
    assert 'editor_state' not in final
    assert 'editor_state' in draft.snapshot()


def test_consultation_draft_blocks_finalizing_with_missing_fields():
    with pytest.raises(DataError):
        ConsultationDraft(draft_record()).snapshot(final=True)


def test_measurement_summary_mentions_pressure_and_bmi():
    group = validate_vitals([{'at': '2026-09-10T10:00:00', 'values': {
        'systolic': {'value': '120', 'unit': 'mmHg'}, 'diastolic': {'value': '80', 'unit': 'mmHg'},
        'weight': {'value': '70', 'unit': 'kg'}, 'height': {'value': '175', 'unit': 'cm'}}}])[0]
    text = measurement_summary(group)
    assert 'Presión: 120 / 80 mmHg' in text and 'IMC: 22.86' in text
