# Estado de la entrega de rediseño

Actualización 11/09/2026: el [recorrido simplificado 1.0.1](recorrido-simple.md) sustituye la entrada y organización descritas en esta etapa anterior. Agenda y Seguimientos están retirados; la consulta usa secciones SOAP progresivas. El MSI 1.0.0 conserva la entrega anterior. La revisión actual aprobó 114 pruebas y una repetición final de 9 casos de alta/consulta/recuperación; se revisaron seis capturas de ventanas reales con datos sintéticos.

Implementación sobre TresVizo-Med, 10 de septiembre de 2026. El rediseño y las correcciones de cierre están incluidos en la distribución MSI **1.0.0 x64**. Se puede seguir ejecutando desde Python para desarrollar. Consulta [instalación, versiones y actualización](distribucion.md).

El estado actual se detalla en [Revisión de confianza y uso cotidiano](hardening-ux.md): correcciones A–H, matriz de 22 recorridos, pruebas, mediciones y límites. La [auditoría del rediseño](auditoria-redisenio.md) se conserva como registro histórico de la etapa anterior.

Se conserva la [consulta en una sola pantalla](consulta-contextual.md), con capturas contextuales, estado central, recuperación de pendientes y lectura final continua. La revisión actual amplía esas protecciones a navegación, agenda, metadatos, importación y trabajos de archivos.

## Implementado

- Navegación clara y persistente; Inicio con citas, borradores y seguimientos; perfiles con 16 avatares, fotografía recortable y reducción de movimiento.
- Alta completa en el espacio principal, datos demográficos, contactos, alergias, problemas y medicamentos estructurados; borradores privados recuperables.
- Consulta con narrativa, diagnósticos por elementos, medicamentos con dosis y frecuencia separadas, catálogo/favoritos, revisión de tratamientos previos, estudios y seguimiento.
- Varias tomas de signos vitales, unidades, IMC de la misma toma y evolución con presión sistólica/diastólica, fechas personalizadas, tabla exacta y marcadores provisionales.
- Adjuntos administrados, cola, arrastrar y soltar mediante tkdnd, progreso, validación, duplicados explícitos, metadatos, versiones, archivo, filtros, miniaturas y visores de imágenes/PDF. Apertura DOCX local explícita.
- Archivo/restauración de pacientes, papelera privada de borradores y anulación con motivo; originales e historial conservados.
- Migración respaldada, transacciones recuperables de JSON y binarios, restauración verificada en carpeta separada y paquetes de expediente.
- Galería y vista previa de temas, personalización avanzada, preferencias por doctor e identidad de impresión separada. Logo y enlace TresVizo conservados.
- Contexto clínico actualizado sin sustituir la nota, búsqueda con foco real, colecciones por ID, conflictos revisables y colas documentales durables por doctor/destino.
- Agenda vinculada a una consulta reutilizable, finalización transaccional con cita/seguimiento, cambio de día y protección de la asociación al paciente.
- Importación CSV con mapeo, vista previa, errores por fila, duplicados explícitos y transacción; exportación con alcance/cantidad y estadísticas con filtros coherentes.
- Navegación y acciones principales con icono y texto según la petición de hardening; avatares con ayuda y sin etiquetas permanentes.
- MSI por usuario con identidad de actualización estable, versión compartida entre EXE/interfaz/instalador, accesos e iconos propios. Configuración → General permite activar o desactivar el inicio al entrar a Windows; las actualizaciones respetan el estado.

## Verificación

El rediseño inicial aprobó 55 pruebas, la consulta contextual 67, el hardening 84 y la corrección de cierre 91. La suite con distribución e inicio de Windows aprobó **106 pruebas en 81,38 segundos**, con Python 3.13 en Windows. El resultado está en artifacts/pytest-distribution-final.txt, extraído de artifacts/release-x64.log. La corrección de capturas cubre listas desplegables que bloqueaban la X, decisiones de cierre con foco y retorno a la consulta conservando la captura. `git diff --check` terminó sin errores.

El ejecutable compilado aprobó comprobaciones de Tcl/Tk, tkdnd, pantalla de acceso, icono y generación/renderizado de PDF. La prueba MSI usa una familia aislada y datos sintéticos: instalación, actualización con inicio apagado/encendido, reparación, rechazo de downgrade, bloqueo con proceso abierto, reversión de un fallo durante instalación y desinstalación con conservación byte a byte de expedientes, credenciales y adjuntos. El orden final instala primero los archivos nuevos y solo después retira el producto anterior, dentro de la transacción. Se comprobó además el estado registrado del producto anterior tras el fallo.

La batería comprueba persistencia, permisos, contrastes, cambios de tema sin pérdida de texto/foco, escalado de acciones, CSV/PDF, migración idempotente, fallos de reemplazo, adjuntos cruzados, duplicados, reinicio con campos incompletos, archivo/anulación, lectura concurrente y visor PDF incremental. Las pruebas de escritorio se ejecutan en procesos separados para aislar intérpretes Tcl/Tk nativos.

La medición actual usa 1 000/10 000 pacientes y 1 500/15 000 consultas, en procesos separados. Con 10 000 pacientes: búsqueda indexada en memoria 3,992 ms frente a 164,284 ms del recorrido anterior; primera lectura desde JSON 14,544 s. Apertura de paciente con datos cargados 237,308 ms; intervalo máximo del bucle gráfico 320,755 ms; sin errores de interfaz. [Método, resultados e intentos descartados](hardening-ux.md#rendimiento-medido). Son mediciones de este equipo, no garantías para otros discos o equipos.

Se revisaron ventanas reales con datos ficticios en 1366×768. Las pruebas de factores 100/125/150/200 % simulan la escala de Tk; no cambian ni certifican las cuatro configuraciones de escala de Windows. Las capturas están en artifacts/ui-qa y se describen en [Guía visual](guia-visual.md).

## Límites de verificación y distribución

El MSI x64 se verificó en Windows 11 y exige Windows 10 o posterior; no se ha probado en una instalación física de Windows 10. Windows antiguos y sistemas de 32 bits siguen pendientes de construcción y pruebas específicas; la instalación del entorno x86 fue bloqueada por revisión automática. Los binarios portables de trabajos anteriores no contienen este rediseño: usar dist/installer/TresVizo-Med-1.0.0-x64.msi. No se ha reiniciado esta PC para probar un inicio de sesión real; se verifica el registro de inicio, su persistencia y el arranque del ejecutable instalado. Los ensayos de actualización y fallo utilizan versiones de paquete sintéticas, no versiones históricas de esquemas clínicos.

Queda fuera de esta entrega una certificación clínica/normativa o de accesibilidad integral. No hay vaciado definitivo de papeleras, firma digital ni edición simultánea desde varias computadoras. Las ventanas nativas de archivos y colores conservan el estilo de Windows.
