# Recorrido simplificado · 1.0.1

El código fuente del 11 de septiembre de 2026 conserva las herramientas existentes y reorganiza su entrada. El instalador MSI 1.0.0 anterior permanece intacto; esta revisión todavía no se ha compilado como MSI.

## Entrada y funciones secundarias

La sesión abre Pacientes con buscador, Nuevo paciente y Registros en curso. Los resultados muestran nombre, expediente, edad y contacto; flecha abajo, Enter y botones permiten trabajar sin descubrir el doble clic. La búsqueda, selección y posición sobreviven a la navegación. Atender / retomar busca primero un borrador del mismo paciente y doctor; dos solicitudes consecutivas no generan consultas duplicadas. Si hay varios borradores antiguos, propone el más reciente; los demás siguen accesibles en Consultas y Registros en curso.

Más opciones reúne registros incompletos, estadísticas, configuración, perfil y transferencia. Exportar y respaldar conserva además un acceso directo. La importación, revisión de integridad y restauración conservan sus permisos administrativos. Más acciones en la lista de pacientes reúne exportación y archivo/restauración.

## Alta y consulta

El alta usa una pantalla desplazable con nombre, nacimiento o edad desconocida/aproximada, sexo y estado de alergias. Contacto, emergencia, antecedentes, medicación y documentos se despliegan a demanda y muestran un resumen. El único dato obligatorio continúa siendo el nombre. Guardar y comenzar consulta publica el paciente y sus documentos e inicia la atención sin repetirlos; Guardar paciente sirve para un registro independiente.

La consulta tiene S — Subjetivo, O — Objetivo, A — Análisis y P — Plan. Cada sección conserva la explicación de SOAP y un resumen editable desde sus controles. S empieza abierta; los accesos superiores permanecen visibles y permiten ampliar cualquier sección sin cerrar las demás. Los Text y formularios se conservan al plegar: no se reconstruye la captura. El borrador guarda el estado abierto/cerrado de las cuatro secciones.

O contiene mediciones, exploración y evolución; A contiene diagnósticos/impresiones y valoración libre; P contiene indicaciones, medicamentos y opciones de tratamientos/estudios. Documentos muestra qué está incorporado a la consulta y qué sigue pendiente. Finalizar consulta mantiene la revisión de requisitos actuales y abre directamente la sección de un error. No se añaden requisitos opcionales ni contenido clínico automático. La lectura final y los PDF mantienen los campos originales y las adendas.

## Agenda y Seguimientos retirados

Se retiró la pantalla de agenda, sus rutas y accesos, las acciones de programación y los indicadores de citas/seguimientos de Estadísticas. Finalizar una consulta ya no crea seguimientos ni cambia estados de citas. Los archivos anteriores y sus relaciones no se borran ni migran: continúan en Documentos y respaldos. La información de seguimiento que ya pertenecía a una nota sigue legible como dato histórico. Las capturas pendientes anteriores conservan una vía de resolución explícita; no se ofrecen capturas nuevas de seguimiento.

## Verificación

La suite completa aprobó **114 pruebas en 142,39 segundos** (`artifacts/pytest-simple-verified.txt`). Tras el ajuste final de foco del alta, se repitieron los ocho casos del recorrido y la recuperación de formularios/archivos: **9 pruebas en 31,52 segundos** (`artifacts/pytest-simple-final-focus.txt`). La sintaxis de todos los módulos Python y `git diff --check` terminaron sin errores.

| Recorrido | Comprobación |
| --- | --- |
| Buscar, distinguir homónimos y retomar | Búsqueda/selección conservadas, folios distintos y reintento sin duplicación. |
| Alta mínima y atención | Solo nombre, alergias no interrogadas y consulta vinculada al paciente recién guardado. |
| SOAP sencillo | Secciones progresivas, requisitos de finalización, foco en el campo pendiente y lectura final. |
| Medicamentos, mediciones y documentos | La regresión de consulta contextual compara valores, unidades, IDs, fechas, PDF y archivos al guardar/reabrir. |
| Historial | Botón Abrir atención completa y Enter; autor, fecha, nota y documentos conservados. |
| Recuperación y fallos | Capturas incompletas, colas, conflictos, fallo simulado de guardado y retorno del cursor. |
| Datos anteriores | Notas heredadas intactas; archivos de citas/seguimientos idénticos byte a byte al finalizar. |

Pruebas específicas: `tests/test_simple_workflow.py`, junto con la suite de cierre de capturas, consulta contextual, hardening, temas y distribución. Se comprueban acciones esenciales en 1024×768 a escala normal y en 1366×768 con escalado Tk de 125/150/200 %. Esto no equivale a cambiar físicamente el DPI de Windows ni a certificar todos los monitores.

La demostración usa una carpeta temporal y datos ficticios:

```powershell
..\.venv\Scripts\python.exe scripts\preview_simple.py --view patients
```

F1 muestra Pacientes, F2 Alta, F3 SOAP vacío, F4 Más opciones, F5 una nota antigua y F6 una consulta con mediciones, tratamiento y documento de prueba. Las capturas de ventanas reales se guardan en `artifacts/ui-simple/`: `pacientes.jpg`, `alta.jpg`, `soap.jpg`, `opciones.jpg`, `historial.jpg` y `consulta-con-datos.jpg`. Se revisaron sobre la paleta clara; las regresiones de temas siguen verificando cambios sin reconstruir controles. Los informes de pruebas están en `artifacts/pytest-simple-*.txt`; ambos directorios están excluidos de Git.

No se modificó la base clínica real ni se sustituyó la instalación abierta. No se compiló un instalador 1.0.1, no se publicó un nuevo commit y no se ha validado una PC de 32 bits en esta revisión.
