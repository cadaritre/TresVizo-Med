$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Ejecuta primero scripts\ejecutar.ps1 para instalar las dependencias.' }
& $pythonPath -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'No se distribuye: hay pruebas fallidas.' }
& $pythonPath -m PyInstaller --noconfirm --windowed --name TresVizo-Med --icon assets\tresvizo_medico.ico --add-data 'assets;assets' --collect-all pypdfium2 main.py
if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar la aplicación.' }
& $pythonPath scripts\licencias.py
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron incluir las licencias.' }
Write-Host 'Aplicación en dist\TresVizo-Med\TresVizo-Med.exe'
