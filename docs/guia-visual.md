# Guía visual del rediseño

Capturas de la aplicación real, con nombres y expedientes ficticios. No son maquetas. Cada pantalla conserva controles nativos de Windows/Tk.

La actualización de consulta en una sola pantalla tiene su [propia guía y ocho capturas](consulta-contextual.md). Sustituye las capturas antiguas del editor de consulta de esta tabla.

| Vista | Evidencia |
|---|---|
| Inicio, citas y borradores | [Inicio](../artifacts/ui-qa/01-inicio.png) |
| Registro de paciente | [Alta](../artifacts/ui-qa/02-alta.png) |
| Expediente | [Expediente](../artifacts/ui-qa/03-expediente.png) |
| Presión arterial y evolución | [Evolución](../artifacts/ui-qa/04-evolucion.png) |
| Consulta y guardado | [Consulta](../artifacts/ui-qa/05-consulta.png) |
| Signos vitales | [Mediciones](../artifacts/ui-qa/06-signos-vitales.png) |
| Galería de temas y acciones | [Apariencia](../artifacts/ui-qa/07-apariencia.png) |
| Avatares del doctor | [Perfil](../artifacts/ui-qa/08-perfil.png) |
| Acceso | [Acceso](../artifacts/ui-qa/09-acceso.png) |
| Navegación y acciones sin etiquetas, revisión posterior | [Iconos en Inicio](../artifacts/ui-qa/10-iconos-inicio.png) |
| Avatares sin nombres y selección destacada, revisión posterior | [Galería de perfil](../artifacts/ui-qa/11-iconos-perfil.png) |

Las capturas 01–09 documentan el rediseño anterior a la petición de ocultar los nombres de los iconos. Las capturas 10–11 muestran esa modificación en la aplicación real a 1366×768.

Los archivos de revisión se mantienen fuera de Git. El recorrido puede repetirse con `python scripts/preview_redesign.py --page home`; crea una clínica sintética temporal. Las opciones incluyen login, patient, record, consultation, vitals, medications, settings y stats. Cerrar la ventana finaliza la sesión de prueba. La aplicación normal se inicia con `python main.py`.
