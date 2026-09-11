# Consulta en un solo espacio de trabajo

Implementación del 10 de septiembre de 2026. Sustituye las cinco pestañas del editor de consulta por una página continua. El resto del acceso, alta de pacientes, perfiles y navegación mantiene su diseño.

## Flujo implementado

El encabezado conserva identidad del paciente, folio, edad, responsable, fecha, estado y alergias. Fecha, hora y tipo se editan en una captura breve. Los cinco accesos rápidos tienen icono y texto, con conteos reales, y se distribuyen según el ancho disponible.

Motivo, evolución, valoración y plan se escriben directamente. Exploración física está desplegada cuando contiene texto. Ampliar cambia la altura del mismo editor: no se reconstruye la nota ni se reinicia su historial de deshacer. Aplicar una herramienta devuelve el foco y conserva la posición de lectura.

Signos vitales abre una captura de dos columnas. Cada toma conserva identificador, fecha, hora y unidades; editar y registrar otra son acciones distintas. El resumen identifica una toma de esta consulta y permite elegir entre varias. Si solo se registró una presión, la otra aparece como ausente. Más mediciones incluye glucosa, contexto y dolor. El IMC se calcula exclusivamente con peso y estatura de la misma toma. El histórico se carga en segundo plano a demanda, separado de la captura.

Medicamentos muestra primero los campos de la pauta y adapta la etiqueta y ayuda de frecuencia. Las fechas, cantidades e indicaciones adicionales siguen disponibles; si contienen datos se despliegan. Catálogo y favoritos están dentro de la misma herramienta. Los tratamientos previos se agregan pendientes de revisión y requieren confirmación de la pauta antes de finalizar. Los resúmenes muestran medicamento, dosis, unidad, vía, frecuencia, duración e indicaciones.

Estudios y seguimiento usan capturas específicas. Los documentos se muestran como filas de nombre, tipo y estado, sin cargar todas las miniaturas al abrir la consulta. Selección y arrastrar/soltar abren la gestión existente. Editar metadatos usa el mismo espacio de la herramienta; abrir una vista previa regresa primero a la consulta y conserva la cola. Incorporar un archivo es una escritura explícita, distinta de cerrar su gestor.

Revisar y finalizar muestra la consulta y sus problemas pendientes, con acceso a cada campo o captura. Confirmar finalización es la única confirmación final. La lectura posterior también es continua y conserva documentos, PDF, receta y adendas. El presentador común incorpora valoración narrativa, notas de estudios y seguimiento tanto a la lectura como al PDF.

## Persistencia y recuperación

`ConsultationDraft` mantiene datos aplicados, capturas temporales y cola de documentos sin depender de widgets. Cada captura parte de una copia; aplicar valida antes de publicarla. Cancelar o cerrar con cambios ofrece descartar, seguir editando o conservar pendiente. Los elementos pendientes se distinguen de los datos clínicos aplicados y bloquean la finalización.

El autoguardado conserva valores incompletos y solo muestra Guardado después de persistir. Utiliza las revisiones del servicio y no introduce escrituras asíncronas que puedan sobrescribir una revisión posterior. Un fallo de disco conserva el estado y permite reintentar.

El esquema clínico sigue en versión 2. `editor_state.version: 3` conserva capturas por tipo e identificador. Al leer el formato anterior se recuperan header, followup, colecciones, tomas incompletas y cola, sin confirmar automáticamente sus contenidos. El primer guardado del formato anterior incluye una copia íntegra del registro original en `backups/editor-consulta/UUID-rREVISION.json`, dentro de la misma transacción. Bloqueo y cambio de sesión ocultan también las capturas, liberan la captura de teclado y conservan el trabajo para su doctor.

## Comprobaciones

La batería general aprobó **67 pruebas en 51,38 s**, registrada en `artifacts/pytest-context-final.txt`. Después del ajuste visual final se repitieron las diez pruebas del módulo; su resultado está en `artifacts/context-tests-final.txt`.

- Consulta sin pestañas, escritura, dos tomas, cancelación de la edición de una toma sin cambios en su versión aplicada, dos tratamientos y edición de frecuencia.
- Estudio, seguimiento y documento; guardado, destrucción de la vista, reapertura y finalización; un único seguimiento asociado.
- PDF generado y texto extraído coincidentes con tratamientos, pauta, IMC, estudio, indicaciones y motivo de seguimiento.
- Cursor, selección y foco de la nota conservados; Enter en una nota de captura inserta un salto de línea; Escape con cambios conserva la captura hasta resolverla.
- Una sola captura activa y bloqueo de navegación a otra pantalla durante esa captura.
- Fallo de guardado y reintento, autoguardado con captura abierta, recuperación de valores parciales y de metadatos sin aplicar.
- Recuperación del formato anterior y comparación íntegra de su copia previa.
- Bloqueo, cambio de doctor y aislamiento de borradores; reapertura por el responsable original.
- Cambio de paleta con una captura abierta y acciones dentro de la ventana en factores de escala Tk 100/125/150/200 %.

## Capturas reales

Todas contienen información ficticia y corresponden a ventanas reales de 1366×768. El encabezado y el pie permanecen fijos; las vistas intermedias muestran diferentes posiciones del mismo desplazamiento.

| Vista | Captura |
|---|---|
| Nota principal con datos | [Consulta](../artifacts/consulta-contextual/01-consulta.png) |
| Signos vitales con la consulta detrás | [Contexto de captura](../artifacts/consulta-contextual/02-signos-vitales.png) |
| Captura compacta de una toma existente | [Mediciones](../artifacts/consulta-contextual/03-captura-mediciones.png) |
| Resumen de una toma y selector entre varias | [Tomas](../artifacts/consulta-contextual/04-resumen-tomas.png) |
| Dos tratamientos legibles | [Tratamientos](../artifacts/consulta-contextual/05-tratamientos.png) |
| Estudios, seguimiento y documentos | [Secciones inferiores](../artifacts/consulta-contextual/06-estudios-documentos.png) |
| Consulta sin contenido | [Estado vacío](../artifacts/consulta-contextual/07-consulta-vacia.png) |
| Nombre extenso, treinta párrafos y doce documentos | [Contenido largo](../artifacts/consulta-contextual/08-nota-extensa.png) |

Para repetir la demostración: `python scripts/preview_consultation.py --view filled`. Las otras vistas son empty, long, vitals, medication, review y final. Se usa una clínica temporal separada de los datos habituales. Cerrar la demostración finaliza esa instancia.

## Límites comprobados

Los cuatro factores de escala corresponden a pruebas de Tk, no a cambiar las cuatro configuraciones reales de Windows. No se certificaron monitores con DPI distintos, Windows antiguos ni 32 bits. No se generó un ejecutable ni un instalador. El formato de datos, las reglas clínicas y la identidad de impresión se conservaron; la revisión no constituye una validación médica de las pautas ficticias utilizadas.
