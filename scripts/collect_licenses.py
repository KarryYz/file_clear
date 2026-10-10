"""Collect dependency notices from the pinned build environment."""
import importlib.metadata as metadata
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect():
    sections = [
        'ShiXu third-party notices\n'
        'Project code is licensed under MIT; see LICENSE. Dependencies retain their own licenses.\n'
        'Includes runtime and build dependencies from the pinned environment.\n'
    ]
    python_license = next((p for p in (
        Path(sys.base_prefix) / 'LICENSE_PYTHON.txt',
        Path(sys.base_prefix) / 'LICENSE.txt',
        Path(sys.base_prefix) / 'LICENSE',
    ) if p.is_file()), None)
    if python_license is None:
        raise RuntimeError('Python license file not found in the build environment.')
    sections.append(f'Python {sys.version.split()[0]}\n\n' + python_license.read_text(encoding='utf-8'))
    names = [line.split('==')[0] for line in
             (ROOT / 'backend/requirements-lock.txt').read_text().splitlines()
             if line.strip() and not line.startswith('#')]
    for name in names:
        dist = metadata.distribution(name)
        license_files = [p for p in dist.files or []
                         if Path(str(p)).name.lower().startswith(('license', 'copying', 'notice'))]
        header = f'{dist.metadata["Name"]} {dist.version}\n'
        header += f'License: {dist.metadata.get("License-Expression") or dist.metadata.get("License") or "See bundled license text"}\n'
        header += f'Author: {dist.metadata.get("Author") or dist.metadata.get("Author-email") or "See bundled license text"}\n'
        header += f'Upstream: {dist.metadata.get("Home-page") or dist.metadata.get("Project-URL") or "See package metadata"}\n'
        sections.append(header)
        for path in license_files:
            sections.append(f'{name}/{Path(str(path)).name}\n\n' +
                            Path(dist.locate_file(path)).read_text(encoding='utf-8', errors='replace'))
        if not license_files:
            sections.append(f'{name} package metadata\n\n' + (dist.read_text('METADATA') or ''))
    lock = json.loads((ROOT / 'frontend/package-lock.json').read_text(encoding='utf-8'))
    for location, package in lock['packages'].items():
        if not location or package.get('dev') or not location.startswith('node_modules/'):
            continue
        folder = ROOT / 'frontend' / location
        if not folder.is_dir():
            raise RuntimeError(f'Run npm ci first; missing {location}')
        sections.append(f'{location} {package.get("version", "")}\nLicense: {package.get("license", "See bundled text")}')
        for path in sorted(folder.iterdir()):
            if path.is_file() and path.name.lower().startswith(('license', 'copying', 'notice')):
                sections.append(f'{location}/{path.name}\n\n' + path.read_text(encoding='utf-8', errors='replace'))
    for parent in (Path(sys.base_prefix) / 'tcl', Path(sys.base_prefix) / 'Library/lib'):
        if not parent.is_dir():
            continue
        for path in sorted(parent.glob('*/license.terms')):
            if path.parent.name.startswith(('tcl', 'tk')):
                sections.append(f'{path.parent.name} license\n\n' + path.read_text(encoding='utf-8', errors='replace'))
    output = ROOT / 'THIRD_PARTY_NOTICES.txt'
    output.write_text(('\n\n' + '=' * 72 + '\n\n').join(sections) + '\n', encoding='utf-8')
    print(f'Collected notices: {output.name}')


if __name__ == '__main__':
    collect()
