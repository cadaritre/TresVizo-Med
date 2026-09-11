param(
    [string]$PythonPath,
    [switch]$SkipTests,
    [switch]$ReplaceUnpublished
)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectPath
if (-not $PythonPath) {
    $candidates = @((Join-Path $projectPath '.venv\Scripts\python.exe'), (Join-Path (Split-Path -Parent $projectPath) '.venv\Scripts\python.exe'))
    $PythonPath = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $PythonPath) { throw 'Indica -PythonPath con Python 3.13 y las dependencias del proyecto.' }
if (-not (Get-Command wix -ErrorAction SilentlyContinue)) { throw 'Se requiere WiX 4.0.6. Consulta docs/distribucion.md.' }
$releaseArgs = @('scripts\release.py')
if ($SkipTests) { $releaseArgs += '--skip-tests' }
if ($ReplaceUnpublished) { $releaseArgs += '--replace-unpublished' }
& $PythonPath @releaseArgs
if ($LASTEXITCODE -ne 0) { throw 'La distribución no terminó correctamente. Revisa el error anterior.' }
