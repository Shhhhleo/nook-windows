import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication, QCheckBox
from nook import news, assistant, storage, services, speech
from nook.ui import Notch

FEED = b'''<rss><channel><item><title>World test headline</title><link>https://example.org/story</link><pubDate>Sat, 14 Nov 2026 08:00:00 GMT</pubDate></item></channel></rss>'''


class CurrentDataTests(unittest.TestCase):
    def test_news_cache_fresh_stale_and_topic_miss(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(news, 'CACHE', Path(folder)/'news.json'), patch.object(news, 'DATA', Path(folder)):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = FEED
            with patch.object(news.urllib.request, 'urlopen', return_value=response) as request:
                first = news.answer('What is the latest news?')
                self.assertIn('retrieved', first['text'])
                self.assertEqual(first['links'][0]['url'], 'https://example.org/story')
                self.assertIn('2026-11-14', first['links'][0]['detail'])
                news.answer('Any news?')
                self.assertEqual(request.call_count, 2)
                self.assertIn('No matching story', news.answer('news about mars')['text'])
            cached = news.read_cache(); cached['fetched'] = 1
            news.CACHE.write_text(json.dumps(cached), encoding='utf-8')
            with patch.object(news.urllib.request, 'urlopen', side_effect=OSError):
                self.assertIn('unable to verify freshness', news.answer('news')['text'])

    def test_identity_guard_and_news_bypass_model(self):
        self.assertEqual(assistant.identity_guard("I'm Nook. My name is Notch."), "I'm Snippy. My name is Snippy.")
        self.assertEqual(assistant.identity_guard('Notch is the app.'), 'Notch is the app.')
        with patch.object(news, 'answer', return_value={'text':'Fresh sources'}) as retrieve, patch.object(assistant, 'chat_request') as model:
            self.assertEqual(assistant.respond('current affairs today', [], storage.DEFAULTS)['text'], 'Fresh sources')
            retrieve.assert_called_once(); model.assert_not_called()

    def test_structured_forecast_contains_real_high_low(self):
        forecast = {'current':dict(temperature_2m=27,apparent_temperature=26,weather_code=2,time='2026-11-14T09:00'),
                    'daily':dict(temperature_2m_max=[30],temperature_2m_min=[17])}
        with patch.object(services, 'request', return_value=forecast):
            result = services.weather_at(dict(latitude=1,longitude=2,name='Fixture'),False,True)
            self.assertEqual((result['high'],result['low'],result['condition']), (30,17,'Partly cloudy'))

    def test_speech_capture_begins_before_model_and_drains_on_release(self):
        release = threading.Event(); events=[]
        class Stream:
            def __init__(self, **kwargs): self.callback = kwargs['callback']
            def __enter__(self):
                events.append('capture'); self.callback(b'audio',1,None,None)
                release.set(); return self
            def __exit__(self,*args): pass
        recognizer = Mock()
        recognizer.AcceptWaveform.return_value = False
        recognizer.FinalResult.return_value = json.dumps({'text':'what time is it','result':[{'conf':.9}]})
        def load(language): events.append('model'); return object()
        with patch('sounddevice.query_devices',return_value={'default_samplerate':16000}), patch('sounddevice.RawInputStream',Stream), patch.object(speech,'model',side_effect=load), patch('vosk.KaldiRecognizer',return_value=recognizer):
            text, confidence = speech.listen(release, {}, lambda _:None)
        self.assertEqual(events,['capture','model'])
        self.assertEqual(text,'what time is it'); self.assertEqual(confidence,.9)
        recognizer.AcceptWaveform.assert_called_once_with(b'audio')


class SurfaceTests(unittest.TestCase):
    def test_completed_tasks_click_dismiss_and_settings_navigation(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder, patch.object(storage,'DATA',Path(folder)), patch.object(Notch,'refresh_media'), patch.object(Notch,'refresh_widgets'), patch.object(Notch,'refresh_tasks'), patch.object(assistant,'prepare_model'):
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
                snippy=notch.cloud; snippy.submit('What is my name?'); app.processEvents()
                self.assertFalse(snippy.bubble.isHidden())
                snippy.toggle_input(); self.assertTrue(snippy.bubble.isHidden()); self.assertFalse(snippy.input.isHidden())
                snippy.submit('2 + 2'); self.assertFalse(snippy.bubble.isHidden())
                self.assertFalse(snippy.workspace.isVisible())
                notch.open_settings(); panel=notch.settings_window
                panel.navigation.setCurrentRow(3)
                self.assertEqual(panel.page_title.text(),'Assistant'); self.assertEqual(panel.tabs.currentIndex(),3)
            finally:
                if getattr(notch,'settings_window',None): notch.settings_window.close()
                for window in notch.desktop.windows.values(): window.close()
                notch.cloud.close(); notch.tray.hide(); notch.close(); notch.deleteLater(); app.processEvents()
