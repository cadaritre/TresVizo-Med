# Uso del espacio clínico

El primer arranque permite crear al administrador. Después, el acceso muestra tarjetas de doctores y una contraseña para el perfil seleccionado. El enlace tresvizo.com se abre únicamente al pulsarlo.

## Pacientes y borradores

La aplicación entra directamente en Pacientes. El buscador combina palabras del nombre, folio o teléfono y tolera mayúsculas, acentos y espacios; muestra 100 filas por página y conserva búsqueda, selección y posición. Folio y edad distinguen homónimos. Ctrl+K enfoca el buscador, flecha abajo entra a los resultados y Enter abre el expediente; Abrir expediente ofrece la misma acción con ratón. Atender / retomar ofrece primero el borrador del mismo paciente y doctor; rechazar esa propuesta no crea otra consulta. Registros en curso permite continuar altas incompletas y consultas privadas.

Nuevo paciente abre el espacio principal. Solo el nombre es obligatorio. La fecha admite escritura día/mes/año y calendario con mes y año directos. Si se desconoce el nacimiento, activar esa opción para registrar edad aproximada, unidad y fecha de referencia. No se deduce el sexo. Contacto y responsables se despliegan cuando se necesitan. Teléfonos, alergias, problemas y medicamentos se agregan como elementos que deben confirmarse.

El alta se autoguarda como borrador privado tras 900 ms sin cambios o cada cinco segundos durante escritura continua. También conserva campos incompletos, elementos sin confirmar y la cola de archivos. Guardar paciente publica el registro y sus documentos juntos; los documentos pendientes o fallidos deben incorporarse o retirarse explícitamente. Guardar y comenzar consulta publica el paciente y abre su atención directamente. Nuevo paciente desde la búsqueda propone esa continuación; un alta independiente usa Guardar paciente. Cancelar permite conservar o descartar el borrador sin crear un paciente.

## Consulta

La consulta deja a la vista Motivo de consulta, Diagnóstico o impresión e Indicaciones para el paciente. Síntomas y evolución y Notas de valoración se despliegan cuando hacen falta. Su contenido queda resumido si se pliega y se conserva en el borrador. No es necesario abrir secciones SOAP para completar una consulta básica; la nota final y los PDF mantienen esos campos clínicos.

Signos vitales, Medicamentos y Documentos tienen accesos superiores con cantidades. Sus resúmenes quedan al lado de la nota en ventanas amplias y pasan debajo al estrecharla. Exploración y mediciones permite revisar las tomas y escribir la exploración. Estudios y otras opciones conserva solicitudes, tratamientos previos y receta. Los textos y controles se mantienen al reorganizar la ventana; no se reconstruye la captura.

El encabezado mantiene paciente, folio, edad, fecha, estado y alergias. El doctor autenticado aparece en la cabecera de la aplicación. Más opciones en la consulta abre expediente, fecha/hora/tipo, evolución y receta. Los campos crecen al escribir; Ampliar / reducir campo sigue disponible con clic derecho. Ctrl+S guarda; Ctrl+Enter abre la revisión de Finalizar consulta. El diagnóstico que aún está escrito se incluye en esa revisión sin exigir pulsar Agregar antes; finalizar siempre requiere la confirmación final. Solo hay una captura contextual activa a la vez.

Signos vitales abre Registrar signos vitales con dos columnas y unidades explícitas. Más mediciones incluye glucosa, contexto y dolor. Aplicar incorpora una toma al borrador; Editar toma conserva su identificador y Nueva toma crea otra. El resumen muestra una sola toma identificada, sin mezclar valores de fechas distintas. El IMC requiere peso y estatura de esa toma. Ver evolución carga a demanda las gráficas y la tabla histórica, en segundo plano; los círculos vacíos corresponden al borrador. Consultar el histórico desde una captura conserva esa edición como pendiente.

Aplicar al borrador y guardar en disco son estados distintos. Cancelar o cerrar una captura modificada permite descartarla, continuar editando o conservarla pendiente. Guardado se muestra después de completar la escritura. Las capturas incompletas se recuperan para el mismo doctor y no se confirman automáticamente. Finalizar consulta muestra pendientes con acceso al campo correspondiente y una sola confirmación final.

La X cierra una captura sin cambios aunque quede una lista desplegable abierta. Si hay cambios, enfoca Conservar pendiente y volver; las otras opciones son Seguir editando y Descartar captura. Estas acciones se acomodan en filas cuando la ventana se estrecha. En documentos, la X cierra la ventana completa; Volver a documentos regresa a la lista cuando se están editando sus detalles. Cerrar la captura nunca aplica automáticamente una pauta ni finaliza la consulta.

Cada medicamento separa producto, principio activo, presentación, concentración, dosis, unidad, vía, frecuencia, duración, fechas, cantidad e instrucciones. La pauta se previsualiza al editarla. El catálogo local y los favoritos reutilizan la identidad del producto; las dosis se completan para cada consulta. Los tratamientos habituales o previos se incorporan pendientes de revisión. Los estudios tienen estado y observaciones. Finalizar no programa tareas. Una captura de seguimiento recuperada de una versión anterior puede resolverse explícitamente y quedar como información de la nota.

La receta y el resumen se revisan en un visor PDF por páginas antes de exportarse. La apariencia personal no modifica los colores ni la identidad de impresión. Las correcciones de consultas finalizadas se registran mediante adendas.

Al regresar a la consulta, el aviso de alergias refleja el expediente actual sin reemplazar la nota en edición. Si otra edición ya guardó una versión diferente, Revisar conflicto conserva tu captura y muestra las diferencias. Elige qué conservar de cada campo en conflicto antes de Combinar y guardar; también puedes guardar una copia de recuperación. Los cambios independientes se combinan. Un registro finalizado exige el mecanismo de corrección autorizado y no se sobrescribe desde un borrador antiguo.

## Herramientas secundarias y módulos retirados

Más opciones agrupa Registros en curso, Mis estadísticas, Configuración, Exportar y respaldar y Mi perfil. La importación administrativa continúa en Exportar y respaldar, con los mismos permisos. Exportar y respaldar también conserva un acceso directo en la navegación. Más acciones en Pacientes reúne exportación y archivo/restauración. El historial del expediente incluye Abrir atención completa y Enter, además del doble clic.

Agenda y Seguimientos ya no aparecen en navegación, consulta ni estadísticas. Sus archivos y vínculos anteriores se conservan en Documentos y en los respaldos. Finalizar una consulta no modifica sus estados ni crea nuevos seguimientos.

## Documentos e imágenes

Arrastrar archivos al área de documentos o seleccionar varios JPEG, PNG, PDF y DOCX. Se admiten hasta 50 MiB por archivo e imágenes de hasta 40 megapíxeles. Elegir categoría, incorporar y revisar el resultado individual. La copia administrada conserva el original aunque se mueva el archivo de origen. Una repetición idéntica requiere aceptación explícita.

La lista permite buscar, filtrar categoría, doctor, fechas y origen, ordenar y mostrar archivados. La galería usa miniaturas de imágenes; los otros documentos conservan su título. Hay paginación, metadatos editables, nuevas versiones y exportación individual o de un paquete con documentos seleccionados. Las imágenes tienen zoom y desplazamiento; el PDF carga una página a la vez. DOCX se abre con la aplicación local solo tras una acción explícita.

Una selección pendiente solo conserva la referencia al original: todavía no es un documento protegido. La cola se recupera para el mismo doctor y paciente/consulta. Si falta el original, Volver a elegir original permite localizarlo. Reintentar incorpora únicamente los elementos no guardados. Los archivos ya incorporados no se borran al retirar una selección. Antes de finalizar hay que incorporar o retirar los pendientes, incluidos los errores de copia.

Los cambios incompletos del título, fecha o descripción se conservan como edición pendiente. Cerrar permite conservarlos, descartarlos o seguir editando. Al reabrir se comprueba la versión que estaba editándose; una diferencia posterior requiere revisión y no reemplaza silenciosamente los metadatos de otra edición.

## Perfil, apariencia y sesión

Mi perfil ofrece 16 ilustraciones, iniciales o foto con encuadre y zoom, datos profesionales y reducción de movimiento. El administrador puede editar el perfil de otros doctores en Configuración → Doctores. Las fotos de perfil se limitan a 10 MiB y 12 megapíxeles.

Apariencia presenta paletas y vista previa. Personalización avanzada contiene los selectores y valores hexadecimales; Más opciones contiene guardar con nombre, duplicar, renombrar, importar, exportar, restablecer y eliminar temas propios. Aplicar cambia la interfaz actual sin reconstruir formularios. La preferencia de cada doctor puede heredar la paleta clínica. La pantalla de acceso usa la apariencia general.

Bloquear oculta pantallas y visores y conserva la sesión. Los resultados visuales de trabajos en curso esperan al desbloqueo. Cambiar doctor guarda los borradores, espera las operaciones de archivos y oculta el contenido antes del nuevo acceso. Si el disco impide guardar, la aplicación conserva los cambios en la sesión anterior y exige recuperarla.

## Archivar y recuperar

El administrador archiva o restaura pacientes desde Pacientes. Las consultas históricas siguen contando; iniciar nuevas atenciones requiere reactivar el expediente. El responsable retira sus borradores a una papelera privada y puede restaurarlos con el mismo identificador. Anular una consulta finalizada exige motivo, conserva su contenido y la excluye de estadísticas. Restaurar una consulta anulada vuelve a incluirla; ambas acciones dejan una adenda y respetan responsable/administrador. No reprograman ni eliminan seguimientos anteriores. Los documentos archivados conservan sus originales e historial. Esta entrega no vacía papeleras ni elimina originales automáticamente.

Exportar y respaldar incluye copias verificadas, restauración en una carpeta nueva y revisión de documentos ausentes. Abrir la copia restaurada es una acción separada; nunca reemplaza automáticamente los datos activos. Véase [Migración y recuperación](migracion.md).

## Estadísticas y transferencia de datos

Mis estadísticas muestra consultas finalizadas, pacientes únicos y diagnósticos del periodo y doctor indicados. Al modificar filtros se deshabilita exportar hasta pulsar Actualizar y recibir los datos correspondientes. CSV y PDF llevan el doctor y periodo de ese resultado; las cifras previas se identifican como pendientes de actualización.

Exportar pacientes permite elegir Todos los activos, Resultado filtrado o Seleccionados, con cantidad antes de elegir destino. CSV contiene identidad/contacto; JSON conserva campos estructurados del paciente. Para un expediente con documentos usa el paquete del expediente. Los textos CSV que una hoja de cálculo podría interpretar como fórmula reciben un apóstrofo protector; JSON conserva el texto original sin esa transformación. No elimines esa protección para abrir archivos no confiables en una hoja de cálculo.

Importar CSV admite UTF-8, separadores coma/punto y coma/tabulador, hasta 10 MB y 10 000 filas. Elige archivo, asigna columnas y revisa la vista previa. Solo se requiere nombre; nacimiento usa AAAA-MM-DD. Los errores se muestran por fila/campo. Las posibles coincidencias por nombre o teléfono se explican y no se importan por defecto: aceptarlas significa registrar a una persona distinta, nunca fusionar. Confirma las filas elegidas para guardarlas en una transacción. Si la base cambia después de la vista previa, vuelve a revisarla antes de confirmar. No se ofrece importación de expedientes completos desde JSON/PDF/DOCX.

Configuración → Datos y respaldos muestra la ubicación activa y el último respaldo válido. Una restauración verificada informa la carpeta nueva y que la actual sigue activa. Abrir la copia inicia explícitamente esa base separada. Un error de destino conserva las opciones elegidas para poder corregirlo y reintentar.

Para iniciar desde el código y ejecutar verificaciones, consulta [Revisión de confianza y uso cotidiano](hardening-ux.md#ejecución-y-límites).
