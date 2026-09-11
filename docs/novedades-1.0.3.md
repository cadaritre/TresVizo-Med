# Versión 1.0.3

La identidad de la aplicación utiliza la cruz médica azul y turquesa. Los recursos activos son `assets/clinica_cruz.png`, `assets/clinica_icono.png` y `assets/clinica.ico`; los PNG son imágenes rasterizadas y no se presentan como SVG. El ICO contiene 16, 20, 24, 32, 40, 48, 64, 128 y 256 píxeles. Los recursos anteriores se conservan para mantener referencias históricas.

Al crear una clínica se elige su nombre y logo (cruz médica o archivo propio PNG, JPG o ICO). El archivo se copia a la configuración local, así que mover el original no rompe la identidad. Puede aplicarse también a las ventanas. El ejecutable y los accesos instalados llevan el icono médico de la aplicación; el logo elegido por la clínica corresponde a sus ventanas y documentos. Una actualización no sustituye la identidad documental de una clínica existente.

El primer administrador configura también una contraseña maestra. La acción Olvidé mi contraseña del acceso restablece la contraseña del perfil seleccionado y conserva sus datos. La clave maestra y las contraseñas admiten ocho caracteres como mínimo y se guardan mediante scrypt y sal individual. No se escriben en auditorías ni se distribuyen claves universales con el programa. La recuperación rechazada aplica una espera persistente; el cambio válido queda registrado.

La foto de un médico se guarda al confirmar Guardar foto de perfil en la ventana de recorte. Las vistas abiertas actualizan su imagen sin reconstruir pantallas. Cancelar antes de guardar el recorte mantiene la imagen anterior; los demás campos del perfil siguen usando Guardar perfil.

Exportar consultas CSV incluye un registro por atención, paciente y médico, estado, fecha, tipo y nota. Las mediciones más recientes incluyen sus unidades en columnas independientes. Prescripciones, diagnósticos, todas las tomas de signos vitales, estudios, adendas y seguimiento histórico se conservan además como JSON dentro de columnas dedicadas. Los adjuntos se distribuyen mediante Exportar expediente. El alcance excluye borradores ajenos y consultas archivadas; los borradores propios se incluyen solo al solicitarlo.

El calendario conserva el mes de la fecha existente y diferencia los controles de entrada de la ventana emergente. El selector de sexo contiene Masculino y Femenino; los valores anteriores de expedientes no se reclasifican automáticamente.
