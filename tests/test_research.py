"""Research dossiers and PDF/DOCX reading — scripted model, fake search and pages, no network."""
import json
import os
import re
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
# The offscreen platform has no fonts of its own; use the Windows fonts so PDF text is real text.
os.environ.setdefault('QT_QPA_FONTDIR', os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts'))
from PySide6.QtWidgets import QApplication

from nook import storage, brain, actions, cowork, research


TOPIC = 'solar sails'
PAGES = {
    'https://nasa.example/sails': ('NASA: Solar sails', 'Solar sails use the pressure of sunlight for propulsion. ' * 12),
    'https://www.space.example/news/acs3': ('ACS3 mission news', 'NASA launched the ACS3 solar sail demonstrator in April 2024. ' * 10),
    'https://wiki.example/Solar_sail': ('Solar sail - Wiki', 'IKAROS was the first interplanetary solar sail, launched by JAXA in 2010. ' * 10),
    'https://cooking.example/bread': ('Bread recipes', 'Knead the dough for ten minutes and let it rise. ' * 10),
    'https://blocked.example/paper': ('Blocked paper', ''),
    'https://nasa.example/other': ('NASA: More on sails', 'Sails can steer by tilting relative to the Sun. ' * 10),
}


def fake_search(query):
    rows = [
        {'title': 'NASA sails', 'url': 'https://nasa.example/sails', 'snippet': 'Sunlight pressure.'},
        {'title': 'Duplicate NASA page', 'url': 'https://nasa.example/sails/', 'snippet': ''},      # Same page.
        {'title': 'Same site again', 'url': 'https://nasa.example/other', 'snippet': ''},          # Same site.
        {'title': 'Insecure', 'url': 'http://insecure.example/x', 'snippet': ''},                  # Not https.
        {'title': 'A PDF', 'url': 'https://files.example/sail.pdf', 'snippet': ''},               # Not a web page.
        {'title': 'Search page', 'url': 'https://duckduckgo.com/?q=x', 'snippet': ''},
    ]
    if 'latest' in query:
        rows.append({'title': 'ACS3', 'url': 'https://www.space.example/news/acs3', 'snippet': ''})
        rows.append({'title': 'Blocked', 'url': 'https://blocked.example/paper', 'snippet': 'short'})
    else:
        rows.append({'title': 'Wiki', 'url': 'https://wiki.example/Solar_sail', 'snippet': ''})
        rows.append({'title': 'Bread', 'url': 'https://cooking.example/bread', 'snippet': ''})
    return rows


class FakePages:
    """fetch_page stand-in that records how many pages were being read at once."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = self.peak = 0
        self.fetched = []

    def __call__(self, url):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.fetched.append(url)
        try:
            time.sleep(.05)
            if 'blocked' in url:
                raise ValueError('HTTP Error 403: Forbidden')
            title, text = PAGES[url]
            return {'url': url, 'title': title, 'text': text, 'truncated': False}
        finally:
            with self.lock:
                self.active -= 1


class FakeModel:
    """Routes research prompts by their system text; agent turns (payloads with tools) follow a script."""

    def __init__(self, agent_replies=()):
        self.agent_replies = list(agent_replies)
        self.payloads = []
        self.sections = 0

    def __call__(self, payload, on_partial=None):
        self.payloads.append(json.loads(json.dumps(payload)))
        if 'tools' in payload:
            content, calls = self.agent_replies.pop(0)
            return {'role': 'assistant', 'content': content, 'tool_calls': calls}
        system = payload['messages'][0]['content']
        user = payload['messages'][1]['content']
        if system.startswith('You plan web research'):
            text = 'Sure! ["solar sails", "solar sail latest missions", "solar sail physics", "solar sails"]'
        elif system.startswith('Extract facts'):
            if 'Bread' in user:
                text = 'NONE'
            elif 'ACS3' in user:
                text = '- NASA launched ACS3 in April 2024 [4].\n- It tests composite booms.'
            elif 'IKAROS' in user:
                text = '- IKAROS was launched by JAXA in 2010.\n- It was the first interplanetary solar sail.'
            else:
                text = '- Solar sails are pushed by the pressure of sunlight.\n- They need no fuel.'
        elif system.startswith('You write one section'):
            self.sections += 1
            numbers = sorted(set(re.findall(r'^\[(\d+)\]', user, re.M)))
            text = ('## Heading the model should not add\nSolar sails ride on sunlight [1]. IKAROS flew in 2010 [%s]. '
                    'A made-up claim [9]. Combined [1, 7].' % numbers[-1])
            if 'bullet' in system:
                text = '- First finding [1]\n- Second finding [2][12]'
        else:
            raise AssertionError('Unexpected prompt: ' + system[:80])
        return {'role': 'assistant', 'content': text, 'tool_calls': []}


def call(name, **arguments):
    return {'function': {'name': name, 'arguments': arguments}}


class StubApprovals:
    def __init__(self, answer):
        self.answer = answer
        self.asked = []

    def ask(self, kind, title, detail):
        self.asked.append((kind, title, detail))
        return self.answer, detail


class ResearchTests(unittest.TestCase):
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

    # ------------------------------------------------------------ pieces
    def test_queries_parse_json_dedupe_and_fall_back(self):
        self.assertEqual(research.parse_queries('Here: ["a b c", "A B C", "d e f"]', 'topic x', 3), ['topic x', 'a b c', 'd e f'])
        self.assertEqual(research.parse_queries('not json at all', 'topic x', 2), ['topic x', 'not json at all'])
        self.assertEqual(research.parse_queries('', 'topic x', 3), ['topic x', 'topic x overview', 'topic x latest news'])

    def test_candidates_are_distinct_public_web_pages(self):
        picked = research.pick_candidates([fake_search('solar sails'), fake_search('latest')], 10)
        urls = [p['url'] for p in picked]
        self.assertEqual(urls[0], 'https://nasa.example/sails')
        self.assertEqual(len({research.domain(u) for u in urls[:5]}), 5)   # Different sites come first…
        self.assertEqual(urls[5:], ['https://nasa.example/other'])          # …then other pages fill in.
        self.assertNotIn('https://nasa.example/sails/', urls)
        self.assertTrue(all(u.startswith('https://') for u in urls))
        self.assertFalse(any(u.endswith('.pdf') or 'duckduckgo' in u for u in urls))
        self.assertEqual(len(research.pick_candidates([fake_search('solar sails'), fake_search('latest')], 3)), 3)
        # The Wikipedia fallback gives several articles on one site that differ only by query string.
        wiki = [{'title': str(n), 'url': 'https://en.wikipedia.org/?curid=%s' % n} for n in range(6)]
        self.assertEqual(len(research.pick_candidates([wiki], 8)), research.PER_SITE)

    def test_citations_only_point_at_real_sources(self):
        text, removed = research.fix_citations('A [1][9]. B [2, 7]. C [1-3]. D [5].', 2)
        self.assertEqual(text, 'A [1]. B [2]. C [1][2]. D.')
        self.assertEqual(removed, 4)

    # ------------------------------------------------------------ whole pipeline
    def test_pipeline_parallel_reads_failures_and_citations(self):
        model, pages, progress = FakeModel(), FakePages(), []
        with patch.object(brain, 'ollama_chat', model):
            report = research.run(TOPIC, 'standard', progress.append, search=fake_search, fetch=pages)
        self.assertEqual(report['queries'][:3], ['solar sails', 'solar sail latest missions', 'solar sail physics'])
        self.assertGreater(pages.peak, 1, 'pages should be read in parallel')
        self.assertEqual(len(pages.fetched), len(set(pages.fetched)))
        self.assertEqual([f['url'] for f in report['failed']], ['https://blocked.example/paper'])
        self.assertIn('403', report['failed'][0]['reason'])
        self.assertEqual([s['url'] for s in report['skipped']], ['https://cooking.example/bread'])
        self.assertEqual([s['n'] for s in report['sources']], [1, 2, 3, 4])
        self.assertEqual([s['url'] for s in report['sources']],
                         ['https://nasa.example/sails', 'https://wiki.example/Solar_sail',
                          'https://www.space.example/news/acs3', 'https://nasa.example/other'])
        self.assertEqual([s['name'] for s in report['sections']], ['Summary', 'Key findings', 'Details', 'Open questions'])
        for section in report['sections']:
            cited = {int(n) for n in re.findall(r'\[(\d+)\]', section['text'])}
            self.assertTrue(cited and cited <= {1, 2, 3, 4}, section)
            self.assertNotIn('##', section['text'])
        self.assertGreater(report['removed_citations'], 0)
        for note in report['sources'][2]['notes'] + report['sources'][0]['notes']:
            self.assertNotRegex(note, r'\[\d+\]')   # Model-written numbers in notes are dropped.
        self.assertTrue(any(p.startswith('Searching 5 queries') for p in progress))
        self.assertTrue(any(p.startswith('Reading ') and 'sources' in p for p in progress))
        self.assertIn('Writing section 2/4…', progress)
        for payload in model.payloads:
            self.assertFalse(payload['think'])
            self.assertLessEqual(payload['options']['num_ctx'], 4096)
            self.assertLessEqual(len(payload['messages'][1]['content']), research.SOURCE_CHARS + research.NOTES_CHARS)

    def test_offline_or_unreadable_research_is_reported_not_invented(self):
        def offline(query):
            raise ValueError('Web search returned nothing.')

        def refuse(url):
            raise ValueError('timed out')

        with patch.object(brain, 'ollama_chat', FakeModel()):
            with self.assertRaisesRegex(research.ResearchError, 'internet'):
                research.run(TOPIC, 'quick', search=offline, fetch=refuse)
            with self.assertRaisesRegex(research.ResearchError, 'could be read.*timed out'):
                research.run(TOPIC, 'quick', search=lambda q: [{'title': 't', 'url': 'https://a.example/x', 'snippet': ''}], fetch=refuse)

    def test_pdf_renders_from_a_worker_thread(self):
        report = {'topic': 'Thread test', 'title': 'Research dossier: Thread test', 'date': '14 November 2026',
                  'sections': [{'name': 'Summary', 'text': 'Rendered off the GUI thread [1].\n\n- **Bold** point [1]'}],
                  'sources': [{'n': 1, 'title': 'Example', 'url': 'https://example.com/a', 'accessed': '14 November 2026', 'kind': 'page'}],
                  'failed': [{'title': 'Gone', 'url': 'https://gone.example', 'reason': 'HTTP Error 404'}], 'skipped': []}
        result = {}
        worker = threading.Thread(target=lambda: result.update(pdf=research.render_pdf(report)))
        worker.start()
        worker.join(30)
        self.assertTrue(result['pdf'].startswith(b'%PDF'))
        target = self.root / 'thread.pdf'
        target.write_bytes(result['pdf'])
        text = cowork.read(self.root, 'thread.pdf')['text']
        self.assertIn('Thread test', text)
        self.assertIn('Rendered off the GUI thread', text)
        self.assertIn('https://example.com/a', text)
        # Readable type size: a long dossier must flow onto several A4 pages, not shrink onto one.
        from pypdf import PdfReader
        report['sections'] = [{'name': 'Details', 'text': 'A sentence of ordinary length about the topic [1]. ' * 300}]
        (self.root / 'long.pdf').write_bytes(research.render_pdf(report))
        reader = PdfReader(str(self.root / 'long.pdf'))
        self.assertGreaterEqual(len(reader.pages), 3)
        self.assertEqual([round(float(v)) for v in reader.pages[0].mediabox[2:]], [595, 842])   # A4 in points.

    # ------------------------------------------------------------ the tool inside Snippy's brain
    def run_brain(self, approved):
        model = FakeModel([('', [call('research_dossier', topic=TOPIC, depth='quick')]), ('Your dossier is ready, Sir.', [])])
        approvals, statuses = StubApprovals(approved), []
        with patch.object(brain, 'ollama_chat', model), patch.object(actions, 'web_search', fake_search), \
                patch.object(actions, 'fetch_page', FakePages()), patch.object(actions, 'scholar_search', lambda q, n: []):
            # Worded so the direct research route does not catch it: this covers the model calling the tool.
            result = brain.Brain(self.store, approvals).respond('Put together something on solar sails for me', [],
                                                                 on_status=statuses.append)
        tool_message = next(m for m in model.payloads[-1]['messages'] if m.get('role') == 'tool')
        return result, approvals, statuses, tool_message['content']

    def test_research_tool_saves_cited_pdf_after_approval(self):
        result, approvals, statuses, tool_text = self.run_brain(True)
        self.assertIn('research_dossier', [t['function']['name'] for t in brain.tools_for(self.store)])
        self.assertEqual(len(approvals.asked), 1)
        kind, title, detail = approvals.asked[0]
        self.assertEqual(kind, 'file')
        self.assertIn('Save research PDF', title)
        self.assertIn('Sections: Summary, Key findings, Open questions', detail)
        self.assertIn('Sources cited: 3', detail)
        self.assertIn('blocked.example', detail)
        files = list(self.root.glob('*.pdf'))
        self.assertEqual(len(files), 1)
        self.assertRegex(files[0].name, r'^Research - solar sails - \d{4}-\d{2}-\d{2}\.pdf$')
        self.assertTrue(files[0].read_bytes().startswith(b'%PDF'))
        self.assertGreater(files[0].stat().st_size, 2000)
        self.assertIn('Saved the research dossier', tool_text)
        self.assertEqual(result['text'], 'Your dossier is ready, Sir.')
        self.assertTrue(result['links'])
        self.assertIn('Starting the research…', statuses)
        self.assertIn('Writing section 2/3…', statuses)
        self.assertIn('Waiting for your approval…', statuses)
        text = cowork.read(self.root, files[0].name)['text']     # The saved dossier reads back.
        self.assertIn('solar sails', text.lower())
        self.assertIn('Sources', text)
        self.assertIn('https://nasa.example/sails', text)

    def test_declined_research_writes_nothing(self):
        result, approvals, statuses, tool_text = self.run_brain(False)
        self.assertEqual(len(approvals.asked), 1)
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertIn('declined', tool_text)

    def test_research_requests_and_avoided_sites_are_understood(self):
        earlier = [{'role': 'user', 'content': 'make a pdf on child labor in the industrial revolution'}]
        cases = {
            'Make me a PDF about child labour in the industrial revolution': 'child labour in the industrial revolution',
            "Research the history of the Factory Acts, don't use Wikipedia": 'the history of the Factory Acts',
            'Research solar sails and make me a PDF dossier': 'solar sails',
            'Dont use wikipedia for sources': 'child labor in the industrial revolution',   # A follow-up rule.
            'read the pdf in my folder': '', 'what is the weather': '', 'I am not sure about that': ''}
        for prompt, topic in cases.items():
            request = brain.research_request(prompt, earlier)
            self.assertEqual(request and brain.research_topic(request), topic, prompt)
        self.assertEqual(brain.avoided_sites('avoid reddit.com and no Quora, not sure'), ['quora', 'reddit'])
        self.assertEqual(brain.avoided_sites("don't use wikipedia"), ['wikipedia'])

    def test_pdf_request_goes_straight_to_research_and_respects_avoided_sites(self):
        model, approvals, pages = FakeModel(), StubApprovals(True), FakePages()   # No agent replies: the model must not be asked.
        history = [{'role': 'user', 'content': 'Make me a PDF about solar sails'},
                   {'role': 'assistant', 'content': 'I will write it in chat instead.'}]
        with patch.object(brain, 'ollama_chat', model), patch.object(actions, 'web_search', fake_search), \
                patch.object(actions, 'fetch_page', pages), patch.object(actions, 'scholar_search', lambda q, n: []):
            result = brain.Brain(self.store, approvals).respond("Don't use wiki.example for sources", history)
        self.assertFalse([p for p in model.payloads if 'tools' in p])
        self.assertTrue(result['text'].startswith('Saved the research dossier'))
        self.assertEqual(len(list(self.root.glob('*.pdf'))), 1)
        self.assertNotIn('https://wiki.example/Solar_sail', pages.fetched)
        self.assertNotIn('wiki.example', approvals.asked[0][2])

    def test_published_abstracts_are_used_without_reading_the_paywalled_page(self):
        pages = FakePages()
        paper = {'title': 'A paper (Lee, 2020)', 'url': 'https://doi.org/10.1/sail', 'snippet': 'x', 'abstract': 'Sail findings. ' * 30}
        sources, failed = research.gather(['solar sails'], 4, fake_search, pages, scholar=lambda q, n: [paper])
        self.assertEqual(sources[0]['kind'], 'abstract')
        self.assertNotIn(paper['url'], pages.fetched)
        with self.assertRaisesRegex(research.ResearchError, 'avoid'):
            research.gather(['x'], 4, lambda q: [paper], pages, avoid=['doi.org'])

    def test_existing_dossier_is_never_overwritten(self):
        name = research.file_name(TOPIC)
        (self.root / name).write_bytes(b'original')
        first = research.save_pdf(str(self.root), name, b'%PDF-new-1')
        second = research.save_pdf(str(self.root), name, b'%PDF-new-2')
        self.assertEqual((self.root / name).read_bytes(), b'original')
        self.assertEqual(first.name, name[:-4] + ' (2).pdf')
        self.assertEqual(second.name, name[:-4] + ' (3).pdf')
        self.assertEqual(first.read_bytes(), b'%PDF-new-1')
        self.assertEqual(research.file_name('a/b:c*?'), 'Research - a b c - %s.pdf' % time.strftime('%Y-%m-%d'))
        with self.assertRaises(ValueError):
            research.dossier(lambda *a: (True, ''), str(self.root / 'missing'), TOPIC)

    # ------------------------------------------------------------ reading PDF and Word files
    def test_read_pdf_and_docx_inside_cowork_folder(self):
        import docx
        from pypdf import PdfWriter
        document = docx.Document()
        document.add_paragraph('Quarterly plan for the sail project.')
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].text = 'Budget'
        table.rows[0].cells[1].text = '42'
        document.save(self.root / 'plan.docx')
        report = {'topic': 'Fixture PDF', 'title': 'Fixture PDF', 'date': '1 January 2026',
                  'sections': [{'name': 'Summary', 'text': 'The launch window opens in March.'}],
                  'sources': [], 'failed': [], 'skipped': []}
        (self.root / 'brief.pdf').write_bytes(research.render_pdf(report))
        blank = PdfWriter()
        blank.add_blank_page(200, 200)
        with open(self.root / 'scan.pdf', 'wb') as output:
            blank.write(output)
        (self.root / 'broken.docx').write_bytes(b'not a zip')

        self.assertIn('Budget | 42', cowork.read(self.root, 'plan.docx')['text'])
        self.assertIn('Quarterly plan', cowork.read(self.root, 'plan.docx')['text'])
        self.assertIn('launch window opens in March', cowork.read(self.root, 'brief.pdf')['text'])
        self.assertIn('[Page 1]', cowork.read(self.root, 'brief.pdf')['text'])
        with self.assertRaisesRegex(ValueError, 'no readable text'):
            cowork.read(self.root, 'scan.pdf')
        with self.assertRaisesRegex(ValueError, 'could not be read'):
            cowork.read(self.root, 'broken.docx')
        (self.root / 'broken.pdf').write_bytes(b'%PDF-1.4 truncated')
        with self.assertRaisesRegex(ValueError, 'could not be read|no readable text'):
            cowork.read(self.root, 'broken.pdf')
        outside = Path(self.temp.name) / 'outside.pdf'
        outside.write_bytes((self.root / 'brief.pdf').read_bytes())
        with self.assertRaisesRegex(ValueError, 'inside your selected cowork folder'):
            cowork.read(self.root, '../outside.pdf')
        # Through Snippy's read_file tool, including the extension-free lookup.
        self.assertIn('Quarterly plan', json.loads(actions.read_file(self.store, 'plan'))['text'])
        listing = json.loads(actions.list_files(self.store, '.'))['text']
        self.assertIn('plan.docx', listing)
        self.assertIn('brief.pdf', listing)


if __name__ == '__main__':
    unittest.main()
