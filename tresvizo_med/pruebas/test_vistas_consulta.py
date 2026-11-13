"""Vistas de la consulta: editor, autoguardado, capturas laterales, revisión, finalización, adendas y conflictos."""
import json

import pytest

from tresvizo_med.models import Consulta
from tresvizo_med.servicios import Actor, borradores, consultas, pacientes
from .conftest import datos_consulta, datos_paciente
from .conftest import reverse_med as reverse

pytestmark = pytest.mark.django_db(databases=['default', 'med'])
HTMX = {'HTTP_HX_REQUEST': 'true'}


@pytest.fixture
def web(cliente_med):
    cliente = cliente_med('medico', username='dra')
    cliente.actor = Actor.de(cliente.usuario)
    return cliente


@pytest.fixture
def paciente(web):
    return pacientes.guardar(web.actor, datos_paciente('Ana Muñoz', birth_date='1990-05-01', allergy_status='Alergias registradas',
                                                      allergy_records=[{'substance': 'Penicilina'}]))


@pytest.fixture
def borrador(web, paciente):
    return consultas.guardar(web.actor, datos_consulta(paciente))


def formulario(c, **cambios):
    """Lo que envía el formulario SOAP tal como se cargó."""
    base = json.dumps({'reason': c.motivo, 'subjective': c.contenido.get('subjective', ''), 'objective': c.contenido.get('objective', ''),
                       'assessment_notes': c.contenido.get('assessment_notes', ''), 'plan': c.plan, 'type': c.tipo,
                       'attended_at': c.atendida_iso}, ensure_ascii=False)
    datos = {'date': c.atendida_iso[:10], 'time': c.atendida_iso[11:16], 'type': c.tipo, 'reason': c.motivo, 'plan': c.plan,
             'subjective': c.contenido.get('subjective', ''), 'objective': c.contenido.get('objective', ''),
             'assessment_notes': c.contenido.get('assessment_notes', ''), 'revision': c.revision, 'base': base}
    datos.update(cambios)
    return datos


def test_editor_con_banda_de_alergias_y_resumenes(web, borrador):
    html = web.get(reverse('med:consulta', args=[borrador.id])).content.decode()
    for texto in ('Consulta · Ana Muñoz', 'Penicilina', 'Motivo de consulta', 'Indicaciones y plan', 'Diagnóstico o impresión',
                  'Signos vitales', 'Medicamentos', 'Estudios', 'Revisar y finalizar', 'id="panel"', 'name="revision"'):
        assert texto in html
    assert 'style=' not in html and 'onclick=' not in html  # la CSP no admite estilos ni manejadores en línea


def test_borrador_ajeno_es_404_en_todas_las_rutas_de_consulta(web, borrador, cliente_med):
    otro = cliente_med('medico', username='otro')
    args = [borrador.id]
    for nombre, metodo in (('consulta', 'get'), ('guardar', 'post'), ('revisar', 'get'), ('finalizar', 'post'), ('adenda', 'post'),
                           ('anular', 'post'), ('papelera', 'post'), ('conflicto', 'get')):
        assert getattr(otro, metodo)(reverse(f'med:{nombre}', args=args)).status_code in (404, 403), nombre
    for tipo in ('vitals', 'medication', 'study', 'diagnosis'):
        assert otro.get(reverse('med:captura', args=[borrador.id, tipo])).status_code in (404, 403)
    assert otro.get(reverse('med:consulta', args=args)).status_code == 404


def test_autoguardado_actualiza_la_revision_y_no_escribe_sin_cambios(web, borrador):
    url = reverse('med:guardar', args=[borrador.id])
    r = web.post(url, formulario(borrador, reason='Dolor de cabeza', plan='Reposo'), **HTMX)
    html = r.content.decode()
    assert r.status_code == 200 and 'Guardado' in html and 'id="f-revision"' in html and 'value="2"' in html
    borrador.refresh_from_db()
    assert borrador.motivo == 'Dolor de cabeza' and borrador.plan == 'Reposo' and borrador.revision == 2
    r = web.post(url, formulario(borrador, reason='Dolor de cabeza', plan='Reposo'), **HTMX)
    borrador.refresh_from_db()
    assert borrador.revision == 2  # idéntico: no se escribe


def test_autoguardado_conserva_hora_y_cambia_fecha_con_zona(web, borrador):
    web.post(reverse('med:guardar', args=[borrador.id]), formulario(borrador, date='2026-09-11', time='08:30'), **HTMX)
    borrador.refresh_from_db()
    assert borrador.atendida_iso == '2026-09-11T08:30:00-06:00'
    r = web.post(reverse('med:guardar', args=[borrador.id]), formulario(borrador, time='25:99'), **HTMX)
    assert r.status_code == 422 and 'No se pudo guardar' in r.content.decode()


def test_guardado_explicito_sin_htmx_redirige(web, borrador):
    r = web.post(reverse('med:guardar', args=[borrador.id]), formulario(borrador, reason='X'))
    assert r['Location'] == reverse('med:consulta', args=[borrador.id])
    r = web.post(reverse('med:guardar', args=[borrador.id]), {**formulario(borrador, reason='Y'), 'revision': 2, 'ir': 'revisar'})
    assert r['Location'] == reverse('med:revisar', args=[borrador.id])


def test_dos_pestanas_sin_campos_en_comun_se_combinan_sin_perdida(web, borrador):
    pestana_a = formulario(borrador)
    web.post(reverse('med:guardar', args=[borrador.id]), formulario(borrador, reason='Desde B'), **HTMX)
    r = web.post(reverse('med:guardar', args=[borrador.id]), {**pestana_a, 'plan': 'Plan desde A'}, **HTMX)
    assert r.status_code == 200
    borrador.refresh_from_db()
    assert borrador.motivo == 'Desde B' and borrador.plan == 'Plan desde A'


def test_conflicto_en_el_mismo_campo_pide_decidir_y_no_pierde_nada(web, borrador):
    pestana_a = formulario(borrador)
    web.post(reverse('med:guardar', args=[borrador.id]), formulario(borrador, reason='Versión B'), **HTMX)
    r = web.post(reverse('med:guardar', args=[borrador.id]), {**pestana_a, 'reason': 'Versión A', 'subjective': 'Nota de A'}, **HTMX)
    assert r.status_code == 204 and r['HX-Redirect'] == reverse('med:conflicto', args=[borrador.id])
    borrador.refresh_from_db()
    assert borrador.motivo == 'Versión B'  # nada se sobrescribió
    html = web.get(r['HX-Redirect']).content.decode()
    assert 'Versión A' in html and 'Versión B' in html and 'Motivo de consulta' in html and 'Nota de A' not in html.split('Mi versión')[0]
    sin_elegir = web.post(r['HX-Redirect'], {})
    assert sin_elegir.status_code == 302 and sin_elegir['Location'] == reverse('med:conflicto', args=[borrador.id])
    r2 = web.post(r['HX-Redirect'], {'campo_reason': 'local'})
    assert r2['Location'] == reverse('med:consulta', args=[borrador.id])
    borrador.refresh_from_db()
    assert borrador.motivo == 'Versión A' and borrador.contenido['subjective'] == 'Nota de A'
    assert web.get(reverse('med:conflicto', args=[borrador.id])).status_code == 302  # ya resuelto


def test_conflicto_elegir_la_version_guardada(web, borrador):
    pestana_a = formulario(borrador)
    web.post(reverse('med:guardar', args=[borrador.id]), formulario(borrador, reason='Versión B'), **HTMX)
    web.post(reverse('med:guardar', args=[borrador.id]), {**pestana_a, 'reason': 'Versión A'}, **HTMX)
    web.post(reverse('med:conflicto', args=[borrador.id]), {'campo_reason': 'remoto'})
    borrador.refresh_from_db()
    assert borrador.motivo == 'Versión B'


# --- Capturas laterales -----------------------------------------------------------------------------------------

def aplicar(web, c, tipo, item='nuevo', **campos):
    return web.post(reverse('med:captura_item', args=[c.id, tipo, item]), {'accion': 'aplicar', 'item': item, **campos}, **HTMX)


def test_paneles_de_captura_se_abren(web, borrador):
    for tipo, texto in (('vitals', 'Presión sistólica'), ('medication', 'Medicamento'), ('study', 'Estudio'), ('diagnosis', 'Diagnóstico')):
        r = web.get(reverse('med:captura', args=[borrador.id, tipo]), **HTMX)
        assert r.status_code == 200 and texto in r.content.decode(), tipo
    assert web.get(reverse('med:captura', args=[borrador.id, 'inventada'])).status_code == 404


def test_signos_vitales_se_capturan_normalizan_y_se_resumen(web, borrador):
    r = aplicar(web, borrador, 'vitals', v_systolic='120', u_systolic='mmHg', v_diastolic='80', u_diastolic='mmHg',
                v_weight='154.3', u_weight='lb', v_height='1,75', u_height='m', date='2026-09-10', time='10:15', context='Ayuno')
    html = r.content.decode()
    assert r.status_code == 200 and 'Presión: 120 / 80 mmHg' in html and 'IMC' in html and 'id="resumenes"' in html and 'hx-swap-oob' in html
    borrador.refresh_from_db()
    toma = borrador.contenido['vitals'][0]
    assert toma['values']['weight']['normalized_unit'] == 'kg' and toma['at'].startswith('2026-09-10T10:15') and borrador.revision == 2


def test_signos_vitales_invalidos_se_explican_y_no_se_guardan(web, borrador):
    r = aplicar(web, borrador, 'vitals', v_oxygen='101', u_oxygen='%', date='2026-09-10', time='10:15')
    assert r.status_code == 422 and 'fuera de la escala' in r.content.decode()
    r = aplicar(web, borrador, 'vitals', date='2026-09-10', time='10:15')
    assert r.status_code == 422 and 'al menos una medición' in r.content.decode()
    r = aplicar(web, borrador, 'vitals', v_pain='3', u_pain='0–10', date='mal', time='10:15')
    assert r.status_code == 422
    borrador.refresh_from_db()
    assert borrador.contenido.get('vitals', []) == []


def test_editar_y_quitar_una_toma(web, borrador):
    aplicar(web, borrador, 'vitals', v_weight='70', u_weight='kg', date='2026-09-10', time='10:15')
    borrador.refresh_from_db()
    toma = borrador.contenido['vitals'][0]['id']
    assert 'value="70"' in web.get(reverse('med:captura_item', args=[borrador.id, 'vitals', toma]), **HTMX).content.decode()
    aplicar(web, borrador, 'vitals', toma, v_weight='72', u_weight='kg', date='2026-09-10', time='10:15')
    borrador.refresh_from_db()
    assert len(borrador.contenido['vitals']) == 1 and borrador.contenido['vitals'][0]['values']['weight']['value'] == '72'
    r = web.post(reverse('med:quitar', args=[borrador.id, 'vitals', toma]), **HTMX)
    borrador.refresh_from_db()
    assert r.status_code == 200 and borrador.contenido['vitals'] == []


def test_medicamento_estructurado_catalogo_y_favoritos(web, borrador):
    r = aplicar(web, borrador, 'medication', name='Paracetamol', strength='500 mg', dose='1', dose_unit='tableta', route='Oral',
                frequency_kind='Cada N horas', frequency='8', al_catalogo='on', favorito='on')
    assert r.status_code == 200 and 'Paracetamol' in r.content.decode() and 'Cada 8 horas' in r.content.decode()
    borrador.refresh_from_db()
    assert borrador.contenido['prescriptions'][0]['name'] == 'Paracetamol'
    catalogo = borradores.catalogo(web.actor)
    assert [f['name'] for f in catalogo] == ['Paracetamol'] and web.actor.cuenta_id in catalogo[0]['favorites']
    nuevo = web.get(reverse('med:captura', args=[borrador.id, 'medication']), **HTMX).content.decode()
    assert 'Favoritos' in nuevo and 'Paracetamol' in nuevo and 'datalist' in nuevo
    prellenado = web.get(reverse('med:captura_item', args=[borrador.id, 'medication', 'otro']), {'de': catalogo[0]['id']}, **HTMX).content.decode()
    assert 'value="500 mg"' in prellenado


def test_medicamento_sin_nombre_o_con_frecuencia_cero(web, borrador):
    assert aplicar(web, borrador, 'medication', name='').status_code == 422
    r = aplicar(web, borrador, 'medication', name='X', frequency_kind='Cada N horas', frequency='0')
    assert r.status_code == 422 and 'mayor que cero' in r.content.decode()


def test_diagnostico_y_estudio(web, borrador):
    r = aplicar(web, borrador, 'diagnosis', name='Gastritis')
    assert 'Gastritis' in r.content.decode() and 'id="diagnosticos"' in r.content.decode()
    aplicar(web, borrador, 'study', name='Biometría hemática', status='Solicitado', notes='En ayuno')
    borrador.refresh_from_db()
    assert borrador.diagnostico == 'Gastritis' and borrador.contenido['study_orders'][0]['name'] == 'Biometría hemática'
    assert aplicar(web, borrador, 'diagnosis', name=' ').status_code == 422


def test_captura_pendiente_se_conserva_y_se_retoma(web, borrador):
    r = web.post(reverse('med:captura_item', args=[borrador.id, 'medication', 'abc']), {'accion': 'pendiente', 'name': 'Ibuprofeno'}, **HTMX)
    assert r['HX-Reswap'] == 'none' and 'Guardado' in r.content.decode()
    borrador.refresh_from_db()
    assert borrador.editor_state['pending']['medication:abc']['values']['name'] == 'Ibuprofeno'
    assert 'Medicamento pendiente' in web.get(reverse('med:consulta', args=[borrador.id])).content.decode()
    panel = web.get(reverse('med:captura_item', args=[borrador.id, 'medication', 'abc']), **HTMX).content.decode()
    assert 'Ibuprofeno' in panel and 'sin aplicar' in panel
    web.post(reverse('med:captura_item', args=[borrador.id, 'medication', 'abc']), {'accion': 'descartar'}, **HTMX)
    borrador.refresh_from_db()
    assert not borrador.editor_state['pending']


# --- Revisar y finalizar ---------------------------------------------------------------------------------------

def test_revisar_lista_lo_que_falta_y_bloquea_finalizar(web, borrador):
    web.post(reverse('med:captura_item', args=[borrador.id, 'study', 'x']), {'accion': 'pendiente', 'name': 'Rayos X'}, **HTMX)
    html = web.get(reverse('med:revisar', args=[borrador.id])).content.decode()
    for texto in ('Completa el motivo', 'Completa el plan', 'Añade un diagnóstico', 'pendiente de aplicar', 'Falta resolver', 'disabled'):
        assert texto in html
    assert f'?abrir=study/x' in html
    r = web.post(reverse('med:finalizar', args=[borrador.id]))
    assert r['Location'] == reverse('med:revisar', args=[borrador.id])
    borrador.refresh_from_db()
    assert borrador.estado == 'Borrador'
    assert 'data-abrir-url="' + reverse('med:captura_item', args=[borrador.id, 'study', 'x']) in web.get(
        reverse('med:consulta', args=[borrador.id]), {'abrir': 'study/x'}).content.decode()


def completar(web, c):
    web.post(reverse('med:guardar', args=[c.id]), formulario(c, reason='Dolor de cabeza', plan='Reposo e hidratación'), **HTMX)
    aplicar(web, c, 'diagnosis', name='Migraña')


def test_finalizar_y_la_consulta_deja_de_ser_editable(web, borrador):
    completar(web, borrador)
    assert 'Todo está completo' in web.get(reverse('med:revisar', args=[borrador.id])).content.decode()
    r = web.post(reverse('med:finalizar', args=[borrador.id]))
    assert r['Location'] == reverse('med:consulta', args=[borrador.id])
    borrador.refresh_from_db()
    assert borrador.estado == 'Finalizada' and borrador.diagnostico == 'Migraña'
    lectura = web.get(reverse('med:consulta', args=[borrador.id])).content.decode()
    assert 'Migraña' in lectura and 'Agregar adenda' in lectura and 'Anular consulta' in lectura and 'name="revision"' not in lectura
    assert web.post(reverse('med:guardar', args=[borrador.id]), formulario(borrador, reason='Cambio')).status_code == 403
    assert web.get(reverse('med:captura', args=[borrador.id, 'diagnosis'])).status_code == 403
    assert web.post(reverse('med:finalizar', args=[borrador.id])).status_code == 403
    borrador.refresh_from_db()
    assert borrador.motivo == 'Dolor de cabeza'


def test_finalizar_con_medicamento_incompleto_se_explica(web, borrador):
    completar(web, borrador)
    aplicar(web, borrador, 'medication', name='Producto', dose='1')
    html = web.get(reverse('med:revisar', args=[borrador.id])).content.decode()
    assert 'Revisa dosis, unidad, vía y frecuencia de Producto' in html
    assert web.post(reverse('med:finalizar', args=[borrador.id]), follow=True).redirect_chain[-1][0] == reverse('med:revisar', args=[borrador.id])


def test_adendas_anulacion_y_restauracion_por_rol(web, borrador, cliente_med):
    completar(web, borrador)
    web.post(reverse('med:finalizar', args=[borrador.id]))
    otro = cliente_med('medico', username='otro')
    admin = cliente_med('admin', username='jefa')
    url = lambda n: reverse(f'med:{n}', args=[borrador.id])  # noqa: E731
    # Adenda: cualquier médico; el admin que no es médico no escribe clínica.
    assert otro.post(url('adenda'), {'motivo': 'Aclaración', 'contenido': 'Texto de la adenda'}).status_code == 302
    assert admin.post(url('adenda'), {'motivo': 'x', 'contenido': 'y'}).status_code == 403
    web.post(url('adenda'), {'motivo': '', 'contenido': 'sin motivo'})
    assert borrador.adendas.count() == 1
    html = web.get(url('consulta')).content.decode()
    assert 'Texto de la adenda' in html and 'Autor: ' in html
    # Anular: no el médico ajeno; sí el responsable o el administrador.
    assert otro.post(url('anular'), {'motivo': 'Duplicada'}).status_code == 403
    assert 'Anular consulta' not in otro.get(url('consulta')).content.decode()
    assert web.post(url('anular'), {'motivo': 'Duplicada'}).status_code == 302
    borrador.refresh_from_db()
    assert borrador.estado == 'Anulada'
    assert 'Consulta anulada' in web.get(url('consulta')).content.decode()
    assert otro.post(url('restaurar'), {'motivo': 'x'}).status_code == 403
    assert admin.post(url('restaurar'), {'motivo': 'Error de captura'}).status_code == 302
    borrador.refresh_from_db()
    assert borrador.estado == 'Finalizada' and [a.tipo for a in borrador.adendas.all()] == ['adenda', 'anulacion', 'restauracion']
    assert admin.post(url('anular'), {'motivo': 'Revisión'}).status_code == 302


def test_papelera_y_recuperacion_de_un_borrador(web, borrador, paciente):
    r = web.post(reverse('med:papelera', args=[borrador.id]), {'motivo': 'Duplicado'})
    assert r['Location'] == reverse('med:expediente', args=[paciente.id])
    assert not consultas.visibles(web.actor).exists()
    lectura = web.get(reverse('med:consulta', args=[borrador.id])).content.decode()
    assert 'en la papelera' in lectura and 'Recuperar borrador' in lectura
    web.post(reverse('med:papelera', args=[borrador.id]), {'accion': 'restaurar', 'motivo': 'x'})
    assert consultas.visibles(web.actor).count() == 1


# --- Bloquear ------------------------------------------------------------------------------------------------------

def test_bloquear_oculta_todo_y_la_contrasena_lo_reabre(web, borrador):
    r = web.post(reverse('med:bloquear'))
    assert r['Location'] == reverse('med:desbloquear')
    for url in (reverse('med:pacientes'), reverse('med:consulta', args=[borrador.id])):
        bloqueada = web.get(url)
        assert bloqueada.status_code == 302 and bloqueada['Location'].startswith(reverse('med:desbloquear'))
    assert web.post(reverse('med:guardar', args=[borrador.id]), formulario(borrador, reason='Intruso'), **HTMX)['HX-Redirect'] == reverse('med:desbloquear')
    borrador.refresh_from_db()
    assert borrador.motivo == ''
    pagina = web.get(reverse('med:desbloquear')).content.decode()
    assert 'Sesión bloqueada' in pagina and 'Ana Muñoz' not in pagina
    mala = web.post(reverse('med:desbloquear'), {'password': 'equivocada', 'siguiente': reverse('med:pacientes')})
    assert mala.status_code == 401 and 'no coincide' in mala.content.decode()
    buena = web.post(reverse('med:desbloquear'), {'password': 'clave-de-prueba', 'siguiente': 'https://malo.example/robo'})
    assert buena.status_code == 302 and buena['Location'] == reverse('med:pacientes')
    assert web.get(reverse('med:pacientes')).status_code == 200


def test_demasiados_intentos_cierran_la_sesion(web):
    web.post(reverse('med:bloquear'))
    for _ in range(5):
        respuesta = web.post(reverse('med:desbloquear'), {'password': 'no'})
    assert respuesta.status_code == 302
    assert web.get(reverse('med:pacientes')).status_code == 302 and 'sso/entrar' in web.get(reverse('med:pacientes'))['Location']


def test_tema_css_con_los_tokens_del_tema_activo(web):
    r = web.get(reverse('med:tema'))
    assert r['Content-Type'].startswith('text/css') and '--tv-primario' in r.content.decode()
    assert 'no-store' in r['Cache-Control']


def test_los_botones_dentro_del_formulario_no_heredan_el_swap_none(web, borrador):
    """htmx hereda hx-swap del formulario SOAP: los botones que abren un panel deben fijar el suyo."""
    html = web.get(reverse('med:consulta', args=[borrador.id])).content.decode()
    formulario = html.split('<form id="soap"')[1].split('</form>')[0]
    for boton in [b for b in formulario.split('<button') if 'hx-get' in b or 'hx-post' in b]:
        assert 'hx-swap=' in boton, boton[:120]
