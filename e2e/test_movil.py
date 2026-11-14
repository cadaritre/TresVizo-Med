"""Med en el teléfono (360 px): sin desplazamiento horizontal y los criterios de aceptación móvil de med-web.md §8."""
import pytest
from playwright.sync_api import expect

from tresvizo_med.dominio.documents import create_pdf
from tresvizo_med.dominio.themes import DEFAULT_IDENTITY
from tresvizo_med.servicios import consultas, documentos, pacientes
from .conftest import TELEFONO, guardado, sin_scroll_horizontal

pytestmark = pytest.mark.django_db(transaction=True, databases=['default', 'med'])


@pytest.fixture
def telefono(fabrica_sesion):
    return fabrica_sesion('medico', 'admin', username='dra', viewport=TELEFONO, movil=True)


@pytest.fixture
def actor_tel(telefono):
    from tresvizo_med.servicios import Actor
    return Actor.de(telefono.usuario)


def sembrar(actor, tmp_path):
    from PIL import Image
    p = pacientes.guardar(actor, {'name': 'Ana Muñoz', 'birth_date': '1990-05-01', 'phone': '5551234',
                                  'allergy_status': 'Alergias registradas', 'allergy_records': [{'substance': 'Penicilina'}]})
    for n in range(3):
        consultas.guardar(actor, {'patient_id': str(p.id), 'status': 'Finalizada', 'attended_at': f'2026-09-0{n+1}T10:00:00-06:00', 'type': 'Control',
                                  'reason': f'Motivo número {n+1} de la consulta', 'assessment': f'Diagnóstico {n+1}', 'plan': 'Reposo',
                                  'vitals': [{'at': f'2026-09-0{n+1}T10:00:00-06:00', 'values': {'systolic': {'value': str(118+n), 'unit': 'mmHg'},
                                                                                                  'diastolic': {'value': '78', 'unit': 'mmHg'}}}]})
    imagen = tmp_path/'foto.png'
    Image.new('RGB', (600, 400), '#c63').save(imagen)
    pdf = tmp_path/'informe.pdf'
    create_pdf(pdf, DEFAULT_IDENTITY, 'Informe', [('Contenido', 'Texto del informe. ' * 300)])
    di = documentos.agregar(actor, imagen, paciente=p.id, categoria='Fotografía clínica', notas='Lesión en el brazo')
    dp = documentos.agregar(actor, pdf, paciente=p.id, categoria='Referencia')
    return p, di, dp


def revisar(pagina, nombre):
    ancho = sin_scroll_horizontal(pagina)
    assert ancho[0] <= ancho[2] and ancho[1] <= ancho[2], f'{nombre}: desplazamiento horizontal {ancho}'


def test_buscar_abrir_leer_tres_consultas_ver_pdf_e_imagen_sin_scroll_horizontal(telefono, actor_tel, tmp_path):
    p, imagen, pdf = sembrar(actor_tel, tmp_path)
    pagina = telefono.ir('/pacientes/')
    revisar(pagina, 'Pacientes')
    pagina.fill('#q', 'munoz')
    expect(pagina.locator('[data-resultado]')).to_have_count(1)
    expect(pagina.locator('[data-resultado]')).to_contain_text('Penicilina')
    revisar(pagina, 'Resultados')
    pagina.locator('[data-resultado]').tap()
    pagina.wait_for_url(f'**/pacientes/{p.id}/')
    revisar(pagina, 'Expediente (resumen)')
    pagina.locator('.med-pestanas a', has_text='Consultas').tap()
    expect(pagina.locator('.med-historial li')).to_have_count(3)
    revisar(pagina, 'Expediente (consultas)')
    for n in range(3):
        pagina.locator('.med-historial li a').nth(n).tap()
        expect(pagina.locator('.med-lectura')).to_contain_text('Diagnóstico')
        revisar(pagina, f'Consulta {n+1}')
        pagina.go_back()
    pagina.locator('.med-pestanas a', has_text='Evolución').tap()
    expect(pagina.locator('svg.med-grafica:visible')).to_be_visible()
    revisar(pagina, 'Evolución')
    pagina.goto(telefono.servidor+f'/documentos/{imagen.id}/')
    pagina.wait_for_function("() => document.querySelector('[data-zoom-imagen]').naturalWidth > 0")
    revisar(pagina, 'Visor de imagen')
    pagina.goto(telefono.servidor+f'/documentos/{pdf.id}/')
    pagina.wait_for_selector('canvas.med-pdf__pagina--lista', timeout=15000)
    revisar(pagina, 'Visor de PDF')


def test_las_pantallas_de_trabajo_tampoco_se_desbordan(telefono, actor_tel, tmp_path):
    p, imagen, pdf = sembrar(actor_tel, tmp_path)
    c, _ = consultas.iniciar(actor_tel, p.id)
    rutas = ['/pacientes/nuevo/', f'/pacientes/{p.id}/?pestana=documentos', f'/consultas/{c.id}/', f'/consultas/{c.id}/revisar/', '/registros/', '/estadisticas/?desde=2026-09-01&hasta=2026-09-30',
             '/exportar/', '/configuracion/', '/configuracion/apariencia/?base=Cl%C3%ADnico', '/configuracion/clinica/', '/perfil/', '/importar/', '/configuracion/doctores/']
    for ruta in rutas:
        pagina = telefono.ir(ruta)
        if ruta == '/pacientes/nuevo/':
            pagina.wait_for_url('**/pacientes/nuevo/*/')
        revisar(pagina, ruta)
    editor = telefono.ir(f'/consultas/{c.id}/')
    editor.locator('#resumenes button[hx-get*="/vitals/"]').first.tap()
    editor.wait_for_selector('#captura')
    revisar(editor, 'Panel de signos vitales')
    assert editor.locator('#panel').bounding_box()['width'] <= 360


def test_foto_con_la_camara_se_sube_o_falla_con_un_mensaje_claro(telefono, actor_tel, tmp_path):
    from PIL import Image
    p, _, _ = sembrar(actor_tel, tmp_path)
    pagina = telefono.ir(f'/pacientes/{p.id}/?pestana=documentos')
    camara = pagina.locator('tv-subida[data-capture="environment"] input[type=file]')
    assert camara.get_attribute('capture') == 'environment' and 'image' in (camara.get_attribute('accept') or '')
    foto = tmp_path/'camara.png'
    Image.new('RGB', (800, 600), '#06a').save(foto)
    camara.set_input_files(str(foto))
    expect(pagina.locator('#cola-docs form')).to_have_count(1, timeout=15000)  # se subió
    pagina.locator('#cola-docs form button[type=submit]').click()
    expect(pagina.locator('#lista-docs')).to_contain_text('camara')
    # Con la red caída la subida falla con un mensaje claro, sin dejar nada a medias.
    pagina.route('**/subidas/**', lambda ruta: ruta.abort())
    otra = tmp_path/'otra.png'
    Image.new('RGB', (800, 600), '#a60').save(otra)
    camara.set_input_files(str(otra))
    item = pagina.locator('.tv-subida__item[data-estado=error]')
    expect(item).to_have_count(1, timeout=40000)
    assert item.inner_text().strip()
    expect(pagina.locator('#cola-docs form')).to_have_count(0)
    telefono.errores.clear()  # las peticiones abortadas a propósito son errores de consola esperados


def test_sin_senal_med_avisa_y_no_deja_datos_de_una_visita_anterior(telefono, actor_tel, tmp_path):
    p, _, _ = sembrar(actor_tel, tmp_path)
    pagina = telefono.ir(f'/pacientes/{p.id}/')
    expect(pagina.locator('#sin-conexion')).to_be_hidden()
    telefono.contexto.set_offline(True)
    pagina.evaluate("() => window.dispatchEvent(new Event('offline'))")
    expect(pagina.locator('#sin-conexion')).to_be_visible()
    expect(pagina.locator('#sin-conexion')).to_contain_text('Sin conexión')
    antes = pagina.url
    with pytest.raises(Exception):
        pagina.goto(telefono.servidor+'/pacientes/')  # sin service worker, la navegación falla y no se muestra nada guardado
    pagina.wait_for_timeout(800)
    # Chromium pinta su página de error; WebKit deja en pantalla el documento que ya estaba abierto (el mismo expediente, sin
    # cambiar de URL). En ninguno aparece la lista de pacientes desde una caché.
    assert pagina.url.startswith('chrome-error') or pagina.url == antes, pagina.url
    assert pagina.locator('[data-resultado]').count() == 0
    telefono.contexto.set_offline(False)
    pagina.goto(telefono.servidor+'/pacientes/')
    expect(pagina.locator('#sin-conexion')).to_be_hidden()
    telefono.errores.clear()


def test_med_no_guarda_nada_en_el_telefono(telefono, actor_tel, tmp_path):
    p, imagen, _ = sembrar(actor_tel, tmp_path)
    pagina = telefono.ir(f'/pacientes/{p.id}/')
    c, _ = consultas.iniciar(actor_tel, p.id)
    pagina = telefono.ir(f'/consultas/{c.id}/')
    pagina.fill('#id_reason', 'Dolor')
    guardado(pagina)
    estado = pagina.evaluate("""async () => ({
        sw: (await navigator.serviceWorker.getRegistrations()).length,
        local: localStorage.length, sesion: sessionStorage.length,
        bases: (await indexedDB.databases()).length,
        cachees: (await caches.keys()).length })""")
    assert estado == {'sw': 0, 'local': 0, 'sesion': 0, 'bases': 0, 'cachees': 0}
    respuesta = pagina.request.get(telefono.servidor+f'/pacientes/{p.id}/')
    assert 'no-store' in respuesta.headers['cache-control']
    assert pagina.locator('link[rel=manifest]').count() == 0


def test_bloquear_en_el_telefono(telefono, actor_tel):
    pacientes.guardar(actor_tel, {'name': 'Ana Muñoz'})
    pagina = telefono.ir('/pacientes/')
    pagina.locator('summary[aria-label="Menú de la cuenta"]').tap()
    pagina.locator('button:has-text("Bloquear Med")').tap()
    pagina.wait_for_url('**/desbloquear/')
    assert 'Ana Muñoz' not in pagina.content()
    revisar(pagina, 'Bloqueo')
    pagina.fill('#password', 'clave-de-prueba')
    pagina.locator('button:has-text("Desbloquear")').tap()
    expect(pagina.locator('[data-resultado]')).to_have_count(1)
