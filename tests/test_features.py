import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

feature_data = tempfile.TemporaryDirectory()
os.environ['NOOK_DATA_DIR'] = feature_data.name
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from nook import assistant
from nook.presets import PRESETS, validate_template, write_template, read_template
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from nook.storage import Store
from nook.ui import Notch, Settings


class AssistantTests(unittest.TestCase):
    def test_arithmetic_and_execution_boundary(self):
        self.assertEqual(assistant.calculate('(24 + 6) / 5'), '6')
        self.assertEqual(assistant.calculate('2^8'), '256')
        for expression in ['__import__("os").getcwd()', '2**1000000', '[1]*5', '9**9**9']:
            with self.assertRaises((ValueError, SyntaxError)):
                assistant.calculate(expression)

    def test_file_lookup_and_no_model_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'quarterly-report.txt').write_text('private contents')
            settings = {'search_root': directory, 'ollama_model': ''}
            found = assistant.respond('find files report', [], settings)
            self.assertEqual(len(found['files']), 1)
            self.assertNotIn('private contents', json.dumps(found))
            self.assertEqual(assistant.respond('what is 20 * 5?', [], settings)['text'], '20 * 5 = 100')
            with patch.object(assistant, 'models', return_value=['qwen3:0.6b']), patch.object(assistant, 'ollama_request', return_value={'message': {'content': '{"action":"answer","argument":"Hello"}'}}):
                self.assertEqual(assistant.respond('hello', [], settings)['text'], 'Hello')

    def test_model_web_lookup_requires_visible_action(self):
        settings = {'search_root': '.', 'ollama_model': 'test:local'}
        with patch.object(assistant, 'models', return_value=['test:local']), \
             patch.object(assistant, 'ollama_request', return_value={'message': {'content':
                 json.dumps({'action': 'web_lookup', 'argument': 'solar energy'})}}) as api, \
             patch.object(assistant, 'web_lookup') as lookup:
            answer = assistant.respond('research solar energy', [], settings)
            self.assertEqual(answer['confirm_web'], 'solar energy')
            lookup.assert_not_called()
            self.assertEqual(api.call_args.args[1]['keep_alive'], 0)

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
        notch.open_assistant()
        panel = notch.assistant_panel
        panel.input.setText('Unsent message')
        settings = Settings(notch)
        settings.apply_preset(PRESETS['Focus'])
        self.assertIs(notch.assistant_panel, panel)
        self.assertEqual(panel.input.text(), 'Unsent message')
        self.assertEqual(notch.width(), notch.target_geometry().width())
        self.assertEqual(notch.height(), PRESETS['Focus']['music_height'])
        for identity in list(notch.desktop.windows):
            notch.desktop.remove(identity)
        self.assertFalse(notch.desktop.timer.isActive())
        notch.pool.waitForDone(10000)
        notch.tray.hide()
        notch.cloud.close()
        notch.deleteLater()
        app.processEvents()
