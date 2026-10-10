"""File planning and reversible moves. No web framework dependencies."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


DOCUMENTS = {
    **dict.fromkeys(['.doc', '.docx', '.odt'], 'Word文档'),
    '.pdf': 'PDF文档',
    **dict.fromkeys(['.xls', '.xlsx', '.xlsm', '.xlsb', '.csv', '.ods'], 'Excel表格'),
    **dict.fromkeys(['.ppt', '.pptx', '.odp'], '演示文稿'),
}
INSTALLERS = {'.exe': 'EXE', '.msi': 'MSI', '.msix': 'MSIX', '.iso': 'ISO'}
ARCHIVES = {
    '.zip': 'ZIP', '.rar': 'RAR', '.7z': '7Z', '.tar': 'TAR',
    '.gz': 'GZ', '.gzip': 'GZ', '.bz2': 'BZ2', '.xz': 'XZ',
    '.tgz': 'TAR', '.tbz2': 'TAR', '.txz': 'TAR', '.zst': 'ZST',
    '.cab': 'CAB', '.lz': 'LZ', '.lzma': 'LZMA', '.bz': 'BZ2',
}
EXTRA_TYPES = {
    **dict.fromkeys(['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg',
                     '.tif', '.tiff', '.ico', '.heic', '.heif', '.avif', '.raw',
                     '.cr2', '.nef', '.psd'], '图片'),
    **dict.fromkeys(['.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm',
                     '.m4v', '.mpg', '.mpeg', '.ts', '.mts', '.m2ts', '.3gp'], '视频'),
    **dict.fromkeys(['.mp3', '.wav', '.flac', '.aac', '.m4a', '.ogg', '.wma',
                     '.opus', '.aiff', '.alac'], '音频'),
    **dict.fromkeys(['.ttf', '.otf', '.ttc', '.woff', '.woff2', '.eot'], '字体'),
    **dict.fromkeys(['.txt', '.md', '.rtf', '.log'], '文本'),
}
CATEGORY_FOLDERS = {'Word文档': 'Word', 'PDF文档': 'PDF',
                    'Excel表格': 'Excel', '演示文稿': 'PowerPoint',
                    '图片': 'Images', '视频': 'Videos', '音频': 'Audio',
                    '字体': 'Fonts', '文本': 'Text', '其他文件': 'Other'}
EXCLUDED = {'windows', 'program files', 'program files (x86)', 'programdata',
            '$recycle.bin', 'system volume information', 'windowsapps',
            'node_modules', '.git', '.venv', '__pycache__', 'steamapps'}
MAX_FILES = 10000


def classify(path: Path):
    """Classify every ordinary file; do not inspect or unpack its contents."""
    ext = path.suffix.lower()
    if ext in DOCUMENTS:
        category = DOCUMENTS[ext]
        return category, Path(CATEGORY_FOLDERS[category])
    if ext in INSTALLERS:
        return INSTALLERS[ext], Path('Installers') / INSTALLERS[ext]
    name = path.name.lower()
    if name.endswith(('.tar.gz', '.tar.bz2', '.tar.xz', '.tar.zst', '.tar.lz')):
        return '压缩包', Path('Packages') / 'TAR'
    if ext in ARCHIVES:
        return '压缩包', Path('Packages') / ARCHIVES[ext]
    category = EXTRA_TYPES.get(ext, '其他文件')
    return category, Path(CATEGORY_FOLDERS[category])


def stamp():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(path: Path):
    s = path.stat()
    return [s.st_size, s.st_mtime_ns, s.st_dev, s.st_ino]


def is_link(path: Path):
    # Also reject Windows junctions / reparse points on Python 3.11.
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def safe_path(raw: str):
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise ValueError('请输入绝对路径，例如 D:\\下载。')
    for part in [p, *p.parents]:
        if part.is_symlink() or (part.exists() and is_link(part)):
            raise ValueError('为避免越界操作，不支持符号链接或目录联接。')
    p = p.resolve()
    if any(part.lower() in EXCLUDED for part in p.parts):
        raise ValueError('不能整理系统目录、软件目录或被排除的项目目录。')
    return p


def digest(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def free_name(path: Path, reserved: set[str]):
    candidate = path
    index = 1
    while candidate.exists() or str(candidate).casefold() in reserved:
        candidate = path.with_name(f'{path.stem} ({index}){path.suffix}')
        index += 1
    reserved.add(str(candidate).casefold())
    return candidate


def file_error(exc: Exception):
    code = getattr(exc, 'winerror', None)
    location = getattr(exc, 'filename', None)
    suffix = f' 路径：{location}' if location else ''
    if code in (32, 33):
        return f'文件被其他程序占用（WinError {code}）。请关闭相关文档、安装器或预览窗口后重新扫描。{suffix}'
    if isinstance(exc, PermissionError) or code == 5:
        return f'访问被拒绝（WinError 5 / 权限不足）。请检查目录写入和源文件删除权限；若服务由受限环境启动，请在普通 PowerShell 中启动，或更换可写入的归档位置。{suffix}'
    return str(exc)


def check_destination(target: Path, items):
    """Check write + cleanup permissions before moving any source files."""
    directories = {target, *(Path(item['target']).parent for item in items)}
    for folder in sorted(directories, key=lambda p: (len(p.parts), str(p))):
        try:
            safe_path(str(folder))
            folder.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(prefix='.organizer-check-', dir=folder) as probe:
                probe.write(b'file-organizer write check')
                probe.flush()
                os.fsync(probe.fileno())
        except OSError as exc:
            raise ValueError(f'归档目录写入检查失败，尚未移动任何文件。{file_error(exc)}') from exc


def verified_move(source: Path, target: Path, expected: list, expected_hash=None, before_remove=None, progress_callback=None):
    """Exclusive copy, verify content, then remove source; works across disks."""
    safe_path(str(source))
    safe_path(str(target))
    if not source.is_file() or fingerprint(source) != expected:
        raise ValueError('文件已被修改或不存在，请重新扫描。')
    if expected_hash and digest(source) != expected_hash:
        raise ValueError('文件内容已改变，不能自动撤销。')
    target.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        h = hashlib.sha256()
        with source.open('rb') as src, target.open('xb') as dst:
            created = True
            for block in iter(lambda: src.read(1024 * 1024), b''):
                dst.write(block)
                h.update(block)
                if progress_callback:
                    progress_callback('copying', src.tell())
            dst.flush()
            os.fsync(dst.fileno())
        value = h.hexdigest()
        if progress_callback:
            progress_callback('verifying', expected[0])
        if fingerprint(source) != expected or digest(target) != value:
            raise ValueError('复制验证失败或源文件发生变化，保留源文件。')
        if expected_hash and value != expected_hash:
            raise ValueError('文件内容发生变化，保留源文件。')
        shutil.copystat(source, target)
        if before_remove:
            before_remove(value)
        source.unlink()
        return value
    except Exception:
        if created:
            target.unlink(missing_ok=True)
        raise


class Organizer:
    def __init__(self, database: Path):
        database.parent.mkdir(parents=True, exist_ok=True)
        self.database = database
        self.lock = threading.RLock()
        self.previews = {}
        self.active_task = None
        self.stop_event = threading.Event()
        self.worker = None
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
        self.recover()

    def recover(self):
        """Recover durable move intents after an interrupted process."""
        with self.connect() as db:
            tasks = [json.loads(row[0]) for row in db.execute('SELECT payload FROM tasks')]
        for task in tasks:
            if task['status'] not in ('running', 'undoing'):
                continue
            undoing = task['status'] == 'undoing'
            for item in task['files']:
                if item['status'] == 'queued':
                    item['status'] = 'pending'
                    continue
                if item['status'] not in ('copying', 'copied', 'restoring', 'restore_copied'):
                    continue
                source = Path(item['target'] if undoing else item['source'])
                target = Path(item['source'] if undoing else item['target'])
                try:
                    if not source.exists() and target.is_file() and item.get('hash') and digest(target) == item['hash']:
                        item['status'] = 'undone' if undoing else 'moved'
                    else:
                        item['status'] = 'moved' if undoing else 'failed'
                        item['undo_error' if undoing else 'error'] = '上次操作被中断，请核对两处路径；可能保留了复制的文件。'
                except OSError as exc:
                    item['status'] = 'moved' if undoing else 'failed'
                    item['undo_error' if undoing else 'error'] = str(exc)
            task['status'] = ('undo_partial' if any(f['status'] == 'moved' for f in task['files']) else 'undone') if undoing else 'stopped'
            if task.get('progress'):
                task['progress']['phase'] = 'interrupted'
            task['warnings'].append('上次任务被中断，已恢复操作记录；请核对有提示的文件。')
            self.save(task)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, task):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO tasks VALUES (?, ?)',
                       (task['id'], json.dumps(task, ensure_ascii=False)))
        self.previews.pop(task['id'], None)

    def get(self, task_id):
        with self.lock:
            if self.active_task and self.active_task['id'] == task_id:
                return json.loads(json.dumps(self.active_task))
            if task_id in self.previews:
                return json.loads(json.dumps(self.previews[task_id]))
            with self.connect() as db:
                row = db.execute('SELECT payload FROM tasks WHERE id = ?', (task_id,)).fetchone()
            if not row:
                raise ValueError('任务不存在或临时预览已过期，请重新扫描；需要下次继续时请先保存草稿。')
            return json.loads(row[0])

    def history(self):
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT payload FROM tasks WHERE json_extract(payload, '$.status') NOT IN ('preview', 'draft') ORDER BY rowid DESC LIMIT 30").fetchall()
        return [json.loads(row[0]) for row in rows]

    def drafts(self):
        with self.lock, self.connect() as db:
            rows = db.execute("SELECT payload FROM tasks WHERE json_extract(payload, '$.status') = 'draft' ORDER BY rowid DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_draft(self, task_id, selected_ids, category_filter='全部'):
        with self.lock:
            task = self.get(task_id)
            if task['status'] not in ('preview', 'draft'):
                raise ValueError('只能保存尚未执行的预览。')
            ids = set(selected_ids)
            if not ids.issubset({f['id'] for f in task['files']}):
                raise ValueError('草稿包含无效的文件选择。')
            if category_filter not in {'全部', *(f['category'] for f in task['files'])}:
                raise ValueError('未知的分类筛选。')
            task['status'] = 'draft'
            task['selected_ids'] = [f['id'] for f in task['files'] if f['id'] in ids]
            task['category_filter'] = category_filter
            task['saved_at'] = stamp()
            self.save(task)
            self.previews.pop(task_id, None)
            return task

    def scan(self, source_raw, target_raw, mode, recursive):
        with self.lock:
            if self.active_task:
                raise ValueError('正在处理文件，请等待任务结束或安全停止后再扫描。')
            source, target = safe_path(source_raw), safe_path(target_raw)
            if not source.is_dir():
                raise ValueError('源目录不存在。')
            if target == source or source.is_relative_to(target):
                raise ValueError('目标不能与源目录相同，也不能是源目录的上级目录。')
            if mode not in ('documents', 'installers', 'all'):
                raise ValueError('未知整理规则。')
            types = DOCUMENTS if mode == 'documents' else INSTALLERS if mode == 'installers' else None
            files, warnings, reserved = [], [], set()
            examined = 0
            def walk_error(error):
                warnings.append(f'目录无法访问：{error.filename}')
            for root, dirs, names in os.walk(source, followlinks=False, onerror=walk_error):
                base = Path(root)
                allowed = []
                for name in dirs:
                    folder = base / name
                    try:
                        if name.lower() not in EXCLUDED and not is_link(folder) and not folder.resolve().is_relative_to(target):
                            allowed.append(name)
                    except OSError:
                        warnings.append(f'目录无法访问：{folder}')
                dirs[:] = allowed if recursive else []
                for name in sorted(names):
                    examined += 1
                    if examined > MAX_FILES:
                        raise ValueError('扫描超过 10000 个文件，请缩小范围；尚未移动任何文件。')
                    p = base / name
                    ext = p.suffix.lower()
                    if types is not None and ext not in types:
                        continue
                    if name.startswith('~$'):
                        warnings.append(f'已跳过 Office 临时锁文件：{p}')
                        continue
                    try:
                        if is_link(p) or not p.is_file():
                            warnings.append(f'已跳过链接或非普通文件：{p}')
                            continue
                        fp = fingerprint(p)
                        category, bucket = classify(p)
                        dest = free_name(target / bucket / name, reserved)
                        caution = ext in INSTALLERS
                        files.append({'id': uuid.uuid4().hex, 'source': str(p), 'target': str(dest),
                                      'name': name, 'category': category, 'size': fp[0], 'fingerprint': fp,
                                      'selected': not caution, 'warning': '请确认是可移动的安装包或镜像；EXE 也可能是软件主程序。' if caution else '',
                                      'status': 'planned'})
                    except OSError as exc:
                        warnings.append(f'{p}：{exc}')
            task = {'id': uuid.uuid4().hex, 'created_at': stamp(), 'source': str(source),
                    'target': str(target), 'mode': mode, 'recursive': recursive,
                    'status': 'preview', 'files': files, 'warnings': warnings}
            # Scans stay in memory. Only explicitly saved drafts and executed
            # tasks are persisted; bound memory usage for abandoned previews.
            if len(self.previews) >= 30:
                self.previews.pop(next(iter(self.previews)))
            self.previews[task['id']] = task
            return task

    def active(self):
        with self.lock:
            return {'id': self.active_task['id']} if self.active_task else None

    def progress(self, task_id):
        with self.lock:
            task = self.active_task if self.active_task and self.active_task['id'] == task_id else self.get(task_id)
            return {'id': task_id, 'status': task['status'],
                    'progress': dict(task.get('progress', {})),
                    'summary': {status: sum(f['status'] == status for f in task['files'])
                                for status in ('moved', 'failed', 'pending', 'skipped', 'undone')}}

    def stop(self, task_id):
        with self.lock:
            if not self.active_task or self.active_task['id'] != task_id:
                raise ValueError('该任务已经结束。')
            self.stop_event.set()
            self.active_task['progress']['stop_requested'] = True
            self.save(self.active_task)
            return self.progress(task_id)

    def wait(self, timeout=None):
        worker = self.worker
        if worker and worker is not threading.current_thread():
            worker.join(timeout)

    def _start(self, task_id, kind, selected_ids=None, background=False):
        with self.lock:
            if self.active_task:
                raise ValueError('已有文件任务正在运行，请等待或先安全停止。')
            task = self.get(task_id)
            if kind == 'move':
                if task['status'] not in ('preview', 'draft'):
                    raise ValueError('该预览已经执行过，请重新扫描。')
                ids = set(selected_ids or [])
                if not ids or not ids.issubset({f['id'] for f in task['files']}):
                    raise ValueError('请勾选预览中的有效文件。')
                items = [f for f in task['files'] if f['id'] in ids]
                task['selected_ids'] = [f['id'] for f in items]
            elif kind == 'undo':
                if task['status'] not in ('completed', 'stopped', 'undo_partial', 'undone'):
                    raise ValueError('只能撤销已经结束或停止的整理任务。')
                items = [f for f in reversed(task['files']) if f['status'] == 'moved']
            else:
                if task['status'] not in ('completed', 'stopped'):
                    raise ValueError('只能重试已结束或停止的整理任务。')
                wanted = 'failed' if kind == 'retry' else 'pending'
                items = [f for f in task['files'] if f['status'] == wanted]
                if not items:
                    raise ValueError('没有可重试或继续的文件。')
                reserved = {str(f['target']).casefold() for f in task['files'] if f not in items}
                for item in items:
                    item['target'] = str(free_name(Path(item['target']), reserved))
            if kind != 'undo':
                check_destination(Path(task['target']), items)
                item_ids = {item['id'] for item in items}
                for item in task['files']:
                    if item['id'] in item_ids:
                        item['status'] = 'queued'
                        item.pop('error', None)
                    elif kind == 'move':
                        item['status'] = 'skipped'
            task['status'] = 'undoing' if kind == 'undo' else 'running'
            task['progress'] = {'kind': kind, 'total': len(items), 'completed': 0,
                                'current_name': '', 'current_bytes': 0, 'current_size': 0,
                                'phase': 'preparing', 'stop_requested': False}
            self.stop_event = threading.Event()
            self.active_task = task
            self.save(task)
            snapshot = json.loads(json.dumps(task))
            if background:
                self.worker = threading.Thread(target=self._process, args=(task, items, kind),
                                               name='organizer-files', daemon=False)
                self.worker.start()
                return snapshot
        self._process(task, items, kind)
        return self.get(task_id)

    def _process(self, task, items, kind):
        undoing = kind == 'undo'
        try:
            for index, item in enumerate(items):
                with self.lock:
                    if self.stop_event.is_set():
                        if not undoing:
                            for remaining in items[index:]:
                                remaining['status'] = 'pending'
                        break
                    task['progress'].update(current_name=item['name'], current_size=item['size'],
                                            current_bytes=0, phase='copying')
                    item['status'] = 'restoring' if undoing else 'copying'
                    item['attempts'] = item.get('attempts', 0) + 1
                    self.save(task)
                try:
                    def report(phase, copied):
                        with self.lock:
                            task['progress'].update(phase=phase, current_bytes=copied)

                    def journal(value):
                        with self.lock:
                            item['hash'] = value
                            item['status'] = 'restore_copied' if undoing else 'copied'
                            self.save(task)

                    if undoing:
                        current = Path(item['target'])
                        verified_move(current, Path(item['source']), fingerprint(current), item['hash'], journal, report)
                    else:
                        verified_move(Path(item['source']), Path(item['target']), item['fingerprint'],
                                      before_remove=journal, progress_callback=report)
                    with self.lock:
                        item['status'] = 'undone' if undoing else 'moved'
                        item.pop('undo_error' if undoing else 'error', None)
                except Exception as exc:
                    with self.lock:
                        item['status'] = 'moved' if undoing else 'failed'
                        item['undo_error' if undoing else 'error'] = file_error(exc)
                with self.lock:
                    task['progress']['completed'] += 1
                    task['progress']['current_bytes'] = 0
                    task['progress']['current_size'] = 0
                    self.save(task)
            with self.lock:
                if undoing:
                    task['status'] = 'undo_partial' if any(f['status'] == 'moved' for f in task['files']) else 'undone'
                else:
                    task['status'] = 'stopped' if any(f['status'] == 'pending' for f in task['files']) else 'completed'
                task['progress'].update(phase='finished', current_name='')
                self.save(task)
        except Exception as exc:
            with self.lock:
                for item in items:
                    if item['status'] == 'queued':
                        item['status'] = 'pending'
                task['status'] = 'undo_partial' if undoing else 'stopped'
                task['warnings'].append(f'任务异常停止，已保留操作记录：{file_error(exc)}')
                task['progress']['phase'] = 'interrupted'
                self.save(task)
        finally:
            with self.lock:
                self.active_task = None

    def execute(self, task_id, selected_ids):
        return self._start(task_id, 'move', selected_ids)

    def undo(self, task_id):
        return self._start(task_id, 'undo')

    def retry(self, task_id):
        return self._start(task_id, 'retry')

    def resume(self, task_id):
        return self._start(task_id, 'resume')

    def start_execute(self, task_id, selected_ids):
        return self._start(task_id, 'move', selected_ids, background=True)

    def start_undo(self, task_id):
        return self._start(task_id, 'undo', background=True)

    def start_retry(self, task_id):
        return self._start(task_id, 'retry', background=True)

    def start_resume(self, task_id):
        return self._start(task_id, 'resume', background=True)
