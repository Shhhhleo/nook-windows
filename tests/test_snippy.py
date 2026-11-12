"""First-run identity, compact/fullscreen continuity and idle lifecycle checks."""
import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from nook import storage, local_ai
from nook.snippy import greeting
from nook.ui import Notch, STYLE
from nook.notifications import NotificationDelta


class SnippyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        from pathlib import Path
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(storage, 'DATA', Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ('refresh_media', 'refresh_widgets', 'refresh_tasks'):
            patcher = patch.object(Notch, name)
            patcher.start()
            self.addCleanup(patcher.stop)
        store = storage.Store()
        store.settings['animation'] = False
        self.notch = Notch(store)
        self.snippy = self.notch.cloud
        self.chat = self.snippy.workspace
        self.notch.show()
        self.app.processEvents()

    def tearDown(self):
        self.snippy.close()
        self.chat.deleteLater()
        self.notch.tray.hide()
        self.notch.hide()
        self.notch.deleteLater()
        self.app.processEvents()

    def test_first_run_name_saved_and_prompt_not_repeated(self):
        self.snippy.onboard()
        self.assertTrue(self.chat.name_input.isVisible())
        self.chat.name_input.setText('   ')
        self.chat.save_name()
        self.assertFalse(storage.Store().settings['user_name'])
        self.chat.name_input.setText('  Alex  ')
        QTest.keyClick(self.chat.name_input, Qt.Key_Return)
        self.assertEqual(storage.Store().settings['user_name'], 'Alex')
        self.assertTrue(self.chat.name_input.isHidden())
        self.chat.close()
        self.snippy.onboard()
        self.assertFalse(self.chat.isVisible())
        index = storage.Store().settings['greeting_index']
        self.snippy.open_fullscreen()
        self.assertEqual(storage.Store().settings['greeting_index'], index + 1)

    def test_time_greetings_boundaries_and_rotation(self):
        for hour, minute, prefix in [(5, 59, 'Working late'), (6, 0, 'Good morning'),
                (12, 0, 'Good morning'), (12, 1, 'Good afternoon'), (16, 0, 'Good afternoon'),
                (16, 1, 'Good evening'), (18, 0, 'Good evening'), (18, 1, 'Working late')]:
            self.assertTrue(greeting('Alex', datetime(2026, 1, 1, hour, minute), 0).startswith(prefix))
        self.assertEqual(len({greeting('Alex', datetime.now(), i) for i in range(5)}), 5)

    def test_quick_send_bubble_fullscreen_and_sleep(self):
        self.notch.store.settings['user_name'] = 'Alex'
        def immediate(key, work, done, failed=None):
            done(work())
        with patch.object(self.notch, 'run_job', side_effect=immediate), patch.object(local_ai, 'stop') as stop:
            self.snippy.toggle_input()
            self.assertEqual(self.snippy.width(), 220)
            self.snippy.input.setText('24 * 7')
            QTest.keyClick(self.snippy.input, Qt.Key_Return)
            self.assertIn('168', self.snippy.reply.text())
            self.assertFalse(self.snippy.bubble.isHidden())
            self.assertEqual(self.chat.input.text(), '')
            self.snippy.open_fullscreen()
            self.assertIn('168', self.chat.transcript.toPlainText())
            self.assertTrue(self.snippy.isHidden())
            self.chat.close()
            self.snippy.sleep()
            stop.assert_called_once()
            self.assertTrue(self.snippy.sleeping)
            self.assertEqual(self.snippy.width(), 62)
            self.snippy.toggle_input()
            self.assertFalse(self.snippy.sleeping)
            self.snippy.activity(True)
            self.snippy.sleep()
            stop.assert_called_once()
            self.snippy.activity(False)
            for _ in range(3):
                self.snippy.submit('12 + 3')
            self.assertTrue(self.chat.isVisible())

    def test_long_answer_opens_chat_and_keeps_sources(self):
        self.notch.store.settings['user_name'] = 'Alex'
        self.notch.assistant_panel.history = [{'role': 'assistant', 'content': 'Long answer ' * 55}]
        self.notch.assistant_panel.show_result({'text': 'Long answer ' * 55,
            'links': [{'title': 'Source', 'detail': 'Details', 'url': 'https://example.com'}],
            'web_query': 'public topic'})
        self.assertTrue(self.chat.isVisible())
        self.assertEqual(self.chat.results.count(), 1)
        self.assertTrue(self.chat.results.isVisible())
        self.assertTrue(self.chat.web.isVisible())
        self.chat.clear()
        self.assertFalse(self.chat.results.isVisible())

    def test_idle_notch_uses_selected_widgets_and_keeps_paused_song(self):
        self.notch.media_state = {}
        self.notch.switch_view('Music')
        self.assertTrue(self.notch.card_frames['Music'].isHidden())
        self.assertFalse(self.notch.card_frames['Time'].isHidden())
        self.assertFalse(self.notch.card_frames['To do'].isHidden())
        self.notch.media_state = {'source': 'Spotify', 'playing': False, 'title': 'Paused track'}
        self.notch.layout_cards()
        self.assertFalse(self.notch.card_frames['Music'].isHidden())
        self.assertTrue(self.notch.card_frames['To do'].isHidden())
        self.notch.media_state['has_track'] = False
        self.notch.layout_cards()
        self.assertTrue(self.notch.card_frames['Music'].isHidden())
        self.notch.media_state = {}
        self.notch.store.settings['enabled'] = ['To do', 'Weather']
        self.notch.rebuild()
        self.assertFalse(self.notch.card_frames['Weather'].isHidden())
        self.assertFalse(self.notch.card_frames['To do'].isHidden())

    def test_notification_baseline_filters_dedup_and_private_bubbles(self):
        delta = NotificationDelta()
        old = {'key': ('1', 'old'), 'app': 'Slack', 'title': 'Private title', 'body': 'Private message'}
        new = dict(old, key=('2', 'new'))
        self.assertEqual(delta.update([old]), [])
        self.assertEqual(delta.update([old, new], 'WhatsApp'), [])
        newer = dict(new, key=('2', 'newer'))
        self.assertEqual(delta.update([old, newer], 'slack'), [newer])
        self.assertEqual(delta.update([old, newer]), [])
        self.snippy.activity(True)
        self.snippy.notify([newer])
        self.assertTrue(self.snippy.bubble.isHidden())
        self.snippy.activity(False)
        self.snippy.show_pending_alerts()
        self.assertIn('Slack', self.snippy.reply.text())
        self.assertNotIn('Private', str(self.snippy.alerts))
        self.assertEqual(self.notch.assistant_panel.history, [])
        self.notch.store.settings['notifications_preview'] = True
        self.snippy.notify([newer])
        self.assertIn('Private message', self.snippy.reply.text())
        self.notch.notifications.failed('Access revoked')
        self.assertFalse(self.notch.notifications.timer.isActive())
        self.assertEqual(self.snippy.alerts, [])

    def test_titles_removed_photo_crop_and_clock_square(self):
        self.notch.desktop.add('Clock')
        self.notch.desktop.add('Photo')
        for widget in self.notch.desktop.windows.values():
            self.assertTrue(widget.heading.isHidden())
            if widget.kind == 'Clock':
                self.assertEqual(widget.width(), widget.height())
            else:
                from PySide6.QtGui import QPixmap, QColor
                from pathlib import Path
                source = QPixmap(400, 100)
                source.fill(QColor('blue'))
                path = Path(self.temp.name) / 'test-photo.png'
                source.save(str(path))
                widget.config['path'] = str(path)
                widget.load_photo()
                self.assertTrue(widget.choose_button.isHidden())
                self.assertEqual(widget.photo.pixmap().width(), widget.width()-32)
        for identity in list(self.notch.desktop.windows):
            self.notch.desktop.remove(identity)


if __name__ == '__main__':
    unittest.main()
