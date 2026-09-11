# Uso y recuperación

Crear el primer administrador en el asistente inicial. Los administradores agregan doctores en Configuración → Doctores. Elegir doctor y contraseña al iniciar sesión. Cada usuario conserva su propia preferencia de apariencia.

En Pacientes se puede buscar por nombre, expediente o teléfono sin distinguir acentos o mayúsculas. Nuevo paciente requiere nombre; los demás campos pueden completarse después. Abrir el expediente mediante doble clic o Enter. Los antecedentes vacíos se muestran como no registrados.

Confirmar al paciente antes de iniciar atención. La consulta permite texto libre organizado como SOAP. Ctrl+S guarda; Ctrl+Enter solicita revisión antes de finalizar. La pantalla muestra si el borrador se guardó realmente. Las consultas finalizadas permiten adendas. Al abrir un borrador desde Consultas se recupera su contenido persistido.

Bloquear/cambiar doctor oculta ventanas clínicas. Si falla el guardado de un borrador, se exige al mismo doctor autenticarse para recuperarlo antes de permitir cambio de sesión. Esa recuperación conserva contenido en memoria; no protege frente al apagado del equipo si el disco no permite guardar.

Los PDF se muestran en vista previa antes de elegir destino. Usan exclusivamente identidad y colores de documentos; el tema personal no los altera. La aplicación no afirma que una receta cumpla requisitos de una jurisdicción ni que un nombre constituya firma digital.

## Respaldos

Exportar y respaldar → Crear respaldo completo verificado produce un ZIP con datos, configuración, adjuntos y avatares existentes, y un manifiesto SHA-256. Elegir un medio adicional bajo control de la clínica. Las exportaciones de pacientes no incluyen cuentas ni hashes.

Esta versión no tiene restauración guiada. Para recuperación técnica: cerrar todas las instancias, conservar una copia íntegra de la carpeta actual, verificar el manifiesto con `Transfer.verify_backup`, inspeccionar el contenido y reconstruir en una carpeta separada mediante personal técnico. Abrirla con `--data-dir` para validar antes de sustituir la instalación. Las rutas de logos clínicos guardadas como absolutas deben reconfigurarse si cambia la ubicación. No extraer archivos de respaldos no confiables directamente sobre expedientes.

No borrar archivos corruptos para forzar un arranque vacío. Conservarlos y solicitar recuperación técnica desde un respaldo verificado. La aplicación muestra el fallo de lectura sin reemplazarlo automáticamente.
