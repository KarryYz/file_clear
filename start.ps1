$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    $taskPython = (Get-Command python -ErrorAction Stop).Source
}

if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) {
    throw 'Build the UI first: cd frontend; npm install; npm run build'
}

& $taskPython -c 'import fastapi, uvicorn'
if ($LASTEXITCODE -ne 0) {
    throw 'Install backend dependencies first: python -m pip install -r backend\requirements.txt'
}

Write-Host 'Open http://127.0.0.1:8000 . Keep this terminal running; Ctrl+C stops the service.'
& $taskPython -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
