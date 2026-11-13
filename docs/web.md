# TresVizo Med web (rama `web`)

Estado al cierre de ME-6 (13-11-2026). El diseño completo está en `med-web.md` del repositorio TresVizo-Portal; este
documento dice qué se construyó, qué cambió respecto al diseño y cómo se verifica.

## Qué es

App Django `tresvizo_med` (paquete `tresvizo-med-web`, etiqueta `med`) que corre dentro del Portal TresVizo en
`med.tresvizo.com`. Depende de `tvplataforma` 1.x (permisos, plantilla base, tareas, subidas). La rama `main` sigue siendo el
escritorio 1.0.3, congelado.

```text
tresvizo_med/
  dominio/       reglas puras (sin Django ni Tk), portadas de app/ con git mv
  models/        modelos de la base tv_med (alias med), migraciones en migrations/
  servicios/     reglas de Clinic, Care, Attachments y Appearance sobre PostgreSQL
  vistas/ formularios/ templates/ static/    interfaz HTMX sobre la plantilla base de tvplataforma
  tareas.py      PDF, paquete del expediente y exportación completa (cola med)
  subidas.py     destino de subida «med.documento»
  limpieza.py    limpieza diaria enganchada a tv_limpiar
  pruebas/       pytest-django; corren solas con PostgreSQL local
paridad/         escritorio (main, vía git archive) frente a la rama web con las mismas entradas
e2e/             Playwright (flujos de escritorio y móvil) y carga de 10 000 pacientes
```

## Cambios respecto a `med-web.md`

- **Sin importación desde el escritorio (§5, ME-5).** El propietario no tiene pacientes en el escritorio: Med web arranca vacío
  y no hay migración. Se quitaron las tablas de históricos de agenda y seguimientos y el SHA-256 de lotes de ZIP
  (migración `0002`). Se conservan la importación de pacientes por CSV y la exportación completa en el formato de respaldo del
  escritorio. Texto propuesto para `med-web.md`:
  - §5: «Descartado el 13-11-2026: no hay datos del escritorio que migrar. Si algún día los hubiera, este recorrido (ensayo en
    base desechable, asignación de personas a cuentas, verificación con `verify_backup`) sigue siendo el diseño.»
  - §3: la fila «Importar desde TresVizo Med escritorio» y la de «Agenda y Seguimientos» pasan a «No aplica».
  - §4: quitar `med_historico_cita`, `med_historico_seguimiento` y el tipo «ZIP del escritorio» de `med_lote_importacion`.
  - §7.2: «No aplica». Plan: ME-5 descartado; PO-6 depende solo de ME-6; F3, pasos 1 y 3 del propietario no hacen falta.
- **Subidas (§3, Documentos).** El contrato de subidas solo envía `destino`, `name`, `type` y `sha256`; el destino no sabe a qué
  expediente va el archivo. El archivo queda en la lista «subidos» de la persona y la página lo asocia a su destino. Se simplifica
  cuando `tvplataforma` acepte metadatos propios.
- **PDF con Liberation Sans** en lugar de Segoe UI: la paridad de PDF es de texto y de páginas, no de bytes.
- **Sin conexión.** Med no usa service worker, `localStorage` ni IndexedDB. Sin señal, el navegador muestra su propia página de
  error al navegar y Med avisa «Sin conexión» dentro de la página abierta; no hay una página «Sin conexión» propia porque
  requeriría un service worker.
- **Folios** de una secuencia de PostgreSQL: un lote o alta que se revierte puede dejar huecos.

## Criterios de aceptación (`med-web.md` §7)

| # | Criterio | Estado | Evidencia |
| --- | --- | --- | --- |
| 1 | Paridad funcional | Cumplido, con los matices de la tabla de abajo | `e2e/test_flujos.py` reproduce los recorridos de `recorrido-simple.md` y `uso.md` |
| 2 | Importación de un ZIP real | **No aplica** (no hay datos del escritorio) | — |
| 3 | Paridad de salidas | Cumplido | `paridad/` (PDF por texto y páginas, CSV de consultas y pacientes byte a byte) |
| 4 | Reglas | Cumplido | finalizada inmutable, borrador ajeno invisible, conflictos de dos pestañas, 404 sin Med: `pruebas/` y `e2e/` |
| 5 | Suspender saca de Med en la siguiente petición | Cumplido | `pruebas/test_servicios_permisos.py`, `e2e/test_flujos.py` |
| 6 | Rendimiento con 10 000 pacientes y 15 000 consultas | Cumplido | `e2e/test_carga.py` (cifras abajo) |
| — | Móvil (`med-web.md` §8) | Cumplido en Chromium a 360 px; falta probar en iPhone y Android reales | `e2e/test_movil.py` |
| 7 | Respaldo y restauración con Med | Parcial | la exportación completa se verifica con `verify_backup`; el respaldo de `tv_med` y su ensayo de restauración son de PO-6 |
| 8 | Pruebas solas y dentro del armazón | Parcial | solas: sí; dentro del armazón: PO-6 |

## Paridad funcional, fila por fila (`med-web.md` §3)

Las filas no mencionadas están implementadas como describe el diseño.

| Fila | Estado |
| --- | --- |
| Alta: elementos «a confirmar» | Filas editables (teléfonos, alergias, problemas, medicamentos habituales); la marca «por revisar» solo existe en los medicamentos de la consulta |
| Expediente: cabecera fija | La cabecera no queda fija al desplazar |
| Tratamientos previos por revisar | Se muestran con la insignia «Por revisar»; no se incorporan automáticamente desde el expediente |
| Conflicto: copia de recuperación | Lo escrito se conserva en la sesión y se resuelve campo por campo; no se genera un archivo de recuperación |
| Documentos: filtros | Texto, categoría y archivados; sin filtro por médico, fechas u origen ni orden elegible |
| Exportar pacientes «seleccionados» | El servicio y la URL aceptan `ids`; la pantalla exporta activos, archivados o todos con filtro de texto, sin casillas de selección |
| Perfil: reducir movimiento | Se guarda y se aplica a las animaciones de Med |
| Importar desde el escritorio; Agenda y Seguimientos | No aplica (ver arriba) |
| Configuración → Seguridad, General (inicio con Windows) | Desaparecen, como en el diseño |

## Cifras de carga (13-11-2026)

10 000 pacientes y 15 000 consultas sintéticas (los 100 pacientes con más consultas concentran la cola), PostgreSQL 16 local,
Mac de 16 GB. Se mide en el servidor con el cliente de pruebas de Django (sin red ni navegador); cada medición verifica que la
respuesta fue correcta y que trae el contenido esperado.

| Operación | Mediana | Percentil 95 | Límite |
| --- | --- | --- | --- |
| Búsqueda (HTMX, 60 consultas con nombres, folios y teléfonos) | 5,3 ms | 6,9 ms | < 300 ms |
| Búsqueda, página completa | 6,2 ms | 10,0 ms | — |
| Apertura de expediente (resumen) | 1,7 ms | 2,1 ms | < 500 ms |
| Expediente, pestaña Consultas | 2,2 ms | 2,6 ms | < 500 ms |
| Expediente del paciente con más consultas (48) | 4,5 ms | 5,5 ms | < 500 ms |
| Evolución de ese paciente | 6,6 ms | 8,4 ms | — |
| Autoguardado de una consulta | 2,2 ms | 2,7 ms | < 200 ms |
| Estadísticas de toda la clínica (15 000 consultas) | 513 ms | 567 ms | — |
| Exportar el CSV de consultas de toda la clínica | 3,9 s | 3,9 s | — |

La exportación completa de consultas se hace dentro de la petición; con muchos más datos conviene pasarla a una tarea.

## Pruebas de punta a punta

16 recorridos con Playwright (Chromium 1254, Playwright 1.65), todos verdes: búsqueda con atajos, alta con borrador que sobrevive a
recargar, consulta completa hasta finalizar, adenda, anulación y restauración, conflicto de dos pestañas, subida reanudable de
imagen y PDF con visores, PDF de receta con vista previa, estadísticas con exportación, exportar pacientes y consultas, Bloquear,
suspender a un médico; y en teléfono (360 px): sin desplazamiento horizontal en 20 pantallas, foto con la cámara que se sube o
falla con mensaje, sin conexión, «Med no guarda nada» (sin service worker, `localStorage`, `sessionStorage`, IndexedDB ni caché)
y Bloquear. Cualquier error de JavaScript o de la CSP en el navegador hace fallar la prueba.

## Verificación

- `pytest` (en la raíz): pruebas de dominio, servicios, vistas por ruta (sin sesión, 404, 403, 405) y flujos. PostgreSQL 16 local.
- `pytest paridad`: extrae `main` con `git archive` y compara salidas.
- `e2e/ejecutar.sh e2e --ds=tresvizo_med.pruebas.ajustes_e2e`: Playwright con Chromium; toma el turno de la Mac y levanta su
  PostgreSQL desechable. Falla ante cualquier error de JavaScript o violación de la CSP.
- Carga: `e2e/ejecutar.sh e2e/test_carga.py --ds=tresvizo_med.pruebas.ajustes_e2e -m carga -s`.

Pendiente de personas: probar en iPhone con Safari y en Android con Chrome reales (cámara, una mano, 360 px), y la validación
del propietario.
