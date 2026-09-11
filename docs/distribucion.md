# Instalación y versiones MSI

La línea de instaladores comienza en **1.0.0**. El ejecutable incluye Python, Tcl/Tk, las bibliotecas de PDF y los recursos de la aplicación. El equipo de destino no necesita instalar Python ni conectarse a internet.

## Instalar y actualizar

1. Ejecutar `TresVizo-Med-1.0.0-x64.msi` en Windows de 64 bits. Se instala para la cuenta actual, en `%LocalAppData%\Programs\TresVizo-Med`, con accesos en Inicio y Escritorio.
2. Abrir TresVizo Med. La primera ejecución sin datos pide crear la clínica y el administrador; no hay credenciales predeterminadas.
3. Para una nueva versión, guardar el trabajo, cerrar TresVizo Med y ejecutar su nuevo MSI. Se conserva la ubicación de instalación. El instalador detecta una app compilada abierta y cancela antes de cambiar archivos; no termina consultas ni fuerza reinicios.
4. El MSI sustituye los archivos de programa. Los pacientes, consultas, borradores, usuarios, contraseñas, adjuntos, temas y preferencias siguen en la carpeta real `Documentos\RegistroClinico`. También se conservan si se desinstala el programa.

La cuenta de Windows debe ser la misma al actualizar. Instalar desde otra cuenta crea otra instalación por usuario. Una carpeta de Documentos redirigida continúa resolviéndose con la API de carpetas conocidas.

La misma versión permite mantenimiento con su MSI original. Una versión inferior se rechaza. No se debe desinstalar antes de actualizar: la nueva versión instala sus archivos antes de retirar el producto anterior, dentro de la transacción de Windows Installer (`afterInstallExecute`). Esto requiere conservar las identidades de los componentes compartidos. Si una versión futura necesita cambiar el esquema clínico, la migración debe crear y verificar un respaldo antes de modificarlo; la aplicación rechaza esquemas más nuevos que los que entiende.

La actualización se entrega como un nuevo archivo MSI. La aplicación no contacta un servidor de actualizaciones.

## Inicio de Windows

La primera instalación activa abrir la pantalla de acceso al iniciar sesión en Windows. Se cambia en **Configuración → General → Abrir TresVizo Med al iniciar sesión en Windows**. La opción pertenece a esa cuenta de Windows, no a un doctor ni a los documentos de la clínica. No autentica al doctor automáticamente.

El estado se guarda en `HKCU\Software\TresVizo\Med` y el comando, con la ruta entre comillas, en el valor `TresVizoMed` de `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`. Se usa la vista de registro de 32 bits tanto para x64 como para x86. Las actualizaciones y reparaciones leen el estado existente antes de retirar la instalación anterior. Con el estado desactivado, una reparación puede dejar un valor Run vacío, que no ejecuta ningún programa. Al desinstalar se retira ese valor, incluso si la opción se activó desde la app después de instalar.

La ejecución desde código fuente o desde una carpeta portable no puede reemplazar el inicio automático de la instalación activa. Windows o una política administrada pueden deshabilitar aplicaciones de inicio de forma independiente.

## Compilar una nueva versión

Se requiere Windows, Python 3.13 de la arquitectura de destino, las dependencias de `requirements.txt`, .NET SDK 8 y WiX **4.0.6**. Preparación del entorno de compilación:

```powershell
dotnet tool install --global wix --version 4.0.6
wix extension add WixToolset.UI.wixext/4.0.6
wix extension add WixToolset.Util.wixext/4.0.6
```

1. Modificar el código, incrementar `VERSION` en `app/version.py` y registrar los cambios en `CHANGELOG.md`.
2. Usar tres números: `mayor.menor.corrección`, por ejemplo `1.0.0` → `1.0.1`. Límites MSI: 255, 255 y 65535 respectivamente. No reutilizar una versión ya distribuida ni añadir un cuarto número.
3. Ejecutar desde el proyecto:

```powershell
.\scripts\distribuir.ps1 -PythonPath '..\.venv\Scripts\python.exe'
```

El script ejecuta las pruebas, genera el recurso de versión de Windows, compila el `.exe`, conserva las licencias, verifica Tk/DnD/iconos/PDF y genera el MSI. El recurso EXE, Acerca de, Configuración, MSI y manifiesto comparten la misma versión. La salida queda en `dist\installer`, con un JSON de versiones de dependencias y huellas de fuentes, además del SHA-256 del MSI.

El script rechaza sobrescribir un MSI existente. `-ReplaceUnpublished` solo sirve para corregir artefactos locales que **todavía no se han entregado**. `-SkipTests` solo corresponde a una revisión de código ya verificada. Conservar el MSI original y sus manifiestos de cada versión entregada; opcionalmente marcar esa revisión en Git con `v1.0.0`, `v1.0.1`, etc.

`UpgradeCode` en `scripts/generate_msi.py` es la identidad permanente del producto y no debe cambiar. Los ProductCode se derivan de la versión y arquitectura. Los componentes tienen identificadores estables por ruta. El instalador incluye una lista explícita de archivos compilados y nunca incorpora la carpeta clínica.

### Arquitecturas y sistemas

El paquete **x64** está orientado a Windows 10/11 de 64 bits. El proceso acepta un intérprete Python **x86 real** para generar un paquete separado; no basta renombrar el MSI x64 o cambiar una bandera. Las actualizaciones y reparaciones deben usar la misma arquitectura: el MSI bloquea cambios x86/x64 sobre una instalación existente. Para cambiar de arquitectura, respaldar los datos, desinstalar el programa e instalar el paquete correspondiente; los expedientes permanecen en Documentos. Esta restricción evita mezclar los componentes nativos de 32 y 64 bits.

No se ha validado Windows 7/8/8.1 ni una PC física de 32 bits. Aunque Python 3.13 documenta soporte desde Windows 8.1, eso no demuestra compatibilidad de todas las dependencias; este MSI exige Windows 10 o posterior. La compilación x86 queda pendiente hasta disponer de un entorno Python x86 autorizado. La instalación de ese entorno fue bloqueada por la revisión automática de permisos durante esta entrega.

Los MSI generados aquí no tienen firma Authenticode comercial. Para una distribución firmada, firmar primero el ejecutable y después el MSI con el certificado del editor, y recalcular su SHA-256 y manifiesto. No modificar un paquete después de publicarlo.

## Prueba de actualizaciones

```powershell
..\.venv\Scripts\python.exe scripts\verify_msi.py --payload dist\x64\TresVizo-Med --arch x64
```

Este ensayo usa una familia MSI distinta, accesos con nombre de prueba y claves de inicio aisladas que no se ejecutan al entrar a Windows. Construye paquetes sintéticos 0.9.0, 1.0.0, 1.0.1 y 1.0.2 con el código actual. El payload anterior recibe recurso EXE 0.9.0, manifiesto diferente y un archivo obsoleto; así se comprueba el reemplazo de archivos, además de la versión del MSI. Verifica actualización con inicio desactivado y activado, reparación, rechazo de retroceso, bloqueo por proceso abierto, reversión de un fallo antes de registrar el nuevo producto y conservación byte a byte de los expedientes sintéticos. El fallo solo se puede inyectar en paquetes de prueba. Abre el ejecutable instalado en una comprobación temporal de Tk, PDF e icono. Desinstala la familia de prueba al terminar y deja informes en `artifacts/msi-validation-*`.

## Referencias técnicas

- [Versiones y major upgrades de Windows Installer](https://learn.microsoft.com/en-us/windows/win32/msi/major-upgrades).
- [Transacción de MajorUpgrade y orden de retirada](https://docs.firegiant.com/wix3/xsd/wix/majorupgrade/).
- [Detección de aplicaciones abiertas sin terminar sus procesos](https://docs.firegiant.com/wix/schema/util/closeapplication/).
- [Control de Restart Manager](https://learn.microsoft.com/en-us/windows/win32/msi/msirestartmanagercontrol).
- [Compatibilidad de Python 3.13 con Windows](https://docs.python.org/3.13/using/windows.html).
