$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    throw 'Create the project venv and install backend\requirements-desktop.txt first.'
}
$taskVersion = & $taskPython -c 'from backend.runtime import VERSION; print(VERSION)'
if ($LASTEXITCODE -ne 0) { throw 'Could not read application version.' }
$taskUiVersion = (Get-Content -LiteralPath 'frontend\package.json' -Raw | ConvertFrom-Json).version
if ($taskVersion -ne $taskUiVersion) { throw 'Backend and frontend versions must match.' }
Push-Location -LiteralPath frontend
try {
    & npm test
    if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed.' }
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
& $taskPython -m unittest backend.test_organizer backend.test_api backend.test_desktop_lock -v
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
& $taskPython scripts\collect_licenses.py
if ($LASTEXITCODE -ne 0) { throw 'Dependency notice collection failed.' }
& $taskPython -m PyInstaller --noconfirm ShiXu.spec
if ($LASTEXITCODE -ne 0) { throw 'EXE build failed.' }
Get-FileHash -LiteralPath "dist\ShiXu-$taskVersion-windows-x64.exe" -Algorithm SHA256
