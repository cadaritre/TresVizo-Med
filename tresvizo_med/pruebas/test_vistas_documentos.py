"""Documentos: destino de subida, cola, incorporación, visor, versiones y documentos en consulta y borrador de alta."""
from pathlib import Path

import pytest
from tvplataforma.subidas import ErrorDeSubida
from tvplataforma.subidas.destinos import ArchivoSubido, destinos_registrados

from tresvizo_med.models import Documento
from tresvizo_med.servicios import Actor, consultas, documentos, pacientes
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
    return pacientes.guardar(web.actor, datos_paciente('Ana Muñoz'))


def subir(web, tmp_path, imagen, nombre='placa.png', color='white'):
    """Lo que hace el contrato de subidas: entrega al destino un archivo completo ya recibido."""
    origen = imagen(nombre, color=color)
    archivo = ArchivoSubido(ruta=origen, nombre=nombre, tipo='image/png', tamano=origen.stat().st_size, sha256='x')
    return destinos_registrados()['med.documento'].funcion(archivo, {}, web.usuario)


def test_el_destino_med_documento_esta_registrado_para_medicos():
    destino = destinos_registrados()['med.documento']
    assert destino.roles == (('med', 'medico'),) and destino.limite() == 50*1024*1024


def test_subida_valida_deja_el_archivo_en_la_lista_de_subidos(web, tmp_path, imagen):
    resultado = subir(web, tmp_path, imagen)
    assert resultado['nombre'] == 'placa.png' and resultado['tipo'] == 'image/png'
    fila = documentos.subidos(web.actor)[0]
    assert fila['id'] == resultado['subido_id'] and Path(fila['path']).is_file() and Path(fila['path']).suffix == '.png'


def test_subida_invalida_se_rechaza_con_mensaje_y_sin_residuos(web, tmp_path):
    falso = tmp_path/'falso.png'
    falso.write_bytes(b'no es una imagen')
    archivo = ArchivoSubido(ruta=falso, nombre='falso.png', tipo='image/png', tamano=16, sha256='x')
    with pytest.raises(ErrorDeSubida, match='dañado'):
        destinos_registrados()['med.documento'].funcion(archivo, {}, web.usuario)
    assert documentos.subidos(web.actor) == [] and not list((documentos.raiz()/'subidos').rglob('*.png'))


def test_asociar_incorporar_con_metadatos_y_listar(web, paciente, tmp_path, imagen):
    fila = subir(web, tmp_path, imagen)['subido_id']
    r = web.post(reverse('med:asociar', args=['paciente', paciente.id]), {'subido': fila}, **HTMX)
    html = r.content.decode()
    assert r.status_code == 200 and 'placa.png' in html and 'Incorporar al expediente' in html and 'id="lista-docs"' in html
    assert documentos.subidos(web.actor) == [] and len(documentos.cola(web.actor, paciente=paciente.id)) == 1
    r = web.post(reverse('med:incorporar', args=['paciente', paciente.id, fila]),
                 {'categoria': 'Laboratorio', 'titulo': 'Radiografía de tórax', 'notas': 'AP', 'fecha': '2026-09-01'}, **HTMX)
    assert r.status_code == 200 and 'Radiografía de tórax' in r.content.decode() and 'hx-swap-oob' in r.content.decode()
    x = Documento.objects.get()
    assert (x.titulo, x.categoria, x.descripcion, x.fecha_documento.isoformat(), x.nombre_original) == ('Radiografía de tórax', 'Laboratorio', 'AP', '2026-09-01', 'placa.png')
    assert documentos.cola(web.actor, paciente=paciente.id) == [] and not list((documentos.raiz()/'subidos').rglob('*.png'))
    assert documentos.ruta_verificada(web.actor, x.id).is_file()


def test_archivo_duplicado_se_avisa_y_se_permite_de_forma_explicita(web, paciente, tmp_path, imagen):
    primero = subir(web, tmp_path, imagen)['subido_id']
    web.post(reverse('med:asociar', args=['paciente', paciente.id]), {'subido': primero}, **HTMX)
    web.post(reverse('med:incorporar', args=['paciente', paciente.id, primero]), {'categoria': 'Estudio'}, **HTMX)
    segundo = subir(web, tmp_path, imagen)['subido_id']
    web.post(reverse('med:asociar', args=['paciente', paciente.id]), {'subido': segundo}, **HTMX)
    r = web.post(reverse('med:incorporar', args=['paciente', paciente.id, segundo]), {'categoria': 'Estudio'}, **HTMX)
    assert 'idéntico' in r.content.decode() and 'Incorporarlo de todos modos' in r.content.decode() and Documento.objects.count() == 1
    web.post(reverse('med:incorporar', args=['paciente', paciente.id, segundo]), {'categoria': 'Estudio', 'permitir_duplicado': 'on'}, **HTMX)
    assert Documento.objects.count() == 2


def test_retirar_de_la_cola_borra_la_copia(web, paciente, tmp_path, imagen):
    fila = subir(web, tmp_path, imagen)['subido_id']
    web.post(reverse('med:asociar', args=['paciente', paciente.id]), {'subido': fila}, **HTMX)
    ruta = Path(documentos.cola(web.actor, paciente=paciente.id)[0]['path'])
    r = web.post(reverse('med:retirar', args=['paciente', paciente.id, fila]), **HTMX)
    assert r.status_code == 200 and not ruta.exists() and documentos.cola(web.actor, paciente=paciente.id) == []
    assert web.post(reverse('med:retirar', args=['paciente', paciente.id, fila]), **HTMX).status_code == 404


def test_asociar_un_archivo_inexistente_o_a_un_destino_ajeno(web, cliente_med, paciente, tmp_path, imagen):
    assert web.post(reverse('med:asociar', args=['paciente', paciente.id]), {'subido': '00000000-0000-0000-0000-000000000001'}, **HTMX).status_code == 404
    borrador = consultas.guardar(web.actor, datos_consulta(paciente))
    otro = cliente_med('medico', username='otro')
    assert otro.post(reverse('med:asociar', args=['consulta', borrador.id]), {'subido': 'x'}, **HTMX).status_code == 404
    assert otro.get(reverse('med:gestor', args=['consulta', borrador.id])).status_code == 404
    assert web.get(reverse('med:gestor', args=['inventado', paciente.id])).status_code == 404


def test_visor_de_imagen_pdf_y_docx(web, paciente, tmp_path, imagen):
    import zipfile
    from tresvizo_med.dominio.documents import create_pdf
    from tresvizo_med.dominio.themes import DEFAULT_IDENTITY
    img = documentos.agregar(web.actor, imagen(), paciente=paciente.id)
    pdf = tmp_path/'carta.pdf'
    create_pdf(pdf, DEFAULT_IDENTITY, 'Carta', [('A', 'B')])
    doc_pdf = documentos.agregar(web.actor, pdf, paciente=paciente.id, categoria='Referencia')
    docx = tmp_path/'nota.docx'
    with zipfile.ZipFile(docx, 'w') as z:
        z.writestr('[Content_Types].xml', '<x/>')
        z.writestr('word/document.xml', '<x/>')
    doc_docx = documentos.agregar(web.actor, docx, paciente=paciente.id)
    html = web.get(reverse('med:visor', args=[img.id])).content.decode()
    assert 'data-zoom-imagen' in html and 'en_linea=1' in html and 'Usar como foto del paciente' in html and 'med-visor.js' in html
    html = web.get(reverse('med:visor', args=[doc_pdf.id])).content.decode()
    assert 'data-pdf' in html and 'pdf.min.mjs' in html and 'pdf.worker.min.mjs' in html and 'type="module"' in html
    assert 'nonce=' in html
    assert 'aplicación local' in web.get(reverse('med:visor', args=[doc_docx.id])).content.decode()


def test_archivo_en_linea_solo_para_imagenes_y_pdf(web, paciente, tmp_path, imagen):
    x = documentos.agregar(web.actor, imagen(), paciente=paciente.id)
    descarga = web.get(reverse('med:archivo', args=[x.id]))
    assert 'attachment' in descarga['Content-Disposition'] and descarga['X-Content-Type-Options'] == 'nosniff'
    en_linea = web.get(reverse('med:archivo', args=[x.id]), {'en_linea': '1'})
    assert 'inline' in en_linea['Content-Disposition'] and en_linea['Content-Type'] == 'image/png'
    Path(documentos.ruta_absoluta(x)).write_bytes(b'alterado')
    alterado = web.get(reverse('med:archivo', args=[x.id]))
    assert alterado.status_code == 409 and 'integridad' in alterado.content.decode()
    assert web.get(reverse('med:miniatura', args=[x.id])).status_code in (200, 404)


def test_miniatura_y_filtros_de_la_lista(web, paciente, tmp_path, imagen):
    a = documentos.agregar(web.actor, imagen('a.png', color='red'), paciente=paciente.id, categoria='Laboratorio', notas='glucosa')
    documentos.agregar(web.actor, imagen('b.png', color='blue'), paciente=paciente.id, categoria='Estudio')
    miniatura = web.get(reverse('med:miniatura', args=[a.id]))
    assert miniatura['Content-Type'] == 'image/png' and 'no-store' in miniatura['Cache-Control']
    url = reverse('med:lista_documentos', args=['paciente', paciente.id])
    assert web.get(url, {'q': 'GLUCOSA'}, **HTMX).content.decode().count('class="tv-tarjeta med-doc"') == 1
    assert web.get(url, {'categoria': 'Estudio'}, **HTMX).content.decode().count('class="tv-tarjeta med-doc"') == 1
    assert web.get(url, {'q': 'nada'}).content.decode().count('class="tv-tarjeta med-doc"') == 0


def test_editar_archivar_versiones_y_foto(web, paciente, tmp_path, imagen):
    x = documentos.agregar(web.actor, imagen('a.png', color='red'), paciente=paciente.id)
    r = web.post(reverse('med:editar_documento', args=[x.id]), {'titulo': 'Placa', 'categoria': 'Estudio', 'notas': 'n', 'fecha': '2026-09-02', 'revision': 1})
    assert r['Location'] == reverse('med:visor', args=[x.id])
    x.refresh_from_db()
    assert (x.titulo, x.categoria, x.revision) == ('Placa', 'Estudio', 2)
    web.post(reverse('med:editar_documento', args=[x.id]), {'titulo': 'Viejo', 'categoria': 'Estudio', 'revision': 1})  # revisión obsoleta
    x.refresh_from_db()
    assert x.titulo == 'Placa'
    web.post(reverse('med:editar_documento', args=[x.id]), {'accion': 'archivar', 'revision': 2})
    x.refresh_from_db()
    assert x.archivado
    web.post(reverse('med:foto_paciente', args=[x.id]))
    paciente.refresh_from_db()
    assert paciente.foto_documento == x.id
    # Nueva versión por la cola, con «reemplaza».
    nueva = subir(web, tmp_path, imagen, 'v2.png', 'green')['subido_id']
    web.post(reverse('med:asociar', args=['paciente', paciente.id]), {'subido': nueva, 'reemplaza': str(x.id)}, **HTMX)
    r = web.post(reverse('med:incorporar', args=['paciente', paciente.id, nueva]), {'categoria': 'Estudio'}, **HTMX)
    v2 = Documento.objects.get(version_de=x)
    assert [v.id for v in documentos.versiones(web.actor, x)] == [v2.id, x.id]
    html = web.get(reverse('med:visor', args=[v2.id])).content.decode()
    assert 'Versiones' in html and 'v2.png' in html


def test_documentos_en_una_consulta_borrador_y_finalizada(web, paciente, tmp_path, imagen):
    borrador = consultas.guardar(web.actor, datos_consulta(paciente))
    panel = web.get(reverse('med:panel_documentos', args=[borrador.id]), **HTMX).content.decode()
    assert 'Documentos de la consulta' in panel and 'tv-subida' in panel and 'data-asociar' in panel and 'capture="environment"' in panel
    assert 'Documentos' in web.get(reverse('med:consulta', args=[borrador.id])).content.decode()
    fila = subir(web, tmp_path, imagen)['subido_id']
    web.post(reverse('med:asociar', args=['consulta', borrador.id]), {'subido': fila}, **HTMX)
    # Un archivo sin incorporar impide finalizar.
    with pytest.raises(Exception, match='sin incorporar'):
        consultas.guardar(web.actor, datos_consulta(paciente, 'Finalizada', id=str(borrador.id)), 1)
    web.post(reverse('med:incorporar', args=['consulta', borrador.id, fila]), {'categoria': 'Laboratorio'}, **HTMX)
    assert Documento.objects.get().consulta_id == borrador.id
    assert 'Abrir (1)' in web.get(reverse('med:consulta', args=[borrador.id])).content.decode()
    final = consultas.guardar(web.actor, datos_consulta(paciente, 'Finalizada', id=str(borrador.id)), 1)
    segundo = subir(web, tmp_path, imagen, 'otro.png', 'blue')['subido_id']
    web.post(reverse('med:asociar', args=['consulta', final.id]), {'subido': segundo}, **HTMX)
    sin_motivo = web.post(reverse('med:incorporar', args=['consulta', final.id, segundo]), {'categoria': 'Estudio'}, **HTMX)
    assert 'motivo' in sin_motivo.content.decode() and Documento.objects.count() == 1
    web.post(reverse('med:incorporar', args=['consulta', final.id, segundo]), {'categoria': 'Estudio', 'motivo': 'Resultado tardío'}, **HTMX)
    assert Documento.objects.count() == 2 and final.adendas.count() == 1


def test_borrador_de_alta_con_documentos_que_pasan_al_expediente(web, tmp_path, imagen):
    from tresvizo_med.servicios import borradores
    borrador = borradores.guardar_borrador(web.actor, {'name': 'Luis'})
    html = web.get(reverse('med:alta', args=[borrador.id])).content.decode()
    assert 'Documentos e imágenes' in html and 'tv-subida' in html
    fila = subir(web, tmp_path, imagen)['subido_id']
    web.post(reverse('med:asociar', args=['borrador', borrador.id]), {'subido': fila}, **HTMX)
    web.post(reverse('med:incorporar', args=['borrador', borrador.id, fila]), {'categoria': 'Fotografía clínica'}, **HTMX)
    assert Documento.objects.get().borrador_id == borrador.id
    r = web.post(reverse('med:alta_registrar', args=[borrador.id]), {'name': 'Luis'})
    paciente = pacientes.Paciente.objects.get()
    assert Documento.objects.get().paciente_id == paciente.id and r.status_code == 302


def test_el_administrador_ve_documentos_pero_no_sube(cliente_med, web, paciente, tmp_path, imagen):
    admin = cliente_med('admin', username='jefa')
    documentos.agregar(web.actor, imagen(), paciente=paciente.id)
    html = admin.get(reverse('med:expediente', args=[paciente.id]), {'pestana': 'documentos'}).content.decode()
    assert 'placa' not in html and 'med-doc' in html and 'tv-subida' not in html
    assert admin.post(reverse('med:asociar', args=['paciente', paciente.id]), {'subido': 'x'}).status_code == 403


def test_estado_de_la_cola_y_tipo_del_archivo_en_palabras_de_uso():
    from tresvizo_med.templatetags.med import estado_cola, tipo_legible
    assert estado_cola('Pendiente de copia / reintento') == 'Falta incorporar' and estado_cola('Otro') == 'Otro'
    assert tipo_legible('image/jpeg') == 'Imagen JPEG' and tipo_legible('application/pdf') == 'PDF' and tipo_legible('x/y') == 'x/y'
