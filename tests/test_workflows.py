import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch, Mock

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtCore import QRect, QPoint
from PySide6.QtWidgets import QApplication
from nook import storage, services


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch.object(storage, 'DATA', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = dict(storage.DEFAULTS, user_name='Alex', search_root=str(self.root))

    def test_unit_switch_requests_provider_unit(self):
        with patch.object(services, 'request', return_value={'current': dict(temperature_2m=77, apparent_temperature=75, weather_code=0, time='2026-11-13T12:00')}) as request:
            result = services.weather_at(dict(name='Test', latitude=10, longitude=20), True)
            self.assertIn('77°F', result)
            self.assertIn('temperature_unit=fahrenheit', request.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
