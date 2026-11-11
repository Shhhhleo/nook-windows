"""Regression checks for local persistence, cancellation and widget rebuilding."""
import os
import tempfile
import threading
import unittest
from pathlib import Path

temporary = tempfile.TemporaryDirectory()
os.environ['NOOK_DATA_DIR'] = temporary.name
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PySide6.QtWidgets import QApplication
from nook.storage import Store, protect
from nook.services import search_files
from nook.ui import Notch, Settings


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication([])

    def test_encrypted_credentials_roundtrip(self):
        payload = b'example-test-secret'
        encrypted = protect(payload)
        self.assertNotIn(payload, encrypted)
        self.assertEqual(protect(encrypted, True), payload)
        store = Store()
        store.secret('test', 'local-only')
        self.assertEqual(Store().secret('test'), 'local-only')

    def test_settings_and_tasks_persist(self):
        store = Store()
        store.settings['todos'] = [{'text': 'Regression check', 'done': True}]
        store.save()
        self.assertEqual(Store().settings['todos'], store.settings['todos'])

    def test_search_cancellation_and_skips(self):
        root = Path(temporary.name) / 'files'
        root.mkdir(exist_ok=True)
        (root / 'report.txt').write_text('test')
        (root / 'node_modules').mkdir(exist_ok=True)
        (root / 'node_modules' / 'report.txt').write_text('excluded')
        results, limited = search_files(root, 'REPORT', threading.Event())
        self.assertEqual(len(results), 1)
        cancel = threading.Event()
        cancel.set()
        self.assertEqual(search_files(root, 'report', cancel), ([], True))

    def test_widget_rebuild_and_geometry(self):
        store = Store()
        store.settings['animation'] = False
        notch = Notch(store)
        notch.pool.waitForDone(10000)
        bounds = QApplication.primaryScreen().geometry()
        self.assertEqual(notch.target_geometry().top(), bounds.top())
        self.assertLessEqual(abs(notch.target_geometry().center().x() - bounds.center().x()), 1)
        notch.expand(True)
        self.assertEqual(notch.height(), min(store.settings['height'], bounds.height() - 40))
        notch.todo_input.setText('Added through UI handler')
        notch.add_todo()
        self.assertEqual(store.settings['todos'][-1]['text'], 'Added through UI handler')
        for enabled in [[], ['Time'], ['Music'], list(store.settings['order'])]:
            store.settings['enabled'] = enabled
            notch.rebuild()
            self.app.processEvents()
        settings = Settings(notch)
        self.assertEqual(settings.tabs.count(), 4)
        notch.expand(False)
        self.assertEqual(notch.height(), 38)
        notch.pool.waitForDone(10000)
        notch.tray.hide()
        notch.deleteLater()


if __name__ == '__main__':
    unittest.main()
