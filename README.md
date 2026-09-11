# TresVizo Med · Registro Clínico

Aplicación local para Windows, Python 3.13, Tkinter y ttk. El trabajo se guarda en la carpeta real de Documentos, resuelta con la API de carpetas conocidas de Windows. La instalación inicia sin pacientes ni contraseñas predeterminadas.

## Ejecución

1. Instalar Python 3.13 para Windows con Tkinter y acceso al comando `python`.
2. Abrir `ejecutar.cmd`. El primer arranque prepara `.venv` e instala `requirements.txt`; esta preparación requiere internet.
3. Crear la clínica y su primer administrador. Después, la aplicación funciona sin internet. El enlace web solo abre el navegador al pulsarlo.

Instalación manual desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Pruebas y vista de demostración aislada:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\preview_simple.py --view patients
```

La demostración crea únicamente información sintética en un directorio temporal. No afecta los datos de la clínica. `--data-dir RUTA` permite otra carpeta explícita para pruebas.

## Apariencia y marca

Configuración → Apariencia → Colores ofrece Clínico, TresVizo, Verde suave, Azul profundo, Neutro y el editor Personalizada. Cada token tiene entrada hexadecimal, muestra de color y selector visual. La vista previa usa ejemplos sintéticos de tarjeta, formulario, botones, selección, alerta y gráfica.

Aplicar guarda y actualiza los widgets existentes. Cancelar descarta las ediciones aún no aplicadas. Restablecer carga Clínico en el editor y requiere Aplicar para persistir. Guardar con nombre y Duplicar crean temas; un doctor puede renombrar o eliminar los suyos. Un tema en uso no se elimina. El administrador puede administrar todos los temas y cambiar el predeterminado de la clínica.

El inicio de sesión usa la paleta de la clínica. El doctor puede heredar esa paleta o usar otra. Las paletas de documentos son independientes. La interfaz bloquea Aplicar si detecta contraste insuficiente; el botón de corrección ajusta los tokens. La corrección puede acercar los dos fondos cuando es imposible conservar un texto común legible sobre ambos.

Configuración → Clínica e identidad permite cambiar nombre, contacto, logo clínico, enlace HTTP/HTTPS, texto visible y preferencias de documentos. La marca de la aplicación y su enlace están desactivados por defecto en PDF.

## Recorrido cotidiano

La versión de código fuente 1.0.1 simplifica la atención con SOAP progresivo. Consulta el [recorrido, verificaciones y límites](docs/recorrido-simple.md). El MSI 1.0.0 anterior permanece intacto y no incluye estos cambios.

## Funciones clínicas disponibles

- Creación de administradores y doctores, autenticación scrypt, espera progresiva, cambio de contraseña, activación/desactivación y protección del último administrador.
- Registro y búsqueda de pacientes, advertencia de posibles duplicados, antecedentes y alergias visibles.
- Consultas SOAP, borradores con autoguardado, revisión antes de finalizar y adendas sin sobrescribir el original.
- Entrada directa en Pacientes; herramientas secundarias en Más opciones, estadísticas por periodo y alta con secciones desplegables. Agenda y Seguimientos están retirados; sus datos históricos se conservan.
- Exportación de pacientes CSV/JSON, PDF con vista previa y respaldos ZIP con manifiesto e integridad verificada.

Este repositorio **no implementa todavía la totalidad de los 26 apartados del encargo**. Consultar [estado y límites](docs/estado.md) antes de usarlo con información real. No se declara validado para producción clínica.

## Documentación

- [Arquitectura y esquema JSON](docs/arquitectura.md).
- [Guía visual](docs/estilo.md).
- [Guía de uso y recuperación](docs/uso.md).
- [Estado y verificación](docs/estado.md).

## Distribución

`scripts/distribuir.ps1` ejecuta las pruebas, compila con PyInstaller y genera el MSI versionado con WiX 4. Los expedientes y preferencias de Documentos se conservan al actualizar y al desinstalar. El inicio automático se cambia en Configuración → General. Consulta [instalación, versiones y compilación](docs/distribucion.md) y [cambios por versión](CHANGELOG.md).
