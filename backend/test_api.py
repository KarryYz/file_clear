import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app
from backend.organizer import Organizer


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'docs'
        self.source.mkdir()
        self.patch = patch('backend.main.organizer', Organizer(self.root / 'db.sqlite3'))
        self.patch.start()
        self.client = TestClient(app, base_url='http://127.0.0.1:8000')
        self.service = __import__('backend.main', fromlist=['organizer']).organizer

    def tearDown(self):
        if self.service.active():
            self.service.stop(self.service.active()['id'])
        self.service.wait(10)
        self.client.close()
        self.patch.stop()
        self.temp.cleanup()

    def finished(self, task_id):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            progress = self.client.get(f'/api/tasks/{task_id}/progress').json()
            if progress['status'] not in ('running', 'undoing'):
                return self.client.get(f'/api/tasks/{task_id}').json()
            time.sleep(.01)
        self.fail('Background task did not finish')

    def test_full_http_flow(self):
        original = self.source / 'report.pdf'
        original.write_bytes(b'API test document')
        scan = self.client.post('/api/scan', json={
            'source': str(self.source), 'target': str(self.source / 'archive')})
        self.assertEqual(scan.status_code, 200)
        task = scan.json()
        result = self.client.post(f"/api/tasks/{task['id']}/execute", json={
            'selected_ids': [task['files'][0]['id']]})
        self.assertEqual(result.status_code, 200)
        self.finished(task['id'])
        self.assertFalse(original.exists())
        undo = self.client.post(f"/api/tasks/{task['id']}/undo", json={})
        self.assertEqual(undo.status_code, 200)
        self.assertEqual(self.finished(task['id'])['status'], 'undone')
        self.assertTrue(original.exists())
        self.assertEqual(len(self.client.get('/api/tasks').json()), 1)

    def test_access_and_inputs(self):
        self.assertEqual(self.client.get('/api/health').status_code, 200)
        self.assertEqual(self.client.get('/api/tasks', headers={'Origin': 'https://example.com'}).status_code, 403)
        self.assertEqual(self.client.get('/api/tasks', headers={'Host': 'example.com'}).status_code, 403)
        self.assertEqual(self.client.post('/api/scan', data={'source': str(self.source)}).status_code, 415)
        self.assertEqual(self.client.post('/api/scan', json={'source': 'relative', 'target': 'other'}).status_code, 400)

    def test_explicit_draft_and_record_details(self):
        (self.source / 'font.ttf').write_bytes(b'test font')
        task = self.client.post('/api/scan', json={
            'source': str(self.source), 'target': str(self.source / 'Archive'), 'mode': 'all'}).json()
        self.assertEqual(self.client.get('/api/tasks').json(), [])
        selected = [task['files'][0]['id']]
        saved = self.client.post(f"/api/tasks/{task['id']}/draft", json={
            'selected_ids': selected, 'category_filter': '字体'})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get('/api/drafts').json()[0]['selected_ids'], selected)
        self.assertEqual(self.client.get(f"/api/tasks/{task['id']}").json()['category_filter'], '字体')
        self.assertEqual(self.client.get('/api/tasks').json(), [])
        result = self.client.post(f"/api/tasks/{task['id']}/execute", json={'selected_ids': selected})
        self.assertEqual(result.status_code, 200)
        self.finished(task['id'])
        self.assertEqual(self.client.get('/api/drafts').json(), [])
        self.assertEqual(self.client.get(f"/api/tasks/{task['id']}").json()['files'][0]['status'], 'moved')
        self.assertEqual(len(self.client.get('/api/tasks').json()), 1)

    def test_directory_selection_and_cancel(self):
        with patch('backend.main.choose_directory', return_value=str(self.source)) as picker:
            response = self.client.post('/api/directories/choose', json={'initial': str(self.root), 'title': '选择源目录'})
            self.assertEqual(response.json()['path'], str(self.source))
            picker.assert_called_once_with(str(self.root), '选择源目录')
        with patch('backend.main.choose_directory', return_value=None):
            self.assertIsNone(self.client.post('/api/directories/choose', json={}).json()['path'])


if __name__ == '__main__':
    unittest.main()
