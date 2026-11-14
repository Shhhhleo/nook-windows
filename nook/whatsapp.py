"""WhatsApp Web automation through Microsoft Edge (Playwright), plus Snippy's chat autopilot.

One thread owns the browser. Other threads send it commands through call().
WhatsApp Web's page structure changes from time to time; all selectors live in SEL
so they can be updated in one place. This automates the user's own logged-in
WhatsApp Web session on their PC; WhatsApp may restrict accounts that automate heavily.
"""
import queue
import re
import threading
import time
from concurrent.futures import Future

from PySide6.QtCore import QObject, Signal

from .storage import DATA

URL = 'https://web.whatsapp.com/'
SEL = {
    'ready': '#pane-side',
    'qr': 'canvas[aria-label], div[data-ref]',
    'row': '#pane-side div[role="listitem"], #pane-side div[role="row"]',
    'row_title': 'span[title]',
    'unread': 'span[aria-label*="unread" i]',
    'search': '#side div[contenteditable="true"], #side input[type="text"], div[contenteditable="true"][data-tab="3"]',
    'composer': '#main footer div[contenteditable="true"]',
    'header_title': '#main header span[title], #main header span[dir="auto"]',
    'message': '#main div.message-in, #main div.message-out',
    'message_text': 'span.selectable-text',
    'message_meta': 'div.copyable-text',
}
POLL_SECONDS = 15
MIN_GAP_SECONDS = 45
MAX_AUTO_PER_HOUR = 30


def digits(value):
    return re.sub(r'\D', '', value or '')


def same_contact(contact, title):
    title = (title or '').strip()
    if not title:
        return False
    if contact.get('name', '').strip().casefold() == title.casefold():
        return True
    number = digits(contact.get('phone'))
    return bool(number) and len(number) >= 7 and number[-10:] == digits(title)[-10:]


class WhatsApp(QObject):
    status = Signal(str)
    activity = Signal(str)        # Human-readable log line for the UI.
    draft = Signal(object)        # {'contact', 'incoming', 'reply'} awaiting approval.

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.brain = None
        self.commands = queue.Queue()
        self.thread = None
        self.page = None
        self.context = None
        self.playwright = None
        self.logged_in = False
        self.handled = {}         # contact name -> last incoming message key already answered
        self.last_auto = {}       # contact name -> time of last auto reply
        self.auto_log = []        # timestamps of auto replies (rate limit)
        self.stopping = False

    # ------------------------------------------------------------ public API (any thread)
    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stopping = False
        self.thread = threading.Thread(target=self.loop, name='whatsapp', daemon=True)
        self.thread.start()

    def call(self, command, *args, timeout=120):
        self.start()
        future = Future()
        self.commands.put((command, args, future))
        return future.result(timeout)

    def submit(self, command, *args):
        self.start()
        future = Future()
        self.commands.put((command, args, future))
        return future

    def stop(self):
        self.stopping = True
        if self.thread and self.thread.is_alive():
            self.commands.put(('quit', (), Future()))

    # ------------------------------------------------------------ browser thread
    def loop(self):
        try:
            self.open_browser()
        except Exception as error:
            self.status.emit('WhatsApp could not start: %s' % str(error)[:160])
            self.fail_pending(error)
            self.thread = None
            return
        next_poll = 0
        while not self.stopping:
            try:
                command, args, future = self.commands.get(timeout=1)
            except queue.Empty:
                if time.monotonic() >= next_poll:
                    next_poll = time.monotonic() + POLL_SECONDS
                    self.safe(self.autopilot)
                continue
            if command == 'quit':
                future.set_result(None)
                break
            try:
                future.set_result(getattr(self, 'do_' + command)(*args))
            except Exception as error:
                future.set_exception(error)
        self.close_browser()

    def fail_pending(self, error):
        while True:
            try:
                _, _, future = self.commands.get_nowait()
            except queue.Empty:
                return
            future.set_exception(RuntimeError('WhatsApp is unavailable: %s' % str(error)[:160]))

    def safe(self, work):
        try:
            work()
        except Exception as error:
            self.activity.emit('WhatsApp check skipped: %s' % str(error)[:160])

    def open_browser(self):
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        profile = DATA / 'whatsapp-profile'
        profile.mkdir(parents=True, exist_ok=True)
        self.context = self.playwright.chromium.launch_persistent_context(
            str(profile), channel='msedge', headless=False, viewport=None,
            args=['--window-size=1150,820', '--disable-blink-features=AutomationControlled'])
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        self.page.goto(URL, wait_until='domcontentloaded')
        self.status.emit('WhatsApp is opening. If you see a QR code, scan it with your phone (WhatsApp → Linked devices).')
        self.wait_ready(180)

    def close_browser(self):
        for item in (self.context, self.playwright):
            try:
                item and (item.close() if item is self.context else item.stop())
            except Exception:
                pass
        self.page = self.context = self.playwright = None
        self.logged_in = False

    def wait_ready(self, seconds=30):
        try:
            self.page.wait_for_selector(SEL['ready'], timeout=seconds * 1000)
        except Exception:
            self.logged_in = False
            raise RuntimeError('WhatsApp Web is not signed in. Scan the QR code in the WhatsApp window, then try again.')
        if not self.logged_in:
            self.logged_in = True
            self.status.emit('WhatsApp connected.')

    def contact_record(self, name):
        for row in self.store.settings.get('whatsapp_contacts', []):
            if same_contact(row, name) or row.get('name', '').casefold() == name.strip().casefold():
                return row
        return {'name': name.strip(), 'phone': name if len(digits(name)) >= 7 else ''}

    def current_title(self):
        element = self.page.query_selector(SEL['header_title'])
        return (element.get_attribute('title') or element.inner_text()) if element else ''

    def open_chat(self, name):
        self.wait_ready()
        contact = self.contact_record(name)
        # 1. A visible chat-list row with the same title.
        for row in self.page.query_selector_all(SEL['row']):
            title = row.query_selector(SEL['row_title'])
            if title and same_contact(contact, title.get_attribute('title')):
                row.click()
                self.page.wait_for_selector(SEL['composer'], timeout=15000)
                return contact
        # 2. A phone number: WhatsApp's own deep link.
        number = digits(contact.get('phone'))
        if len(number) >= 7:
            self.page.goto(URL + 'send?phone=' + number, wait_until='domcontentloaded')
            self.page.wait_for_selector(SEL['composer'], timeout=45000)
            return contact
        # 3. The search box.
        search = self.page.query_selector(SEL['search'])
        if not search:
            raise RuntimeError('WhatsApp search box not found. WhatsApp Web may have changed its layout.')
        search.click()
        self.page.keyboard.press('Control+A')
        self.page.keyboard.insert_text(contact['name'])
        time.sleep(1.5)
        self.page.keyboard.press('Enter')
        try:
            self.page.wait_for_selector(SEL['composer'], timeout=8000)
        except Exception:
            raise RuntimeError('I could not find a WhatsApp chat called “%s”. Use the exact chat name or a phone number with country code.' % name)
        if not same_contact(contact, self.current_title()):
            raise RuntimeError('The chat that opened is “%s”, not “%s”. Nothing was sent.' % (self.current_title(), name))
        return contact

    def messages(self, limit=15):
        rows = []
        for element in self.page.query_selector_all(SEL['message'])[-max(1, min(int(limit), 40)):]:
            text_node = element.query_selector(SEL['message_text'])
            meta_node = element.query_selector(SEL['message_meta'])
            text = text_node.inner_text().strip() if text_node else '[media or sticker]'
            meta = meta_node.get_attribute('data-pre-plain-text') if meta_node else ''
            rows.append({'from_me': 'message-out' in (element.get_attribute('class') or ''),
                         'text': text, 'meta': (meta or '').strip()})
        return rows

    def type_and_send(self, text):
        composer = self.page.wait_for_selector(SEL['composer'], timeout=15000)
        composer.click()
        lines = text.split('\n')
        for index, line in enumerate(lines):
            if index:
                self.page.keyboard.press('Shift+Enter')
            if line:
                self.page.keyboard.insert_text(line)
        self.page.keyboard.press('Enter')
        time.sleep(1.2)

    # ------------------------------------------------------------ commands
    def do_open(self):
        self.page.bring_to_front()
        self.wait_ready(5)
        return 'WhatsApp is connected.'

    def do_read(self, contact, limit=15):
        record = self.open_chat(contact)
        return {'chat': self.current_title() or record['name'], 'messages': self.messages(limit)}

    def do_send(self, contact, text):
        record = self.open_chat(contact)
        self.type_and_send(text)
        self.activity.emit('Sent to %s: %s' % (record['name'], text[:80]))
        return 'WhatsApp message sent to %s.' % (self.current_title() or record['name'])

    def do_reply(self, contact, text, key):
        result = self.do_send(contact, text)
        self.handled[contact] = key
        return result

    # ------------------------------------------------------------ autopilot
    def autopilot(self):
        settings = self.store.settings
        contacts = settings.get('whatsapp_contacts', [])
        if not (settings.get('whatsapp_autopilot') and contacts and self.brain and self.page):
            return
        self.wait_ready(5)
        for row in self.page.query_selector_all(SEL['row']):
            if not row.query_selector(SEL['unread']):
                continue
            title_node = row.query_selector(SEL['row_title'])
            title = title_node.get_attribute('title') if title_node else ''
            contact = next((c for c in contacts if same_contact(c, title)), None)
            if not contact:
                continue
            row.click()
            self.page.wait_for_selector(SEL['composer'], timeout=15000)
            transcript = self.messages(20)
            if not transcript or transcript[-1]['from_me']:
                continue
            last = transcript[-1]
            key = last['meta'] + last['text']
            if self.handled.get(contact['name']) == key:
                continue
            self.handled[contact['name']] = key
            reply = self.brain.compose_reply(contact, transcript)
            if not reply:
                self.activity.emit('%s messaged you. Snippy left it for you to answer.' % contact['name'])
                continue
            if contact.get('mode') == 'auto' and self.may_auto_send(contact['name']):
                self.type_and_send(reply)
                self.last_auto[contact['name']] = time.time()
                self.auto_log.append(time.time())
                self.activity.emit('Auto-replied to %s: %s' % (contact['name'], reply[:80]))
            else:
                self.draft.emit({'contact': contact['name'], 'incoming': last['text'], 'reply': reply, 'key': key})

    def may_auto_send(self, name):
        now = time.time()
        self.auto_log = [t for t in self.auto_log if now - t < 3600]
        return now - self.last_auto.get(name, 0) >= MIN_GAP_SECONDS and len(self.auto_log) < MAX_AUTO_PER_HOUR
