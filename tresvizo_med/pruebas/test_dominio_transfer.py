"""Exportaciones, importación CSV y verificación de respaldos (portado de test_documents/test_clinic_update/test_redesign)."""
import csv
import hashlib
import io
import json
import zipfile

import pytest

from tresvizo_med.dominio.errores import DataError
from tresvizo_med.dominio.transfer import (CONSULTATION_FIELDS, check_period, inspect_import, loads_strict, read_csv_bytes,
                                           read_csv_text, safe_csv, select_consultations, verify_backup,
                                           write_consultation_csv, write_patient_csv)
from .conftest import make_encounter, make_patient


@pytest.mark.parametrize('value', ['=1+1', '+cmd', '-1', '@SUM(A1)', '   =HYPERLINK("bad")'])
def test_csv_formula_protection(value):
    assert safe_csv(value).startswith("'")


def test_safe_csv_leaves_normal_text_and_none():
    assert safe_csv('Texto normal') == 'Texto normal' and safe_csv(None) == '' and safe_csv(12) == '12'


def test_consultation_csv_scope_structured_values_and_formula_safety(doctor):
    other = 'otro-doctor'
    patient = make_patient('=Paciente sintético')
    medication = {'name': 'Producto sintético', 'dose': '1', 'dose_unit': 'tableta', 'route': 'Oral', 'frequency': '12',
                  'frequency_kind': 'Cada N horas'}
    vital = {'at': '2026-09-10T10:00:00', 'values': {'weight': {'value': '70', 'unit': 'kg'}}}
    common = dict(reason='Motivo, con coma\ny salto', plan='@Indicaciones', type='Control')
    finished = make_encounter(patient['id'], doctor, prescriptions=[medication], vitals=[vital], **common)
    own = make_encounter(patient['id'], doctor, status='Borrador', **common)
    private = make_encounter(patient['id'], other, status='Borrador', **common)
    rows = [finished, own]  # el servicio ya excluyó el borrador ajeno
    assert [r['id'] for r in select_consultations(rows)] == [finished['id']]
    assert {r['id'] for r in select_consultations(rows, include_drafts=True)} == {finished['id'], own['id']}
    assert not select_consultations(rows, identifiers=[private['id']], include_drafts=True)
    stream = io.StringIO(newline='')
    write_consultation_csv(stream, select_consultations(rows), {patient['id']: patient}, {doctor: {'name': 'Dra. Prueba'}})
    row = next(csv.DictReader(io.StringIO(stream.getvalue(), newline='')))
    assert list(row) == list(CONSULTATION_FIELDS)
    assert row['reason'] == common['reason']
    assert row['patient_name'].startswith("'=") and row['plan'].startswith("'@")
    assert row['consultation_type'] == 'Control' and row['doctor_name'] == 'Dra. Prueba'
    assert row['weight'] == '70' and row['weight_unit'] == 'kg'
    assert json.loads(row['prescriptions_json'])[0]['frequency'] == '12'
    assert json.loads(row['vitals_json'])[0]['values']['weight']['value'] == '70'
    assert 'Producto sintético' in row['prescription_summary']
    assert not select_consultations(rows, start='2026-09-11')


def test_period_validation():
    with pytest.raises(DataError):
        check_period('2026-10-01', '2026-09-01')
    with pytest.raises(DataError):
        check_period('mal', '')
    check_period('2026-09-01', '2026-09-30')


def test_patient_csv_export_columns_and_protection():
    stream = io.StringIO(newline='')
    write_patient_csv(stream, [make_patient('=Cmd', 1, phone='555', email='a@b.mx')])
    lines = list(csv.reader(io.StringIO(stream.getvalue())))
    assert lines[0] == ['id', 'file_number', 'name', 'birth_date', 'phone', 'email']
    assert lines[1][2] == "'=Cmd" and lines[1][4] == '555'


def csv_text(rows, delimiter=';'):
    stream = io.StringIO(newline='')
    csv.writer(stream, delimiter=delimiter).writerows(rows)
    return stream.getvalue()


def test_import_mapping_mixed_rows_and_duplicates():
    existing = [make_patient('Ana Muñoz', 1)]
    text = csv_text([['Nombre', 'Nacimiento', 'Correo'], ['María; Luz\nPrueba', '1980-01-02', ''],
                     ['Nombre inválido', '31/02/2020', 'invalido'], ['ANA MUNOZ', '', '']])
    parsed = read_csv_text(text, ';')
    preview = inspect_import(parsed, {'name': 'Nombre', 'birth_date': 'Nacimiento', 'email': 'Correo'}, existing)
    assert preview[0]['patient']['name'] == 'María; Luz\nPrueba' and not preview[0]['errors']
    assert set(preview[1]['errors']) == {'birth_date', 'email'}
    assert preview[2]['duplicates'] == ['Nombre coincidente: RC-000001']
    assert [r['number'] for r in preview] == [2, 3, 4]


def test_import_detects_duplicates_inside_the_same_batch():
    parsed = read_csv_text('name\nLuis Pérez\nluis perez\n', ',')
    preview = inspect_import(parsed, {'name': 'name'}, [])
    assert not preview[0]['duplicates'] and preview[1]['duplicates'] == ['Nombre coincidente: fila 2']


def test_import_requires_name_mapping_and_known_columns():
    parsed = read_csv_text('a,b\n1,2\n', ',')
    with pytest.raises(DataError):
        inspect_import(parsed, {}, [])
    with pytest.raises(DataError):
        inspect_import(parsed, {'name': 'zzz'}, [])


def test_csv_reading_limits():
    with pytest.raises(DataError):
        read_csv_text('a,a\n1,2\n')
    with pytest.raises(DataError):
        read_csv_text('name\n'+'x\n'*10001)
    with pytest.raises(DataError):
        read_csv_text('name\nx\n', '|')
    with pytest.raises(DataError):
        read_csv_bytes(b'x', 'datos.zip')
    with pytest.raises(DataError):
        read_csv_bytes(b'a'*10_000_001, 'datos.csv')
    with pytest.raises(DataError):
        read_csv_bytes('name\n\xe9'.encode('latin-1'), 'datos.csv')
    assert read_csv_bytes('﻿name\nÁngel\n'.encode('utf-8'), 'datos.CSV')['rows'] == [{'name': 'Ángel'}]


def build_backup(path, files=None, extra=None, manifest_changes=None):
    files = files if files is not None else {'config/schema.json': b'{"version": 2}', 'data/users/u.json': b'{}'}
    manifest = {'schema_version': 1, 'files': {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    manifest.update(manifest_changes or {})
    with zipfile.ZipFile(path, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
        archive.writestr('manifest.json', json.dumps(manifest))
    return path


def test_verify_backup_accepts_a_valid_package(tmp_path):
    manifest = verify_backup(build_backup(tmp_path/'ok.zip'))
    assert set(manifest['files']) == {'config/schema.json', 'data/users/u.json'}


def test_verify_backup_rejects_every_anomaly(tmp_path):
    with pytest.raises(DataError):
        verify_backup(build_backup(tmp_path/'extra.zip', extra={'data/sobrante.json': b'{}'}))
    with pytest.raises(DataError):
        verify_backup(build_backup(tmp_path/'version.zip', manifest_changes={'schema_version': 2}))
    with pytest.raises(DataError):
        verify_backup(build_backup(tmp_path/'ruta.zip', files={'../fuera.json': b'{}'}))
    with pytest.raises(DataError):
        verify_backup(build_backup(tmp_path/'categoria.zip', files={'otra/x.json': b'{}'}))
    corrupt = build_backup(tmp_path/'hash.zip')
    with zipfile.ZipFile(corrupt) as src, zipfile.ZipFile(tmp_path/'hash2.zip', 'w') as out:
        for name in src.namelist():
            out.writestr(name, b'{"x": 1}' if name == 'data/users/u.json' else src.read(name))
    with pytest.raises(DataError):
        verify_backup(tmp_path/'hash2.zip')
    (tmp_path/'basura.zip').write_bytes(b'no es un zip')
    with pytest.raises(DataError):
        verify_backup(tmp_path/'basura.zip')
    with zipfile.ZipFile(tmp_path/'sin_manifiesto.zip', 'w') as out:
        out.writestr('data/x.json', b'{}')
    with pytest.raises(DataError):
        verify_backup(tmp_path/'sin_manifiesto.zip')


def test_strict_json_rejects_duplicates_and_nan():
    assert loads_strict('{"a": 1}'.encode('utf-8-sig')) == {'a': 1}
    for bad in ('{"a": 1, "a": 2}', '{"a": NaN}', '{', b'\xff\xfe'):
        with pytest.raises(DataError):
            loads_strict(bad)
