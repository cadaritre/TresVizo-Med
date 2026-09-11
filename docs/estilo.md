# Sistema visual

Referencia revisada: código de la aplicación de reportes, específicamente ui.py, ux_components.py, settings_dialog.py y las definiciones visuales de branding.py. No se ejecutó la aplicación de referencia ni se copiaron sus datos, firmas, cédulas o contactos.

La apariencia predeterminada es clara: fondo #F5F5F7, tarjetas blancas, texto #1D1D1F, secundario #626269 y azul #0066CC. La barra lateral ocupa aproximadamente 210 unidades lógicas. Segoe UI y sus variantes semibold mantienen jerarquía sin títulos saturados. Los iconos Lucide se incluyen localmente con su licencia. La petición de hardening prioriza icono y texto en navegación y acciones importantes. Los dibujos de la galería de avatares conservan la presentación sin etiquetas permanentes, con nombre en ttk y ayuda al pasar el cursor o recibir foco con Tab. Los nombres de doctores, etiquetas de campos y advertencias clínicas siguen visibles. Los separadores decorativos se derivan del tema y se distinguen de bordes y foco funcionales.

Los iconos de acciones usan los colores derivados de su botón para reposo, selección, hover, presionado y deshabilitado. Cambiar de sección actualiza también el color del icono seleccionado. Las ayudas no solicitan foco y se ocultan al pulsar, abandonar el control, ocultar la pantalla o bloquear la sesión. La selección de avatar se destaca antes de guardar.

La consulta usa un solo desplazamiento principal, encabezado y pie estables; las capturas se centran y limitan al área útil del monitor, con acciones fuera del desplazamiento interno. Los accesos contextuales muestran el nombre y un resumen o conteo. El alta separa acciones y estado de guardado en dos filas para evitar que se recorten. Los fondos de lienzos desplazables usan el token de fondo general; una zona sin contenido no deja una tarjeta blanca de altura arbitraria.

Los formularios reutilizan Form y Collection: dos columnas cuando caben, una cuando el ancho se reduce, edición de elementos y resumen de la pauta. Las secciones desplegables usan una transición de 150 ms que respeta Reducir movimiento. Los encabezados y las acciones de alta/consulta permanecen fuera del contenido desplazable.

Las listas usan IDs estables, selección explícita y estado vacío con una acción útil. La cola documental aparece cuando hay selecciones; el progreso se muestra mientras se trabaja y las acciones se reorganizan según el ancho. Conflictos e importación tienen contenido desplazable y acciones de cierre/confirmación fuera de él. Los errores conservan el formulario y señalan qué debe revisarse. Cambiar página mueve el foco a contenido visible; regresar reutiliza el foco y la posición cuando siguen disponibles.

Todos los colores de pantallas proceden de `themes.py`. `derived()` genera colores de texto sobre botones y variantes hover, presionado y deshabilitado. El foco usa el token correspondiente. Las alertas utilizan tokens semánticos protegidos con icono y texto: error, advertencia y éxito. No se pueden sustituir desde JSON de temas.

El contraste usa luminancia relativa sRGB: (L mayor + 0.05)/(L menor + 0.05). El editor requiere 4.5:1 para texto sobre fondos y paneles; 3:1 para bordes, foco y series de gráficas. Los valores y etiquetas de gráficas se muestran explícitamente, sin depender solo del color. No constituye una certificación integral de accesibilidad.

La aplicación cambia estilos sin reconstruir pantallas. Los widgets Canvas que dibujan datos se suscriben al gestor. El editor de colores usa una paleta de previsualización independiente. Las ventanas secundarias se recorren junto al árbol existente. Las ventanas nativas de selección de archivo/color usan la apariencia de Windows.

La marca médica utiliza el símbolo original como referencia. El original no contiene un nombre escrito: el nombre TresVizo se representa junto al símbolo como texto nativo Segoe UI, sin inventar una tipografía original. No se entrega un SVG con una imagen incrustada.

Archivos entregados en assets: símbolo transparente y compacto de 512 px, variante con contorno claro para fondos oscuros, composiciones con nombre para ambos fondos y .ico con 16, 20, 24, 32, 40, 48, 64, 128 y 256 px. La aplicación elige la versión de fondo oscuro según la luminancia del panel. A 16 px se prioriza el reconocimiento del símbolo; el detalle completo del estetoscopio se aprecia mejor desde 32–48 px.
