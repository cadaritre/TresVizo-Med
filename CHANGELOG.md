# Cambios por versión

## 1.0.3 — 2026-09-11

- Cruz médica azul y turquesa en la aplicación, ventanas, ejecutable, accesos e instalador, con ICO de nueve resoluciones.
- Configuración inicial en dos pasos: nombre de clínica, logo propio PNG/JPG/ICO o cruz médica, administrador y contraseña maestra. La identidad de los documentos existentes se conserva al actualizar.
- Recuperación de contraseñas desde el acceso mediante clave maestra de la clínica, protegida con scrypt, espera persistente ante intentos fallidos y registro de auditoría. Todas las contraseñas admiten un mínimo de ocho caracteres; no hay una contraseña universal en el instalador.
- Corrección del calendario de pacientes: elegir un día no intenta cambiar el estado de la ventana como si fuera un campo. Al reabrir conserva el mes elegido; Escape cierra el calendario.
- Selector de sexo con Masculino y Femenino. No se reclasifican los valores de expedientes anteriores.
- Exportación de consultas CSV con periodo, médico y borradores propios opcionales; nota, diagnóstico, tratamientos, mediciones e historial estructurado. Protección frente a fórmulas de hojas de cálculo y escritura mediante archivo temporal.
- Guardar el recorte de una foto de médico la aplica de inmediato en el perfil y cabecera; el selector de acceso carga la misma imagen. Las vistas mantienen referencias a sus imágenes y ya no pierden otros avatares al renovar la caché.

## 1.0.2 — 2026-09-11

- Consulta simplificada: motivo, diagnóstico e indicaciones visibles sin desplegar secciones, con lenguaje directo y cabecera de paciente compacta.
- Accesos directos a signos vitales, medicamentos y documentos con cantidades; fecha, historial y receta en Más opciones.
- Resúmenes clínicos laterales en ventanas amplias, apilados debajo en ventanas pequeñas; acciones de cada elemento se acomodan sin estrechar su texto.
- Síntomas, notas de valoración, exploración y herramientas complementarias se despliegan según necesidad. Los borradores conservan textos, estado de secciones y capturas pendientes.
- Finalizar incorpora el diagnóstico que se está escribiendo a la revisión; el cierre sigue requiriendo confirmar la consulta.
- Se conservan iconos, desinstalador, identidad de actualización y los datos externos de Documentos.

## 1.0.1 — 2026-09-11

- Selección de médicos renovada: tarjetas de perfil, especialidad y usuario, panel de acceso separado, búsqueda por resultados y distribución adaptable. Errores junto a la contraseña y limpieza al cambiar de perfil.
- Acceso Desinstalar TresVizo Med en Inicio, además de la desinstalación estándar de Windows; los datos de Documentos se conservan.
- Verificación del icono pequeño y grande y de la identidad de barra de tareas en el ejecutable compilado.
- Inicio directo en Pacientes, búsqueda visible, alta mínima y acceso explícito para atender o retomar un borrador del mismo doctor.
- Consulta SOAP progresiva en una sola pantalla; los campos y elementos estructurados mantienen sus valores y su estado al plegar secciones.
- Alta sin pestañas: alergias visibles y datos complementarios con resúmenes desplegables.
- Herramientas secundarias en Más opciones; exportaciones y respaldos siguen accesibles.
- Agenda y Seguimientos retirados de la interfaz y las estadísticas. Finalizar ya no genera ni actualiza tareas; se conserva la información histórica y la recuperación de capturas anteriores.
- Historial con botón Abrir atención completa y corrección del retorno de foco desde una captura contextual.

Esta versión actualiza el MSI 1.0.0 conservando los datos y preferencias. El instalador original de 1.0.0 se mantiene sin sustituir.

## 1.0.0 — 2026-09-10

- Primera distribución MSI de TresVizo Med por usuario de Windows.
- Actualizaciones de versión que conservan datos y preferencias; rechazo de versiones anteriores y detección de la aplicación abierta.
- Inicio al entrar a Windows, activado en la primera instalación y editable en Configuración → General.
- Versión e identidad propias en el ejecutable, accesos directos, iconos, Acerca de e instalador.
- Incluye el rediseño y endurecimiento de la consulta contextual: captura estructurada, recuperación de pendientes y corrección del cierre de ventanas con desplegables abiertos.

El número de distribución no constituye una certificación clínica. Los alcances funcionales y las verificaciones están en `docs/estado.md`.
