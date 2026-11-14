import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

feature_data = tempfile.TemporaryDirectory()
os.environ['NOOK_DATA_DIR'] = feature_data.name
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from nook.presets import PRESETS, validate_template, write_template, read_template
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from nook.storage import Store
from nook.ui import Notch, Settings


class TemplateTests(unittest.TestCase):
    def test_templates_exclude_accounts_and_reject_extreme_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'template.json')
            settings = dict(PRESETS['Focus'], notion_token='secret', search_root='private')
            write_template(path, settings)
            self.assertEqual(read_template(path), PRESETS['Focus'])
            self.assertNotIn('secret', path.read_text())
        with self.assertRaises(ValueError):
            validate_template({'format': 'nook-appearance-v1', 'settings': {'width': 99999}})


class DesktopTests(unittest.TestCase):
    def setUp(self):
        for name in ('refresh_media', 'refresh_widgets', 'refresh_tasks'):
            patcher = patch.object(Notch, name)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_tiles_tasks_drag_and_settings_rebuild(self):
        app = QApplication.instance() or QApplication([])
        store = Store()
        store.settings.update(desktop_widgets=[], todos=[], animation=False)
        notch = Notch(store)
        for kind in ('Clock', 'To do', 'Note'):
            notch.desktop.add(kind)
        self.assertEqual(len(notch.desktop.windows), 3)
        task = next(w for w in notch.desktop.windows.values() if w.kind == 'To do')
        task.task_input.setText('Desktop regression task')
        task.add_task()
        self.assertEqual(Store().settings['todos'][0]['text'], 'Desktop regression task')
        note = next(w for w in notch.desktop.windows.values() if w.kind == 'Note')
        note.note.setPlainText('Saved locally')
        notch.desktop.flush()
        self.assertTrue(any(r.get('text') == 'Saved locally' for r in Store().settings['desktop_widgets']))
        clock = next(w for w in notch.desktop.windows.values() if w.kind == 'Clock')
        QTest.mousePress(clock, Qt.LeftButton, pos=QPoint(12, 12))
        QTest.mouseMove(clock, QPoint(30, 30))
        QTest.mouseRelease(clock, Qt.LeftButton, pos=QPoint(30, 30))
        self.assertEqual(clock.config['x'], clock.x())
        self.assertEqual(clock.config['y'], clock.y())
        settings = Settings(notch)
        settings.apply_preset(PRESETS['Focus'])
        self.assertEqual(notch.width(), notch.target_geometry().width())
        self.assertEqual(notch.height(), PRESETS['Focus']['compact_height'])
        for identity in list(notch.desktop.windows):
            notch.desktop.remove(identity)
        self.assertFalse(notch.desktop.timer.isActive())
        notch.pool.waitForDone(10000)
        notch.tray.hide()
        notch.deleteLater()
        app.processEvents()
