import asyncio
import base64
import hashlib
import http.server
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, QRunnable, Signal


class Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, work):
        super().__init__()
        self.work = work
        self.signals = Signals()

    def run(self):
        try:
            self.signals.done.emit(self.work())
        except Exception as error:
            # Never surface URLs or response bodies that may contain account tokens.
            if isinstance(error, urllib.error.HTTPError):
                message = 'Service returned HTTP %s. Check the account connection.' % error.code
            elif isinstance(error, urllib.error.URLError):
                message = 'Connection unavailable. Check your internet connection.'
            else:
                message = str(error)[:180]
            self.signals.failed.emit(message)


def request(url, data=None, headers=None, form=False):
    headers = dict(headers or {})
    headers['User-Agent'] = 'Notch-Windows/0.1'
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, body, headers), timeout=15) as response:
        return json.load(response)


async def media_async(action=None, preferred=''):
    from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as Manager
    from winrt.windows.media import MediaPlaybackAutoRepeatMode
    manager = await Manager.request_async()
    sessions = list(manager.get_sessions())
    session = next((s for s in sessions if s.source_app_user_model_id == preferred), None)
    session = session or manager.get_current_session()
    if session is None:
        return {'title': 'Nothing playing', 'artist': 'Start Spotify or Apple Music', 'sessions': []}
    info = session.get_playback_info()
    if action:
        methods = {'previous': session.try_skip_previous_async, 'next': session.try_skip_next_async,
                   'play': session.try_toggle_play_pause_async}
        if isinstance(action, tuple) and action[0] == 'seek':
            success = await session.try_change_playback_position_async(int(action[1] * 10_000_000))
        elif action == 'repeat':
            modes = [MediaPlaybackAutoRepeatMode.NONE, MediaPlaybackAutoRepeatMode.LIST, MediaPlaybackAutoRepeatMode.TRACK]
            current = info.auto_repeat_mode
            mode = modes[(modes.index(current) + 1) % 3] if current in modes else modes[1]
            success = await session.try_change_auto_repeat_mode_async(mode)
        else:
            success = await methods[action]()
        if not success:
            raise RuntimeError('This player does not support that control through Windows.')
        await asyncio.sleep(0.2)
        info = session.get_playback_info()
    props = await session.try_get_media_properties_async()
    timeline = session.get_timeline_properties()
    duration = (timeline.end_time - timeline.start_time).total_seconds()
    position = (timeline.position - timeline.start_time).total_seconds()
    artwork = None
    if props.thumbnail:
        from winrt.windows.storage.streams import DataReader
        stream = await props.thumbnail.open_read_async()
        try:
            if stream.size <= 4 * 1024 * 1024:
                reader = DataReader(stream)
                await reader.load_async(stream.size)
                artwork = bytearray(stream.size)
                reader.read_bytes(artwork)
                reader.detach_stream()
                reader.close()
        finally:
            stream.close()
    controls = info.controls
    return dict(title=props.title or 'Unknown track', artist=props.artist or session.source_app_user_model_id, album=props.album_title,
                playing=int(info.playback_status) == 4,
                has_track=bool(props.title) and int(info.playback_status) in (3, 4, 5),
                repeat=int(info.auto_repeat_mode or 0),
                position=position, duration=duration, artwork=artwork,
                sessions=[s.source_app_user_model_id for s in sessions], source=session.source_app_user_model_id,
                can_play=controls.is_play_pause_toggle_enabled, can_next=controls.is_next_enabled,
                can_previous=controls.is_previous_enabled, can_repeat=controls.is_repeat_enabled,
                can_seek=controls.is_playback_position_enabled)


def media(action=None, preferred=''):
    async def bounded():
        try:
            return await asyncio.wait_for(media_async(action, preferred), timeout=8)
        except asyncio.TimeoutError:
            raise RuntimeError('Windows media timed out. Retrying shortly.')
    return asyncio.run(bounded())


def weather(city, fahrenheit, windows_location=False, structured=False):
    if windows_location:
        async def locate():
            from winrt.windows.devices.geolocation import Geolocator, PositionAccuracy
            locator = Geolocator()
            locator.desired_accuracy = PositionAccuracy.DEFAULT
            point = (await locator.get_geoposition_async()).coordinate.point.position
            return {'name': 'Windows location', 'latitude': round(point.latitude, 2), 'longitude': round(point.longitude, 2)}
        try:
            place = asyncio.run(asyncio.wait_for(locate(), timeout=15))
        except Exception:
            raise ValueError('Windows location is unavailable. Enable Location for desktop apps in Windows Settings, or choose City in Notch.')
    else:
        place = weather_city(city)
    return weather_at(place, fahrenheit, structured)


def weather_city(city):
    query = urllib.parse.urlencode({'name': city, 'count': 1, 'language': 'en', 'format': 'json'})
    places = request('https://geocoding-api.open-meteo.com/v1/search?' + query).get('results', [])
    if not places:
        raise ValueError('City not found. Add a nearby city in Settings.')
    return places[0]


def format_weather(data):
    return '%s  %s%s\n%s · Feels like %s%s\nOpen-Meteo · %s' % (data['name'], data['temperature'], data['unit'], data['condition'], data['feels'], data['unit'], data['asof'])


def weather_at(place, fahrenheit, structured=False):
    query = urllib.parse.urlencode(dict(latitude=place['latitude'], longitude=place['longitude'],
                current='temperature_2m,apparent_temperature,weather_code', daily='temperature_2m_max,temperature_2m_min', forecast_days=1,
                temperature_unit='fahrenheit' if fahrenheit else 'celsius', timezone='auto'))
    forecast = request('https://api.open-meteo.com/v1/forecast?' + query)
    result, daily = forecast['current'], forecast.get('daily', {})
    code = result['weather_code']
    condition = 'Clear' if code == 0 else 'Partly cloudy' if code < 3 else 'Cloudy' if code == 3 else 'Fog' if code < 50 else 'Rain' if code < 70 else 'Snow' if code < 80 else 'Showers' if code < 95 else 'Thunderstorm'
    data = dict(name=place['name'], temperature=result['temperature_2m'], feels=result['apparent_temperature'], condition=condition,
                code=code, unit='°F' if fahrenheit else '°C', high=daily.get('temperature_2m_max',[None])[0],
                low=daily.get('temperature_2m_min',[None])[0], asof=result['time'].replace('T',' '))
    return data if structured else format_weather(data)


def notion(token):
    result = request('https://api.notion.com/v1/search', {'page_size': 12, 'sort': {'direction': 'descending', 'timestamp': 'last_edited_time'}},
                     {'Authorization': 'Bearer ' + token, 'Notion-Version': '2022-06-28'})
    pages = []
    for page in result.get('results', []):
        title = page.get('title', [])
        for prop in page.get('properties', {}).values():
            if prop.get('type') == 'title':
                title = prop['title']
        pages.append((''.join(t.get('plain_text', '') for t in title) or 'Untitled', page.get('url', '')))
    return pages


def stocks(symbols, token):
    rows = []
    for symbol in [s.strip().upper() for s in symbols.split(',') if s.strip()][:8]:
        result = request('https://finnhub.io/api/v1/quote?' + urllib.parse.urlencode({'symbol': symbol}), headers={'X-Finnhub-Token': token})
        if not result.get('t'):
            rows.append(symbol + ' · Quote unavailable')
            continue
        stamp = datetime.fromtimestamp(result['t']).strftime('%d %b %H:%M')
        rows.append('%s  %s  (%+.2f%%)\nAs of %s' % (symbol, result['c'], result.get('dp') or 0, stamp))
    return '\n\n'.join(rows)


def running_tasks():
    names = {'claude.exe', 'codex.exe', 'chatgpt.exe', 'windowsterminal.exe', 'powershell.exe', 'pwsh.exe', 'cmd.exe'}
    rows = []
    for process in psutil.process_iter(['name', 'pid']):
        if (process.info['name'] or '').lower() in names:
            rows.append('%s · PID %s' % (process.info['name'], process.pid))
    return '\n'.join(rows[:16]) or 'No matching apps running.'


def search_files(root, term, cancelled):
    found = []
    deadline = time.monotonic() + 8
    skip = {'.git', '.venv', 'node_modules', 'AppData', '$Recycle.Bin', 'Windows', 'Program Files', 'Program Files (x86)'}
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in skip and not os.path.islink(os.path.join(directory, d))]
        if cancelled.is_set() or time.monotonic() > deadline:
            return found, True
        for name in files:
            if term.casefold() in name.casefold():
                found.append(str(Path(directory) / name))
                if len(found) >= 50:
                    return found, True
    return found, False


def google_connect(store):
    client = store.settings['google_client_id'].strip()
    if not client:
        raise ValueError('Add a Google Desktop OAuth client ID in Settings first.')
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if query.get('state', [''])[0] != state:
                self.send_error(400)
                return
            result.update(query)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'You may return to Notch.')

        def log_message(self, *_):
            pass

    with http.server.HTTPServer(('127.0.0.1', 0), Callback) as server:
        server.timeout = 1
        redirect = 'http://127.0.0.1:%s/' % server.server_port
        query = urllib.parse.urlencode(dict(client_id=client, redirect_uri=redirect, response_type='code',
            scope='https://www.googleapis.com/auth/calendar.readonly', access_type='offline', prompt='consent',
            state=state, code_challenge=challenge, code_challenge_method='S256'))
        webbrowser.open('https://accounts.google.com/o/oauth2/v2/auth?' + query)
        end = time.monotonic() + 180
        while not result and time.monotonic() < end:
            server.handle_request()
    if 'code' not in result:
        raise ValueError('Google sign-in cancelled or timed out.')
    data = dict(client_id=client, code=result['code'][0], redirect_uri=redirect, grant_type='authorization_code', code_verifier=verifier)
    secret = store.secret('google_client_secret')
    if secret:
        data['client_secret'] = secret
    tokens = request('https://oauth2.googleapis.com/token', data, form=True)
    store.secret('google_tokens', tokens)
    return 'Google Calendar connected.'


def calendar(store):
    tokens = store.secret('google_tokens')
    if not tokens:
        raise ValueError('Connect Google Calendar in Settings.')
    if tokens.get('refresh_token'):
        data = dict(client_id=store.settings['google_client_id'], refresh_token=tokens['refresh_token'], grant_type='refresh_token')
        if store.secret('google_client_secret'):
            data['client_secret'] = store.secret('google_client_secret')
        fresh = request('https://oauth2.googleapis.com/token', data, form=True)
        tokens.update(fresh)
        store.secret('google_tokens', tokens)
    query = urllib.parse.urlencode(dict(timeMin=datetime.now(timezone.utc).isoformat(), singleEvents='true', orderBy='startTime', maxResults=10))
    response = request('https://www.googleapis.com/calendar/v3/calendars/primary/events?' + query,
                       headers={'Authorization': 'Bearer ' + tokens['access_token']})
    return [(e.get('summary', 'Untitled event') + '\n' + e['start'].get('dateTime', e['start'].get('date', '')), e.get('htmlLink', '')) for e in response.get('items', [])]
