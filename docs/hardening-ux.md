# Revisión de confianza y uso cotidiano

10 de septiembre de 2026. Implementación sobre el árbol de trabajo existente, con Python, Tkinter y ttk. Se conservaron la consulta continua, los datos estructurados, temas, marca, permisos, transacciones y visores. No se generó ejecutable ni instalador. Todos los ensayos y capturas descritos aquí usan datos ficticios y carpetas aisladas.

## Problemas corregidos

| Hallazgo | Resultado y protección |
|---|---|
| A. Alergias al retomar | Se reprodujo el contexto desactualizado. Al entrar se consulta el paciente actual y se actualiza la cabecera sin sustituir narrativa, cursor ni selección. |
| B. Temperatura existente | Se comprueba la edición de 98.6 °F → 37.0 °C → 98.6 °F y la persistencia de valor y unidad. El estado de la unidad anterior se sincroniza al cargar la toma. |
| C. Añadir repetido | Se reprodujo la pérdida o interrupción de la captura compartida. Añadir enfoca el editor existente; confirmar localiza el elemento por ID incluso si otras filas cambian de orden. |
| D. Desplazamiento horario | Fecha y hora conservan el desplazamiento ISO del registro al editar. Se preservan segundos cuando no cambia la hora; las tareas sin hora permanecen como fecha. |
| E. Primer archivo del alta | Seleccionar modifica y persiste el borrador aunque todavía no haya nombre. La recuperación comprueba el archivo fuente y distingue una ruta pendiente de una copia administrada. |
| F. Finalización con archivos | La revisión y el servicio impiden finalizar con selecciones sin resolver. Incorporar o retirar la selección es una decisión explícita; sin selecciones, finaliza normalmente. |
| G. Copia y sesión | Se reprodujo `busy` retenido tras cambiar la generación. La finalización interna limpia recursos aunque la entrega visual se invalide. La cola durable recupera los resultados bajo su doctor original. |
| H. Ctrl+K | Se reprodujo el foco incorrecto y otro efecto de Tk: su atajo de Text borraba el resto de la línea antes del manejador global. El enlace de clase dirige el foco al buscador visible y devuelve `break`. |

También se corrigieron la acumulación de vistas limpias, IDs ausentes en colecciones antiguas, campos de metadatos que podían sobrescribirse tras recuperar una edición, y una referencia circular en el historial al guardar metadatos combinados. Los conflictos conservan base, captura y versión guardada; las diferencias requieren elección antes de persistir. Una consulta y sus relaciones ya vinculadas conservan el paciente original.

### Corrección posterior: cierre de capturas

Se reprodujo el fallo al ejecutar el protocolo de cierre de una captura de medicamentos con una lista de ttk desplegada: `grab_current()` intentaba convertir el subwidget Tcl `popdown` en un widget Python y lanzaba `KeyError`, dejando la ventana abierta. El cierre compartido ahora repliega las listas y libera únicamente el control de entrada perteneciente a esa captura, sin convertir subwidgets internos a objetos Python. La nota, el cursor y el foco se conservan al volver.

Cuando hay datos sin aplicar, las decisiones para cerrar reciben foco y se distribuyen en una columna si no caben. Seguir editando regresa al campo; Conservar pendiente y volver mantiene incluso valores incompletos; Descartar captura no elimina elementos ya aplicados. En metadatos, la X distingue cerrar toda la ventana de regresar a su lista interna.

`tests/test_capture_closing.py` contiene siete regresiones: X con lista desplegada, decisiones en ventana pequeña, tres recorridos de diez clases de captura mediante X/Cancelar/Escape, recuperación de valores incompletos y cierre de metadatos. Las dos primeras fallaron antes del arreglo; las siete aprobaron después. La X se prueba invocando el protocolo `WM_DELETE_WINDOW` de la ventana Tk; esto no se presenta como clic manual sobre el marco de Windows. El resultado de la batería general posterior está en `artifacts/pytest-popup-close-final.txt`.

## Decisiones de uso

- Navegación y acciones importantes con icono y texto, conforme a esta petición más reciente. La galería de avatares sigue usando dibujos con ayuda y selección visible.
- Inicio prioriza buscar, retomar y atender; folio y edad ayudan a distinguir homónimos. Las cifras quedan después de las tareas.
- Agenda tiene acciones visibles, filtros por día/periodo y una consulta estable por cita. Abrir marca En consulta; finalizar marca Atendida en la misma transacción. Repetir Atender abre el mismo ID. Los seguimientos sin hora muestran «sin hora».
- La consulta conserva un espacio continuo. Las capturas aplicadas, guardadas y pendientes se distinguen; añadir o cancelar no confirma datos incompletos.
- La cola de archivos se guarda por doctor y destino. Reintentar conserva los éxitos; Volver a elegir original recupera una fuente ausente. La cola vacía y el progreso inactivo no ocupan una tabla adicional.
- Metadatos incompletos se recuperan también desde el expediente, con la revisión de origen. La resolución muestra nombres de campos y valores legibles, sin obligar a leer JSON.
- Estadísticas invalida la exportación al tocar un filtro; CSV y PDF usan la instantánea del resultado y el doctor seleccionado. Hoy se recalcula tanto al cambiar el día como al regresar a una vista previamente oculta.
- Importar CSV es un recorrido real de archivo, mapeo, vista previa, decisiones por fila y confirmación transaccional. Exportar distingue todos, filtrados y seleccionados con cantidad previa.
- Datos y respaldos muestra la carpeta activa y el último respaldo verificado. Restaurar en otra carpeta no cambia silenciosamente la base activa.

## Matriz de aceptación

«Automatizada» incluye comprobaciones de widgets reales de Tk y de JSON persistido; no equivale a uso manual ni a una captura. Los nombres siguientes corresponden a pruebas del repositorio. El recorrido nativo está delimitado en la sección siguiente.

| Caso | Evidencia y alcance |
|---|---|
| 01. Homónimo, autor y finalización | `test_attend_and_finalization_relationships_are_atomic_and_idempotent`, `test_linked_encounter_patient_and_relations_cannot_be_reassigned`; búsqueda y finalización por teclado en ventana nativa, con comprobación posterior del JSON. La sesión inicial del ensayo se prepara por código. |
| 02. Alta mínima y retorno | `test_workspace_patient_consultation_roundtrip`, `test_registration_draft_and_files_publish_together`; callback de creación al flujo de agenda. |
| 03. Ctrl+K | `test_resume_current_allergies_and_search_focus_without_changing_note`; además búsqueda nativa, flecha abajo y Enter. |
| 04. Ctrl+S | `test_single_capture_cancel_keyboard_autosave_failure_and_private_recovery`; foco, selección y persistencia en la batería de consulta. |
| 05. Añadir repetido | `test_shared_collection_repeated_add_and_stable_edit_identity`; conserva los valores pendientes. |
| 06. Identidad de elemento | Misma prueba, edición por ID después de reordenar; pruebas de estado de tomas en `test_consultation_context.py`. |
| 07. Temperatura | `test_existing_temperature_conversion_both_directions_and_durable_units`. |
| 08. Alergias | `test_resume_current_allergies_and_search_focus_without_changing_note`. |
| 09. Fecha y desplazamiento | `test_temporal_semantics_and_three_way_conflict`; relaciones y fechas en las pruebas de finalización/agenda. |
| 10. Archivo como primer cambio | `test_first_file_selection_is_durable_and_missing_source_is_reported`; incluye desaparición del original. |
| 11. Pendientes al finalizar | `test_complete_contextual_visit_final_view_and_pdf_match`, `test_attend_and_finalization_relationships_are_atomic_and_idempotent`; bloqueo en UI y servicio. |
| 12. Bloqueo y doctor | `test_copy_finishes_after_generation_change_and_retries_only_failures`, `test_application_lock_hides_capture_and_reconciles_copy`, `test_all_screens_session_change_and_private_drafts`. La primera simula generación; la segunda llama al bloqueo real de la app con reanudación programática; la tercera comprueba cambio de actor. No se automatizó el diálogo nativo de autenticación ni el bloqueo de Windows. |
| 13. Éxito parcial | `test_copy_finishes_after_generation_change_and_retries_only_failures`; conserva IDs de éxitos y reintenta el fallo. |
| 14. Recuperación | `test_incomplete_forms_and_file_queue_survive_restart`, `test_attachment_recovery_finds_committed_operation_without_original`, `test_document_buffer_recovery_keeps_base_revision_and_requires_conflict_choice`. Reapertura desde persistencia; no ensayo de corte eléctrico físico. |
| 15. Error y conflicto | Pruebas de autoguardado fallido, reemplazo atómico, transacción revertida y conflictos de consulta/documentos. La copia local sigue disponible si la persistencia falla. |
| 16. Repetición | Atender/finalizar transaccionales; incorporación con ID de operación y recuperación del commit. |
| 17. Cambio de día | `test_day_rollover_and_agenda_explicit_selection` y prueba de estadísticas con reloj sustituido; no espera nocturna real. |
| 18. Estadísticas y exportación | `test_statistics_invalidates_on_filter_edit_and_labels_selected_doctor`; respuesta vieja rechazada, exportación deshabilitada y etiqueta del doctor verificada. |
| 19. Importación | `test_import_mapping_mixed_rows_duplicates_failure_and_idempotent_retry`, `test_import_ui_mapping_preview_and_commit_and_bounded_views`; datos mixtos, mapeo, selección, fallo simulado, reintento y ausencia de pacientes parciales. |
| 20. Restauración | `test_restore_verified_separate_folder_and_invalid_backup`; integridad, copia separada y respaldo inválido. Configuración y mensaje indican que la base activa no cambió. |
| 21. Anular y restaurar | `test_annul_restore_permissions_history_and_statistics`; permiso, autoría, adendas y conteo. |
| 22. Teclado y tamaño | Pruebas de acciones/capturas a escalas Tk 1/1.25/1.5/2, pantallas vacías, datos largos, temas y focos; capturas nativas descritas abajo. No certifica cuatro escalas del sistema Windows ni lector de pantalla. |

La suite completa y su duración actual se registran en [Estado](estado.md) y `artifacts/pytest-hardening-final.txt`. Se ejecuta sin reintentos silenciosos, aislando las pruebas de escritorio en procesos separados para evitar contaminación entre intérpretes Tcl/Tk.

## Revisión visual e interactiva interna

`scripts/preview_hardening.py` crea una clínica ficticia en una carpeta temporal: dos pacientes homónimos con folios y edades diferentes, dos doctores, citas, una consulta y documentos sintéticos. Sus escenarios permiten revisar inicio, pacientes, agenda, consulta, documentos, conflictos, importación, configuración y acceso sin usar una base clínica real.

Se verificó por teclado en ventanas nativas Ctrl+K → escribir nombre/folio → flecha abajo → Enter. Se abrió la revisión con Ctrl+Enter y se confirmó con Tab y Espacio. La lectura final indicó Finalizada y la inspección independiente del JSON confirmó Ana Lucía Ramírez, RC-000001, Dra. Elena Martínez, cita Atendida, relación correcta y seguimiento `2026-09-10` sin hora inventada. La evidencia está en `artifacts/hardening-native-finalization.json`.

Los valores clínicos y el documento de ese ensayo se prepararon mediante la fixture. Su incorporación, edición y recuperación completas están verificadas por pruebas de widgets y servicios; no se presentan como captura manual de todos los campos. El control remoto del ratón no activó consistentemente los botones durante esta sesión; se usó teclado para las acciones nativas comprobadas. No se atribuye este resultado a un defecto de ratón de la aplicación sin una reproducción independiente.

El recorrido diseñado desde Inicio necesita dos cambios de página para buscar y entrar a la atención y uno para volver al Inicio. Desde una cita basta entrar a la consulta y volver. Signos vitales y documentos se capturan sobre la misma atención; cada captura exige Aplicar o resolver el pendiente. La finalización tiene una revisión y una confirmación. Este conteo describe las rutas de la implementación, no una medición de tiempos de un médico.

Las capturas nuevas se conservan en `artifacts/hardening-ui/`: 01 Inicio con homónimos, 02 búsqueda por folio, 03 consulta continua, 04 revisión final, 05 consulta finalizada, 06 documentos sin cola vacía, 07 importación con errores por campo, 08 conflicto de versiones y 09 agenda. Para evitar superposiciones de otras aplicaciones se puede usar `--front` exclusivamente en la demostración; no cambia el comportamiento de la aplicación normal. Las capturas de tamaños y capturas contextuales de la etapa anterior permanecen en `artifacts/consulta-contextual/` y `artifacts/ui-qa/`. Los artefactos están excluidos de Git. No hubo prueba de uso con profesionales clínicos ni certificación de accesibilidad. Tk no expuso un árbol de accesibilidad útil al inspector de este entorno.

## Rendimiento medido

Equipo de ensayo: Windows 11, compilación 26200, arquitectura AMD64, Python 3.13.14. Los tiempos dependen de este equipo y del almacenamiento local; no son una promesa de rendimiento. Cada volumen se ejecutó en un proceso separado, con un Store nuevo después de generar los archivos. Las consultas sintéticas varían entre cero y tres por paciente. Se compararon las mismas búsquedas, comprobando IDs y resultados no vacíos.

| Operación (ms) | 1 000 pacientes / 1 500 consultas | 10 000 pacientes / 15 000 consultas |
|---|---:|---:|
| Primera lectura de pacientes desde JSON | 5 697.039 | 14 543.617 |
| Búsqueda anterior con datos en memoria | 15.914 | 164.284 |
| Construcción del índice compacto | 24.490 | 250.496 |
| Búsqueda con índice en memoria | 0.750 | 3.992 |
| Abrir paciente con datos cargados | 154.894 | 237.308 |
| Guardar borrador | 12.018 | 22.244 |
| Retomar borrador | 6.692 | 6.027 |
| Incorporar documento pequeño sintético | 36.295 | 40.879 |
| Finalizar | 11.769 | 13.095 |
| Cambiar vista | 31.883 | 236.868 |
| Intervalo máximo entre pulsos del bucle Tk | 136.244 | 320.755 |

No hubo errores de interfaz en los dos ensayos completos válidos. El volumen de 1 000 se midió antes de habilitar los cuatro lectores de JSON; el de 10 000, después. La lectura fría de 10 000 pacientes antes de ese cambio tardó 57 895.012 ms; el ensayo posterior del mismo volumen tardó 14 543.617 ms. El primer intento de cargar todas las historias superó el límite de espera: no se cuenta como ejecución completa aprobada. El diagnóstico mostró lectura de archivos, no un fallo de Tcl. Se ajustaron lectores acotados y limpieza del ensayo antes de repetirlo.

Fuentes reproducibles: `artifacts/benchmark-hardening-1000.json`, `artifacts/benchmark-hardening-10000.json` y los logs del mismo nombre. `benchmark-hardening.log` contiene un intento descartado por una caché de fixture ya cargada: sus tiempos no deben usarse. Las lecturas iniciales de muchos JSON todavía pueden tardar segundos; trabajan fuera del hilo gráfico. No se introdujo una base de datos distinta.

## Ejecución y límites

Desde la carpeta del proyecto, en PowerShell:

```powershell
& '..\.venv\Scripts\python.exe' -m pytest -q
& '..\.venv\Scripts\python.exe' -m pytest -q tests/test_hardening.py
& '..\.venv\Scripts\python.exe' scripts/benchmark_hardening.py --count 1000
& '..\.venv\Scripts\python.exe' scripts/benchmark_hardening.py --count 10000
& '..\.venv\Scripts\python.exe' scripts/preview_hardening.py --view consultation
& '..\.venv\Scripts\python.exe' main.py
```

`main.py` usa la carpeta resuelta de Documentos. `--data-dir RUTA` permite una base separada. Los scripts de revisión usan sus propias carpetas temporales y no deben emplearse para capturar pacientes reales.

Persisten los límites de una aplicación local: no edición simultánea desde varias computadoras, JSON clínico sin cifrado de disco propio, auditoría local no inviolable, sin firma digital ni vaciado definitivo de papeleras. Los cambios externos de JSON mientras la aplicación está abierta no están soportados. CSV importa datos de identidad/contacto; no importa expedientes completos ni binarios. La selección de paciente de agenda sigue siendo un desplegable de pacientes activos y puede ser poco cómoda con catálogos grandes. El formato de fecha/hora no convierte las citas entre zonas distintas: conserva su fecha local y su desplazamiento original.

Windows de 32 bits, sistemas antiguos, instalador y pruebas de DPI real 100/125/150/200 % siguen requiriendo equipos y construcciones específicos. No están certificados por ejecutar desde Python en este equipo. La restauración se realiza en otra carpeta y requiere una acción explícita para abrirla como base separada.
