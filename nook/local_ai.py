"""Start and own the bundled Ollama service without an external installer."""
import atexit
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

PORT = 11435
BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1] / 'vendor'
MODEL = 'qwen3:0.6b'
_process = None
_lock = threading.Lock()


def stop():
    global _process
    if _process is not None and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _process.kill()
    _process = None


def ensure_running():
    global _process
    executable = BASE / 'ollama/ollama.exe'
    if not executable.is_file():
        raise ValueError('Bundled AI runtime is missing. Restore the complete Nook app folder.')
    with _lock:
        if _process is None or _process.poll() is not None:
            environment = dict(os.environ, OLLAMA_HOST=f'127.0.0.1:{PORT}',
                               OLLAMA_MODELS=str(BASE / 'models'), OLLAMA_NO_CLOUD='1',
                               OLLAMA_KEEP_ALIVE='0', OLLAMA_NUM_PARALLEL='1')
            _process = subprocess.Popen([str(executable), 'serve'], env=environment,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        for attempt in range(40):
            try:
                with opener.open(f'http://127.0.0.1:{PORT}/api/tags', timeout=1):
                    return
            except OSError:
                if _process.poll() is not None:
                    raise ValueError('The bundled AI service could not start. Restart Nook and try again.')
                time.sleep(0.25)
        raise ValueError('Local AI is taking too long to start. Try again.')


atexit.register(stop)
