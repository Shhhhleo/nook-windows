"""Hover, idle layout, migration and desktop tile checks."""
import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import Qt, QEvent, QPoint, QPointF
from PySide6.QtGui import QEnterEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from nook import storage
from nook.ui import Notch, STYLE


class NotchTests(unittest.TestCase):
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
        self.notch.show()
        self.app.processEvents()

    def tearDown(self):
        self.notch.tray.hide()
        self.notch.hide()
        self.notch.deleteLater()
        self.app.processEvents()

    def test_hover_collapses_and_templates_never_pin(self):
        self.notch.store.settings['animation'] = True
        self.assertFalse(self.notch.expanded)
        self.assertTrue(self.notch.body.isHidden())
        self.assertEqual(self.notch.height(), 42)
        self.app.sendEvent(self.notch, QEnterEvent(QPointF(10, 5), QPointF(10, 5), QPointF(10, 5)))
        QTest.qWait(180)
        self.assertTrue(self.notch.expanded)
        self.assertEqual(self.notch.height(), 132)
        self.assertFalse(self.notch.body.isHidden())
        self.notch.switch_view('Files')
        self.notch.search_input.setFocus()
        with patch('nook.ui.QCursor.pos', return_value=QPoint(-100, -100)):
            self.app.sendEvent(self.notch, QEvent(QEvent.Leave))
            QTest.qWait(250)
        self.assertFalse(self.notch.expanded)
        self.assertTrue(self.notch.body.isHidden())
        self.assertEqual(self.notch.height(), 42)
        self.notch.rebuild()
        self.assertTrue(self.notch.body.isHidden())
        self.notch.preview()
        self.assertFalse(self.notch.pinned)

    def test_previous_dimensions_migrate_to_wide_shallow_resting_strip(self):
        self.notch.store.settings.update(ui_revision=5, width=640, compact_width=420,
            compact_height=58, music_height=150, user_name='Saved name')
        self.notch.store.save()
        restored = storage.Store().settings
        self.assertEqual((restored['width'], restored['compact_width'], restored['compact_height']), (840, 700, 42))
        self.assertEqual(restored['user_name'], 'Saved name')

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
                self.assertEqual(widget.photo.pixmap().width(), widget.width())
        for identity in list(self.notch.desktop.windows):
            self.notch.desktop.remove(identity)


if __name__ == '__main__':
    unittest.main()
