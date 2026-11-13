"""Rutas de Med en la raíz de su host (``med.tresvizo.com``). Todas se resuelven con ``reverse('med:…')``."""
from django.urls import path

from .vistas import consulta, documentos, pacientes, sistema

app_name = 'med'

urlpatterns = [
    path('', pacientes.inicio, name='inicio'),
    path('pacientes/', pacientes.buscar, name='pacientes'),
    path('registros/', pacientes.en_curso, name='en_curso'),
    path('pacientes/nuevo/', pacientes.alta_nueva, name='alta_nueva'),
    path('pacientes/nuevo/<uuid:borrador>/', pacientes.alta, name='alta'),
    path('pacientes/nuevo/<uuid:borrador>/guardar/', pacientes.alta_guardar, name='alta_guardar'),
    path('pacientes/nuevo/<uuid:borrador>/registrar/', pacientes.alta_registrar, name='alta_registrar'),
    path('pacientes/nuevo/<uuid:borrador>/descartar/', pacientes.alta_descartar, name='alta_descartar'),
    path('pacientes/fila/<str:coleccion>/', pacientes.fila, name='fila'),
    path('pacientes/<uuid:paciente>/', pacientes.expediente, name='expediente'),
    path('pacientes/<uuid:paciente>/editar/', pacientes.editar, name='editar'),
    path('pacientes/<uuid:paciente>/archivar/', pacientes.archivar, name='archivar'),
    path('pacientes/<uuid:paciente>/atender/', pacientes.atender, name='atender'),
    path('pacientes/<uuid:paciente>/evolucion/', pacientes.evolucion, name='evolucion'),
    path('documentos/gestor/<str:tipo>/<uuid:identificador>/', documentos.gestor, name='gestor'),
    path('documentos/lista/<str:tipo>/<uuid:identificador>/', documentos.lista, name='lista_documentos'),
    path('documentos/asociar/<str:tipo>/<uuid:identificador>/', documentos.asociar, name='asociar'),
    path('documentos/cola/<str:tipo>/<uuid:identificador>/<uuid:fila>/incorporar/', documentos.incorporar, name='incorporar'),
    path('documentos/cola/<str:tipo>/<uuid:identificador>/<uuid:fila>/retirar/', documentos.retirar, name='retirar'),
    path('documentos/<uuid:documento>/', documentos.visor, name='visor'),
    path('documentos/<uuid:documento>/archivo/', documentos.archivo, name='archivo'),
    path('documentos/<uuid:documento>/miniatura/', documentos.miniatura, name='miniatura'),
    path('documentos/<uuid:documento>/editar/', documentos.editar, name='editar_documento'),
    path('documentos/<uuid:documento>/foto/', documentos.foto, name='foto_paciente'),
    path('consultas/<uuid:consulta>/documentos/', documentos.panel_consulta, name='panel_documentos'),
    path('consultas/<uuid:consulta>/', consulta.consulta, name='consulta'),
    path('consultas/<uuid:consulta>/guardar/', consulta.guardar, name='guardar'),
    path('consultas/<uuid:consulta>/conflicto/', consulta.conflicto, name='conflicto'),
    path('consultas/<uuid:consulta>/captura/<str:tipo>/', consulta.captura, name='captura'),
    path('consultas/<uuid:consulta>/captura/<str:tipo>/<str:item>/', consulta.captura, name='captura_item'),
    path('consultas/<uuid:consulta>/quitar/<str:tipo>/<str:item>/', consulta.quitar, name='quitar'),
    path('consultas/<uuid:consulta>/revisar/', consulta.revisar, name='revisar'),
    path('consultas/<uuid:consulta>/finalizar/', consulta.finalizar, name='finalizar'),
    path('consultas/<uuid:consulta>/adenda/', consulta.adenda, name='adenda'),
    path('consultas/<uuid:consulta>/anular/', consulta.anular, name='anular'),
    path('consultas/<uuid:consulta>/restaurar/', consulta.restaurar, name='restaurar'),
    path('consultas/<uuid:consulta>/papelera/', consulta.papelera, name='papelera'),
    path('bloquear/', sistema.bloquear, name='bloquear'),
    path('desbloquear/', sistema.desbloquear, name='desbloquear'),
    path('tema.css', sistema.tema_css, name='tema'),
]
