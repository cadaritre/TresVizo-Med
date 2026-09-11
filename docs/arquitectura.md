# Arquitectura y datos

Actualización 11/09/2026: el [recorrido simplificado 1.0.1](recorrido-simple.md) sustituye la entrada y organización descritas en esta etapa anterior. Agenda y Seguimientos están retirados; la consulta usa secciones SOAP progresivas. El MSI 1.0.0 conserva la entrega anterior.

`main.py` inicia la aplicación. `main_window.py` coordina sesión, configuración y tareas; `workspace.py` conserva navegación y vistas. `patient_ui.py`, `consultation_ui.py`, `attachment_ui.py`, `statistics_ui.py` y `profiles.py` separan los flujos. `widgets.py` y `components.py` son controles reutilizables. `services.py` concentra permisos y registros; `care.py` aporta borradores, catálogo, evolución y migración. `clinical_models.py` valida y presenta mediciones y pautas sin depender de Tk. `attachments.py` administra originales y asociaciones. `storage.py` implementa JSON, caché, transacciones y exclusión de segunda instancia. `themes.py` persiste apariencia; `ui_theme.py` aplica tokens. `branding.py` mantiene identidad y `documents.py` consume solo ajustes de impresión. `transfer.py` crea paquetes, respaldos y restauraciones verificadas.

Las operaciones de fondo usan un ejecutor de un trabajador. Los widgets se actualizan mediante `after()`. Cada trabajo captura actor y generación. Su finalización interna (`settled`) se ejecuta una vez aunque se invalide la entrega visual; elimina la operación pendiente y libera estados ocupados. La entrega de resultados espera si la sesión está bloqueada y se omite si cambió el actor/generación. La reconciliación documental consulta su cola durable. Al cerrar sesión se ocultan las ventanas y se espera a que terminen operaciones en curso antes de cambiar el actor.

`editing_state.py` define el conflicto de versión y la combinación de base/local/remoto; `conflict_ui.py` presenta las diferencias y conserva una salida de recuperación. `schedule_ui.py` administra agenda y seguimiento; `import_ui.py` y `export_ui.py` muestran los recorridos de transferencia. `document_edit_ui.py` conserva los buffers de metadatos y su revisión base fuera de la vida de un widget.

## Estructura de almacenamiento

La consulta continua usa `consultation_state.py` como estado independiente de Tk y `consultation_tools.py` para capturas temporales. Los textos actualizan el estado central; las ventanas publican una copia validada al aplicar. La captura activa se conserva por separado en `editor_state.version: 3`, con tipo, identificador y valores parciales. Los resúmenes no leen widgets destruidos. El autoguardado se serializa en el hilo principal y usa la revisión del servicio; los trabajos de documentos e histórico retornan mediante `after()` y un identificador de solicitud.

La recuperación del formato anterior no exige migrar masivamente la clínica. Al guardar por primera vez una consulta con `editor_state` anterior, la transacción conserva una copia íntegra del registro original en `backups/editor-consulta/UUID-rREVISION.json` junto al nuevo borrador. Los datos clínicos siguen en esquema 2. La revisión de finalización elimina únicamente el estado temporal resuelto; la autoría y las relaciones no cambian.

```text
Documentos/RegistroClinico/
  config/appearance.json
  config/identity.json
  config/schema.json
  config/profiles/UUID.json
  config/attachment_categories.json
  config/security.json
  config/last_backup.json
  config/clinic-logo-UUID.png
  data/users/UUID.json
  data/patients/UUID.json
  data/encounters/UUID.json
  data/appointments/UUID.json
  data/followups/UUID.json
  data/registration_drafts/UUID.json
  data/attachment_queues/UUID.json
  data/document_edits/UUID.json
  data/import_batches/UUID.json
  data/attachments/UUID.json
  data/medication_catalog/UUID.json
  data/audit/UUID.json
  attachments/originals/UUID.ext
  attachments/thumbnails/UUID-tamano.png
  avatars/UUID.png
  operations/UUID/journal.json
  backups/antes-migracion-fecha.zip
```

Los modelos clínicos nuevos usan `schema_version: 2`, UUID y fechas ISO 8601; apariencia conserva su formato compatible v1. La migración conserva los textos previos en `legacy` sin interpretarlos como registros estructurados. Pacientes y consultas agregan `revision`, `created_at`, `created_by`, `updated_at`, `updated_by`. La revisión impide sobrescribir una versión obsoleta. El expediente usa un folio independiente del nombre. `patient_id` relaciona consultas, agenda y seguimientos; `doctor_id` conserva al responsable; `captured_by` identifica al capturista original. Las adendas tienen UUID, actor, fecha, motivo y contenido.

Colas, buffers y recibos de importación son archivos adicionales con `schema_version: 1`; no reescriben el esquema clínico 2. Las colas antiguas embebidas en un borrador se recuperan cuando aún no existe la cola compartida. Las colas y buffers se identifican por doctor/destino; un buffer de metadatos incluye la revisión y copia base para detectar cambios posteriores al reinicio. Un campo nuevo no interpreta ni convierte textos clínicos heredados.

La consulta asociada a una cita usa un UUID determinista y relaciones bidireccionales. Iniciar la atención y cambiar la cita a En consulta se confirman juntos; finalizar la atención, crear su seguimiento y marcar la cita Atendida también. La repetición reutiliza los IDs. Los registros ya vinculados no pueden cambiar de paciente ni perder su relación original. Los seguimientos sin hora almacenan únicamente fecha; editar una fecha/hora existente conserva el desplazamiento ISO, sin conversión automática a otra zona.

Las contraseñas usan scrypt con salt aleatorio individual de 16 bytes, N=16384, r=8, p=1; se guarda algoritmo y parámetros junto al hash. La comparación usa tiempo constante. La limitación de intentos de esta versión es en memoria; no sobrevive al reinicio.

## Apariencia v1

`appearance.json` contiene `schema_version`, `clinic` (ID de tema), `custom` (ID → tema), `owners` (ID → UUID del creador) y `users` (UUID → `{inherit, theme}`). Los temas de fábrica se definen en código. Los nombres personalizados son etiquetas; sus UUID permanecen estables al renombrar.

Un tema importable/exportable contiene exactamente `schema_version: 1`, `name` y `tokens`. Los 19 tokens son: `primary`, `accent`, `background`, `surface`, `header`, `sidebar`, `text`, `muted`, `border`, `button`, `secondary`, `selection`, `focus`, `chart1` a `chart6`. Los colores deben ser `#RRGGBB`. No se admiten campos desconocidos, claves duplicadas, versiones distintas, nombres vacíos, colores abreviados ni archivos mayores de 64 KB.

Se valida el documento completo antes de escribir. La configuración en memoria se sustituye solo después del reemplazo atómico correcto. Cada escritura usa archivo temporal, flush, fsync y reemplazo. Un archivo ilegible no se sustituye por datos vacíos. La exclusión de segunda instancia protege el mismo directorio; no proporciona soporte multicomputadora.

## Transacciones y recuperación

Store.transaction prepara JSON y binarios bajo operations/UUID, conserva versiones anteriores, persiste el journal, reemplaza los destinos y marca el commit. La entidad, asociaciones relacionadas y auditoría clínica se publican juntas. Al arrancar, las operaciones sin commit se revierten antes de cargar vistas. Los fallos conservan material de recuperación. La revisión de origen detecta ediciones concurrentes; el identificador del borrador evita duplicar un alta confirmada por reintentos.

La caché de entidades se reconstruye desde JSON. Su primera lectura ocurre fuera del bloqueo global; las actualizaciones concurrentes se incorporan antes de exponer la instantánea. Una recuperación invalida las lecturas en curso. Búsquedas e indicadores costosos usan el trabajador de fondo y descartan resultados obsoletos. Las llamadas a PDFium se serializan en el mismo ejecutor; las imágenes de Tk se crean y se liberan en el hilo gráfico.

Lecturas iniciales de más de 256 JSON usan cuatro lectores, en tandas de 128; solo se paraleliza la lectura, no la publicación transaccional ni el acceso a Tk. Store mantiene generación por tipo y época de caché. La búsqueda usa un índice compacto normalizado, invalidado al cambiar pacientes, y copia solo la página resultante. El expediente selecciona su historia sin copiar en profundidad todas las historias. Workspace retiene hasta ocho páginas dinámicas limpias; protege la actual, editores modificados, capturas activas y trabajos ocupados, y elimina referencias a widgets destruidos.

Una operación de archivo lleva ID estable antes de iniciar. El ID de metadatos se deriva de actor/destino/operación, de modo que una recuperación puede reconocer un commit aun si desapareció el original. Cada éxito se persiste individualmente y una repetición omite los ya incorporados. Una operación en proceso se reconcilia antes de volver a mostrarse como pendiente o guardada.

La combinación de conflictos acepta automáticamente cambios independientes; un campo cambiado de dos maneras necesita elección explícita. Las colecciones completas en conflicto se revisan como un campo, sin fusionar filas clínicamente por semejanza. Identidad, revisión y autoría provienen de la versión guardada. Los registros cerrados no se editan desde este mecanismo.

La importación CSV valida archivo, columnas, filas y duplicados antes de persistir. Un recibo estable por lote permite reconocer reintentos. Pacientes, auditoría y recibo se publican en una transacción; una modificación de pacientes desde la vista previa exige revisarla de nuevo. Las estadísticas guardan una instantánea de alcance junto al resultado; los exportadores consumen esa instantánea y no variables de filtro que puedan haber cambiado.

## Límites operativos

La exclusión de instancia se aplica a una carpeta y no proporciona edición simultánea desde varias computadoras. No modificar los JSON externamente mientras la aplicación esté abierta. Los archivos clínicos están en texto claro: los permisos del programa no sustituyen los permisos de Windows. La auditoría local conserva historial, pero no es inviolable. La copia de seguridad sigue siendo necesaria ante pérdida física del dispositivo.
