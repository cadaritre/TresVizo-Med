"""Mismas entradas al escritorio (`main`) y a la rama `web`; las salidas deben coincidir."""
import copy
import csv
import io
import json
import zipfile

import pytest
from PIL import Image
from pypdf import PdfReader

from tresvizo_med.dominio import attachments as w_attachments
from tresvizo_med.dominio import care as w_care
from tresvizo_med.dominio import clinical_models as w_clinical
from tresvizo_med.dominio import consultation_state as w_state
from tresvizo_med.dominio import documents as w_documents
from tresvizo_med.dominio import editing_state as w_editing
from tresvizo_med.dominio import estadisticas as w_stats
from tresvizo_med.dominio import themes as w_themes
from tresvizo_med.dominio import transfer as w_transfer
from tresvizo_med.dominio.errores import DataError as WebError


def sin_ids(valor):
    """Quita los identificadores generados al azar para comparar estructuras."""
    if isinstance(valor, list):
        return [sin_ids(v) for v in valor]
    if isinstance(valor, dict):
        return {k: sin_ids(v) for k, v in valor.items() if k != 'id'}
    return valor


def ambos(viejo_fn, nuevo_fn, *args, **kwargs):
    """Ejecuta las dos versiones: devuelve los dos resultados o exige que las dos fallen."""
    resultados = []
    for fn in (viejo_fn, nuevo_fn):
        try:
            resultados.append(('ok', fn(*copy.deepcopy(args), **copy.deepcopy(kwargs))))
        except ValueError as error:  # DataError y los errores de formato de fecha o número
            resultados.append(('error', str(error)))
    return resultados


def igual(viejo_fn, nuevo_fn, *args, normalizar=lambda x: x, **kwargs):
    a, b = ambos(viejo_fn, nuevo_fn, *args, **kwargs)
    assert a[0] == b[0], (a, b)
    assert normalizar(a[1]) == normalizar(b[1])


# --- Reglas clínicas ----------------------------------------------------------------------------------------

VITALES = [
    [{'at': '2026-09-10T10:00:00', 'values': {'weight': {'value': '154.3235835', 'unit': 'lb'}, 'height': {'value': '1,75', 'unit': 'm'},
                                                'temperature': {'value': '98.6', 'unit': '°F'}}}],
    [{'at': '2026-09-10T10:00:00', 'values': {'oxygen': {'value': '101', 'unit': '%'}}}],
    [{'at': '2026-09-10T10:00:00', 'values': {'glucose': {'value': '5.5', 'unit': 'mmol/L'}, 'pain': {'value': '4', 'unit': '0–10'}}}],
    [{'at': '2026-09-10T10:00:00', 'values': {'weight': {'value': '-3', 'unit': 'kg'}}}],
    [{'at': '2026-09-10T10:00:00', 'values': {'height': {'value': '70', 'unit': 'in'}, 'weight': {'value': '80', 'unit': 'kg'}}}],
    [{'at': 'no-es-fecha', 'values': {}}],
]


@pytest.mark.parametrize('grupos', VITALES)
def test_signos_vitales(viejo, grupos):
    igual(viejo.clinical_models.validate_vitals, w_clinical.validate_vitals, grupos, normalizar=sin_ids)


MED = {'name': 'Producto', 'strength': '500 mg', 'dose': '2', 'dose_unit': 'tableta', 'route': 'Oral',
       'frequency_kind': 'Cada N horas', 'frequency': '12', 'start': '10/09/2026', 'end': '2026-09-20'}
MEDICAMENTOS = [([MED], True), ([MED], False), ([{**MED, 'needs_review': True}], True), ([{**MED, 'frequency': '0'}], False),
                ([{**MED, 'end': '2026-09-01'}], False), ([{'name': ''}], False), ([{**MED, 'dose': 'x'}], False)]


@pytest.mark.parametrize('filas,final', MEDICAMENTOS)
def test_medicamentos(viejo, filas, final):
    igual(viejo.clinical_models.validate_medications, w_clinical.validate_medications, filas, final, normalizar=sin_ids)
    igual(lambda r: [viejo.clinical_models.medication_text(m) for m in r], lambda r: [w_clinical.medication_text(m) for m in r], filas)


def test_secciones_de_consulta_y_resumen(viejo, clinica):
    registro = [r for r in clinica.clinic.list('encounters') if r['prescriptions']][0]
    registro['addenda'] = [{'id': 'a', 'actor': clinica.uid, 'at': '2026-09-11T08:00:00', 'reason': 'Aclaración', 'content': 'Texto'}]
    autores = {clinica.uid: 'Dra. Sintética'}
    assert viejo.clinical_models.encounter_sections(registro, autores) == w_clinical.encounter_sections(registro, autores)
    for grupo in registro['vitals']:
        assert viejo.consultation_state.measurement_summary(grupo) == w_state.measurement_summary(grupo)


@pytest.mark.parametrize('campos,previo', [
    ({'date': '10/09/2026', 'time': '10:15'}, '2026-09-10T10:15:23-06:00'),
    ({'date': '11/09/2026', 'time': '10:30'}, '2026-09-10T10:15:23-06:00'),
    ({'date': '2026-09-11', 'time': '10:30'}, ''), ({'date': '31/02/2026', 'time': '10:30'}, ''),
    ({'date': '10/09/2026', 'time': '9:5'}, '')])
def test_hora_de_atencion(viejo, campos, previo):
    igual(viejo.consultation_state.attention_time, w_state.attention_time, campos, previo)


def test_fusion_de_tres_vias(viejo):
    base = {'id': 'x', 'revision': 1, 'reason': 'Base', 'plan': 'P', 'subjective': ''}
    local = {**base, 'reason': 'Local', 'subjective': 'Nota local', 'plan': ''}
    remoto = {**base, 'revision': 2, 'reason': 'Remoto', 'plan': 'Plan remoto'}
    assert viejo.editing_state.merge_draft(base, local, remoto) == w_editing.merge_draft(base, local, remoto)


def test_borrador_de_consulta(viejo):
    registro = {'id': '11111111-1111-1111-1111-111111111111', 'revision': 1, 'attended_at': '2026-09-10T10:15:23-06:00',
                'reason': '', 'plan': '', 'type': 'General'}
    pasos = [('diagnosis', 'd1', {'name': 'Gastritis'}),
             ('vitals', 'v1', {'at': '2026-09-10T10:15:23-06:00', 'values': {'weight': {'value': '70', 'unit': 'kg'}}}),
             ('medication', 'm1', MED), ('study', 's1', {'name': 'Biometría'})]
    resultados = []
    for modulo in (viejo.consultation_state, w_state):
        borrador = modulo.ConsultationDraft(registro)
        borrador.data.update(reason='Dolor', plan='Reposo')
        problemas_vacio = [p[1] for p in borrador.problems()]
        for tipo, ident, valores in pasos:
            borrador.apply(tipo, ident, valores)
        resultados.append((problemas_vacio, borrador.problems(), sin_ids(borrador.snapshot(final=True)), sin_ids(borrador.snapshot())))
    assert resultados[0] == resultados[1]


# --- Temas e identidad ------------------------------------------------------------------------------------

def test_temas_de_fabrica(viejo):
    assert viejo.themes.BUILTINS == w_themes.BUILTINS
    assert viejo.themes.DEFAULT_IDENTITY == w_themes.DEFAULT_IDENTITY
    for nombre, tokens in viejo.themes.BUILTINS.items():
        assert viejo.themes.issues(tokens) == w_themes.issues(tokens)
        assert viejo.themes.derived(tokens) == w_themes.derived(tokens)
        assert viejo.themes.repair(tokens) == w_themes.repair(tokens)


def test_reparacion_de_tema_roto(viejo):
    roto = {k: '#FFFFFF' for k in viejo.themes.BUILTINS['Clínico']}
    assert viejo.themes.issues(roto) == w_themes.issues(roto)
    assert viejo.themes.repair(roto) == w_themes.repair(roto)


@pytest.mark.parametrize('url', ['https://www.tresvizo.com/', 'file:///c:/x', 'javascript:alert(1)', 'ftp://example.com', 'https://',
                                 'https://a b.com', 'https://user:password@example.com', 'https://example.com:bad'])
def test_enlaces(viejo, url):
    igual(viejo.themes.validate_url, w_themes.validate_url, url)


@pytest.mark.parametrize('cambio', [{}, {'website': 'javascript:x'}, {'clinic_name': ''}, {'document_text': '#12'}, {'app_name': 'x'*121}])
def test_identidad(viejo, cambio):
    datos = {**viejo.themes.DEFAULT_IDENTITY, **cambio}
    igual(viejo.branding.Identity.validate, lambda d: w_themes.validate_identity(d) and None, datos)


def test_estado_de_apariencia(viejo):
    estado = {'schema_version': 1, 'clinic': 'Clínico', 'custom': {}, 'users': {}, 'owners': {}}
    for variante in (estado, {**estado, 'clinic': 'Nada'}, {**estado, 'users': {'x': {'inherit': True, 'theme': 'Clínico'}}}):
        igual(viejo.themes.Appearance.validate_state, w_themes.validate_appearance_state, variante)


# --- Estadísticas, evolución y catálogo --------------------------------------------------------------------

FILTROS = [dict(), dict(consultation_type='control'), dict(diagnosis='GASTRITIS'), dict(patient_group='Nuevos'),
           dict(patient_group='Recurrentes')]


@pytest.mark.parametrize('filtros', FILTROS)
@pytest.mark.parametrize('periodo', [('2026-09-01', '2026-09-30'), ('2026-08-01', '2026-08-31'), ('2026-01-01', '2026-12-31')])
def test_estadisticas(clinica, filtros, periodo):
    esperado = clinica.clinic.statistics(*periodo, **filtros)
    obtenido = w_stats.calculate(clinica.clinic.list('encounters'), clinica.clinic.list('patients', True), *periodo, clinica.uid, **filtros)
    esperado.pop('updated_at'), obtenido.pop('updated_at')
    assert esperado == obtenido


def test_estadisticas_de_toda_la_clinica(clinica):
    esperado = clinica.clinic.statistics('2026-09-01', '2026-09-30', doctor='*')
    obtenido = w_stats.calculate(clinica.clinic.list('encounters'), clinica.clinic.list('patients', True), '2026-09-01', '2026-09-30', '*')
    esperado.pop('updated_at'), obtenido.pop('updated_at')
    assert esperado == obtenido


@pytest.mark.parametrize('clave', ['systolic', 'bmi', 'weight', 'temperature'])
def test_evolucion(clinica, clave):
    for paciente in clinica.clinic.list('patients'):
        assert clinica.care.evolution(paciente['id'], clave) == \
            w_care.evolution_points(clinica.clinic.list('encounters'), paciente['id'], clave)


def test_catalogo(clinica):
    clinica.care.save_catalog({'name': 'Paracetamol', 'strength': '500 mg'}, favorite=True)
    clinica.care.save_catalog({'name': ' paracetamol', 'strength': '500 mg'}, favorite=False)
    guardado = clinica.care.catalog('PARACETAMOL')
    assert len(guardado) == 1
    nuevo = w_care.catalog_item({'name': ' paracetamol', 'strength': '500 mg'}, [], clinica.uid, favorite=True)
    assert {k: v for k, v in nuevo.items() if k != 'id'} == {k: v for k, v in guardado[0].items() if k != 'id'}
    assert [r['name'] for r in w_care.filter_catalog(guardado, 'paraceta')] == [r['name'] for r in clinica.care.catalog('paraceta')]


def test_migracion_v1_a_v2(viejo, tmp_path):
    carpeta = tmp_path/'v1'
    store = viejo.storage.Store(carpeta)
    filas = {'patients': {'id': '22222222-2222-2222-2222-222222222222', 'name': 'Previo', 'allergies': 'Texto', 'medications': 'Otro'},
             'encounters': {'id': '33333333-3333-3333-3333-333333333333', 'patient_id': 'p', 'objective': 'Exploración', 'history': ''}}
    for tipo, fila in filas.items():
        store.write(f"data/{tipo}/{fila['id']}.json", fila)
    store.write('config/schema.json', {'version': 1})
    viejo.care.migrate(store)
    for tipo, fila in filas.items():
        assert store.read(f"data/{tipo}/{fila['id']}.json") == w_care.migrate_record(fila)


# --- Exportaciones e importación -----------------------------------------------------------------------------

def bytes_csv(escribir):
    flujo = io.StringIO(newline='')
    escribir(flujo)
    return flujo.getvalue().encode('utf-8-sig')


@pytest.mark.parametrize('filtros', [dict(), dict(include_drafts=True), dict(start='2026-09-01'), dict(end='2026-08-31'), dict(doctor_id='x')])
def test_csv_de_consultas_identico_byte_a_byte(clinica, tmp_path, filtros):
    destino = tmp_path/'consultas.csv'
    n = clinica.transfer.export_consultations(destino, **filtros)
    filas = w_transfer.select_consultations(clinica.clinic.list('encounters'), **filtros)
    assert n == len(filas)
    pacientes = {p['id']: p for p in clinica.clinic.list('patients', True)}
    doctores = {u['id']: u for u in clinica.auth.users()}
    nuevo = bytes_csv(lambda f: w_transfer.write_consultation_csv(f, filas, pacientes, doctores))
    assert destino.read_bytes() == nuevo


def test_periodo_invalido_en_ambos(clinica, tmp_path):
    with pytest.raises(ValueError) as viejo_error:
        clinica.transfer.export_consultations(tmp_path/'x.csv', start='2026-10-01', end='2026-09-01')
    with pytest.raises(WebError) as nuevo_error:
        w_transfer.select_consultations([], start='2026-10-01', end='2026-09-01')
    assert str(viejo_error.value) == str(nuevo_error.value)


def test_csv_de_pacientes_identico(clinica, tmp_path):
    destino = tmp_path/'pacientes.csv'
    clinica.transfer.export_patients(destino)
    filas = clinica.clinic.list('patients')
    assert destino.read_bytes() == bytes_csv(lambda f: w_transfer.write_patient_csv(f, filas))


CSV_ENTRADA = [['Nombre', 'Nacimiento', 'Correo', 'Tel'], ['María; Luz\nPrueba', '1980-01-02', '', ''],
               ['Nombre inválido', '31/02/2020', 'invalido', ''], ['ANA MUNOZ', '', '', ''], ['Otra', '', 'a@b.mx', '5551234'],
               ['Futura', '2999-01-01', '', ''], ['', '', '', '']]


def test_importacion_csv_vista_previa(clinica, tmp_path):
    origen = tmp_path/'pacientes.csv'
    with origen.open('w', newline='', encoding='utf-8-sig') as flujo:
        csv.writer(flujo, delimiter=';').writerows(CSV_ENTRADA)
    mapeo = {'name': 'Nombre', 'birth_date': 'Nacimiento', 'email': 'Correo', 'phone': 'Tel'}
    viejo_leido = clinica.transfer.read_csv(origen, ';')
    nuevo_leido = w_transfer.read_csv_bytes(origen.read_bytes(), origen.name, ';')
    assert viejo_leido == nuevo_leido
    esperado = clinica.transfer.inspect_import(viejo_leido, mapeo)['rows']
    obtenido = w_transfer.inspect_import(nuevo_leido, mapeo, clinica.clinic.list('patients', True))
    assert esperado == obtenido


@pytest.mark.parametrize('fila', [{'name': 'X'}, {'name': ''}, {'name': 'X', 'birth_date': '2999-01-01'}, {'name': 'X', 'email': 'mal'},
                                  {'name': 'X', 'birth_date': 'mal'}])
def test_validacion_de_fila_importada(viejo, fila):
    assert viejo.transfer.Transfer.validate_import_patient(fila) == w_transfer.validate_import_patient(fila)


@pytest.mark.parametrize('valor', ['=1+1', '+cmd', '-1', '@SUM(A1)', '\t=x', 'normal', None, 5])
def test_proteccion_de_formulas(viejo, valor):
    assert viejo.transfer.safe_csv(valor) == w_transfer.safe_csv(valor)


def test_verificacion_de_respaldo(clinica, tmp_path):
    respaldo = tmp_path/'respaldo.zip'
    clinica.transfer.backup(respaldo)
    assert clinica.transfer.verify_backup(respaldo) == w_transfer.verify_backup(respaldo)
    roto = tmp_path/'roto.zip'
    with zipfile.ZipFile(respaldo) as origen, zipfile.ZipFile(roto, 'w') as salida:
        for nombre in origen.namelist():
            salida.writestr(nombre, b'{}' if nombre.startswith('data/patients/') else origen.read(nombre))
    with pytest.raises(ValueError):
        clinica.transfer.verify_backup(roto)
    with pytest.raises(WebError):
        w_transfer.verify_backup(roto)
    manifiesto = json.loads(zipfile.ZipFile(respaldo).read('manifest.json'))
    assert manifiesto['schema_version'] == 1


def test_json_estricto(viejo, tmp_path):
    for texto in ('{"a": 1}', '{"a": 1, "a": 2}', '{"a": NaN}'):
        archivo = tmp_path/'x.json'
        archivo.write_text(texto, encoding='utf-8')
        igual(lambda: viejo.storage.read_json(archivo), lambda: w_transfer.loads_strict(texto))


# --- Documentos y PDF --------------------------------------------------------------------------------------

def texto_pdf(ruta):
    return [pagina.extract_text() for pagina in PdfReader(ruta).pages]


@pytest.mark.parametrize('identidad', [{}, {'document_website': True, 'document_app_brand': True},
                                       {'clinic_name': 'Clínica «Ñandú»', 'contact': 'Calle 1\nTel. 555', 'document_primary': '#123456'}])
def test_pdf_mismo_texto_y_paginas(viejo, tmp_path, identidad):
    ident = {**viejo.themes.DEFAULT_IDENTITY, **identidad}
    secciones = [('Evolución', 'Texto sintético con acentos: atención, presión. ' * 120), ('Plan', ''), ('Nota', 'Línea 1\nLínea 2 <b>&')]
    viejo.documents.create_pdf(tmp_path/'viejo.pdf', ident, 'Consulta de prueba', secciones, 'Doctora sintética', 'Paciente sintético')
    w_documents.create_pdf(tmp_path/'nuevo.pdf', ident, 'Consulta de prueba', secciones, 'Doctora sintética', 'Paciente sintético')
    assert texto_pdf(tmp_path/'viejo.pdf') == texto_pdf(tmp_path/'nuevo.pdf')


def archivos_de_prueba(carpeta):
    Image.new('RGB', (40, 30), 'white').save(carpeta/'a.png')
    Image.new('RGB', (40, 30), 'white').save(carpeta/'falso.png', 'JPEG')
    Image.new('RGB', (40, 30), 'white').save(carpeta/'b.jpg', 'JPEG')
    (carpeta/'vacio.png').write_bytes(b'')
    (carpeta/'nota.txt').write_text('hola')
    with zipfile.ZipFile(carpeta/'c.docx', 'w') as z:
        z.writestr('[Content_Types].xml', '<x/>'), z.writestr('word/document.xml', '<x/>')
    with zipfile.ZipFile(carpeta/'macro.docx', 'w') as z:
        z.writestr('[Content_Types].xml', '<x/>'), z.writestr('word/document.xml', '<x/>'), z.writestr('word/vbaProject.bin', 'x')
    return sorted(p.name for p in carpeta.iterdir())


def test_validacion_de_archivos(viejo, tmp_path):
    for nombre in archivos_de_prueba(tmp_path):
        a, b = ambos(viejo.attachments.Attachments.validate, w_attachments.validate, tmp_path/nombre)
        assert a[0] == b[0], nombre
        if a[0] == 'ok':
            assert a[1] == b[1], nombre


def test_identificador_de_operacion(viejo):
    actor = '44444444-4444-4444-4444-444444444444'
    destino = {'patient_id': 'p', 'encounter_id': None, 'draft_id': None}
    assert viejo.attachments.Attachments.operation_identifier(actor, destino, 'op') == w_attachments.operation_identifier(actor, destino, 'op')
