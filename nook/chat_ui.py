import html
import math
from pathlib import Path
from urllib.parse import quote_plus

from PySide6.QtCore import Qt, QTimer, QRectF, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QDesktopServices
from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QHBoxLayout, QLabel,
                              QLineEdit, QTextBrowser, QListWidget, QListWidgetItem)
from . import assistant
from .snippy import CloudFace


class Companion(CloudFace):
    def __init__(self, owner, callback, size=28):
        super().__init__(owner, size)
        self.busy = False
        self.clicked.connect(callback)


class AssistantPanel(QWidget):
    submitted = Signal(str)
    response_ready = Signal(object)
    activity = Signal(bool)
    voice_ready = Signal(str)
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
        self.status = QLabel('Local AI · Ready')
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
        self.input.setAccessibleName('Message Snippy')
        self.input.setPlaceholderText('Ask Snippy, calculate, or find a file…')
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
        self.append('Snippy', 'Ready when you are. Try “24 * 7”, “find files report” or “look up solar energy”.')

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
        self.web_query = ''
        self.confirm_query = ''
        self.append('Snippy', 'Conversation cleared. Messages stay in memory only.')

    def set_busy(self, value, status='Ready'):
        self.busy = value
        self.avatar.busy = value
        self.status.setText(status)
        self.send_button.setEnabled(not value)
        self.mic.setEnabled(not value)
        self.activity.emit(value)

    def send(self):
        prompt = self.input.text().strip()
        if not prompt or self.busy:
            return
        self.input.clear()
        self.append('You', prompt)
        self.submitted.emit(prompt)
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
        self.append('Snippy', result['text'])
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
        self.response_ready.emit(result)
        if self.notch.store.settings['speak_replies']:
            self.notch.run_job('speech-output', lambda: assistant.speak(result['text']), lambda _: None,
                               lambda message: self.status.setText(message))

    def failed(self, message):
        self.set_busy(False, 'Check the connection in Settings → Assistant')
        self.append('Snippy', message)
        self.response_ready.emit({'text': message, 'error': True})

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
            self.voice_ready.emit(text)
        self.notch.run_job('speech-input', assistant.listen, done, self.failed)
