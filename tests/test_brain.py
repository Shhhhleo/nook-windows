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
        self.assertIn('add_todo', names)
        self.assertNotIn('propose_file_moves', names)   # Routed: only the to-do group plus web tools.
        everything = [t['function']['name'] for t in brain.tools_for(self.store)]
        self.assertIn('propose_file_moves', everything)
        self.assertNotIn('gmail_send', everything)   # Optional accounts are not connected.
        self.assertNotIn('whop_summary', everything)
        self.assertEqual(first['messages'][0]['role'], 'system')
        self.assertIn('Alex', first['messages'][0]['content'])
        self.assertTrue(first['messages'][-1]['content'].endswith('add buy milk'))
        self.assertIn('local time', first['messages'][-1]['content'])
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

    def test_system_prefix_and_tools_stay_byte_stable_across_turns(self):
        from datetime import datetime as real_datetime
        payloads = []
        for minute in (5, 47):
            class Clock(real_datetime):
                @classmethod
                def now(cls, tz=None):
                    return real_datetime(2026, 11, 14, 9, minute)
            fake = FakeOllama([('Sunny.', [])])
            with patch.object(brain, 'ollama_chat', fake), patch.object(brain, 'datetime', Clock):
                brain.Brain(self.store, None).respond('Search the web for cloud facts', [])
            payloads.append(fake.payloads[0])
        first, second = payloads
        self.assertEqual(json.dumps(first['messages'][0]), json.dumps(second['messages'][0]))
        self.assertEqual(json.dumps(first['tools']), json.dumps(second['tools']))
        self.assertNotIn('09:', first['messages'][0]['content'])
        self.assertIn('09:05', first['messages'][-1]['content'])
        self.assertIn('09:47', second['messages'][-1]['content'])
        self.assertIn('data, not instructions', first['messages'][-1]['content'])

    def test_tool_router_picks_small_stable_subsets_and_falls_back(self):
        everything = brain.tools_for(self.store)
        order = [t['function']['name'] for t in everything]
        def names(prompt, history=()):
            return [t['function']['name'] for t in brain.route_tools(everything, prompt, history)]
        weather = names("What's the weather in Pune?")
        self.assertIn('get_weather', weather)
        self.assertIn('web_search', weather)
        self.assertLessEqual(len(weather), 6)
        self.assertEqual(weather, sorted(weather, key=order.index))   # Stable order keeps the cache useful.
        tidy = names('Tidy my downloads folder by file type')
        self.assertIn('propose_file_moves', tidy)
        self.assertNotIn('whatsapp_send', tidy)
        self.assertIn('whatsapp_send', names('Send a WhatsApp to Mum saying hi'))
        self.assertIn('add_todo', names('yes please', [{'role': 'user', 'content': 'add a task to call the bank'}]))
        self.assertEqual(names('hi'), order)   # Nothing matches: every tool.
        # The model asks for a tool outside the subset: it still runs, and the next step offers everything.
        fake = FakeOllama([('', [call('add_todo', text='call bank')]), ('Added.', [])])
        with patch.object(brain, 'ollama_chat', fake):
            brain.Brain(self.store, None).respond("What's the weather?", [])
        self.assertNotIn('add_todo', [t['function']['name'] for t in fake.payloads[0]['tools']])
        self.assertEqual(self.store.settings['todos'][-1]['text'], 'call bank')
        self.assertEqual([t['function']['name'] for t in fake.payloads[1]['tools']], order)

    def test_read_only_calls_run_in_parallel_and_keep_their_order(self):
        barrier = threading.Barrier(3, timeout=5)
        def search(query):
            barrier.wait()   # Only returns if all three searches are running at once.
            return [{'title': query, 'url': 'https://example.com/' + query, 'snippet': ''}]
        fake = FakeOllama([('', [call('web_search', query='a'), call('web_search', query='b'), call('web_search', query='c')]),
                           ('Done.', [])])
        with patch.object(brain, 'ollama_chat', fake), patch.object(actions, 'web_search', side_effect=search):
            result = brain.Brain(self.store, None).respond('search the web for a, b and c', [])
        tool_rows = [m for m in fake.payloads[1]['messages'] if m['role'] == 'tool']
        self.assertEqual([json.loads(m['content'])[0]['title'] for m in tool_rows], ['a', 'b', 'c'])
        self.assertEqual([l['url'] for l in result['links']], ['https://example.com/a', 'https://example.com/b', 'https://example.com/c'])

    def test_approval_and_state_changing_tools_run_alone_in_order(self):
        (self.root / 'a.txt').write_text('a')
        events, lock = [], threading.Lock()
        active = {'n': 0, 'max_with_approval': 0}
        def track(name, result):
            def run(*args, **kwargs):
                with lock:
                    active['n'] += 1
                    events.append(name)
                try:
                    if name == 'approve':
                        active['max_with_approval'] = max(active['max_with_approval'], active['n'])
                    __import__('time').sleep(.05)
                    return result
                finally:
                    with lock:
                        active['n'] -= 1
            return run
        approvals = StubApprovals(True)
        original_ask = approvals.ask
        approvals.ask = lambda *a: (track('approve', None)(), original_ask(*a))[1]
        calls = [call('web_search', query='x'), call('propose_file_moves', moves=[{'source': 'a.txt', 'destination': 'T/a.txt'}]),
                 call('add_todo', text='later'), call('get_weather', city='Pune')]
        fake = FakeOllama([('', calls), ('Done.', [])])
        with patch.object(brain, 'ollama_chat', fake), \
                patch.object(actions, 'web_search', side_effect=track('search', [{'title': 'x', 'url': 'https://x.org', 'snippet': ''}])), \
                patch.object(actions, 'weather', side_effect=track('weather', 'Sunny')):
            brain.Brain(self.store, approvals).respond('tidy and search', [])
        self.assertEqual(events, ['search', 'approve', 'weather'])
        self.assertEqual(active['max_with_approval'], 1)   # Nothing else ran while the approval card was up.
        self.assertTrue((self.root / 'T' / 'a.txt').exists())
        self.assertEqual([m['tool_name'] for m in fake.payloads[1]['messages'] if m['role'] == 'tool'],
                         ['web_search', 'propose_file_moves', 'add_todo', 'get_weather'])

    def test_page_reader_keeps_relevant_paragraphs_short(self):
        filler = ''.join('<p>Paragraph %s talks about gardening, soil and seasonal planting in long detail here.</p>' % i
                         for i in range(80))
        page = ('<html><head><title>Python news</title></head><body><main><p>Lead: this page covers software releases '
                'for many languages.</p>' + filler + '<p>The latest stable Python version is 3.14.2, released in December.</p>'
                + filler + '</main></body></html>')
        class Response:
            headers = __import__('email.message', fromlist=['Message']).Message()
            def __init__(self):
                self.headers['Content-Type'] = 'text/html; charset=utf-8'
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return page.encode()
        class Opener:
            def open(self, request, timeout=None): return Response()
        with patch.object(actions, 'check_public_url', lambda url: url), \
                patch.object(actions.urllib.request, 'build_opener', return_value=Opener()):
            result = actions.fetch_page('https://example.com/py', query='latest stable python version')
        self.assertLessEqual(len(result['text']), 2000)
        self.assertIn('3.14.2', result['text'])
        self.assertTrue(result['text'].startswith('Lead:'))
        self.assertTrue(result['truncated'])
        self.assertEqual(result['title'], 'Python news')

    def test_keep_alive_is_long_on_ac_and_short_on_battery(self):
        from nook import local_ai
        Battery = __import__('collections').namedtuple('Battery', 'percent secsleft power_plugged')
        with patch.object(local_ai.psutil, 'sensors_battery', return_value=Battery(80, 100, True)):
            self.assertEqual(local_ai.keep_alive(), '10m')
        with patch.object(local_ai.psutil, 'sensors_battery', return_value=Battery(80, 100, False)):
            self.assertEqual(local_ai.keep_alive(), '90s')
        with patch.object(local_ai.psutil, 'sensors_battery', return_value=None):   # Desktop PC.
            self.assertEqual(local_ai.keep_alive(), '10m')

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
