"""Vistas de pacientes: búsqueda, alta con borrador, expediente, edición y archivo."""
import re

import pytest
from .conftest import reverse_med as reverse

from tresvizo_med.models import BorradorAlta, Paciente
from tresvizo_med.servicios import Actor, borradores, consultas, pacientes
from .conftest import datos_consulta, datos_paciente

pytestmark = pytest.mark.django_db(databases=['default', 'med'])


@pytest.fixture
def web(cliente_med):
    cliente = cliente_med('medico', username='dra')
    cliente.actor = Actor.de(cliente.usuario)
    return cliente


def htmx(**extra):
    return {'HTTP_HX_REQUEST': 'true', **extra}


def test_buscar_en_tarjetas_con_folio_edad_y_alergias(web):
    pacientes.guardar(web.actor, datos_paciente('Ana Muñoz', birth_date='1990-05-01', phone='5551234',
                                               allergy_records=[{'substance': 'Penicilina'}], allergy_status='Alergias registradas'))
    pacientes.guardar(web.actor, datos_paciente('Luis Pérez'))
    html = web.get(reverse('med:pacientes'), {'q': 'munoz'}).content.decode()
    assert 'Ana Muñoz' in html and 'Luis' not in html and 'RC-000001' in html and 'Alergias: Penicilina' in html and '1 paciente' in html
    parcial = web.get(reverse('med:pacientes'), {'q': 'luis'}, **htmx(HTTP_HX_TARGET='resultados')).content.decode()
    assert 'Luis Pérez' in parcial and '<html' not in parcial


def test_cabeceras_sin_cache(web):
    respuesta = web.get(reverse('med:pacientes'))
    assert 'no-store' in respuesta['Cache-Control'] and 'private' in respuesta['Cache-Control']


def test_alta_con_borrador_autoguardado_y_registro(web):
    r = web.get(reverse('med:alta_nueva'))
    assert r.status_code == 302
    borrador = BorradorAlta.objects.get()
    assert r['Location'] == reverse('med:alta', args=[borrador.id])
    assert 'Nuevo paciente' in web.get(r['Location']).content.decode()
    campos = {'name': 'Luis Pérez', 'sex': 'Masculino', 'allergy_status': 'No interrogado',
              'phones__t1__number': '5550001', 'phones__t1__type': 'Móvil', 'hist_personal_status': 'No registrado'}
    guardado = web.post(reverse('med:alta_guardar', args=[borrador.id]), campos, **htmx())
    assert guardado.status_code == 200 and 'Guardado' in guardado.content.decode()
    borrador.refresh_from_db()
    assert borrador.contenido['name'] == 'Luis Pérez' and borrador.contenido['phone'] == '5550001' and not Paciente.objects.exists()
    revision = borrador.revision
    web.post(reverse('med:alta_guardar', args=[borrador.id]), campos, **htmx())
    borrador.refresh_from_db()
    assert borrador.revision == revision  # sin cambios no se escribe
    r = web.post(reverse('med:alta_registrar', args=[borrador.id]), {**campos, 'comenzar': '0'})
    paciente = Paciente.objects.get()
    assert r['Location'] == reverse('med:expediente', args=[paciente.id])
    assert paciente.nombre == 'Luis Pérez' and paciente.telefono == '5550001' and paciente.folio == 'RC-000001'
    assert borradores.propios(web.actor).count() == 0


def test_alta_y_comenzar_consulta(web):
    borrador = borradores.guardar_borrador(web.actor, {})
    r = web.post(reverse('med:alta_registrar', args=[borrador.id]), {'name': 'Ana', 'comenzar': '1'})
    paciente = Paciente.objects.get()
    consulta = paciente.consultas.get()
    assert r['Location'] == reverse('med:consulta', args=[consulta.id]) and consulta.estado == 'Borrador'


def test_registro_valida_y_conserva_el_borrador(web):
    borrador = borradores.guardar_borrador(web.actor, {})
    r = web.post(reverse('med:alta_registrar', args=[borrador.id]), {'name': '', 'email': 'mal', 'birth_date': '2999-01-01'})
    html = r.content.decode()
    assert r.status_code == 422 and 'obligatorio' in html and 'correo' in html and 'no sea futura' in html
    assert BorradorAlta.objects.get(pk=borrador.id).estado == 'Borrador' and not Paciente.objects.exists()


def test_aviso_de_posibles_duplicados_y_confirmacion(web):
    pacientes.guardar(web.actor, datos_paciente('Ana Muñoz', phone='555'))
    borrador = borradores.guardar_borrador(web.actor, {})
    r = web.post(reverse('med:alta_registrar', args=[borrador.id]), {'name': 'ANA MUNOZ'})
    assert r.status_code == 409 and 'Posibles duplicados' in r.content.decode() and Paciente.objects.count() == 1
    r = web.post(reverse('med:alta_registrar', args=[borrador.id]), {'name': 'ANA MUNOZ', 'confirmar_duplicado': '1'})
    assert r.status_code == 302 and Paciente.objects.count() == 2


def test_filas_de_colecciones_y_borradores_ajenos(web, cliente_med):
    fila = web.get(reverse('med:fila', args=['allergies']), **htmx()).content.decode()
    assert re.search(r'name="allergies__[0-9a-f-]+__substance"', fila)
    assert web.get(reverse('med:fila', args=['nada'])).status_code == 404
    borrador = borradores.guardar_borrador(web.actor, {'name': 'Privado'})
    otro = cliente_med('medico', username='otro')
    for nombre in ('alta', 'alta_guardar', 'alta_registrar', 'alta_descartar'):
        metodo = otro.get if nombre == 'alta' else otro.post
        assert metodo(reverse(f'med:{nombre}', args=[borrador.id])).status_code == 404


def test_edicion_de_paciente_con_borrador_y_conflicto(web):
    paciente = pacientes.guardar(web.actor, datos_paciente('Ana', phone='1'))
    r = web.post(reverse('med:editar', args=[paciente.id]))
    borrador = BorradorAlta.objects.get()
    assert r['Location'] == reverse('med:alta', args=[borrador.id]) and borrador.paciente == paciente.id and borrador.revision_origen == 1
    assert web.post(reverse('med:editar', args=[paciente.id]))['Location'] == r['Location']  # reutiliza el borrador
    pacientes.guardar(web.actor, {'id': str(paciente.id), 'name': 'Ana', 'phone': '2'}, 1)  # otra pestaña guarda primero
    r = web.post(reverse('med:alta_registrar', args=[borrador.id]), {'name': 'Ana María', 'phones__a__number': '3'})
    assert r.status_code == 409 and 'El expediente cambió' in r.content.decode()
    assert Paciente.objects.get().nombre == 'Ana'


def test_edicion_exitosa_conserva_folio_y_foto(web, imagen):
    from tresvizo_med.servicios import documentos
    paciente = pacientes.guardar(web.actor, datos_paciente('Ana'))
    foto = documentos.agregar(web.actor, imagen(), paciente=paciente.id, categoria='Fotografía clínica')
    paciente = pacientes.guardar(web.actor, {'id': str(paciente.id), 'name': 'Ana', 'photo_attachment_id': str(foto.id)}, 1)
    web.post(reverse('med:editar', args=[paciente.id]))
    borrador = BorradorAlta.objects.get()
    web.post(reverse('med:alta_registrar', args=[borrador.id]), {'name': 'Ana Muñoz', 'comenzar': '0'})
    paciente.refresh_from_db()
    assert paciente.nombre == 'Ana Muñoz' and paciente.folio == 'RC-000001' and paciente.foto_documento == foto.id and paciente.revision == 3


def test_descartar_borrador(web):
    borrador = borradores.guardar_borrador(web.actor, {'name': 'x'})
    assert web.post(reverse('med:alta_descartar', args=[borrador.id]))['Location'] == reverse('med:pacientes')
    assert not borradores.propios(web.actor).exists()


def test_expediente_pestanas_y_alerta_de_alergias(web):
    paciente = pacientes.guardar(web.actor, datos_paciente('Ana Muñoz', birth_date='1990-05-01', allergy_status='Alergias registradas',
                                                          allergy_records=[{'substance': 'Penicilina', 'severity': 'Grave'}],
                                                          phones=[{'number': '5551', 'type': 'Móvil'}]))
    consultas.guardar(web.actor, datos_consulta(paciente, 'Finalizada', reason='Dolor de cabeza'))
    url = reverse('med:expediente', args=[paciente.id])
    resumen = web.get(url).content.decode()
    assert 'Ana Muñoz' in resumen and 'Penicilina (Grave)' in resumen and 'role="alert"' in resumen and '5551' in resumen
    lista = web.get(url, {'pestana': 'consultas'}).content.decode()
    assert 'Dolor de cabeza' in lista and 'Finalizada' in lista
    assert 'No hay documentos' in web.get(url, {'pestana': 'documentos'}).content.decode()
    assert 'Evolución del paciente' in web.get(url, {'pestana': 'evolucion'}).content.decode()
    assert f'http://med.tresvizo.com{url}' in resumen  # enlace absoluto con el host del módulo
    assert web.get(url, {'pestana': 'inexistente'}).status_code == 200


def test_atender_nunca_crea_dos_borradores_y_abre_la_consulta(web):
    paciente = pacientes.guardar(web.actor, datos_paciente('Ana'))
    r1 = web.post(reverse('med:atender', args=[paciente.id]))
    r2 = web.post(reverse('med:atender', args=[paciente.id]))
    assert r1['Location'] == r2['Location'] and paciente.consultas.count() == 1
    assert 'Retomar' in web.get(reverse('med:expediente', args=[paciente.id]), {'pestana': 'consultas'}).content.decode()


def test_registros_en_curso_solo_los_propios(web, cliente_med):
    paciente = pacientes.guardar(web.actor, datos_paciente('Ana'))
    consultas.guardar(web.actor, datos_consulta(paciente, reason='Mi borrador'))
    borradores.guardar_borrador(web.actor, {'name': 'Alta pendiente'})
    html = web.get(reverse('med:en_curso')).content.decode()
    assert 'Mi borrador' in html and 'Alta pendiente' in html
    otro = cliente_med('medico', username='otro').get(reverse('med:en_curso')).content.decode()
    assert 'Mi borrador' not in otro and 'Alta pendiente' not in otro


def test_archivar_solo_admin(web, cliente_med):
    paciente = pacientes.guardar(web.actor, datos_paciente('Ana'))
    assert web.post(reverse('med:archivar', args=[paciente.id]), {'motivo': 'Duplicado'}).status_code == 403
    admin = cliente_med('admin', username='jefa')
    admin.post(reverse('med:archivar', args=[paciente.id]), {'motivo': 'Duplicado'})
    paciente.refresh_from_db()
    assert paciente.archivado
    assert 'Archivado' in web.get(reverse('med:expediente', args=[paciente.id])).content.decode()
    admin.post(reverse('med:archivar', args=[paciente.id]), {'motivo': 'Error', 'accion': 'restaurar'})
    paciente.refresh_from_db()
    assert not paciente.archivado
    assert web.post(reverse('med:atender', args=[paciente.id])).status_code == 302


def test_el_administrador_sin_rol_medico_no_atiende(cliente_med):
    admin = cliente_med('admin', username='jefa')
    paciente = pacientes.guardar(Actor.de(admin.usuario), datos_paciente('Ana'))
    assert admin.post(reverse('med:atender', args=[paciente.id])).status_code == 403
    assert 'Atender' not in admin.get(reverse('med:expediente', args=[paciente.id])).content.decode()


def test_evolucion_grafica_tabla_y_puntos_huecos(web):
    paciente = pacientes.guardar(web.actor, datos_paciente('Ana'))

    def toma(momento, sistolica, diastolica):
        return [{'at': momento, 'values': {'systolic': {'value': sistolica, 'unit': 'mmHg'}, 'diastolic': {'value': diastolica, 'unit': 'mmHg'}}}]
    hoy = '2026-11-01T10:00:00-06:00'
    consultas.guardar(web.actor, datos_consulta(paciente, 'Finalizada', attended_at=hoy, vitals=toma(hoy, '120', '80')))
    consultas.guardar(web.actor, datos_consulta(paciente, vitals=toma('2026-11-10T10:00:00-06:00', '140', '90')))
    r = web.get(reverse('med:evolucion', args=[paciente.id]), {'periodo': 'todo'})
    html = r.content.decode()
    assert '<svg' in html and 'med-grafica__punto--hueco' in html and 'Consulta finalizada' in html and 'Borrador' in html
    assert '120' in html and '140' in html
    parcial = web.get(reverse('med:evolucion', args=[paciente.id]), {'medicion': 'weight'}, **htmx()).content.decode()
    assert '<html' not in parcial and 'No hay mediciones' in parcial
    assert web.get(reverse('med:evolucion', args=[paciente.id]), {'medicion': 'x', 'periodo': 'y'}).status_code == 200
