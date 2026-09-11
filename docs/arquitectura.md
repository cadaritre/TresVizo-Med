# Arquitectura y datos

`main.py` inicializa el escalado y la aplicación. `app/main_window.py`, `components.py` y `appearance_ui.py` contienen presentación Tkinter/ttk. `services.py` concentra sesión, permisos y operaciones clínicas. `storage.py` centraliza JSON, rutas, escrituras y exclusión de segunda instancia. `themes.py` valida y persiste apariencia sin depender de Tk. `ui_theme.py` aplica tokens a ttk, Text, Canvas y Menu. `branding.py` mantiene identidad; `documents.py` consume exclusivamente los ajustes de impresión. `transfer.py` exporta y crea respaldos.

Las operaciones de fondo usan un ejecutor de un trabajador. Los widgets se actualizan mediante `after()`. El contador de generación de sesión descarta resultados de una sesión anterior. Al cerrar sesión se ocultan las ventanas y se espera a que terminen operaciones en curso antes de cambiar el actor.

## Estructura de almacenamiento

```text
Documentos/RegistroClinico/
  config/appearance.json
  config/identity.json
  config/security.json
  config/clinic-logo-UUID.png
  data/users/UUID.json
  data/patients/UUID.json
  data/encounters/UUID.json
  data/appointments/UUID.json
  data/followups/UUID.json
  data/audit/UUID.json
```

Los archivos de entidades incluyen `schema_version: 1`, UUID y fechas ISO 8601. Pacientes y consultas agregan `revision`, `created_at`, `created_by`, `updated_at`, `updated_by`. La revisión impide sobrescribir una versión obsoleta. El expediente usa un folio independiente del nombre. `patient_id` relaciona consultas, agenda y seguimientos; `doctor_id` conserva al responsable; `captured_by` identifica al capturista original. Las adendas tienen UUID, actor, fecha, motivo y contenido.

Las contraseñas usan scrypt con salt aleatorio individual de 16 bytes, N=16384, r=8, p=1; se guarda algoritmo y parámetros junto al hash. La comparación usa tiempo constante. La limitación de intentos de esta versión es en memoria; no sobrevive al reinicio.

## Apariencia v1

`appearance.json` contiene `schema_version`, `clinic` (ID de tema), `custom` (ID → tema), `owners` (ID → UUID del creador) y `users` (UUID → `{inherit, theme}`). Los temas de fábrica se definen en código. Los nombres personalizados son etiquetas; sus UUID permanecen estables al renombrar.

Un tema importable/exportable contiene exactamente `schema_version: 1`, `name` y `tokens`. Los 19 tokens son: `primary`, `accent`, `background`, `surface`, `header`, `sidebar`, `text`, `muted`, `border`, `button`, `secondary`, `selection`, `focus`, `chart1` a `chart6`. Los colores deben ser `#RRGGBB`. No se admiten campos desconocidos, claves duplicadas, versiones distintas, nombres vacíos, colores abreviados ni archivos mayores de 64 KB.

Se valida el documento completo antes de escribir. La configuración en memoria se sustituye solo después del reemplazo atómico correcto. Cada escritura usa archivo temporal, flush, fsync y reemplazo. Un archivo ilegible no se sustituye por datos vacíos. La exclusión de segunda instancia protege el mismo directorio; no proporciona soporte multicomputadora.

## Límites de persistencia

El RLock serializa escrituras dentro del proceso. No hay transacción atómica entre el archivo clínico y su evento de auditoría; tampoco migraciones automáticas o recuperación transaccional de múltiples archivos. No manipular los JSON mientras la aplicación esté abierta. Los JSON clínicos están en texto claro: los permisos de la aplicación no impiden que el usuario de Windows acceda a ellos. La auditoría local no es inviolable.
