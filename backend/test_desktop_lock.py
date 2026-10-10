import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'nt', 'Windows desktop locking')
class DesktopLockTests(unittest.TestCase):
    def test_second_process_blocked_then_lock_released(self):
        from backend.desktop_lock import DesktopLock
        with tempfile.TemporaryDirectory() as directory:
            code = ('import sys; from pathlib import Path; '
                    'from backend.desktop_lock import DesktopLock; '
                    'lock = DesktopLock(Path(sys.argv[1])); '
                    'sys.exit(0 if lock.handle else 2)')
            def second():
                return subprocess.run([sys.executable, '-c', code, directory],
                                      cwd=Path(__file__).resolve().parents[1],
                                      capture_output=True, timeout=10)
            with DesktopLock(Path(directory)) as first:
                self.assertTrue(first.handle)
                blocked = second()
                self.assertEqual(blocked.returncode, 2, blocked.stderr.decode())
            released = second()
            self.assertEqual(released.returncode, 0, released.stderr.decode())

    def test_separate_data_directories_allowed(self):
        from backend.desktop_lock import DesktopLock
        with tempfile.TemporaryDirectory() as directory:
            with DesktopLock(Path(directory) / 'a') as first:
                with DesktopLock(Path(directory) / 'b') as second:
                    self.assertTrue(first.handle)
                    self.assertTrue(second.handle)
