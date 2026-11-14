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
from nook import assistant, cowork, storage, mcp_client, services
from nook.conversations import Conversations
from nook.ui import Notch


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        patcher = patch.object(storage, 'DATA', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = dict(storage.DEFAULTS, user_name='Alex', search_root=str(self.root))

    def test_identity_never_uses_model(self):
        with patch.object(assistant, 'ollama_request') as api:
            self.assertEqual(assistant.respond('What is my name?', [], self.settings)['text'], 'Your name is Alex.')
            self.assertIn('project creator', assistant.respond('Who made you?', [], self.settings)['text'])
            self.assertIn('local assistant', assistant.respond('Who are you?', [], self.settings)['text'])
            self.assertIn('Snippy', assistant.respond('Briefly introduce yourself.', [], self.settings)['text'])
            self.assertEqual(assistant.respond('Can you tell me my name?', [], self.settings)['text'], 'Your name is Alex.')
            api.assert_not_called()

    def test_cowork_reads_and_only_writes_reviewed_new_files(self):
        (self.root / 'notes.txt').write_text('A real local document.', encoding='utf-8')
        self.assertEqual(assistant.respond('read notes.txt', [], self.settings)['text'], 'A real local document.')
        self.assertIn('notes.txt', assistant.respond('list files', [], self.settings)['text'])
        with self.assertRaises(ValueError):
            cowork.read(self.root, '../outside.txt')
        proposal = cowork.proposal(self.root, 'summary.md', 'My reviewed summary')['proposal']
        self.assertFalse((self.root / 'summary.md').exists())
        cowork.apply(proposal, self.root)
        self.assertEqual((self.root / 'summary.md').read_text(), 'My reviewed summary')
        with self.assertRaises(FileExistsError):
            cowork.apply(proposal, self.root)
        self.assertIn('proposal', cowork.inventory(self.root))

    def test_chat_library_roundtrip_new_and_delete(self):
        archive = Conversations()
        first = archive.save(None, [{'role': 'user', 'content': 'First question'}])
        second = archive.save(None, [{'role': 'user', 'content': 'Second question'}])
        loaded = Conversations()
        self.assertEqual([r['id'] for r in loaded.chats], [second, first])
        self.assertEqual(loaded.load(first)[0]['content'], 'First question')
        loaded.delete(first)
        self.assertEqual(len(Conversations().chats), 1)

    def test_unit_switch_requests_provider_unit(self):
        with patch.object(services, 'request', return_value={'current': dict(temperature_2m=77, apparent_temperature=75, weather_code=0, time='2026-11-13T12:00')}) as request:
            result = services.weather_at(dict(name='Test', latitude=10, longitude=20), True)
            self.assertIn('77°F', result)
            self.assertIn('temperature_unit=fahrenheit', request.call_args.args[0])

    def test_mcp_calls_roundtrip_and_reject_remote_plain_http(self):
        with self.assertRaises(ValueError):
            mcp_client.validate_url('http://example.com/mcp')
        calls = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(body)
                if 'id' not in body:
                    self.send_response(202)
                    self.end_headers()
                    return
                if body['method'] == 'initialize':
                    result = {'protocolVersion': body['params']['protocolVersion'], 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'Fixture', 'version': '1'}}
                elif body['method'] == 'tools/list':
                    result = {'tools': [{'name': 'echo', 'description': 'Test only', 'inputSchema': {'type': 'object', 'properties': {'text': {'type': 'string'}}}}]}
                else:
                    result = {'content': [{'type': 'text', 'text': body['params']['arguments']['text']}], 'isError': False}
                payload = json.dumps({'jsonrpc': '2.0', 'id': body['id'], 'result': result}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            def do_GET(self):
                self.send_response(405)
                self.end_headers()
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            store = storage.Store()
            store.settings['mcp_connections'] = [{'id': 'fixture', 'name': 'Test', 'auth': 'None (local server)', 'url': 'http://127.0.0.1:%s/mcp' % server.server_port}]
            self.assertEqual(mcp_client.invoke(store, 'fixture')[0]['name'], 'echo')
            self.assertEqual(mcp_client.invoke(store, 'fixture', 'echo', {'text': 'Roundtrip'})['text'], 'Roundtrip')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_snippy_keeps_second_display_position_and_voice_hold_release(self):
        app = QApplication.instance() or QApplication([])
        with patch.object(Notch, 'refresh_media'), patch.object(Notch, 'refresh_widgets'), patch.object(Notch, 'refresh_tasks'):
            notch = Notch(storage.Store())
        try:
            snippy = notch.cloud
            notch.store.settings['snippy_position'] = [-900, 120]
            second = Mock()
            second.availableGeometry.return_value = QRect(-1920, 0, 1920, 1080)
            with patch('nook.snippy.QApplication.screenAt', return_value=second):
                snippy.follow()
                self.assertEqual(snippy.pos(), QPoint(-900, 120))
                snippy.show_input(True)
                snippy.refresh_size()
                snippy.follow()
                self.assertEqual(snippy.pos(), QPoint(-900, 120))
            with patch.object(snippy.voice, 'begin') as begin:
                snippy.voice.update_held(True)
                snippy.voice.update_held(True)
                begin.assert_called_once()
                snippy.voice.update_held(False)
                self.assertTrue(snippy.voice.release.is_set())
            self.assertFalse(snippy.voice.timer.isActive())
        finally:
            notch.cloud.close()
            notch.tray.hide()
            notch.hide()
            notch.deleteLater()
            app.processEvents()


if __name__ == '__main__':
    unittest.main()
