# Cambios por versión

## 1.0.1 — 2026-09-11 · código fuente, MSI pendiente

- Inicio directo en Pacientes, búsqueda visible, alta mínima y acceso explícito para atender o retomar un borrador del mismo doctor.
- Consulta SOAP progresiva en una sola pantalla; los campos y elementos estructurados mantienen sus valores y su estado al plegar secciones.
- Alta sin pestañas: alergias visibles y datos complementarios con resúmenes desplegables.
- Herramientas secundarias en Más opciones; exportaciones y respaldos siguen accesibles.
- Agenda y Seguimientos retirados de la interfaz y las estadísticas. Finalizar ya no genera ni actualiza tareas; se conserva la información histórica y la recuperación de capturas anteriores.
- Historial con botón Abrir atención completa y corrección del retorno de foco desde una captura contextual.

El MSI 1.0.0 entregado anteriormente no contiene estos cambios. No se ha recompilado ni sustituido ese instalador.

## 1.0.0 — 2026-09-10

- Primera distribución MSI de TresVizo Med por usuario de Windows.
- Actualizaciones de versión que conservan datos y preferencias; rechazo de versiones anteriores y detección de la aplicación abierta.
- Inicio al entrar a Windows, activado en la primera instalación y editable en Configuración → General.
- Versión e identidad propias en el ejecutable, accesos directos, iconos, Acerca de e instalador.
- Incluye el rediseño y endurecimiento de la consulta contextual: captura estructurada, recuperación de pendientes y corrección del cierre de ventanas con desplegables abiertos.

El número de distribución no constituye una certificación clínica. Los alcances funcionales y las verificaciones están en `docs/estado.md`.
