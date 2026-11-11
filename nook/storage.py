import base64
import ctypes
import json
import os
import threading
from pathlib import Path

DATA = Path(os.environ.get('NOOK_DATA_DIR', str(Path(os.environ['LOCALAPPDATA']) / 'Nook')))
DATA.mkdir(parents=True, exist_ok=True)
WIDGETS = ['Music', 'Time', 'To do', 'Weather', 'Google Calendar', 'Notion', 'Stocks',
           'Claude usage', 'Codex usage', 'Running tasks', 'Calls', 'Academia']
DEFAULTS = dict(enabled=['Music', 'Time', 'To do'], order=WIDGETS, width=680,
                compact_width=380, height=460, radius=28, opacity=100, screen=0,
                accent='#b7b0ff', font='Segoe UI', clock_style='Minimal', weather_style='Detailed',
                hour24=False, seconds=False, animation=True, collapse_ms=90, ui_revision=2,
                city='', fahrenheit=False, symbols='AAPL, MSFT', search_root=str(Path.home()),
                google_client_id='', google_client_secret='', todos=[], deadlines=[])


class Blob(ctypes.Structure):
    _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    """Bind account credentials to the signed-in Windows user with DPAPI."""
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.settings = json.loads(json.dumps(DEFAULTS))
        self.warning = ''
        try:
            saved = json.loads((DATA / 'settings.json').read_text('utf-8'))
            if saved.get('ui_revision', 1) < 2:
                if saved.get('collapse_ms') == 650:
                    saved['collapse_ms'] = 90
                if saved.get('compact_width') == 250:
                    saved['compact_width'] = 380
                saved['ui_revision'] = 2
            self.settings.update(saved)
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            self.warning = 'Settings could not be read. Defaults loaded.'
        self.secrets = {}
        try:
            self.secrets = json.loads(protect((DATA / 'accounts.bin').read_bytes(), True))
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            self.warning = 'Saved accounts could not be unlocked. Reconnect in Settings.'

    def save(self):
        with self.lock:
            temp = DATA / 'settings.tmp'
            temp.write_text(json.dumps(self.settings, indent=2), 'utf-8')
            temp.replace(DATA / 'settings.json')

    def secret(self, key, value=None):
        with self.lock:
            if value is None:
                return self.secrets.get(key, '')
            self.secrets[key] = value
            temp = DATA / 'accounts.tmp'
            temp.write_bytes(protect(json.dumps(self.secrets).encode()))
            temp.replace(DATA / 'accounts.bin')
