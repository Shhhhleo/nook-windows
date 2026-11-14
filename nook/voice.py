"""Hold Ctrl+Alt to speak. Only modifier states are inspected, never typed content."""
import ctypes
import os
import subprocess
import threading
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, Signal

class PushToTalk(QObject):
    text_ready = Signal(str)
    review = Signal(str)
    status = Signal(str)
    finished = Signal()

    def __init__(self, snippy):
        super().__init__(snippy)
        self.snippy = snippy
        self.held = False
        self.running = False
        self.release = threading.Event()
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.poll)
        self.finished.connect(self.complete)
        self.closed = False

    def configure(self, enabled):
        # Offscreen tests never inspect desktop keys or open a microphone.
        active = enabled and os.name == 'nt' and os.environ.get('QT_QPA_PLATFORM') != 'offscreen'
        self.timer.start() if active else self.timer.stop()
        if not active:
            self.release.set()

    def poll(self):
        state = ctypes.windll.user32.GetAsyncKeyState
        held = bool(state(0x11) & 0x8000 and state(0x12) & 0x8000 and not state(0xA5) & 0x8000)
        self.update_held(held)

    def update_held(self, held):
        if held and not self.held and not self.running and not self.snippy.busy:
            self.begin()
        elif not held and self.held:
            self.release.set()
        self.held = held

    def begin(self):
        self.running = True
        self.release.clear()
        self.status.emit('Opening microphone…')
        threading.Thread(target=self.recognize, daemon=True).start()

    def recognize(self):
        from . import speech
        try:
            text, confidence = speech.listen(self.release, dict(self.snippy.owner.store.settings), self.status.emit)
            if not self.closed:
                if not text:
                    self.status.emit('No speech heard. Check the selected microphone in Settings → Assistant.')
                elif confidence < .65:
                    self.review.emit(text)
                    self.status.emit('Please check what I heard, then press Enter.')
                else:
                    self.text_ready.emit(text)
        except Exception:
            if not self.closed:
                self.status.emit('Microphone unavailable. Check Windows microphone permission and the input selected in Settings → Assistant.')
        finally:
            if not self.closed:
                self.finished.emit()

    def complete(self):
        self.running = False

    def close(self):
        self.closed = True
        self.timer.stop()
        self.release.set()
