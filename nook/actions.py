"""Real-world actions Snippy's local brain can take on this PC and connected accounts.

Every function here is called from a worker thread. Anything that sends a message
or creates a file is gated by the approval callback in brain.py, never here.
"""
import base64
import html
import ipaddress
import json
import os
import re
import socket
import time
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from . import services, cowork

WHOP_API = 'https://api.whop.com/api/v1'
GMAIL_API = 'https://gmail.googleapis.com/gmail/v1/users/me'


# ---------------------------------------------------------------- browser & apps

def open_url(url):
    url = url.strip()
    if not re.match(r'^(https?://|mailto:)', url, re.I):
        if re.match(r'^[\w.-]+\.[a-z]{2,}(/.*)?$', url, re.I):
            url = 'https://' + url
        else:
            url = 'https://www.google.com/search?q=' + urllib.parse.quote_plus(url)
    webbrowser.open(url)
    return 'Opened ' + url + ' in your default browser.'


def start_menu_entries():
    roots = [Path(os.environ.get('ProgramData', r'C:\ProgramData')) / 'Microsoft/Windows/Start Menu/Programs',
             Path(os.environ.get('APPDATA', '')) / 'Microsoft/Windows/Start Menu/Programs',
             Path.home() / 'Desktop']
    entries = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob('*'):
            if path.suffix.lower() in ('.lnk', '.url', '.appref-ms'):
                entries.append(path)
    return entries


def open_app(name):
    wanted = re.sub(r'\s+', ' ', name.strip().casefold())
    if not wanted:
        raise ValueError('Name the app to open.')
    entries = start_menu_entries()
    def rank(path):
        stem = path.stem.casefold()
        if 'uninstall' in stem:
            return 9
        return 0 if stem == wanted else 1 if stem.startswith(wanted) else 2 if wanted in stem else 9
    best = sorted(entries, key=lambda p: (rank(p), len(p.stem)))
    if not best or rank(best[0]) == 9:
        raise ValueError('I could not find an app called “%s” in the Start menu.' % name)
    os.startfile(str(best[0]))
    return 'Opened ' + best[0].stem + '.'


# ---------------------------------------------------------------- free web research

BROWSER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'


def _text(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', fragment))).strip()


def web_search(query, limit=6):
    """Keyless public web search (DuckDuckGo HTML results), falling back to Wikipedia."""
    query = query.strip()[:300]
    if not query:
        raise ValueError('Give me something to search for.')
    rows = []
    try:
        request = urllib.request.Request('https://html.duckduckgo.com/html/', urllib.parse.urlencode({'q': query}).encode(),
                                         {'User-Agent': BROWSER_AGENT, 'Content-Type': 'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(request, timeout=12) as response:
            page = response.read(1_500_000).decode('utf-8', 'replace')
        snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', page, re.S)
        for index, (href, title) in enumerate(re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', page, re.S)):
            href = html.unescape(href)
            if 'uddg=' in href:
                href = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get('uddg', [''])[0])
            if href.startswith('//'):
                href = 'https:' + href
            if not href.startswith('http') or 'duckduckgo.com/y.js' in href:
                continue  # Skip ads and internal links.
            rows.append({'title': _text(title), 'url': href, 'snippet': _text(snippets[index]) if index < len(snippets) else ''})
            if len(rows) >= limit:
                break
    except (OSError, ValueError):
        rows = []
    if not rows:
        from . import assistant
        result = assistant.web_lookup(query)
        rows = [{'title': r['title'], 'url': r['url'], 'snippet': r['detail']} for r in result.get('links', [])]
    if not rows:
        raise ValueError('Web search returned nothing. Check the internet connection or try different words.')
    return rows


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def check_public_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname:
        raise ValueError('Only public https pages can be read.')
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, parts.port or 443)}
    except socket.gaierror:
        raise ValueError('That website could not be found.')
    for address in addresses:
        ip = ipaddress.ip_address(address.split('%')[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError('Pages on local or private networks cannot be read.')
    return url


def fetch_page(url, limit=6000):
    """Readable text of a public https page, bounded in size. Never local or private addresses."""
    check_public_url(url.strip())
    opener = urllib.request.build_opener(SafeRedirect)
    request = urllib.request.Request(url.strip(), headers={'User-Agent': BROWSER_AGENT, 'Accept': 'text/html,text/plain'})
    with opener.open(request, timeout=15) as response:
        kind = response.headers.get('Content-Type', '')
        if 'html' not in kind and 'text' not in kind:
            raise ValueError('That link is not a readable web page (%s).' % kind.split(';')[0])
        charset = response.headers.get_content_charset() or 'utf-8'
        page = response.read(2_000_000).decode(charset, 'replace')
    title = _text((re.search(r'<title[^>]*>(.*?)</title>', page, re.S | re.I) or [None, ''])[1])
    page = re.sub(r'<(script|style|noscript|svg|nav|footer|header|form)\b.*?</\1>', ' ', page, flags=re.S | re.I)
    body = re.search(r'<(article|main)\b.*?</\1>', page, re.S | re.I)
    text = _text(body.group(0) if body and len(_text(body.group(0))) > 400 else page)
    return {'url': url, 'title': title[:200], 'text': text[:limit], 'truncated': len(text) > limit}


# ---------------------------------------------------------------- local data

def list_todos(store):
    active = [row['text'] for row in store.settings.get('todos', []) if not row.get('done')]
    return json.dumps({'open_tasks': active})


def add_todo(store, text):
    text = text.strip()[:240]
    if not text:
        raise ValueError('The task is empty.')
    with store.lock:
        todos = store.settings.setdefault('todos', [])
        if any(r['text'].casefold() == text.casefold() and not r.get('done') for r in todos):
            return 'That task is already on the list.'
        todos.append({'text': text, 'done': False})
        store.settings['todos'] = todos[-200:]
        store.save()
    return 'Added task: ' + text


def complete_todo(store, text):
    query = text.strip().casefold()
    with store.lock:
        row = next((r for r in store.settings.get('todos', []) if not r.get('done') and query in r['text'].casefold()), None)
        if not row:
            return 'No open task matches “%s”.' % text
        row['done'] = True
        store.save()
    return 'Marked complete: ' + row['text']


def weather(store, city=''):
    settings = store.settings
    use_windows = not city and settings.get('weather_source') == 'Windows location'
    data = services.weather(city or settings.get('city') or 'London', settings.get('fahrenheit', False), use_windows, True)
    return json.dumps(data)


def calendar(store):
    rows = services.calendar(store)
    return json.dumps([{'event': text, 'link': link} for text, link in rows])


def find_files(store, query):
    from . import assistant
    return json.dumps(assistant.find_files(query, store.settings['search_root']))


def list_files(store, folder='.'):
    return json.dumps(cowork.listing(store.settings['search_root'], folder or '.'))


def read_file(store, path):
    from . import assistant
    result = assistant.read_cowork_file(store.settings['search_root'], path)
    return json.dumps(result)[:60000]


def plan_moves(root, moves):
    """Validate a file-organisation plan. Sources must exist; destinations must not. All inside root."""
    base = Path(root).resolve()
    if not moves:
        raise ValueError('The move plan is empty.')
    if len(moves) > 200:
        raise ValueError('Move at most 200 files at once.')
    plan, targets = [], set()
    for move in moves:
        source = cowork.resolve(root, move['source'])
        if not source.is_file() or source.is_symlink():
            raise ValueError('%s is not a file in the cowork folder.' % move['source'])
        destination = cowork.resolve(root, move['destination'], exists=False)
        if destination.suffix == '' and not destination.is_file():
            destination = destination / source.name  # A folder was given.
        if destination.exists() or destination in targets:
            raise ValueError('%s already exists. Nothing is ever overwritten.' % destination.relative_to(base).as_posix())
        if source == destination:
            continue
        targets.add(destination)
        plan.append({'source': source.relative_to(base).as_posix(), 'destination': destination.relative_to(base).as_posix()})
    if not plan:
        raise ValueError('Nothing to move.')
    return plan


def apply_moves(root, plan):
    done = []
    for move in plan:
        source = cowork.resolve(root, move['source'])
        destination = cowork.resolve(root, move['destination'], exists=False)
        if destination.exists():
            continue  # Created meanwhile; never overwrite.
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.rename(source, destination)  # Same volume; fails instead of overwriting on Windows.
        done.append(move)
    skipped = len(plan) - len(done)
    return 'Moved %s file%s%s.' % (len(done), '' if len(done) == 1 else 's',
                                   ' (%s skipped because the destination already existed)' % skipped if skipped else '') + \
           ''.join('\n%s → %s' % (m['source'], m['destination']) for m in done[:20])


# ---------------------------------------------------------------- Google / Gmail

def google_token(store, need_gmail=False):
    tokens = store.secret('google_tokens')
    if not tokens:
        raise ValueError('Google is not connected. Open Settings → Connections and choose Connect Google.')
    if need_gmail and 'gmail' not in tokens.get('scope', ''):
        raise ValueError('Gmail access was not granted. Open Settings → Connections and choose Connect Google again to allow Gmail.')
    fresh_until = tokens.get('obtained_at', 0) + tokens.get('expires_in', 0) - 120
    if time.time() > fresh_until and tokens.get('refresh_token'):
        data = dict(client_id=store.settings['google_client_id'], refresh_token=tokens['refresh_token'], grant_type='refresh_token')
        if store.secret('google_client_secret'):
            data['client_secret'] = store.secret('google_client_secret')
        tokens.update(services.request('https://oauth2.googleapis.com/token', data, form=True))
        tokens['obtained_at'] = time.time()
        store.secret('google_tokens', tokens)
    return tokens['access_token']


def gmail_search(store, query='is:unread in:inbox', limit=10):
    token = google_token(store, True)
    headers = {'Authorization': 'Bearer ' + token}
    params = urllib.parse.urlencode({'q': query, 'maxResults': max(1, min(int(limit), 25))})
    listing = services.request(GMAIL_API + '/messages?' + params, headers=headers)
    rows = []
    for item in listing.get('messages', []):
        meta = services.request(GMAIL_API + '/messages/%s?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date' % item['id'], headers=headers)
        head = {h['name']: h['value'] for h in meta.get('payload', {}).get('headers', [])}
        rows.append({'id': item['id'], 'thread_id': meta.get('threadId'), 'from': head.get('From', ''),
                     'subject': head.get('Subject', ''), 'date': head.get('Date', ''),
                     'snippet': meta.get('snippet', ''), 'unread': 'UNREAD' in meta.get('labelIds', [])})
    return json.dumps(rows)


def _body_text(part):
    if part.get('mimeType', '').startswith('text/plain') and part.get('body', {}).get('data'):
        return base64.urlsafe_b64decode(part['body']['data'] + '==').decode('utf-8', 'replace')
    for child in part.get('parts', []) or []:
        text = _body_text(child)
        if text:
            return text
    if part.get('mimeType', '').startswith('text/html') and part.get('body', {}).get('data'):
        html = base64.urlsafe_b64decode(part['body']['data'] + '==').decode('utf-8', 'replace')
        return re.sub(r'<[^>]+>', ' ', html)
    return ''


def gmail_read(store, message_id):
    token = google_token(store, True)
    message = services.request(GMAIL_API + '/messages/%s?format=full' % urllib.parse.quote(message_id),
                               headers={'Authorization': 'Bearer ' + token})
    head = {h['name']: h['value'] for h in message.get('payload', {}).get('headers', [])}
    return json.dumps({'id': message_id, 'thread_id': message.get('threadId'), 'from': head.get('From', ''),
                       'to': head.get('To', ''), 'subject': head.get('Subject', ''), 'date': head.get('Date', ''),
                       'message_id_header': head.get('Message-ID', head.get('Message-Id', '')),
                       'body': _body_text(message.get('payload', {}))[:12000]})


def gmail_send(store, to, subject, body, reply_to_id=''):
    token = google_token(store, True)
    headers = {'Authorization': 'Bearer ' + token}
    email = EmailMessage()
    email['To'] = to
    email['Subject'] = subject
    email.set_content(body)
    payload = {}
    if reply_to_id:
        original = json.loads(gmail_read(store, reply_to_id))
        if original.get('message_id_header'):
            email['In-Reply-To'] = original['message_id_header']
            email['References'] = original['message_id_header']
        payload['threadId'] = original.get('thread_id')
    payload['raw'] = base64.urlsafe_b64encode(email.as_bytes()).decode()
    result = services.request(GMAIL_API + '/messages/send', payload, headers)
    return 'Email sent to %s (message %s).' % (to, result.get('id', '?'))


# ---------------------------------------------------------------- Whop

def money(value):
    if isinstance(value, dict):
        try:
            return float(value.get('amount') or 0)
        except (TypeError, ValueError):
            return 0.0
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def whop_get(store, path, params):
    key = store.secret('whop_api_key')
    if not key:
        raise ValueError('Whop is not connected. Add your Whop API key in Settings → Connections.')
    account = store.settings.get('whop_account_id', '').strip()
    params = list(params) + ([('account_id', account)] if account else [])
    return services.request(WHOP_API + path + '?' + urllib.parse.urlencode(params),
                            headers={'Authorization': 'Bearer ' + key})


def whop_pages(store, path, params, limit=1000):
    rows, after = [], None
    while len(rows) < limit:
        page = whop_get(store, path, params + [('first', 100)] + ([('after', after)] if after else []))
        rows += page.get('data', [])
        info = page.get('page_info', {})
        if not info.get('has_next_page') or not info.get('end_cursor'):
            break
        after = info['end_cursor']
    return rows[:limit]


def whop_count(store, status):
    page = whop_get(store, '/memberships', [('status', status), ('first', 0), ('include_total_count', 'true')])
    return page.get('page_info', {}).get('total_count')


def since(days):
    return (datetime.now(timezone.utc) - timedelta(days=max(1, min(int(days), 365)))).isoformat()


def whop_summary(store, days=30):
    payments = whop_pages(store, '/payments', [('statuses', 'paid'), ('created_after', since(days))])
    revenue = {}
    for row in payments:
        currency = (row.get('currency') or 'usd').upper()
        revenue[currency] = round(revenue.get(currency, 0) + money(row.get('total')), 2)
    new_members = whop_get(store, '/memberships', [('created_after', since(days)), ('first', 0), ('include_total_count', 'true')])
    return json.dumps({
        'period_days': int(days),
        'paid_payments': len(payments),
        'revenue_by_currency': revenue,
        'active_memberships': whop_count(store, 'active'),
        'trialing_memberships': whop_count(store, 'trialing'),
        'past_due_memberships': whop_count(store, 'past_due'),
        'canceling_memberships': whop_count(store, 'canceling'),
        'new_memberships_in_period': new_members.get('page_info', {}).get('total_count'),
        'source': 'Whop API, retrieved ' + datetime.now().strftime('%d %b %Y %H:%M'),
    })


def whop_payments(store, days=7, status=''):
    params = [('created_after', since(days))] + ([('statuses', status)] if status else [])
    rows = whop_pages(store, '/payments', params, 40)
    return json.dumps([{'id': r.get('id'), 'status': r.get('status'), 'amount': money(r.get('total')),
                        'currency': r.get('currency'), 'created_at': r.get('created_at'), 'paid_at': r.get('paid_at'),
                        'product': (r.get('product') or {}).get('title') if isinstance(r.get('product'), dict) else r.get('product_id')}
                       for r in rows])


def whop_memberships(store, status='active', days=0):
    params = [('status', status)] if status else []
    if days:
        params.append(('created_after', since(days)))
    rows = whop_pages(store, '/memberships', params, 40)
    return json.dumps([{'id': r.get('id'), 'status': r.get('status'), 'product': (r.get('product') or {}).get('title'),
                        'renewal_price': money(r.get('renewal_price')), 'billing_period_days': r.get('billing_period_days'),
                        'created_at': r.get('created_at'), 'cancel_at_period_end': r.get('cancel_at_period_end')}
                       for r in rows])
