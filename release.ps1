# Prepare local reviewable artifacts. This script never uploads anything.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskVersion = '0.2.0'
$taskExe = Join-Path $PSScriptRoot "dist\ShiXu-$taskVersion-windows-x64.exe"
if (-not (Test-Path -LiteralPath $taskExe)) { throw 'Run .\build.ps1 first.' }
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
# Explicit allowlist prevents local databases, caches and fixtures entering releases.
@'
import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path.cwd()
version = '0.2.0'
files = [root / name for name in (
    '.gitignore', 'README.md', 'CHANGELOG.md', 'RELEASE_CHECKLIST.md',
    'VALIDATION.md', 'desktop.py', 'ShiXu.spec', 'start.ps1', 'build.ps1',
    'release.ps1', 'frontend/package.json', 'frontend/package-lock.json',
    'frontend/index.html', 'frontend/tsconfig.json', 'frontend/vite.config.ts')]
files += sorted((root / 'backend').glob('*.py'))
files += sorted((root / 'backend').glob('requirements*.txt'))
files += sorted(p for p in (root / 'frontend' / 'src').rglob('*') if p.is_file())
if (root / 'LICENSE').is_file():
    files.append(root / 'LICENSE')
archive = root / 'dist' / f'ShiXu-{version}-source.zip'
with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
    for path in files:
        if not path.is_file():
            raise RuntimeError(f'Missing release file: {path}')
        bundle.write(path, f'ShiXu-{version}/' + path.relative_to(root).as_posix())
with ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    for name in bundle.namelist():
        assert not any(part in name.split('/') for part in (
            'data', 'node_modules', '.venv', '__pycache__', '.exe-smoke', '.ui-smoke'))
checksums = []
for path in [root / 'dist' / f'ShiXu-{version}-windows-x64.exe', archive]:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    checksums.append(f'{h.hexdigest()}  {path.name}')
    print(f'{path.name}: {path.stat().st_size:,} bytes')
(root / 'dist' / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='utf-8')
print('\n'.join(checksums))
'@ | & $taskPython -
if ($LASTEXITCODE -ne 0) { throw 'Release artifact preparation failed.' }
