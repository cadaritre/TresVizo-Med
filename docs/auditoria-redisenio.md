# Auditoría del rediseño

Actualización 11/09/2026: el [recorrido simplificado 1.0.1](recorrido-simple.md) sustituye la entrada y organización descritas en esta etapa anterior. Agenda y Seguimientos están retirados; la consulta usa secciones SOAP progresivas. El MSI 1.0.0 conserva la entrega anterior.

> Registro histórico anterior al hardening. El estado vigente, las correcciones y los límites comprobados están en [hardening-ux.md](hardening-ux.md). La nueva petición vuelve a exigir icono y texto en navegación y acciones principales; las observaciones de esta auditoría describen su fecha de revisión.

Revisión del 10 de septiembre de 2026 contra `Prompt_Rediseno_UI_UX_TresVizo_Med.txt` del Escritorio, el código actual y las pruebas de la aplicación. **El documento no está implementado al 100 %.** Los flujos principales están operativos; la tabla distingue lo existente de las diferencias concretas. No se asigna un porcentaje basado solo en la presencia de pantallas.

La petición posterior de mostrar los iconos sin nombres sustituye las indicaciones del documento de mantener texto junto a cada acción y una barra lateral de 220–240 unidades. Se mantienen ayudas, foco y teclado. Los nombres de personas y las etiquetas clínicas conservan su texto.

| Apartado | Estado comprobado | Diferencia o límite |
|---|---|---|
| 0, identificación y edad | Sexo explícito, fecha legible con calendario de mes/año, edad calculada, fecha desconocida y edad aproximada | La validación no cubre con mensajes junto al campo todos los datos posibles. |
| 1–3, sistema visual | Base clara, jerarquía ttk, colores centralizados y estados derivados | Tipografía, espaciados, tamaños y radios todavía no forman un catálogo completo de tokens; hay tamaños y fuentes definidos en pantallas. No hay implementación general de esquinas redondeadas. |
| 4, navegación | Páginas persistentes, selección, encabezado con doctor, perfil, bloqueo y cambio de sesión | Barra compacta con iconos conforme a la instrucción más reciente. |
| 5 y 17, acceso y perfiles | Tarjetas, una contraseña, limpieza al cambiar doctor, búsqueda/paginación, 16 avatares, foto con recorte, iniciales y selección destacada | La galería de acceso usa hasta tres columnas fijas; falta adaptación completa de columnas y una ayuda para nombres muy largos. El doctor seleccionado muestra su nombre junto a la contraseña, sin repetir allí su avatar. |
| 6 y 18, Inicio | Métricas, citas, consultas pendientes, altas en curso y seguimientos reales; actualización en segundo plano | Las listas siguen en una columna aun con ventana amplia; no todos los estados vacíos tienen una acción contextual propia. |
| 7, pacientes y expediente | Búsqueda, filtros, paginación, selección/posición conservadas, expediente e historial, acceso a consulta | Algunas tablas conservan la barra de desplazamiento aunque no sea necesaria. |
| 8, 16 y 20, alta de paciente | Pantalla principal con cuatro áreas, formulario de una/dos columnas, contactos, emergencia, alergias, problemas, antecedentes, medicamentos, notas y documentos antes del alta | Faltan resúmenes de estado en todas las secciones cerradas, algunos campos condicionales/autocompletados, validación junto a cada campo y nombre/folio en el encabezado de edición. La revisión muestra identidad y conteos; debe ampliar el detalle de contactos y documentos. |
| 9 y 16.6, consulta | Narrativa, diagnósticos, dosis/unidad/vía/frecuencia/duración separadas, pauta legible, catálogo/favoritos, medicamentos anteriores sujetos a revisión, estudios y seguimiento | No hay selección automática de dosis. La cobertura de UX no equivale a validar una indicación médica. |
| Signos vitales | Tomas múltiples, unidades, validaciones numéricas, IMC de la misma toma, evolución, presión sistólica/diastólica y tabla de valores exactos | No se declaran umbrales clínicos automáticos ni diagnóstico a partir de gráficas. |
| 10, apariencia | Paletas, previsualización, editor avanzado, contraste, temas personalizados, JSON, preferencias por doctor y documentos separados | Los diálogos nativos de Windows mantienen su apariencia del sistema. |
| 11, estadísticas | Periodos, tres indicadores, actividad, diagnósticos, pacientes frecuentes, registros/distribuciones y CSV/PDF | Carga inicial sintética de 50 000 consultas medida en 10,831 s; sigue habiendo margen para reducir la latencia. |
| 12, interacción | Foco y selección, carga asíncrona, búsqueda diferida, expansión de 150 ms y reducción de movimiento | No existe una revisión exhaustiva con lector de pantalla; Tk ofrece accesibilidad nativa limitada. |
| 13, conservación | Persistencia JSON, autoría/permisos, borradores privados, archivo y anulación, preferencias, importación y respaldo | No hay eliminación definitiva de información clínica ni edición simultánea entre computadoras, conforme al alcance acordado. |
| 19.1–19.3, adjuntos | Originales administrados, metadatos, hashes, cola, arrastrar/soltar, progreso, duplicados explícitos, galería, filtros y visores de imagen/PDF; DOCX por apertura explícita | La cola aún no muestra tamaño ni miniatura/icono por archivo. El destino usa una descripción genérica; debe mostrar nombre y fecha. El filtro distingue expediente/consulta pero no permite elegir una consulta concreta. La edición de categoría/observaciones usa acciones separadas. |
| 19.4, autoría e historial | Permisos de acceso, versiones, archivado, adendas posteriores a consultas finalizadas y ocultación al bloquear | Los originales se conservan. |
| 19.5, migración y respaldo | Esquema versionado, respaldo previo verificado, preservación de textos/IDs, transacción recuperable, migración idempotente y restauración separada con hashes | La incorporación de adjuntos valida sus relaciones, pero la migración no hace todavía una validación global de todas las relaciones heredadas antes de publicar. |
| 20.3–20.5, borradores | Alta privada con archivos, recuperación de campos parcialmente capturados, publicación coordinada, guardado idempotente y continuidad entre páginas | El descarte conserva archivos administrados; la política acordada de no borrar físicamente sustituye la limpieza automática que pedía el documento. |
| Marca e iconos | Logo propio, enlace explícito, identidad de impresión separada, identificador Windows y recursos ICO; botones con icono sin texto permanente | No se reconstruyó el instalador ni se modificaron accesos directos anclados previamente por el usuario. |
| 14–15, verificación | Pruebas de servicios y ventanas nativas, capturas sintéticas reales y simulación de cuatro escalas de Tk | Pendiente comprobar las cuatro escalas reales de Windows, monitores con DPI distintos, Windows antiguos y 32 bits. No se compiló en esta revisión. |

## Correcciones de esta revisión

- Registro del identificador `TresVizo.Med.Desktop` antes de crear Tk y asignación del ICO a ventanas de la aplicación. La API utilizada identifica el proceso ante la barra de tareas y debe ejecutarse antes de presentar la interfaz: [Microsoft, SetCurrentProcessExplicitAppUserModelID](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid).
- Barra lateral de 80 unidades; acciones Lucide y avatares sin etiquetas permanentes. Nombres de doctores preservados. Ayudas con ratón/teclado y colores de iconos derivados de sus estados.
- Selección visible de avatar y actualización del icono de la sección activa al navegar o cambiar paleta.

## Evidencia reproducible

Código principal: `app/workspace.py`, `app/patient_ui.py`, `app/consultation_ui.py`, `app/attachment_ui.py`, `app/profiles.py`, `app/branding.py`, `app/icons.py`, `app/ui_theme.py`, `app/care.py` y `app/storage.py`.

La ejecución de `python -m pytest -q` aprobó **57 pruebas en 31,16 s** en este equipo. El registro de esta revisión está en `artifacts/pytest-icon-audit.txt`. Las nuevas pruebas consultan la identidad del proceso en Windows, comprueban iconos nativos y resoluciones del ICO, activan la navegación mediante teclado y verifican ayudas, selección de avatar y colores de todas las paletas. La lectura del identificador y de los recursos de ventana no es una captura visual del botón de Explorer en la barra de tareas.

La [guía visual](guia-visual.md) enlaza las capturas con datos sintéticos. El [estado de entrega](estado.md) conserva los resultados funcionales y de carga anteriores. La aplicación se abre desde `main.py`; los ejecutables de entregas anteriores no incluyen estos cambios.
