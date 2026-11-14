"""Buffered, offline dictation. No recording is written to disk or sent online."""
import json
import queue
import threading
import time
from .local_ai import BASE

MODELS = {'English (US)': 'vosk-model-small-en-us-0.15', 'English (India)': 'vosk-model-small-en-in-0.4'}
_model = None
_language = None
_lock = threading.RLock()


def unload():
    global _model, _language
    with _lock:
        _model = _language = None


def model(language):
    global _model, _language
    from vosk import Model, SetLogLevel
    SetLogLevel(-1)
    with _lock:
        if _model is None or language != _language:
            path = BASE / 'speech' / MODELS.get(language, MODELS['English (US)'])
            if not path.is_dir():
                raise ValueError('The bundled speech model is missing. Restore the complete app folder.')
            _model = Model(str(path))
            _language = language
        return _model


def input_devices():
    import sounddevice as sd
    hosts = sd.query_hostapis()
    return [(i, '%s · %s' % (d['name'], hosts[d['hostapi']]['name']))
            for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]


def combine(rows):
    text = ' '.join(row.get('text', '').strip() for row in rows).strip()
    confidences = [word.get('conf', 0) for row in rows for word in row.get('result', [])]
    return text, sum(confidences)/len(confidences) if confidences else 0


def listen(release, settings, status, partial=None, maximum=60):
    import sounddevice as sd
    from vosk import KaldiRecognizer
    audio = queue.Queue(maxsize=1400)
    overflow = threading.Event()
    configured = settings.get('microphone', -1)
    device = None if configured in (-1, '', None) else int(configured)
    info = sd.query_devices(device, 'input')
    rate = int(info['default_samplerate'])
    def capture(data, frames, timing, flags):
        if flags:
            overflow.set()
        try:
            audio.put_nowait(bytes(data))
        except queue.Full:
            overflow.set()
    rows = []
    # Start capture BEFORE loading the speech model so the opening words survive.
    with sd.RawInputStream(device=device, samplerate=rate, channels=1, dtype='int16',
                           blocksize=max(800, int(rate*.05)), callback=capture):
        status('Listening… release Ctrl + Alt to send.')
        recognizer = KaldiRecognizer(model(settings.get('speech_language', 'English (US)')), rate)
        recognizer.SetWords(True)
        deadline = time.monotonic() + maximum
        last_partial = ''
        while not release.is_set() and time.monotonic() < deadline:
            try:
                data = audio.get(timeout=.1)
            except queue.Empty:
                continue
            if recognizer.AcceptWaveform(data):
                rows.append(json.loads(recognizer.Result()))
                if maximum <= 10 and rows[-1].get('text'):
                    break
            elif partial:
                words = json.loads(recognizer.PartialResult()).get('partial', '')
                if words and words != last_partial:
                    partial(words)
                    last_partial = words
    while not audio.empty():
        if recognizer.AcceptWaveform(audio.get_nowait()):
            rows.append(json.loads(recognizer.Result()))
    rows.append(json.loads(recognizer.FinalResult()))
    text, confidence = combine(rows)
    if overflow.is_set():
        confidence = 0  # Show for review if audio was dropped; never silently act.
    return text, confidence
