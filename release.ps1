# Prepare local release files. This script never uploads anything.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Create .venv and install backend\requirements-lock.txt first.' }
& $taskPython scripts\prepare_release.py
if ($LASTEXITCODE -ne 0) { throw 'Release artifact preparation failed.' }
