import html
import math
from pathlib import Path
from urllib.parse import quote_plus

from PySide6.QtCore import Qt, QTimer, QRectF, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QDesktopServices
from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QTextBrowser, QListWidget, QListWidgetItem)
from . import assistant


class Companion(QPushButton):
    """A small native animated companion; no web renderer or video loop."""
    def __init__(self, owner, callback, size=28):
        super().__init__()
        self.owner = owner
        self.phase = 0
        self.busy = False
        self.setFixedSize(size, size)
        self.setAccessibleName('Open Nook assistant')
        self.setToolTip('Nook assistant')
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(callback)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def showEvent(self, event):
        self.timer.start(70 if self.busy else 160)
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def tick(self):
        if self.owner.store.settings['animation']:
            self.phase += 0.22
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(self.width()/32, self.height()/32)
        pulse = math.sin(self.phase) if self.busy else math.sin(self.phase)*0.3
        painter.setPen(QPen(QColor('#555269'), 1))
        painter.setBrush(QColor('#201e2b'))
        painter.drawEllipse(QRectF(1, 1, 30, 30))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#d7d1ff'))
        painter.drawRoundedRect(QRectF(7, 8 + pulse, 18, 16), 7, 7)
        painter.setBrush(QColor('#2b2640'))
        blink = int(self.phase * 10) % 135 < 5
        for x in (12, 19):
            painter.drawRoundedRect(QRectF(x, 14 + pulse, 2, 1 if blink else 4), 1, 1)
        if self.hasFocus():
            painter.setPen(QPen(QColor('#b7b0ff'), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(0.5, 0.5, 31, 31))


class AssistantPanel(QWidget):
    def __init__(self, notch):
        super().__init__()
        self.notch = notch
        self.history = []
        self.busy = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(7)
        head = QHBoxLayout()
        self.avatar = Companion(notch, self.focus_input, 32)
        head.addWidget(self.avatar)
        self.status = QLabel('Local tools · Ollama when connected')
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color: #aaa5ba; font-size: 11px;')
        head.addWidget(self.status, 1)
        clear = QPushButton('Clear')
        clear.clicked.connect(self.clear_chat)
        head.addWidget(clear)
        root.addLayout(head)
        self.transcript = QTextBrowser()
        self.transcript.setOpenLinks(False)
        self.transcript.setStyleSheet('QTextBrowser { background: transparent; border: 0; font-size: 12px; }')
        root.addWidget(self.transcript, 1)
        self.results = QListWidget()
        self.results.setMaximumHeight(115)
        self.results.itemActivated.connect(self.open_result)
        self.results.hide()
        root.addWidget(self.results)
        self.web_button = QPushButton()
        self.web_button.hide()
        self.web_button.clicked.connect(self.web_action)
        root.addWidget(self.web_button)
        self.web_query = ''
        self.confirm_query = ''
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setMaxLength(4000)
        self.input.setAccessibleName('Message Nook assistant')
        self.input.setPlaceholderText('Ask Nook, calculate, or find a file…')
        self.input.returnPressed.connect(self.send)
        row.addWidget(self.input, 1)
        self.mic = QPushButton('Talk')
        self.mic.setToolTip('Listen once with Windows speech. Review the text before sending.')
        self.mic.clicked.connect(self.listen)
        row.addWidget(self.mic)
        self.send_button = QPushButton('Send')
        self.send_button.clicked.connect(self.send)
        row.addWidget(self.send_button)
        root.addLayout(row)
        self.append('Nook', 'Ready when you are. Try “24 * 7”, “find files report” or “look up solar energy”.')

    def focus_input(self):
        self.input.setFocus()

    def append(self, role, text):
        self.transcript.append('<p style="margin-bottom:10px"><b>%s</b><br>%s</p>' %
                               (html.escape(role), html.escape(text).replace('\n', '<br>')))
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_chat(self):
        if self.busy:
            return
        self.history.clear()
        self.transcript.clear()
        self.results.clear()
        self.results.hide()
        self.web_button.hide()
        self.append('Nook', 'Conversation cleared. Messages stay in memory only.')

    def set_busy(self, value, status='Ready'):
        self.busy = value
        self.avatar.busy = value
        self.status.setText(status)
        self.send_button.setEnabled(not value)
        self.mic.setEnabled(not value)

    def send(self):
        prompt = self.input.text().strip()
        if not prompt or self.busy:
            return
        self.input.clear()
        self.append('You', prompt)
        self.results.clear()
        self.results.hide()
        self.web_button.hide()
        self.set_busy(True, 'Working locally…')
        history = list(self.history)
        settings = dict(self.notch.store.settings)
        def done(result):
            self.history.extend([{'role': 'user', 'content': prompt},
                                 {'role': 'assistant', 'content': result['text']}])
            self.history = self.history[-20:]
            self.show_result(result)
        self.notch.run_job('assistant', lambda: assistant.respond(prompt, history, settings), done, self.failed)

    def show_result(self, result):
        self.set_busy(False)
        self.append('Nook', result['text'])
        self.results.clear()
        for path in result.get('files', []):
            item = QListWidgetItem(Path(path).name + '\n' + path)
            item.setData(Qt.UserRole, ('file', path))
            self.results.addItem(item)
        for source in result.get('links', []):
            item = QListWidgetItem(source['title'] + '\n' + source['detail'])
            item.setData(Qt.UserRole, ('web', source['url']))
            self.results.addItem(item)
        self.results.setVisible(self.results.count() > 0)
        self.web_query = result.get('web_query', '')
        self.confirm_query = result.get('confirm_web', '')
        self.web_button.setText('Look up this public topic online' if self.confirm_query else 'Search the wider web in your browser')
        self.web_button.setVisible(bool(self.web_query or self.confirm_query))
        if self.notch.store.settings['speak_replies']:
            self.notch.run_job('speech-output', lambda: assistant.speak(result['text']), lambda _: None,
                               lambda message: self.status.setText(message))

    def failed(self, message):
        self.set_busy(False, 'Check the connection in Settings → Assistant')
        self.append('Nook', message)

    def open_result(self, item):
        kind, target = item.data(Qt.UserRole)
        if kind == 'file':
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(target).parent)))
        elif QUrl(target).scheme() == 'https':
            QDesktopServices.openUrl(QUrl(target))

    def web_action(self):
        if self.confirm_query:
            query = self.confirm_query
            self.web_button.hide()
            self.set_busy(True, 'Looking up public sources…')
            self.notch.run_job('assistant', lambda: assistant.web_lookup(query), self.show_result, self.failed)
        elif self.web_query:
            QDesktopServices.openUrl(QUrl('https://duckduckgo.com/?q=' + quote_plus(self.web_query)))

    def listen(self):
        if self.busy:
            return
        self.set_busy(True, 'Listening once… speak now. Text will appear for review.')
        def done(text):
            self.set_busy(False, 'Review your words, then press Send.' if text else 'No speech heard. Try again.')
            self.input.setText(text)
            self.input.setFocus()
        self.notch.run_job('speech-input', assistant.listen, done, self.failed)
