# Reglas permanentes

- Mantener Python, Tkinter y ttk como base tecnológica.
- Reutilizar componentes y tokens del sistema visual documentado.
- Separar presentación, lógica de negocio y persistencia JSON.
- No introducir datos clínicos reales, credenciales, imágenes privadas ni respaldos en Git.
- No incorporar telemetría ni conexiones externas automáticas.
- No atribuir autoría, colaboración, firmas, créditos o marcas a herramientas automáticas en código, documentación del producto, interfaces, instaladores, documentos o metadatos. No agregar trailers de autoría automática.
- Usar la identidad Git existente, sin inventar identidades ni reescribir autorías históricas.
- Conservar licencias y avisos legales obligatorios de dependencias.
- Verificar funcionamiento, persistencia, permisos y usabilidad; documentar límites sin declarar funcionalidades no verificadas.
- La identidad de documentos pertenece a la clínica. La apariencia de cada doctor nunca modifica documentos.
- No modificar el proyecto de referencia ni copiar su información privada.
- Antes de distribuir cambios, incrementar `app/version.py` y actualizar `CHANGELOG.md`; no reutilizar una versión MSI ya entregada.
- Conservar el UpgradeCode y los identificadores de componentes de `scripts/generate_msi.py`. Las actualizaciones usan la misma arquitectura y nunca incluyen ni borran la carpeta clínica de Documentos.
- Compilar con `scripts/distribuir.ps1`, verificar el ejecutable y ensayar actualización/recuperación con `scripts/verify_msi.py` y datos sintéticos. Consultar `docs/distribucion.md` para el procedimiento y sus límites.
