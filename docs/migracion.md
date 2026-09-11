# Migración y recuperación v2

1. Cerrar la versión anterior antes de abrir la misma carpeta de datos con el nuevo código.
2. Al arrancar, recuperar las operaciones interrumpidas. Si el esquema es v1 y hay datos, crear un ZIP en backups/antes-migracion-fecha.zip y comprobar CRC y SHA-256 antes de cambiar registros.
3. Conservar UUID, folios, fechas, revisiones y autoría. Los campos narrativos anteriores siguen presentes y se copian como información heredada. No se deducen alergias, dosis ni mediciones desde texto libre.
4. Publicar los registros y config/schema.json juntos. Repetir el arranque no repite una migración completada. Si hay un fallo, conservar archivos y detener el arranque normal para recuperación.

Para restaurar: Exportar y respaldar → Restaurar respaldo en otra carpeta. Elegir el ZIP y una carpeta nueva fuera de la clínica activa. Se rechazan rutas que escapan del destino, archivos no declarados, hashes distintos, JSON inválido y versiones futuras. Se revisan también originales y metadatos de adjuntos. Solo después de completar la copia aparece la acción para abrirla como una instancia separada.

La restauración no cambia la carpeta activa ni elimina su contenido. Confirmar expedientes y documentos en la copia antes de decidir cuál utilizar. No borrar un JSON corrupto para forzar un inicio vacío. Conservar el respaldo y el journal cuando una recuperación no puede completarse.

Los paquetes de expediente exportan el paciente, las consultas visibles para el actor y los adjuntos elegidos. Los borradores de otros doctores permanecen excluidos. Las miniaturas son auxiliares y pueden regenerarse; los originales son la referencia documental.
