import tempfile
import unittest
import threading
from pathlib import Path
from unittest.mock import patch

from backend.organizer import Organizer, digest, file_error, verified_move


class OrganizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.target = self.source / 'archive'
        self.service = Organizer(self.root / 'tasks.sqlite3')

    def tearDown(self):
        if self.service.active():
            self.service.stop(self.service.active()['id'])
        self.service.wait(10)
        self.temp.cleanup()

    def write(self, name, content=b'example contents'):
        p = self.source / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def scan(self, mode='documents', recursive=False):
        return self.service.scan(str(self.source), str(self.target), mode, recursive)

    def execute(self, task):
        return self.service.execute(task['id'], [f['id'] for f in task['files']])

    def test_preview_move_and_undo(self):
        original = self.write('报告.docx')
        task = self.scan()
        self.assertTrue(original.exists(), 'Scanning must never move files')
        result = self.execute(task)
        moved = Path(result['files'][0]['target'])
        self.assertFalse(original.exists())
        self.assertEqual(moved.read_bytes(), b'example contents')
        self.assertEqual(self.service.undo(task['id'])['status'], 'undone')
        self.assertTrue(original.exists())
        self.assertFalse(moved.exists())

    def test_installer_requires_selection(self):
        self.write('setup.EXE')
        self.write('report.PDF')
        files = self.scan('all')['files']
        self.assertFalse(next(f for f in files if f['name'] == 'setup.EXE')['selected'])
        self.assertTrue(next(f for f in files if f['name'] == 'report.PDF')['selected'])

    def test_nested_and_existing_names_are_preserved(self):
        self.write('a/report.pdf', b'a')
        self.write('b/report.pdf', b'b')
        prior = self.target / 'PDF' / 'report.pdf'
        prior.parent.mkdir(parents=True)
        prior.write_bytes(b'prior')
        task = self.scan(recursive=True)
        self.assertEqual(len(task['files']), 2, 'Archive must be excluded')
        self.assertEqual(len({f['target'] for f in task['files']}), 2)
        self.execute(task)
        self.assertEqual(prior.read_bytes(), b'prior')

    def test_changed_source_is_not_moved(self):
        original = self.write('a.pdf')
        task = self.scan()
        original.write_bytes(b'changed after scan')
        result = self.execute(task)
        self.assertEqual(result['files'][0]['status'], 'failed')
        self.assertEqual(original.read_bytes(), b'changed after scan')

    def test_new_collision_after_preview_never_overwrites(self):
        original = self.write('a.pdf')
        task = self.scan()
        target = Path(task['files'][0]['target'])
        target.parent.mkdir(parents=True)
        target.write_bytes(b'new file')
        result = self.execute(task)
        self.assertEqual(result['files'][0]['status'], 'failed')
        self.assertTrue(original.exists())
        self.assertEqual(target.read_bytes(), b'new file')

    def test_undo_refuses_changed_content(self):
        self.write('a.pdf')
        task = self.execute(self.scan())
        target = Path(task['files'][0]['target'])
        target.write_bytes(b'changed')
        result = self.service.undo(task['id'])
        self.assertEqual(result['status'], 'undo_partial')
        self.assertEqual(target.read_bytes(), b'changed')

    def test_undo_preserves_new_original_and_can_retry(self):
        original = self.write('a.pdf')
        task = self.execute(self.scan())
        original.write_bytes(b'new original')
        self.assertEqual(self.service.undo(task['id'])['status'], 'undo_partial')
        self.assertEqual(original.read_bytes(), b'new original')
        original.unlink()
        self.assertEqual(self.service.undo(task['id'])['status'], 'undone')
        self.assertEqual(original.read_bytes(), b'example contents')

    def test_scope_and_ids_validation(self):
        self.write('sub/a.pdf')
        self.write('node_modules/b.pdf')
        self.assertEqual(len(self.scan()['files']), 0)
        task = self.scan(recursive=True)
        self.assertEqual(len(task['files']), 1)
        with self.assertRaises(ValueError):
            self.service.execute(task['id'], ['invalid'])
        with self.assertRaises(ValueError):
            self.service.scan(str(self.source), str(self.root), 'documents', True)

    def test_recovery_after_move_before_final_record(self):
        original = self.write('a.pdf')
        task = self.scan()
        item = task['files'][0]
        target = Path(item['target'])
        target.parent.mkdir(parents=True)
        original.replace(target)
        item['status'], item['hash'] = 'copied', digest(target)
        task['status'] = 'running'
        self.service.save(task)
        recovered = Organizer(self.root / 'tasks.sqlite3').get(task['id'])
        self.assertEqual(recovered['files'][0]['status'], 'moved')
        self.assertEqual(self.service.undo(task['id'])['status'], 'undone')

    def test_generated_category_directories_are_english(self):
        for name in ('a.docx', 'b.pdf', 'c.xlsx', 'd.pptx', 'setup.exe'):
            self.write(name)
        task = self.scan('all')
        for item in task['files']:
            relative = Path(item['target']).relative_to(self.target)
            self.assertTrue(str(relative.parent).isascii())
        self.assertEqual(Path(next(f['target'] for f in task['files'] if f['name'] == 'setup.exe')).parent,
                         self.target / 'Installers' / 'EXE')

    def test_destination_failure_preserves_preview_and_sources(self):
        original = self.write('a.pdf')
        task = self.scan()
        with patch('backend.organizer.tempfile.TemporaryFile', side_effect=PermissionError(13, 'denied', str(self.target))):
            with self.assertRaisesRegex(ValueError, '尚未移动任何文件'):
                self.execute(task)
        self.assertTrue(original.exists())
        self.assertEqual(self.service.get(task['id'])['status'], 'preview')

    def test_permission_and_busy_error_messages(self):
        denied = PermissionError(13, 'denied', 'D:/download/Archive')
        self.assertIn('普通 PowerShell', file_error(denied))
        busy = OSError('busy')
        busy.winerror = 32
        self.assertIn('占用', file_error(busy))

    def test_all_types_move_and_undo_without_touching_folders(self):
        mapping = {
            'backup.ZIP': 'Packages/ZIP', 'backup.rar': 'Packages/RAR',
            'backup.7z': 'Packages/7Z', 'backup.tar.gz': 'Packages/TAR',
            'photo.JPG': 'Images', 'clip.mp4': 'Videos', 'song.flac': 'Audio',
            'font.ttf': 'Fonts', 'font.woff2': 'Fonts', 'note.md': 'Text',
            'uncommon.custom': 'Other', 'LICENSE': 'Other', '.settings': 'Other',
            'report.pdf': 'PDF', 'setup.exe': 'Installers/EXE',
        }
        for name in mapping:
            self.write(name, name.encode())
        nested = self.write('untouched/nested.png', b'nested')
        task = self.scan('all')
        self.assertEqual(len(task['files']), len(mapping))
        for item in task['files']:
            self.assertEqual(Path(item['target']).parent, self.target / mapping[item['name']])
        result = self.execute(task)
        self.assertTrue(all(f['status'] == 'moved' for f in result['files']))
        self.assertEqual(nested.read_bytes(), b'nested')
        self.assertEqual(self.service.undo(task['id'])['status'], 'undone')
        for name in mapping:
            self.assertEqual((self.source / name).read_bytes(), name.encode())

    def test_recursive_all_excludes_archive_and_dependencies(self):
        self.write('nested/unknown.zzz')
        self.write('nested/no-extension')
        self.write('node_modules/package.json')
        self.write('archive/Images/already.png')
        self.write('~$locked.docx')
        task = self.scan('all', recursive=True)
        self.assertEqual({f['name'] for f in task['files']}, {'unknown.zzz', 'no-extension'})
        self.assertTrue(any('临时锁文件' in w for w in task['warnings']))

    def test_specific_modes_still_filter_other_types(self):
        self.write('a.pdf')
        self.write('setup.exe')
        self.write('a.zip')
        self.write('unknown')
        self.assertEqual({f['name'] for f in self.scan('documents')['files']}, {'a.pdf'})
        self.assertEqual({f['name'] for f in self.scan('installers')['files']}, {'setup.exe'})

    def test_scan_is_transient_and_not_listed_in_history(self):
        self.write('a.pdf')
        task = self.scan()
        self.assertEqual(self.service.history(), [])
        self.assertEqual(self.service.drafts(), [])
        with self.service.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 0)
        self.assertEqual(self.service.get(task['id'])['status'], 'preview')
        restarted = Organizer(self.root / 'tasks.sqlite3')
        with self.assertRaisesRegex(ValueError, '临时预览已过期'):
            restarted.get(task['id'])

    def test_draft_selection_filter_and_rules_survive_restart(self):
        self.write('a.pdf')
        self.write('b.ttf')
        task = self.scan('all')
        selected = [next(f['id'] for f in task['files'] if f['name'] == 'b.ttf')]
        self.service.save_draft(task['id'], selected, '字体')
        restarted = Organizer(self.root / 'tasks.sqlite3')
        draft = restarted.drafts()[0]
        self.assertEqual(draft['selected_ids'], selected)
        self.assertEqual(draft['category_filter'], '字体')
        self.assertEqual(draft['mode'], 'all')
        self.assertFalse(draft['recursive'])
        self.assertEqual(restarted.history(), [])
        result = restarted.execute(task['id'], selected)
        self.assertEqual(restarted.drafts(), [])
        self.assertEqual(len(restarted.history()), 1)
        self.assertTrue((self.source / 'a.pdf').exists())
        self.assertFalse((self.source / 'b.ttf').exists())
        self.assertEqual(restarted.get(task['id']), result)
        self.assertEqual(restarted.undo(task['id'])['status'], 'undone')

    def test_empty_draft_can_update_and_changed_source_stays_safe(self):
        original = self.write('a.pdf')
        task = self.scan()
        draft = self.service.save_draft(task['id'], [], 'PDF文档')
        self.assertEqual(draft['selected_ids'], [])
        selected = [task['files'][0]['id']]
        with self.assertRaises(ValueError):
            self.service.save_draft(task['id'], ['unknown'])
        with self.assertRaises(ValueError):
            self.service.save_draft(task['id'], [], 'invalid filter')
        self.service.save_draft(task['id'], selected, '全部')
        self.assertEqual(len(self.service.drafts()), 1)
        original.write_bytes(b'new document after saving')
        restarted = Organizer(self.root / 'tasks.sqlite3')
        result = restarted.execute(task['id'], selected)
        self.assertEqual(result['files'][0]['status'], 'failed')
        self.assertEqual(original.read_bytes(), b'new document after saving')
        with self.assertRaises(ValueError):
            restarted.save_draft(task['id'], selected)

    def test_legacy_scan_records_hidden_but_history_survives_restart(self):
        self.write('a.pdf')
        old_scan = self.scan()
        self.service.save(old_scan)  # Old releases persisted every scan.
        completed = self.execute(self.scan())
        restarted = Organizer(self.root / 'tasks.sqlite3')
        self.assertEqual([t['id'] for t in restarted.history()], [completed['id']])
        self.assertEqual(restarted.drafts(), [])
        self.assertEqual(restarted.undo(completed['id'])['status'], 'undone')

    def test_progress_stop_finishes_current_file_and_resume_is_selective(self):
        self.write('a.pdf')
        self.write('b.pdf')
        task = self.scan()
        entered, release = threading.Event(), threading.Event()

        def delayed(*args, **kwargs):
            kwargs['progress_callback']('copying', 5)
            entered.set()
            if not release.wait(5):
                raise RuntimeError('Test synchronization timed out')
            return verified_move(*args, **kwargs)

        with patch('backend.organizer.verified_move', side_effect=delayed):
            result = self.service.start_execute(task['id'], [f['id'] for f in task['files']])
            self.assertEqual(result['status'], 'running')
            self.assertTrue(entered.wait(3))
            progress = self.service.progress(task['id'])
            self.assertEqual(progress['progress']['current_name'], 'a.pdf')
            self.assertEqual(progress['progress']['current_bytes'], 5)
            with self.assertRaises(ValueError):
                self.service.start_execute(task['id'], [task['files'][0]['id']])
            self.assertTrue(self.service.stop(task['id'])['progress']['stop_requested'])
            release.set()
            self.service.wait(5)
        stopped = self.service.get(task['id'])
        self.assertEqual(stopped['status'], 'stopped')
        self.assertEqual([f['status'] for f in stopped['files']], ['moved', 'pending'])
        self.assertFalse((self.source / 'a.pdf').exists())
        self.assertTrue((self.source / 'b.pdf').exists())
        resumed = self.service.resume(task['id'])
        self.assertEqual([f['status'] for f in resumed['files']], ['moved', 'moved'])
        self.assertEqual([f['attempts'] for f in resumed['files']], [1, 1])
        self.assertEqual(self.service.undo(task['id'])['status'], 'undone')

    def test_retry_only_failed_files_and_preserves_success(self):
        self.write('a.pdf')
        self.write('b.pdf')
        task = self.scan()
        def fail_second(source, *args, **kwargs):
            if source.name == 'b.pdf':
                raise PermissionError(13, 'file temporarily locked', str(source))
            return verified_move(source, *args, **kwargs)
        with patch('backend.organizer.verified_move', side_effect=fail_second):
            failed = self.execute(task)
        self.assertEqual([f['status'] for f in failed['files']], ['moved', 'failed'])
        first_hash = failed['files'][0]['hash']
        result = self.service.retry(task['id'])
        self.assertEqual([f['status'] for f in result['files']], ['moved', 'moved'])
        self.assertEqual(result['files'][0]['hash'], first_hash)
        self.assertEqual([f['attempts'] for f in result['files']], [1, 2])
        self.assertEqual(result['progress']['total'], 1)
        self.assertEqual(self.service.undo(task['id'])['status'], 'undone')


if __name__ == '__main__':
    unittest.main()
