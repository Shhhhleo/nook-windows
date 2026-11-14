"""Claude brain loop, approvals, Whop analytics and WhatsApp matching, without network or real accounts."""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import anthropic
import httpx2
from PySide6.QtWidgets import QApplication

from nook import storage, brain, actions, whatsapp
from nook.approvals import Approvals


def sse(events):
    return ''.join('event: %s\ndata: %s\n\n' % (e['type'], json.dumps(e)) for e in events).encode()


def message(blocks, stop):
    events = [{'type': 'message_start', 'message': {'id': 'msg_1', 'type': 'message', 'role': 'assistant',
               'model': 'claude-opus-5-5', 'content': [], 'stop_reason': None, 'stop_sequence': None,
               'usage': {'input_tokens': 10, 'output_tokens': 1}}}]
    for index, block in enumerate(blocks):
        if block['type'] == 'text':
            events += [{'type': 'content_block_start', 'index': index, 'content_block': {'type': 'text', 'text': ''}},
                       {'type': 'content_block_delta', 'index': index, 'delta': {'type': 'text_delta', 'text': block['text']}}]
        else:
            events += [{'type': 'content_block_start', 'index': index, 'content_block': {'type': 'tool_use', 'id': block['id'], 'name': block['name'], 'input': {}}},
                       {'type': 'content_block_delta', 'index': index, 'delta': {'type': 'input_json_delta', 'partial_json': json.dumps(block['input'])}}]
        events.append({'type': 'content_block_stop', 'index': index})
    events += [{'type': 'message_delta', 'delta': {'stop_reason': stop, 'stop_sequence': None}, 'usage': {'output_tokens': 5}},
               {'type': 'message_stop'}]
    return sse(events)


class FakeClaude:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []

    def handler(self, request):
        self.requests.append({'body': json.loads(request.content), 'headers': dict(request.headers)})
        return httpx2.Response(200, headers={'content-type': 'text/event-stream'}, content=self.replies.pop(0))

    def client(self, _store=None):
        http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(self.handler))
        return anthropic.Anthropic(api_key='sk-ant-test', http_client=http, max_retries=0)


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
        self.store = storage.Store()
        self.store.settings.update(user_name='Alex', search_root=self.temp.name)

    def test_tool_loop_request_shape_and_todo(self):
        fake = FakeClaude([message([{'type': 'tool_use', 'id': 'toolu_1', 'name': 'add_todo', 'input': {'text': 'buy milk'}}], 'tool_use'),
                           message([{'type': 'text', 'text': 'Added **buy milk**.'}], 'end_turn')])
        partials = []
        with patch.object(brain, 'client', fake.client):
            result = brain.Brain(self.store, StubApprovals(True)).respond('add buy milk', [{'role': 'assistant', 'content': 'hi'}], partials.append)
        self.assertEqual(result['text'], 'Added **buy milk**.')
        self.assertTrue(result['tasks_changed'])
        self.assertEqual(self.store.settings['todos'][-1]['text'], 'buy milk')
        first = fake.requests[0]
        body = first['body']
        self.assertEqual(body['model'], 'claude-opus-5-5')
        self.assertEqual(body['fallbacks'], 'default')
        self.assertIn('server-side-fallback-2026-07-01', first['headers'].get('anthropic-beta', ''))
        self.assertEqual(body['cache_control'], {'type': 'ephemeral'})
        self.assertEqual(body['output_config'], {'effort': 'medium'})
        self.assertNotIn('thinking', body)
        self.assertIn({'type': 'web_search_20260209', 'name': 'web_search', 'max_uses': 5}, body['tools'])
        # History never starts with an assistant turn; the context note follows the user's message.
        self.assertEqual([m['role'] for m in body['messages']], ['user', 'system'])
        self.assertIn('Alex', body['messages'][1]['content'])
        second = fake.requests[1]['body']['messages']
        self.assertEqual([m['role'] for m in second], ['user', 'system', 'assistant', 'user'])
        self.assertEqual(second[3]['content'][0]['tool_use_id'], 'toolu_1')
        self.assertTrue(partials and partials[-1] == 'Added **buy milk**.')

    def test_declined_email_is_never_sent(self):
        fake = FakeClaude([message([{'type': 'tool_use', 'id': 'toolu_2', 'name': 'gmail_send',
                                     'input': {'to': 'a@example.com', 'subject': 'Hi', 'body': 'Hello'}}], 'tool_use'),
                           message([{'type': 'text', 'text': 'Okay, not sent.'}], 'end_turn')])
        approvals = StubApprovals(False)
        with patch.object(brain, 'client', fake.client), patch.object(actions, 'gmail_send') as send:
            result = brain.Brain(self.store, approvals).respond('email a', [])
        send.assert_not_called()
        self.assertEqual(approvals.asked[0][0], 'email')
        self.assertIn('declined', fake.requests[1]['body']['messages'][-1]['content'][0]['content'])
        self.assertEqual(result['text'], 'Okay, not sent.')

    def test_invalid_tool_input_is_reported_not_run(self):
        fake = FakeClaude([message([{'type': 'tool_use', 'id': 'toolu_3', 'name': 'open_url', 'input': {'link': 'x'}}], 'tool_use'),
                           message([{'type': 'text', 'text': 'Sorry.'}], 'end_turn')])
        with patch.object(brain, 'client', fake.client), patch.object(actions, 'open_url') as opened:
            brain.Brain(self.store, StubApprovals(True)).respond('open', [])
        opened.assert_not_called()
        result = fake.requests[1]['body']['messages'][-1]['content'][0]
        self.assertTrue(result['is_error'])
        self.assertIn('INVALID_JSON', result['content'])

    def test_haiku_skips_server_fallback(self):
        self.store.settings['claude_model'] = 'claude-haiku-5-5'
        fake = FakeClaude([message([{'type': 'text', 'text': 'Hi'}], 'end_turn')])
        with patch.object(brain, 'client', fake.client):
            brain.Brain(self.store, None).respond('hello', [])
        self.assertNotIn('fallbacks', fake.requests[0]['body'])

    def test_whop_summary_sums_paid_revenue(self):
        self.store.secret('whop_api_key', 'test-key')
        def fake_request(url, data=None, headers=None, form=False):
            self.assertEqual(headers['Authorization'], 'Bearer test-key')
            if '/payments' in url:
                return {'data': [{'currency': 'usd', 'total': {'amount': '99.00'}}, {'currency': 'usd', 'total': {'amount': '1.50'}}],
                        'page_info': {'has_next_page': False}}
            return {'data': [], 'page_info': {'total_count': 7}}
        with patch.object(actions.services, 'request', side_effect=fake_request):
            summary = json.loads(actions.whop_summary(self.store, 7))
        self.assertEqual(summary['revenue_by_currency'], {'USD': 100.5})
        self.assertEqual(summary['paid_payments'], 2)
        self.assertEqual(summary['active_memberships'], 7)

    def test_whop_requires_key(self):
        with self.assertRaises(ValueError):
            actions.whop_summary(self.store)

    def test_whatsapp_contact_matching(self):
        self.assertTrue(whatsapp.same_contact({'name': 'Mum'}, 'mum'))
        self.assertTrue(whatsapp.same_contact({'name': 'Rahul', 'phone': '+91 98765 43210'}, '+91 98765 43210'))
        self.assertFalse(whatsapp.same_contact({'name': 'Mum'}, 'Mumbai Group'))
        self.assertFalse(whatsapp.same_contact({'name': 'X', 'phone': '12'}, '12'))

    def test_autopilot_respects_rate_limits(self):
        manager = whatsapp.WhatsApp(self.store)
        self.assertTrue(manager.may_auto_send('Mum'))
        manager.last_auto['Mum'] = __import__('time').time()
        self.assertFalse(manager.may_auto_send('Mum'))
        manager.auto_log = [__import__('time').time()] * whatsapp.MAX_AUTO_PER_HOUR
        self.assertFalse(manager.may_auto_send('Dad'))

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
        self.assertEqual(request['detail'], 'hello')
        approvals.answer(request, True, 'hello there')
        worker.join(2)
        self.assertEqual(outcome['result'], (True, 'hello there'))
        self.assertIsNone(approvals.current())


if __name__ == '__main__':
    unittest.main()
