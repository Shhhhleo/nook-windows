import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication, QCheckBox
from nook import storage, services
from nook.ui import Notch

FEED = b'''<rss><channel><item><title>World test headline</title><link>https://example.org/story</link><pubDate>Sat, 14 Nov 2026 08:00:00 GMT</pubDate></item></channel></rss>'''


class CurrentDataTests(unittest.TestCase):
    def test_structured_forecast_contains_real_high_low(self):
        forecast = {'current':dict(temperature_2m=27,apparent_temperature=26,weather_code=2,time='2026-11-14T09:00'),
                    'daily':dict(temperature_2m_max=[30],temperature_2m_min=[17])}
        with patch.object(services, 'request', return_value=forecast):
            result = services.weather_at(dict(latitude=1,longitude=2,name='Fixture'),False,True)
            self.assertEqual((result['high'],result['low'],result['condition']), (30,17,'Partly cloudy'))


class SurfaceTests(unittest.TestCase):
    def test_completed_tasks_and_settings_navigation(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder, patch.object(storage,'DATA',Path(folder)), patch.object(Notch,'refresh_media'), patch.object(Notch,'refresh_widgets'), patch.object(Notch,'refresh_tasks'):
            store=storage.Store(); store.settings.update(user_name='Alex',animation=False,onboarding_complete=True,
                todos=[dict(text='already done',done=True),dict(text='second task',done=False),dict(text='third task',done=False)])
            notch=Notch(store)
            try:
                notch.show(); app.processEvents()
                notch.desktop.add('To do'); tile=next(iter(notch.desktop.windows.values()))
                checks=tile.findChildren(QCheckBox)
                self.assertEqual([c.toolTip() for c in checks],['second task','third task'])
                checks[0].setChecked(True); app.processEvents(); app.processEvents()
                self.assertTrue(store.settings['todos'][1]['done']); self.assertFalse(store.settings['todos'][2]['done'])
                self.assertEqual([c.toolTip() for c in tile.findChildren(QCheckBox) if not c.isHidden()],['third task'])
                notch.open_settings(); panel=notch.settings_window
                panel.navigation.setCurrentRow(3)
                self.assertEqual(panel.page_title.text(),'Connections'); self.assertEqual(panel.tabs.currentIndex(),3)
            finally:
                if getattr(notch,'settings_window',None): notch.settings_window.close()
                for window in notch.desktop.windows.values(): window.close()
                notch.tray.hide(); notch.close(); notch.deleteLater(); app.processEvents()
