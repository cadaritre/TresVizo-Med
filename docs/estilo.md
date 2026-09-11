# Sistema visual

Referencia revisada: código de la aplicación de reportes, específicamente ui.py, ux_components.py, settings_dialog.py y las definiciones visuales de branding.py. No se ejecutó la aplicación de referencia ni se copiaron sus datos, firmas, cédulas o contactos.

La base TresVizo conserva fondos azulados, paneles claros, encabezados azul profundo y Segoe UI. El acento del tema TresVizo se oscurece ligeramente respecto a la referencia para alcanzar 4.5:1 sobre el fondo general. Los controles conservan su edición nativa.

Todos los colores de pantallas proceden de `themes.py`. `derived()` genera colores de texto sobre botones y variantes hover, presionado y deshabilitado. El foco usa el token correspondiente. Las alertas utilizan tokens semánticos protegidos con icono y texto: error, advertencia y éxito. No se pueden sustituir desde JSON de temas.

El contraste usa luminancia relativa sRGB: (L mayor + 0.05)/(L menor + 0.05). El editor requiere 4.5:1 para texto sobre fondos y paneles; 3:1 para bordes, foco y series de gráficas. Los valores y etiquetas de gráficas se muestran explícitamente, sin depender solo del color. No constituye una certificación integral de accesibilidad.

La aplicación cambia estilos sin reconstruir pantallas. Los widgets Canvas que dibujan datos se suscriben al gestor. El editor de colores usa una paleta de previsualización independiente. Las ventanas secundarias se recorren junto al árbol existente. Las ventanas nativas de selección de archivo/color usan la apariencia de Windows.

La marca médica utiliza el símbolo original como referencia. El original no contiene un nombre escrito: el nombre TresVizo se representa junto al símbolo como texto nativo Segoe UI, sin inventar una tipografía original. No se entrega un SVG con una imagen incrustada.

Archivos entregados en assets: símbolo transparente y compacto de 512 px, variante con contorno claro para fondos oscuros, composiciones con nombre para ambos fondos y .ico con 16, 20, 24, 32, 40, 48, 64, 128 y 256 px. La aplicación elige la versión de fondo oscuro según la luminancia del panel. A 16 px se prioriza el reconocimiento del símbolo; el detalle completo del estetoscopio se aprecia mejor desde 32–48 px.
