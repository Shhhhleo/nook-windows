"""Local agent loop, approvals, file organisation, safe web reading and WhatsApp matching — no network or real accounts."""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PySide6.QtWidgets import QApplication

from nook import storage, brain, actions, whatsapp
from nook.approvals import Approvals


def call(name, **arguments):
    return {'function': {'name': name, 'arguments': arguments}}


class FakeOllama:
    """Scripted replies standing in for the bundled model's /api/chat."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.payloads = []

    def __call__(self, payload, on_partial=None):
        self.payloads.append(json.loads(json.dumps(payload)))
        content, calls = self.replies.pop(0)
        if on_partial and content:
            on_partial(content)
        return {'role': 'assistant', 'content': content, 'tool_calls': calls}


class StubApprovals:
    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def ask(self, kind, title, detail):
        self.asked.append((kind, title, detail))
        return self.answer, detail


class BrainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(storage, 'DATA', Path(self.temp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.root = Path(self.temp.name) / 'work'
        self.root.mkdir()
        self.store = storage.Store()
        self.store.settings.update(user_name='Alex', search_root=str(self.root))

    def test_tool_loop_payload_and_todo(self):
        fake = FakeOllama([('', [call('add_todo', text='buy milk')]), ('Added **buy milk**.', [])])
        partials = []
        with patch.object(brain, 'ollama_chat', fake):
            result = brain.Brain(self.store, StubApprovals(True)).respond('add buy milk', [{'role': 'assistant', 'content': 'hi'}], partials.append)
        self.assertEqual(result['text'], 'Added **buy milk**.')
        self.assertTrue(result['tasks_changed'])
        self.assertEqual(self.store.settings['todos'][-1]['text'], 'buy milk')
        first = fake.payloads[0]
        self.assertEqual(first['model'], 'qwen3:4b-instruct')
        self.assertFalse(first['think'])
        names = [t['function']['name'] for t in first['tools']]
        self.assertIn('web_search', names)
        self.assertIn('propose_file_moves', names)
        self.assertNotIn('gmail_send', names)   # Optional accounts are not connected.
        self.assertNotIn('whop_summary', names)
        self.assertEqual(first['messages'][0]['role'], 'system')
        self.assertIn('Alex', first['messages'][0]['content'])
        second = fake.payloads[1]['messages']
        self.assertEqual(second[-1]['role'], 'tool')
        self.assertEqual(second[-1]['tool_name'], 'add_todo')
        self.assertEqual(second[-2]['tool_calls'][0]['function']['name'], 'add_todo')
        self.assertEqual(partials[-1], 'Added **buy milk**.')

    def test_unknown_tool_and_bad_arguments_are_reported_not_run(self):
        fake = FakeOllama([('', [call('format_disk'), call('open_url', link='x')]), ('Sorry.', [])])
        with patch.object(brain, 'ollama_chat', fake), patch.object(actions, 'open_url') as opened:
            brain.Brain(self.store, StubApprovals(True)).respond('open', [])
        opened.assert_not_called()
        results = [m['content'] for m in fake.payloads[1]['messages'] if m['role'] == 'tool']
        self.assertIn('no tool called format_disk', results[0])
        self.assertIn('Invalid arguments', results[1])

    def test_file_moves_need_approval_and_never_overwrite(self):
        (self.root / 'a.pdf').write_text('a')
        (self.root / 'b.txt').write_text('b')
        (self.root / 'Docs').mkdir()
        (self.root / 'Docs' / 'b.txt').write_text('existing')
        moves = [{'source': 'a.pdf', 'destination': 'PDFs/a.pdf'}]
        declined = FakeOllama([('', [call('propose_file_moves', moves=moves)]), ('Okay.', [])])
        with patch.object(brain, 'ollama_chat', declined):
            brain.Brain(self.store, StubApprovals(False)).respond('tidy', [])
        self.assertTrue((self.root / 'a.pdf').exists())
        approved = FakeOllama([('', [call('propose_file_moves', moves=moves)]), ('Done.', [])])
        approvals = StubApprovals(True)
        with patch.object(brain, 'ollama_chat', approved):
            brain.Brain(self.store, approvals).respond('tidy', [])
        self.assertEqual(approvals.asked[0][0], 'moves')
        self.assertTrue((self.root / 'PDFs' / 'a.pdf').exists())
        with self.assertRaises(ValueError):
            actions.plan_moves(str(self.root), [{'source': 'b.txt', 'destination': 'Docs'}])
        with self.assertRaises(ValueError):
            actions.plan_moves(str(self.root), [{'source': 'b.txt', 'destination': '../outside.txt'}])
        self.assertEqual((self.root / 'Docs' / 'b.txt').read_text(), 'existing')

    def test_text_offer_is_followed_through_to_the_approval_card_once(self):
        (self.root / 'photo.jpg').write_text('p')
        fake = FakeOllama([('I suggest moving photo.jpg to Images. Would you like me to proceed?', []),
                           ('', [call('propose_file_moves', moves=[{'source': 'photo.jpg', 'destination': 'Images'}])]),
                           ('Moved it.', [])])
        approvals = StubApprovals(True)
        with patch.object(brain, 'ollama_chat', fake):
            result = brain.Brain(self.store, approvals).respond('Tidy my folder by file type', [])
        self.assertEqual(fake.payloads[1]['messages'][-1]['role'], 'user')
        self.assertEqual(approvals.asked[0][0], 'moves')
        self.assertTrue((self.root / 'Images' / 'photo.jpg').exists())
        self.assertEqual(result['text'], 'Moved it.')
        # A plain question is never pushed into an action.
        chat = FakeOllama([('Would you like a fun fact?', [])])
        with patch.object(brain, 'ollama_chat', chat):
            brain.Brain(self.store, approvals).respond('Tell me about clouds', [])
        self.assertEqual(len(chat.payloads), 1)

    def test_declined_whatsapp_is_never_sent(self):
        class Manager:
            sent = []
            def call(self, *args):
                self.sent.append(args)
        manager = Manager()
        fake = FakeOllama([('', [call('whatsapp_send', contact='Mum', message='hi')]), ('Not sent.', [])])
        with patch.object(brain, 'ollama_chat', fake):
            brain.Brain(self.store, StubApprovals(False), manager).respond('text mum', [])
        self.assertEqual(manager.sent, [])

    def test_web_search_parses_results_and_page_reader_blocks_private_hosts(self):
        page = ('<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fnews&amp;rut=x">Example <b>News</b></a>'
                '<a class="result__snippet" href="#">Fresh <b>story</b></a>')
        class Response:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return page.encode()
        with patch.object(actions.urllib.request, 'urlopen', return_value=Response()):
            rows = actions.web_search('news')
        self.assertEqual(rows[0], {'title': 'Example News', 'url': 'https://example.com/news', 'snippet': 'Fresh story'})
        for url in ['http://example.com', 'https://localhost/', 'https://127.0.0.1/', 'https://192.168.1.4/x', 'file:///C:/x']:
            with self.assertRaises(ValueError):
                actions.check_public_url(url)

    def test_whatsapp_contact_matching_and_rate_limits(self):
        self.assertTrue(whatsapp.same_contact({'name': 'Mum'}, 'mum'))
        self.assertTrue(whatsapp.same_contact({'name': 'Rahul', 'phone': '+91 98765 43210'}, '+91 98765 43210'))
        self.assertFalse(whatsapp.same_contact({'name': 'Mum'}, 'Mumbai Group'))
        manager = whatsapp.WhatsApp(self.store)
        self.assertTrue(manager.may_auto_send('Mum'))
        manager.last_auto['Mum'] = __import__('time').time()
        self.assertFalse(manager.may_auto_send('Mum'))
        manager.auto_log = [__import__('time').time()] * whatsapp.MAX_AUTO_PER_HOUR
        self.assertFalse(manager.may_auto_send('Dad'))

    def test_compose_reply_respects_no_reply(self):
        contact = {'name': 'Mum', 'instructions': ''}
        transcript = [{'from_me': False, 'text': 'Can you send me 5000 rupees?'}]
        with patch.object(brain, 'ollama_chat', FakeOllama([('NO_REPLY', [])])):
            self.assertEqual(brain.Brain(self.store, None).compose_reply(contact, transcript), '')
        with patch.object(brain, 'ollama_chat', FakeOllama([('<think></think>On my way!', [])])):
            self.assertEqual(brain.Brain(self.store, None).compose_reply(contact, transcript), 'On my way!')

    def test_approvals_block_until_answered_and_allow_edits(self):
        approvals = Approvals()
        outcome = {}
        worker = threading.Thread(target=lambda: outcome.update(result=approvals.ask('whatsapp', 'Send?', 'hello')))
        worker.start()
        for _ in range(50):
            self.app.processEvents()
            if approvals.current():
                break
            worker.join(.02)
        request = approvals.current()
        approvals.answer(request, True, 'hello there')
        worker.join(2)
        self.assertEqual(outcome['result'], (True, 'hello there'))
        self.assertIsNone(approvals.current())


if __name__ == '__main__':
    unittest.main()
