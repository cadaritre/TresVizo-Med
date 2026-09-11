# Estado de implementación

## Verificación realizada

- Pruebas automatizadas de temas prediseñados, variantes de controles, persistencia por doctor, herencia clínica, cambios de sesión, permisos de temas, importación inválida, claves JSON duplicadas, corrupción conservada y fallo de reemplazo atómico.
- Prueba Tkinter real que cambia las cinco paletas conservando widgets, texto, cursor, selección, foco y ventanas secundarias.
- Pruebas de autoría, adendas, revisiones obsoletas, último administrador, autenticación, pacientes únicos, diagnósticos múltiples, CSV seguro y PDF con textos largos.
- Inspección visual de la ventana de Configuración en paletas clara y oscura; aplicación directa mediante la interfaz.
- PDF sintético renderizado con Poppler y revisado visualmente. No se utilizaron expedientes reales.
- Primer arranque del ejecutable portable inspeccionado en una carpeta de prueba vacía: aparece el asistente de creación, sin cuentas precargadas.

La ejecución del 10 de septiembre de 2026 pasó 42 pruebas en Windows 11 con Python 3.13.14. Se verificaron los canales alfa y las nueve resoluciones del .ico. Se inspeccionaron las variantes del logo sobre fondo claro y oscuro en tamaños de 16 a 256 px. Las pruebas simulan factores Tk de 100 %, 125 %, 150 % y 200 % y comprueban que las cuatro acciones del editor permanecen dentro de la ventana; no cambian la escala del sistema operativo. PyInstaller generó la carpeta portable correctamente. El servicio de identidad abrió el sitio correcto en el navegador predeterminado (Chrome). No se declara validación clínica, normativa, de accesibilidad integral ni de todos los equipos Windows.

## Alcance pendiente del encargo general

La carpeta inicial estaba vacía. Se construyó una base funcional y se priorizó la implementación de apariencia e identidad solicitada en los apartados 25 y 26. Los apartados anteriores no están completos:

- No hay todavía modelos completos de signos vitales, prescripciones estructuradas, catálogos/favoritos, estudios, adjuntos ni plantillas personales.
- Pacientes ofrece campos básicos; faltan edad pediátrica contextual en pantalla, tutor y estados estructurados completos de antecedentes.
- La agenda es una lista; faltan vistas diaria/semanal, duración, solapamiento y apertura de consulta vinculada a cita.
- Estadísticas incluye actividad, pacientes únicos, nuevos/recurrentes, comparación, diagnósticos, motivos y distribuciones. Faltan preferencias de tarjetas, inicio de semana configurable, tabla de pacientes frecuentes con accesos y panel completo de pendientes.
- No hay asistente de importación completo, restauración guiada, migraciones, respaldos automáticos/retención ni transacciones de múltiples archivos.
- No hay avatares, perfiles profesionales completos, ajustes de densidad/tamaño, microanimaciones ni modo de movimiento reducido (la interfaz actual no anima).
- No se ha realizado la prueba de carga de 10 000 pacientes y 50 000 consultas. Las listas todavía no están paginadas.
- Falta una evaluación exhaustiva del escalado real de Windows a 125 %, 150 % y 200 % y de todas las combinaciones posibles de paleta.

Estos límites requieren trabajo adicional antes del uso con datos clínicos reales. El instalador se prepara mediante un script; su generación y firma requieren las herramientas de distribución y una revisión de entrega.
