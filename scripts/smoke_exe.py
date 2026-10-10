"""Run the built Windows EXE with workspace-only fixtures and an isolated database."""
import hashlib
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = next(line.split('=')[1].strip().strip("'\"") for line in
               (ROOT / 'backend/runtime.py').read_text(encoding='utf-8').splitlines()
               if line.startswith('VERSION ='))


@contextmanager
def fixture_directory(base):
    temporary = tempfile.TemporaryDirectory(prefix=f'{VERSION}-', dir=base)
    folder = Path(temporary.name).resolve()
    if not folder.is_relative_to(ROOT.resolve()):
        raise RuntimeError('Unexpected smoke directory.')
    try:
        yield folder
    finally:
        # Windows can release the child's log handle just after its parent exits.
        for attempt in range(50):
            try:
                temporary.cleanup()
                break
            except PermissionError:
                if attempt == 49:
                    raise
                time.sleep(.1)


def run():
    base = ROOT / '.exe-smoke'
    base.mkdir(exist_ok=True)
    if not base.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError('Smoke fixtures must stay inside the workspace.')
    with fixture_directory(base) as directory:
        folder = Path(directory).resolve()
        if not folder.is_relative_to(ROOT.resolve()):
            raise RuntimeError('Unexpected smoke directory.')
        marker = folder / 'origin.txt'
        environment = dict(os.environ, FILE_ORGANIZER_DATA_DIR=str(folder / 'data'),
                           FILE_ORGANIZER_SMOKE_MARKER=str(marker))
        process = None
        origin = None

        def api(path, body=None):
            request = urllib.request.Request(origin + '/api' + path,
                data=None if body is None else json.dumps(body).encode(),
                headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.load(response)

        def finished(task_id):
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if api(f'/tasks/{task_id}/progress')['status'] not in ('running', 'undoing'):
                    return api(f'/tasks/{task_id}')
                time.sleep(.01)
            raise RuntimeError('Smoke task timeout')

        def scan(source):
            return api('/scan', {'source': str(source), 'target': str(source / 'Archive'), 'mode': 'all'})

        def launch():
            nonlocal process, origin
            marker.unlink(missing_ok=True)
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            process = subprocess.Popen([str(ROOT / 'dist' / f'ShiXu-{VERSION}-windows-x64.exe')],
                                       env=environment, startupinfo=startup)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                error = Path(str(marker) + '.error')
                if error.exists():
                    raise RuntimeError(error.read_text(encoding='utf-8'))
                if marker.is_file():
                    origin = marker.read_text(encoding='utf-8')
                    try:
                        if api('/health')['version'] == VERSION:
                            return
                    except OSError:
                        pass
                time.sleep(.1)
            raise RuntimeError('EXE startup timeout')

        def close():
            nonlocal process
            if process is None:
                return
            if origin:
                try:
                    active = api('/active')
                    if active:
                        api(f"/tasks/{active['id']}/stop", {})
                        finished(active['id'])
                except OSError:
                    pass
            # These are only our isolated smoke process and its bootloader child.
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
            process.wait(timeout=10)
            process = None

        try:
            launch()
            with urllib.request.urlopen(origin, timeout=10) as response:
                html = response.read().decode()
            asset = html.split('src="')[1].split('"')[0]
            with urllib.request.urlopen(origin + asset, timeout=10) as response:
                assert VERSION.encode() in response.read()
            source = folder / 'source'
            source.mkdir()
            (source / 'a.txt').write_bytes(b'successful file')
            (source / 'b.txt').write_bytes(b'retry file')
            task = scan(source)
            assert len(task['files']) == 2
            assert api('/tasks') == []
            backup = source / 'b.hold'
            (source / 'b.txt').rename(backup)
            api(f"/tasks/{task['id']}/execute", {'selected_ids': [f['id'] for f in task['files']]})
            assert [f['status'] for f in finished(task['id'])['files']] == ['moved', 'failed']
            backup.rename(source / 'b.txt')
            api(f"/tasks/{task['id']}/retry", {})
            result = finished(task['id'])
            assert [f['status'] for f in result['files']] == ['moved', 'moved']
            assert [f['attempts'] for f in result['files']] == [1, 2]
            api(f"/tasks/{task['id']}/undo", {})
            assert finished(task['id'])['status'] == 'undone'
            assert (source / 'a.txt').read_bytes() == b'successful file'
            assert (source / 'b.txt').read_bytes() == b'retry file'

            large = folder / 'large'
            large.mkdir()
            expected = {}
            for name, count in [('a.bin', 128), ('b.bin', 2), ('c.bin', 2)]:
                digest = hashlib.sha256()
                with (large / name).open('wb') as stream:
                    for _ in range(count):
                        block = b'x' * (1024 * 1024)
                        stream.write(block)
                        digest.update(block)
                expected[name] = digest.hexdigest()
            stoppable = scan(large)
            api(f"/tasks/{stoppable['id']}/execute", {'selected_ids': [f['id'] for f in stoppable['files']]})
            state = api(f"/tasks/{stoppable['id']}/progress")
            assert state['status'] == 'running'
            assert state['progress']['current_name'] == 'a.bin'
            api(f"/tasks/{stoppable['id']}/stop", {})
            assert [f['status'] for f in finished(stoppable['id'])['files']] == ['moved', 'pending', 'pending']
            api(f"/tasks/{stoppable['id']}/resume", {})
            assert [f['attempts'] for f in finished(stoppable['id'])['files']] == [1, 1, 1]
            api(f"/tasks/{stoppable['id']}/undo", {})
            assert finished(stoppable['id'])['status'] == 'undone'
            for name, value in expected.items():
                digest = hashlib.sha256()
                with (large / name).open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(block)
                assert digest.hexdigest() == value

            draft = scan(source)
            selected = [draft['files'][0]['id']]
            api(f"/tasks/{draft['id']}/draft", {'selected_ids': selected, 'category_filter': '文本'})
            close()
            launch()
            assert {t['id'] for t in api('/tasks')} == {task['id'], stoppable['id']}
            restored = api('/drafts')[0]
            assert restored['id'] == draft['id']
            assert restored['selected_ids'] == selected
            assert restored['category_filter'] == '文本'
            assert api('/active') is None
            print(f'PASS EXE {VERSION}: assets, selective retry, safe stop/resume, hash-verified undo and restart persistence')
        finally:
            close()


if __name__ == '__main__':
    run()
