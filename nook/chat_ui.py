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
from .conversations import Conversations
from . import cowork


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
    partial = Signal(str)
    progress = Signal(str)
    def __init__(self, notch):
        super().__init__()
        self.notch = notch
        self.history = []
        self.archive = Conversations()
        self.chat_id = None
        self.pending_proposal = None
        self.pending_mcp = None
        self.voice_reply = False
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
        self.apply_button = QPushButton('Create this file')
        self.apply_button.hide()
        self.apply_button.clicked.connect(self.apply_proposal)
        root.addWidget(self.apply_button)
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
        self.history = []
        self.chat_id = None
        self.pending_proposal = None
        self.pending_mcp = None
        self.apply_button.hide()
        self.transcript.clear()
        self.results.clear()
        self.results.hide()
        self.web_button.hide()
        self.web_query = ''
        self.confirm_query = ''
        self.append('Snippy', 'New conversation. Previous chats are in your local chat library.')

    def load_chat(self, identity):
        if self.busy:
            return
        row = next((r for r in self.archive.chats if r['id'] == identity), None)
        if row:
            self.clear_chat()
            self.chat_id = identity
            self.history = self.archive.load(identity)
            self.transcript.clear()
            for message in self.history:
                self.append('You' if message['role'] == 'user' else 'Snippy', message['content'])

    def apply_proposal(self):
        if self.busy or not (self.pending_proposal or self.pending_mcp):
            return
        proposal = self.pending_proposal
        mcp = self.pending_mcp
        self.pending_proposal = None
        self.pending_mcp = None
        self.apply_button.hide()
        self.set_busy(True, 'Creating the reviewed document…')
        def done(result):
            self.history.append({'role': 'assistant', 'content': result['text']})
            self.chat_id = self.archive.save(self.chat_id, self.history)
            self.show_result(result)
        if mcp:
            from . import mcp_client
            self.notch.run_job('assistant', lambda: mcp_client.invoke(self.notch.store, mcp['connection'], mcp['tool'], mcp.get('arguments', {})), done, self.failed)
        else:
            self.notch.run_job('assistant', lambda: cowork.apply(proposal, self.notch.store.settings['search_root']), done, self.failed)

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
        self.pending_proposal = None
        self.pending_mcp = None
        self.apply_button.hide()
        history = list(self.history)
        settings = dict(self.notch.store.settings)
        def done(result):
            if result.get('tasks_changed') is True:
                self.notch.store.save()
                self.notch.build_todos()
                self.notch.desktop.refresh()
            self.history.extend([{'role': 'user', 'content': prompt},
                                 {'role': 'assistant', 'content': result['text']}])
            self.history = self.history[-200:]
            self.chat_id = self.archive.save(self.chat_id, self.history)
            self.show_result(result)
        from . import brain
        cloud = brain.available(self.notch.store)
        try:
            immediate = assistant.instant_response(prompt, settings, cloud)
        except (ValueError, SyntaxError, ZeroDivisionError) as error:
            self.failed(str(error))
            return
        if immediate is not None:
            done(immediate)
            return
        if not cloud:
            self.set_busy(True, 'Working locally…')
            self.notch.run_job('assistant', lambda: assistant.respond(prompt, history, settings, self.partial.emit), done, self.failed)
            return
        self.set_busy(True, 'Thinking…')
        self.notch.run_job('assistant', lambda: self.think(prompt, history, settings), done, self.failed)

    def think(self, prompt, history, settings):
        """Claude first; the bundled local model answers when the internet is unavailable."""
        import anthropic
        try:
            return self.notch.brain.respond(prompt, history, self.partial.emit, self.progress.emit)
        except anthropic.AuthenticationError:
            raise ValueError('Claude rejected the API key. Check it in Settings → Assistant.')
        except anthropic.PermissionDeniedError:
            raise ValueError('This Claude API key cannot use the selected model. Choose another in Settings → Assistant.')
        except anthropic.RateLimitError:
            raise ValueError('Claude is rate-limited right now. Try again in a minute.')
        except anthropic.APIConnectionError:
            self.progress.emit('Offline — answering with local AI…')
            result = assistant.respond(prompt, history, settings, self.partial.emit)
            result['text'] = '(Offline, so this answer comes from the local AI.)\n\n' + result['text']
            return result
        except anthropic.APIStatusError as error:
            raise ValueError('Claude returned an error (%s). Try again shortly.' % error.status_code)

    def show_result(self, result):
        self.set_busy(False)
        self.append('Snippy', result['text'])
        self.pending_proposal = result.get('proposal')
        self.pending_mcp = result.get('mcp_proposal')
        self.apply_button.setText('Run this app action' if self.pending_mcp else 'Create this file')
        self.apply_button.setVisible(bool(self.pending_proposal or self.pending_mcp))
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
        if self.notch.store.settings['speak_replies'] or self.voice_reply:
            self.voice_reply = False
            self.notch.run_job('speech-output', lambda: assistant.speak(result['text']), lambda _: None,
                               lambda message: self.status.setText(message))

    def failed(self, message):
        self.voice_reply = False
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
        from . import speech
        import threading
        settings = dict(self.notch.store.settings)
        self.notch.run_job('speech-input', lambda: speech.listen(threading.Event(), settings, lambda _: None, maximum=10)[0], done, self.failed)
