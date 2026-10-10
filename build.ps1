$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create the project venv and install backend\requirements-desktop.txt first.'
}
Push-Location -LiteralPath frontend
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
& $taskPython -m unittest backend.test_organizer backend.test_api backend.test_desktop_lock -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $taskPython -m PyInstaller --noconfirm ShiXu.spec
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
Get-FileHash -LiteralPath 'dist\ShiXu-0.2.0-windows-x64.exe' -Algorithm SHA256
