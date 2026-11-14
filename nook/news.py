"""Small, dated news cache. Refreshes feeds, never model weights or private chats."""
import json
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from .storage import DATA

FEEDS = ('https://feeds.bbci.co.uk/news/world/rss.xml', 'https://feeds.bbci.co.uk/news/technology/rss.xml')
CACHE = DATA / 'news.json'
TTL = 900
LOCK = threading.Lock()


def is_news_question(text):
    return bool(re.search(r'\b(news|headlines|current affairs|current events)\b', text, re.I))


def parse(data):
    root = ET.fromstring(data)
    rows = []
    for item in root.findall('./channel/item')[:30]:
        title, url = item.findtext('title', '').strip(), item.findtext('link', '').strip()
        if not title or not url.startswith('https://'):
            continue
        try:
            published = parsedate_to_datetime(item.findtext('pubDate')).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, AttributeError):
            published = ''
        rows.append({'title': title[:300], 'url': url, 'published': published})
    return rows


def read_cache():
    try:
        data = json.loads(CACHE.read_text(encoding='utf-8'))
        if not isinstance(data.get('items'), list) or not isinstance(data.get('fetched'), (int, float)):
            return {'items': [], 'fetched': 0}
        return data
    except (OSError, ValueError):
        return {'items': [], 'fetched': 0}


def refresh(force=False):
    with LOCK:
        cached = read_cache()
        if not force and 0 <= time.time()-cached['fetched'] < TTL:
            return cached
        rows, failures = [], 0
        for url in FEEDS:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Notch-Snippy/1.0'})
                with urllib.request.urlopen(req, timeout=6) as response:
                    data = response.read(1_000_001)
                if len(data) > 1_000_000:
                    raise ValueError('Feed too large')
                rows.extend(parse(data))
            except (OSError, ValueError, ET.ParseError):
                failures += 1
        if not rows:
            return dict(cached, unavailable=True)
        unique = {r['url']: r for r in rows}
        result = {'items': sorted(unique.values(), key=lambda r: r['published'], reverse=True)[:60],
                  'fetched': time.time(), 'partial': bool(failures)}
        DATA.mkdir(parents=True, exist_ok=True)
        temporary = CACHE.with_suffix('.tmp')
        temporary.write_text(json.dumps(result), encoding='utf-8')
        temporary.replace(CACHE)
        return result


def answer(prompt, enabled=True):
    data = refresh() if enabled else read_cache()
    rows = data['items']
    if not rows:
        return {'text': 'I cannot verify current news right now. Enable news updates in Settings → Assistant and check the internet connection. I will not guess from the local model.'}
    stop = set('what whats is are the a an any new latest news headlines current affairs events today tell me about give show please snippy happening in on of for world update updates'.split())
    words = [w for w in re.findall(r'[a-z]{3,}', prompt.lower()) if w not in stop]
    selected = [r for r in rows if any(w in r['title'].lower() for w in words)] if words else rows
    stamp = datetime.fromtimestamp(data['fetched'], timezone.utc).astimezone().strftime('%d %b %Y, %H:%M %Z')
    stale = data.get('unavailable') or time.time()-data['fetched'] >= TTL or not enabled
    heading = ('Cached news — unable to verify freshness. ' if stale else 'BBC news, retrieved ') + stamp
    if not selected:
        return {'text': heading + '\nNo matching story in the current World and Technology feeds. I cannot verify that topic from these sources.'}
    selected = selected[:5]
    lines = []
    links = []
    for row in selected:
        published = row['published'][:16].replace('T', ' ') + ' UTC' if row['published'] else 'Publication time unavailable'
        lines.append(row['title'] + ' (' + published + ')')
        links.append({'title': row['title'], 'url': row['url'], 'detail': published})
    return {'text': heading + (' · Some feeds unavailable' if data.get('partial') else '') + '\n\n' + '\n\n'.join(lines), 'links': links}


def start_monitor(notch):
    import os
    from PySide6.QtCore import QTimer
    timer = QTimer(notch)
    timer.setInterval(TTL * 1000)
    def update():
        if notch.store.settings.get('live_news', True):
            notch.run_job('news-refresh', refresh, lambda _: None, lambda _: None)
    timer.timeout.connect(update)
    if os.environ.get('QT_QPA_PLATFORM') != 'offscreen':
        timer.start()
        QTimer.singleShot(1500, update)
    notch.news_timer = timer
