"""Apariencia, identidad de la clínica, doctores y perfil (con foto y avatar)."""
import io
import json
from pathlib import Path

import pytest
from django.contrib.staticfiles.storage import ManifestStaticFilesStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from tresvizo_med.dominio.themes import BUILTINS
from tresvizo_med.models import Clinica, Profesional, Tema
from tresvizo_med.servicios import Actor, apariencia, clinica
from .conftest import reverse_med as reverse

pytestmark = pytest.mark.django_db(databases=['default', 'med'])
HTMX = {'HTTP_HX_REQUEST': 'true'}


@pytest.fixture
def web(cliente_med):
    cliente = cliente_med('medico', username='dra')
    cliente.actor = Actor.de(cliente.usuario)
    return cliente


@pytest.fixture
def admin(cliente_med):
    cliente = cliente_med('admin', username='jefa')
    cliente.actor = Actor.de(cliente.usuario)
    return cliente


def png(tamano=(300, 200), color='red', formato='PNG'):
    flujo = io.BytesIO()
    Image.new('RGB', tamano, color).save(flujo, formato)
    return flujo.getvalue()


def campos_tema(base='Clínico', **cambios):
    tokens = {**BUILTINS[base], **cambios}
    return {'c_'+k: v for k, v in tokens.items()}


# --- Apariencia -----------------------------------------------------------------------------------------------------

def test_pagina_de_apariencia_lista_los_temas_de_fabrica_y_el_editor(web):
    html = web.get(reverse('med:apariencia')).content.decode()
    for nombre in BUILTINS:
        assert nombre in html
    assert 'Editor de colores' not in html
    editor = web.get(reverse('med:apariencia'), {'base': 'Verde suave'}).content.decode()
    assert 'Editor de colores' in editor and editor.count('type="color"') == 19 and 'med-config.js' in editor
    assert 'style=' not in editor


def test_guardar_un_tema_propio_aplicarlo_y_el_css_lo_refleja(web):
    r = web.post(reverse('med:apariencia_guardar'), {'nombre': 'Mi tema', 'base': 'Clínico', **campos_tema(primary='#0A3D91')})
    assert r['Location'] == reverse('med:apariencia')
    tema = Tema.objects.get()
    assert tema.nombre == 'Mi tema' and tema.dueno_id == web.actor.cuenta_id and tema.tokens['primary'] == '#0A3D91'
    web.post(reverse('med:apariencia_aplicar'), {'clave': str(tema.id), 'ambito': 'personal'})
    css = web.get(reverse('med:tema')).content.decode()
    assert '--tv-primario: #0A3D91' in css
    web.post(reverse('med:apariencia_aplicar'), {'clave': str(tema.id), 'ambito': 'personal', 'hereda': 'on'})
    assert '--tv-primario: #0A3D91' not in web.get(reverse('med:tema')).content.decode()


def test_el_contraste_insuficiente_bloquea_se_explica_y_se_corrige(web):
    malos = campos_tema(text='#FFFFFF')
    r = web.post(reverse('med:apariencia_guardar'), {'nombre': 'Ilegible', 'base': 'Clínico', **malos})
    html = r.content.decode()
    assert r.status_code == 422 and 'Contraste insuficiente' in html and not Tema.objects.exists()
    r = web.post(reverse('med:apariencia_guardar'), {'nombre': 'Ilegible', 'base': 'Clínico', 'accion': 'reparar', **malos})
    assert r.status_code == 200 and 'Contraste correcto' in r.content.decode()
    reparado = {c.split('name="')[1].split('"')[0]: c.split('value="')[1].split('"')[0]
                for c in r.content.decode().split('<input id="c-')[1:] for c in [c]}
    assert not apariencia.problemas({k[2:]: v for k, v in reparado.items() if k.startswith('c_')})


def test_verificacion_en_vivo_del_contraste(web):
    ok = web.post(reverse('med:apariencia_verificar'), campos_tema(), **HTMX).content.decode()
    mal = web.post(reverse('med:apariencia_verificar'), campos_tema(text='#FFFFFF'), **HTMX).content.decode()
    roto = web.post(reverse('med:apariencia_verificar'), campos_tema(primary='rojo'), **HTMX).content.decode()
    assert 'Contraste correcto' in ok and 'Contraste insuficiente' in mal and 'tv-alerta--error' in roto


def test_renombrar_eliminar_y_permisos_de_temas(web, admin, cliente_med):
    tema = apariencia.guardar_tema(web.actor, 'Mi tema', campos_tema() and {k[2:]: v for k, v in campos_tema().items()})
    otro = cliente_med('medico', username='otro')
    assert otro.post(reverse('med:apariencia_tema', args=[tema.id]), {'accion': 'renombrar', 'nombre': 'Robado'}).status_code == 403
    web.post(reverse('med:apariencia_tema', args=[tema.id]), {'accion': 'renombrar', 'nombre': 'Renombrado'})
    tema.refresh_from_db()
    assert tema.nombre == 'Renombrado'
    admin.post(reverse('med:apariencia_aplicar'), {'clave': str(tema.id), 'ambito': 'clinica'})
    web.post(reverse('med:apariencia_tema', args=[tema.id]), {'accion': 'eliminar'})
    assert Tema.objects.exists()  # en uso por la clínica
    assert web.post(reverse('med:apariencia_aplicar'), {'clave': 'Neutro', 'ambito': 'clinica'}).status_code == 403
    admin.post(reverse('med:apariencia_aplicar'), {'clave': 'Clínico', 'ambito': 'clinica'})
    web.post(reverse('med:apariencia_tema', args=[tema.id]), {'accion': 'eliminar'})
    assert not Tema.objects.exists()
    assert web.post(reverse('med:apariencia_tema', args=['Clínico']), {'accion': 'otra'}).status_code == 404


def test_exportar_e_importar_el_json_del_tema(web):
    r = web.get(reverse('med:apariencia_exportar', args=['Neutro']))
    datos = json.loads(r.content)
    assert datos['schema_version'] == 1 and datos['tokens'] == BUILTINS['Neutro'] and 'attachment' in r['Content-Disposition']
    web.post(reverse('med:apariencia_importar'), {'archivo': SimpleUploadedFile('t.json', json.dumps({**datos, 'name': 'Neutro propio'}).encode())})
    assert Tema.objects.get().nombre == 'Neutro propio'
    r = web.post(reverse('med:apariencia_importar'), {'archivo': SimpleUploadedFile('t.json', b'{"a": 1, "a": 2}')}, follow=True)
    assert 'JSON inválido' in r.content.decode() or 'repetida' in r.content.decode() or 'Clave JSON' in r.content.decode()
    assert web.get(reverse('med:apariencia_exportar', args=['Inventado'])).status_code == 404


# --- Identidad de la clínica ----------------------------------------------------------------------------------------

def test_primera_vez_el_admin_configura_la_clinica_y_luego_entra_a_pacientes(admin):
    assert admin.get(reverse('med:inicio'))['Location'] == reverse('med:identidad')
    html = admin.get(reverse('med:identidad')).content.decode()
    assert 'Configura tu clínica' in html and 'recetas y resúmenes' in html
    r = admin.post(reverse('med:identidad'), {'clinic_name': 'Clínica Sur', 'app_name': 'Registro Sur', 'contact': 'Tel. 555', 'website': 'https://clinicasur.example/',
                                              'website_text': 'clinicasur.example', 'document_primary': '#112233', 'document_text': '#223344',
                                              'document_website': 'on', 'revision': 1})
    assert r['Location'] == reverse('med:identidad')
    fila = Clinica.obtener()
    assert fila.configurada and fila.valores()['clinic_name'] == 'Clínica Sur' and fila.valores()['document_website'] and not fila.valores()['document_app_brand']
    assert admin.get(reverse('med:inicio'))['Location'] == reverse('med:pacientes')


def test_identidad_valida_y_solo_la_edita_el_admin(web, admin):
    assert web.get(reverse('med:identidad')).status_code == 403 and web.post(reverse('med:identidad'), {}).status_code == 403
    r = admin.post(reverse('med:identidad'), {'clinic_name': 'X', 'app_name': 'Y', 'website': 'javascript:alert(1)', 'website_text': 'z',
                                              'document_primary': '#112233', 'document_text': '#223344', 'revision': 1})
    assert r.status_code == 422 and 'HTTP o HTTPS' in r.content.decode()
    assert not Clinica.obtener().configurada
    r = admin.post(reverse('med:identidad'), {'clinic_name': 'X', 'app_name': 'Y', 'website': 'https://a.example/', 'website_text': 'z',
                                              'document_primary': 'rojo', 'document_text': '#223344', 'revision': 1})
    assert r.status_code == 422
    r = admin.post(reverse('med:identidad'), {'clinic_name': 'X', 'app_name': 'Y', 'website': 'https://a.example/', 'website_text': 'z',
                                              'document_primary': '#112233', 'document_text': '#223344', 'revision': 99})
    assert r.status_code == 422


def test_logo_se_valida_normaliza_y_se_sirve_a_los_documentos(web, admin):
    base = {'clinic_name': 'X', 'app_name': 'Y', 'website': 'https://a.example/', 'website_text': 'z', 'document_primary': '#112233', 'document_text': '#223344'}
    r = admin.post(reverse('med:identidad'), {**base, 'revision': 1, 'logo': SimpleUploadedFile('logo.png', png((3000, 1000)))})
    assert r.status_code == 302
    fila = Clinica.obtener()
    from django.conf import settings
    ruta = Path(settings.TV_MED_ARCHIVOS)/fila.logo_ruta
    with Image.open(ruta) as logo:
        assert logo.format == 'PNG' and max(logo.size) == 1600 and logo.mode == 'RGBA'  # normalizado, nunca la imagen externa
    with Image.open(Path(settings.TV_MED_ARCHIVOS)/fila.icono_ruta) as icono:
        assert icono.ico.sizes() == {(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)}
    assert web.get(reverse('med:logo'))['Content-Type'] == 'image/png'
    from tresvizo_med.servicios import pdf
    assert pdf.identidad()['clinic_logo'] == str(ruta)
    r = admin.post(reverse('med:identidad'), {**base, 'revision': Clinica.obtener().revision, 'logo': SimpleUploadedFile('malo.png', b'no es imagen')})
    assert r.status_code == 422 and 'imagen válida' in r.content.decode()
    admin.post(reverse('med:identidad'), {**base, 'revision': Clinica.obtener().revision, 'quitar_logo': 'on'})
    assert not ruta.exists() and web.get(reverse('med:logo')).status_code == 404


# --- Perfil y doctores ----------------------------------------------------------------------------------------------

def test_perfil_propio_con_datos_profesionales_y_avatar(web):
    html = web.get(reverse('med:perfil')).content.decode()
    assert 'Mi perfil' in html and html.count('name="avatar"') == 1+len(clinica.AVATARES) and 'data-recorte' in html and 'Mi cuenta' in html
    # Avatares de fábrica, archivo por archivo con {% static %} (nombres con hash en producción): nunca la carpeta + el nombre
    assert 'src="/static/med/img/avatares/koala.png"' in html and 'role="radiogroup"' in html
    assert 'http://app.' in html or 'https://' in html  # el enlace al portal sale de tvplataforma, no de una ruta fija
    r = web.post(reverse('med:perfil'), {'nombre_visible': 'Dra. Ana Prueba', 'cedula': '123', 'especialidad': 'Pediatría', 'avatar': 'koala', 'reducir_movimiento': 'on'})
    assert r['Location'] == reverse('med:perfil')
    perfil = Profesional.objects.get(cuenta_id=web.actor.cuenta_id)
    assert (perfil.nombre_visible, perfil.cedula, perfil.avatar, perfil.reducir_movimiento) == ('Dra. Ana Prueba', '123', 'koala', True)
    assert web.get(reverse('med:perfil_foto', args=[web.actor.cuenta_id]))['Content-Type'] == 'image/png'
    pagina = web.get(reverse('med:pacientes')).content.decode()
    assert 'med-yo' in pagina and 'src="/static/med/img/avatares/koala.png"' in pagina
    menu = pagina.split('Menú de la cuenta')[1].split('</details>')[0]  # Perfil y Bloquear viven en el menú de la cuenta, no en el encabezado
    assert 'Mi perfil' in menu and 'Bloquear Med' in menu
    assert 'Bloquear' not in pagina.split('<div class="tv-acciones">')[1].split('</header>')[0]
    assert web.post(reverse('med:perfil'), {'avatar': 'inventado'}).status_code == 422


def test_foto_de_perfil_recortada_se_valida_y_se_guarda_en_256(web):
    r = web.post(reverse('med:perfil'), {'nombre_visible': 'Ana', 'foto': SimpleUploadedFile('foto.png', png((900, 400), 'blue'))})
    assert r.status_code == 302
    perfil = Profesional.objects.get(cuenta_id=web.actor.cuenta_id)
    from django.conf import settings
    with Image.open(Path(settings.TV_MED_ARCHIVOS)/perfil.foto_ruta) as foto:
        assert foto.size == (256, 256) and foto.format == 'PNG'
    assert perfil.avatar == 'photo'
    anterior = Path(settings.TV_MED_ARCHIVOS)/perfil.foto_ruta
    web.post(reverse('med:perfil'), {'foto': SimpleUploadedFile('otra.png', png((300, 300), 'green'))})
    assert not anterior.exists()
    r = web.post(reverse('med:perfil'), {'foto': SimpleUploadedFile('mala.png', b'basura')})
    assert r.status_code == 422 and 'imagen válida' in r.content.decode()


def test_los_doctores_los_ve_el_admin_y_cada_perfil_solo_su_dueno_o_el_admin(web, admin, cliente_med):
    assert web.get(reverse('med:doctores')).status_code == 403
    html = admin.get(reverse('med:doctores')).content.decode()
    assert 'dra' in html and 'portal' in html
    assert web.get(reverse('med:perfil_de', args=[admin.actor.cuenta_id])).status_code == 403
    assert web.post(reverse('med:perfil_de', args=[admin.actor.cuenta_id]), {'cedula': 'x'}).status_code == 403
    r = admin.post(reverse('med:perfil_de', args=[web.actor.cuenta_id]), {'cedula': '999', 'campo_activo': '1'})
    perfil = Profesional.objects.get(cuenta_id=web.actor.cuenta_id)
    assert r.status_code == 302 and perfil.cedula == '999' and perfil.activo is False
    assert 'Inactivo' in admin.get(reverse('med:doctores')).content.decode()


def test_configuracion_muestra_cada_opcion_segun_el_rol(web, admin):
    medico = web.get(reverse('med:configuracion')).content.decode()
    assert 'Mi perfil' in medico and 'Apariencia' in medico and 'Clínica e identidad' not in medico
    jefe = admin.get(reverse('med:configuracion')).content.decode()
    assert 'Clínica' in jefe and 'Doctores' in jefe and 'Exportación completa' in jefe


def test_los_formularios_con_autoguardado_no_se_bloquean_por_validacion_del_navegador(web):
    """HTMX valida los formularios antes de enviar: un correo a medio escribir no debe frenar el autoguardado."""
    from tresvizo_med.models import BorradorAlta
    from tresvizo_med.servicios import borradores, consultas, pacientes
    from .conftest import datos_consulta, datos_paciente
    borrador = borradores.guardar_borrador(web.actor, {})
    assert 'id="alta" novalidate' in web.get(reverse('med:alta', args=[borrador.id])).content.decode()
    paciente = pacientes.guardar(web.actor, datos_paciente('Ana'))
    c = consultas.guardar(web.actor, datos_consulta(paciente))
    html = web.get(reverse('med:consulta', args=[c.id])).content.decode()
    assert 'id="soap" novalidate' in html
    assert 'id="captura" novalidate' in web.get(reverse('med:captura', args=[c.id, 'study']), **HTMX).content.decode()
    # El verificador de contraste va en un elemento aparte: el formulario conserva la validación nativa al guardar.
    editor = web.get(reverse('med:apariencia'), {'base': 'Clínico'}).content.decode()
    assert 'closest form' in editor and 'hx-post="/configuracion/apariencia/verificar/"' in editor


def test_apariencia_una_opcion_de_clinica_arriba_un_boton_principal_por_tema_y_menu_mas(web):
    web.post(reverse('med:apariencia_aplicar'), {'clave': 'Neutro', 'ambito': 'personal'})
    html = web.get(reverse('med:apariencia')).content.decode()
    assert html.count('Usar el tema de la clínica') == 1 and html.count('Usar siempre el tema de la clínica') == 0
    assert html.count('med-vista__barra') == html.count('Usar este tema') + html.count('>En uso</button>') and 'aria-label="Más opciones del tema Clínico"' in html
    assert 'Copiar y editar' in html and 'Exportar' in html



class AlmacenComoProduccion(ManifestStaticFilesStorage):
    """El de producción (tvportal.estaticos.AlmacenDeEstaticos): nombres con hash y sin fallar por una entrada ausente."""
    manifest_strict = False


def test_avatares_con_nombre_con_hash_en_produccion(web, settings, tmp_path):
    """Causa de los avatares rotos en producción: Caddy marca todo /static/* como inmutable un año, también las respuestas 404.
    Con la URL sin hash (``{% static 'carpeta/' %}{{ nombre }}.png``) una sola falla pasajera quedaba fija en el navegador. Cada
    avatar sale por su propio {% static %}, con el nombre con hash del manifiesto, en el selector y en el menú de la cuenta."""
    from django.core.management import call_command
    from django.test import modify_settings
    clinica.elegir_avatar(web.actor, web.actor.cuenta_id, 'koala')
    with modify_settings(INSTALLED_APPS={'append': 'django.contrib.staticfiles'}):
        settings.STATIC_ROOT = str(tmp_path/'estaticos')
        settings.STORAGES = {**settings.STORAGES, 'staticfiles': {'BACKEND': f'{__name__}.AlmacenComoProduccion'}}
        call_command('collectstatic', '--noinput', verbosity=0)
        manifiesto = json.loads((tmp_path/'estaticos'/'staticfiles.json').read_text())['paths']
        html = web.get(reverse('med:perfil')).content.decode()
    for a in clinica.AVATARES:
        con_hash = manifiesto[f'med/img/avatares/{a}.png']
        assert con_hash != f'med/img/avatares/{a}.png' and f'src="/static/{con_hash}"' in html
    assert 'src="/static/med/img/avatares/koala.png"' not in html
    menu = html.split('Menú de la cuenta')[1].split('</details>')[0]
    assert manifiesto['med/img/avatares/koala.png'] in menu


def test_temas_de_med_conviven_con_el_modo_claro_u_oscuro_de_la_cuenta(web):
    """Claro por omisión y nunca según el sistema: un tema claro pinta solo el modo claro; uno oscuro, solo el oscuro (el claro
    queda en Clínico). Elegir un tema propio elige también el modo de la cuenta."""
    from tvplataforma.models import Preferencias
    hoja = web.get(reverse('med:tema')).content.decode()
    assert ':root:not([data-tv-tema="oscuro"])' in hoja and '[data-tv-tema="oscuro"] {' not in hoja and 'prefers-color-scheme' not in hoja
    web.post(reverse('med:apariencia_aplicar'), {'clave': 'Azul profundo', 'ambito': 'personal'})
    hoja = web.get(reverse('med:tema')).content.decode()
    claro, oscuro = hoja.split(':root[data-tv-tema="oscuro"]')
    assert '#101D2E' in oscuro and '#101D2E' not in claro  # el fondo de Azul profundo solo en el modo oscuro
    assert Preferencias.de(web.usuario).tema == 'oscuro'
    web.post(reverse('med:apariencia_aplicar'), {'clave': 'Verde suave', 'ambito': 'personal'})
    assert Preferencias.de(web.usuario).tema == 'claro'
    assert 'Modo oscuro' in web.get(reverse('med:apariencia')).content.decode()
