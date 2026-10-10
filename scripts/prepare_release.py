"""Create local release artifacts without uploading or including user data."""
import hashlib
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from collect_licenses import collect

ROOT = Path(__file__).resolve().parents[1]


def prepare():
    # Read the version without importing the application / opening its database.
    version = next(line.split('=')[1].strip().strip("'\"") for line in
                   (ROOT / 'backend/runtime.py').read_text(encoding='utf-8').splitlines()
                   if line.startswith('VERSION ='))
    output = ROOT / 'dist'
    exe = output / f'ShiXu-{version}-windows-x64.exe'
    if not exe.is_file():
        raise RuntimeError('Run build.ps1 first.')
    collect()
    files = [ROOT / name for name in (
        '.gitignore', '.gitattributes', 'LICENSE', 'THIRD_PARTY_NOTICES.txt', 'README.md', 'CHANGELOG.md',
        'RELEASE_CHECKLIST.md', 'RELEASE_NOTES.md', 'VALIDATION.md', 'desktop.py',
        'ShiXu.spec', 'start.ps1', 'build.ps1', 'release.ps1',
        'frontend/package.json', 'frontend/package-lock.json', 'frontend/index.html',
        'frontend/tsconfig.json', 'frontend/vite.config.ts')]
    files += sorted((ROOT / 'backend').glob('*.py'))
    files += sorted((ROOT / 'backend').glob('requirements*.txt'))
    files += sorted(p for p in (ROOT / 'frontend/src').rglob('*') if p.is_file())
    files += sorted((ROOT / 'frontend/tests').glob('*.mjs'))
    files += sorted((ROOT / 'scripts').glob('*.py'))
    files += sorted((ROOT / '.github/workflows').glob('*.yml'))
    for path in files:
        if not path.is_file():
            raise RuntimeError(f'Missing release source file: {path.name}')
    archive = output / f'ShiXu-{version}-source.zip'
    with ZipFile(archive, 'w', ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, f'ShiXu-{version}/' + path.relative_to(ROOT).as_posix())
    with ZipFile(archive) as bundle:
        invalid = bundle.testzip()
        if invalid:
            raise RuntimeError(f'Archive validation failed: {invalid}')
        for name in bundle.namelist():
            if any(part in name.split('/') for part in (
                'data', 'node_modules', '.venv', '__pycache__', '.exe-smoke', '.ui-smoke')):
                raise RuntimeError(f'Unexpected source archive entry: {name}')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.txt', 'RELEASE_NOTES.md'):
        shutil.copyfile(ROOT / name, output / name)
    checksums = []
    for path in [exe, archive, output / 'LICENSE', output / 'THIRD_PARTY_NOTICES.txt', output / 'RELEASE_NOTES.md']:
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        checksums.append(f'{digest.hexdigest()}  {path.name}')
        print(f'{path.name}: {path.stat().st_size:,} bytes')
    (output / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='utf-8')
    print('\n'.join(checksums))


if __name__ == '__main__':
    prepare()
