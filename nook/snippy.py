"""Snippy's compact desktop conversation and fullscreen workspace."""
import html
import math
import re
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QRectF, QPoint, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QLinearGradient, QRadialGradient, QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QPushButton, QLabel, QLineEdit, QVBoxLayout,
    QHBoxLayout, QFrame, QTextBrowser, QListWidget, QApplication, QComboBox, QMessageBox)
from . import local_ai


def plain(text):
    """Readable plain text for the small bubble from a Markdown reply."""
    text = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'\1', text)
    text = re.sub(r'(\*\*|__|`)', '', text)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.M)
    return re.sub(r'^\s*[-*]\s+', '• ', text, flags=re.M)


def greeting(name, now, index):
    minutes = now.hour * 60 + now.minute
    if 360 <= minutes <= 720:
        timely = 'Good morning'
    elif 721 <= minutes <= 960:
        timely = 'Good afternoon'
    elif 961 <= minutes <= 1080:
        timely = 'Good evening'
    else:
        timely = 'Working late at night?'
    if not timely.endswith('?'):
        timely += (' ' + name if name else '')
    choices = [timely, "What's up " + name + '?' if name else "What's up?",
               'What are we working on today?', 'What do you need help with?', 'Sup G?']
    return choices[index % len(choices)]


class CloudFace(QPushButton):
    def __init__(self, owner, size=54):
        super().__init__()
        self.owner = owner
        self.sleeping = False
        self.phase = 0.0
        self.setFixedSize(size, round(size*.78))
        self.setAccessibleName('Snippy')
        self.setToolTip('Talk to Snippy')
        self.setCursor(Qt.PointingHandCursor)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)

    def animate(self):
        self.phase += .13
        self.update()

    def showEvent(self, event):
        if self.owner.store.settings['animation']:
            self.timer.start(1000 if self.sleeping else 100)

    def hideEvent(self, event):
        self.timer.stop()

    def set_sleeping(self, sleeping):
        self.sleeping = sleeping
        self.timer.stop()
        if self.isVisible() and self.owner.store.settings['animation']:
            self.timer.start(1000 if sleeping else 100)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(self.width()/100, self.height()/78)
        music = not self.sleeping and self.owner.media_state.get('playing', False)
        painter.translate(0, math.sin(self.phase * (2.5 if music else 1))*(0.5 if self.sleeping else 3 if music else 1.7))
        if music:
            painter.translate(50, 40)
            painter.rotate(math.sin(self.phase*2.5)*5)
            painter.translate(-50, -40)
        painter.setPen(Qt.NoPen)
        gradient = QLinearGradient(0, 12, 0, 72)
        gradient.setColorAt(0, QColor('#ffffff'))
        gradient.setColorAt(1, QColor('#e6eefc'))
        painter.setBrush(gradient)
        path = QPainterPath()
        for rect in [QRectF(5, 34, 42, 38), QRectF(26, 12, 45, 50),
                     QRectF(54, 27, 39, 40), QRectF(33, 39, 43, 37)]:
            cloud = QPainterPath()
            cloud.addEllipse(rect)
            path = path.united(cloud)
        painter.drawPath(path)
        painter.setPen(QPen(QColor('#293e6b'), 3.3, Qt.SolidLine, Qt.RoundCap))
        for x in (39, 64):
            eye = QPainterPath()
            eye.moveTo(x-5, 46)
            eye.quadTo(x, 50 if self.sleeping else 38, x+5, 46)
            painter.drawPath(eye)
        mouth = QPainterPath()
        mouth.moveTo(48, 52)
        mouth.quadTo(52, 56, 57, 51)
        painter.drawPath(mouth)
        if self.sleeping:
            painter.drawText(QRectF(73, 0, 25, 25), Qt.AlignCenter, 'z')


class Snippy(QWidget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.busy = False
        self.sleeping = False
        self.step = 0
        self.model_prepared = False
        self.drag_start = None
        self.drag_offset = None
        self.dragged = False
        self.alerts = []
        self.pending_alerts = []
        self.showing_notifications = False
        self.setWindowTitle('Snippy')
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(220)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 0, 4, 4)
        root.setSpacing(5)
        self.face = CloudFace(owner)
        self.face.clicked.connect(self.toggle_input)
        self.face.installEventFilter(self)
        self.face.setToolTip('Click to type · drag to any display')
        root.addWidget(self.face, 0, Qt.AlignHCenter)
        self.input = QLineEdit()
        self.input.setMaxLength(4000)
        self.input.setPlaceholderText('Ask Snippy…')
        self.input.setAccessibleName('Quick message to Snippy')
        self.input.setStyleSheet('color: #243b58; background: white; border: 1px solid #e2e6ee; border-radius: 10px; padding: 5px 9px; font-size: 11px;')
        self.input.setFixedHeight(29)
        self.input.returnPressed.connect(lambda: self.submit(self.input.text()))
        self.composer = QWidget()
        row = QHBoxLayout(self.composer)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        row.addWidget(self.input, 1)
        root.addWidget(self.composer)
        self.bubble = QFrame()
        self.bubble.setStyleSheet('QFrame { background: white; border-radius: 12px; } QLabel { color: #243b58; font-size: 12px; background: transparent; } QPushButton { color: #385473; background: #edf2f8; border: 0; padding: 5px; }')
        bubble = QVBoxLayout(self.bubble)
        self.reply = QLabel()
        self.reply.setTextFormat(Qt.PlainText)
        self.reply.setWordWrap(True)
        bubble.addWidget(self.reply)
        self.details = QPushButton('Open conversation')
        self.details.clicked.connect(self.open_details)
        bubble.addWidget(self.details)
        self.details.hide()
        root.addWidget(self.bubble)
        self.apply_button = QPushButton('Review file')
        self.apply_button.clicked.connect(self.review_proposal)
        bubble.addWidget(self.apply_button)
        self.apply_button.hide()
        self.expand_button = QPushButton('↗')
        self.expand_button.setAccessibleName('Expand Snippy')
        self.expand_button.setToolTip('Open full conversation')
        self.expand_button.setFixedSize(28, 29)
        self.expand_button.setStyleSheet('color: #344d70; background: white; border: 0; border-radius: 8px; padding: 3px; font-size: 10px;')
        self.expand_button.clicked.connect(self.open_fullscreen)
        row.addWidget(self.expand_button)
        self.input.hide()
        self.bubble.hide()
        self.expand_button.hide()
        self.composer.hide()
        self.approve_row = QWidget()
        approve_row = QHBoxLayout(self.approve_row)
        approve_row.setContentsMargins(0, 0, 0, 0)
        self.decline_button = QPushButton('Not now')
        self.decline_button.clicked.connect(lambda: self.answer_approval(False))
        approve_row.addWidget(self.decline_button)
        self.approve_button = QPushButton('Approve')
        self.approve_button.setStyleSheet('color: white; background: #1f4f8f; border: 0; padding: 5px; border-radius: 6px;')
        self.approve_button.clicked.connect(lambda: self.answer_approval(True))
        approve_row.addWidget(self.approve_button)
        bubble.addWidget(self.approve_row)
        self.approve_row.hide()
        self.approval_request = None
        from .workspace import FullscreenChat
        self.workspace = FullscreenChat(self)
        owner.approvals.changed.connect(self.show_approval)
        self.motion = QPropertyAnimation(self, b'pos', self)
        self.motion.setDuration(1600)
        self.motion.setEasingCurve(QEasingCurve.InOutSine)
        self.roam_timer = QTimer(self)
        self.roam_timer.setInterval(2200)
        self.roam_timer.timeout.connect(self.roam)
        self.idle_timer = QTimer(self)
        self.idle_timer.setSingleShot(True)
        self.idle_timer.setInterval(60000)
        self.idle_timer.timeout.connect(self.sleep)
        engine = self.owner.assistant_panel
        engine.activity.connect(self.activity)
        engine.submitted.connect(self.sent)
        engine.response_ready.connect(self.receive)
        engine.voice_ready.connect(self.voice_text)
        engine.partial.connect(self.streaming)
        engine.progress.connect(self.progress)
        self.input.textEdited.connect(self.wake)
        self.workspace.input.textEdited.connect(self.wake)
        self.workspace.name_input.textEdited.connect(self.wake)
        self.idle_timer.start()
        self.refresh_size()
        from .voice import PushToTalk
        self.voice = PushToTalk(self)
        self.voice.text_ready.connect(self.send_voice)
        self.voice.review.connect(self.review_voice)
        self.reply_dismissed = False
        self.voice.status.connect(self.voice_status)
        self.voice.configure(owner.store.settings.get('voice_hotkey', False))

    def review_proposal(self):
        proposal = self.owner.assistant_panel.pending_proposal
        mcp = self.owner.assistant_panel.pending_mcp
        if mcp:
            import json
            text = 'Run this app action?\n\n' + json.dumps(mcp, indent=2)[:6000]
        elif proposal:
            text = 'Create this new file?\n' + proposal['path'] + '\n\n' + proposal['content'][:5000]
        else:
            return
        if QMessageBox.question(self, 'Review action', text) == QMessageBox.Yes:
            self.owner.assistant_panel.apply_proposal()

    def voice_status(self, text):
        self.wake()
        self.reply.setText(text)
        self.bubble.show()
        self.show_input(True)
        self.refresh_size()

    def review_voice(self, text):
        self.wake()
        self.show_input(True)
        self.input.setText(text)
        self.input.setFocus()
        self.refresh_size()

    def send_voice(self, text):
        if text and not self.busy:
            self.owner.assistant_panel.voice_reply = True
            self.submit(text)

    def show_input(self, visible):
        self.composer.setVisible(visible)
        self.input.setVisible(visible)
        self.expand_button.setVisible(visible)

    def eventFilter(self, watched, event):
        if watched is self.face:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self.motion.stop()
                self.drag_start = event.globalPosition().toPoint()
                self.drag_offset = self.drag_start - self.pos()
                self.dragged = False
            elif event.type() == QEvent.MouseMove and self.drag_start is not None:
                point = event.globalPosition().toPoint()
                if (point-self.drag_start).manhattanLength() >= QApplication.startDragDistance():
                    self.dragged = True
                if self.dragged:
                    self.move(point-self.drag_offset)
                    return True
            elif event.type() == QEvent.MouseButtonRelease and self.drag_start is not None:
                self.drag_start = None
                if self.dragged:
                    self.face.setDown(False)
                    self.owner.store.settings['snippy_position'] = [self.x(), self.y()]
                    self.owner.store.save()
                    self.follow(force=True)
                    self.wake()
                    return True
        return super().eventFilter(watched, event)

    def refresh_size(self):
        expanded = any(not widget.isHidden() for widget in (self.input, self.bubble, self.expand_button))
        self.setFixedWidth(220 if expanded else 62)
        self.layout().activate()
        self.adjustSize()

    def onboard(self):
        from .onboarding import Onboarding
        if not hasattr(self, 'setup') or not self.setup.isVisible():
            self.setup = Onboarding(self.owner)
        self.setup.show()
        self.setup.raise_()

    def wake(self):
        self.sleeping = False
        self.face.set_sleeping(False)
        self.workspace.face.set_sleeping(False)
        self.idle_timer.start()

    def sync_preferences(self):
        self.model_prepared = False
        self.face.set_sleeping(self.sleeping)
        self.workspace.face.set_sleeping(self.sleeping)
        self.voice.configure(self.owner.store.settings.get('voice_hotkey', False))
        if not self.owner.store.settings['animation']:
            self.roam_timer.stop()
            self.motion.stop()

    def sleep(self):
        if self.busy or self.voice.running:
            self.idle_timer.start()
            return
        self.sleeping = True
        self.model_prepared = False
        self.show_input(False)
        self.bubble.hide()
        self.expand_button.hide()
        self.face.set_sleeping(True)
        self.workspace.face.set_sleeping(True)
        self.roam_timer.stop()
        self.motion.stop()
        self.refresh_size()
        self.follow()
        from . import speech
        speech.unload()
        self.owner.run_job('snippy-sleep', local_ai.stop, lambda _: None)

    def toggle_input(self):
        if not self.owner.store.settings.get('user_name'):
            self.onboard()
            return
        dismiss = not self.bubble.isHidden()
        self.reply_dismissed = True
        self.bubble.hide()
        self.showing_notifications = False
        visible = self.input.isVisible() and not dismiss
        self.wake()
        self.show_input(not visible)
        self.refresh_size()
        self.follow()
        if not visible:
            self.activateWindow()
            self.input.setFocus()
            self.prepare_model()

    def prepare_model(self):
        if self.model_prepared or 'snippy-prepare' in self.owner.jobs:
            return
        from . import assistant, brain
        if brain.available(self.owner.store):
            return  # Claude needs no local warm-up.
        self.model_prepared = True
        if not self.busy:
            self.workspace.status.setText('Preparing local AI…')
        settings = dict(self.owner.store.settings)
        def ready(_):
            if not self.busy and not self.sleeping:
                self.workspace.status.setText('Local AI ready')
        def failed(_):
            self.model_prepared = False
            if not self.busy:
                self.workspace.status.setText('Local AI will retry when you send a message.')
        self.owner.run_job('snippy-prepare', lambda: assistant.prepare_model(settings), ready, failed)

    def submit(self, text):
        text = text.strip()
        if not text or self.busy:
            return
        self.wake()
        self.input.clear()
        self.owner.assistant_panel.input.setText(text)
        self.owner.assistant_panel.send()
        self.workspace.input.clear()

    def activity(self, busy):
        self.busy = busy
        self.workspace.send_button.setEnabled(not busy)
        self.workspace.voice.setEnabled(not busy)
        self.workspace.status.setText('Snippy is working…' if busy else '')
        if busy:
            self.reply_dismissed = False
            self.idle_timer.stop()
            self.bubble.hide()
            self.show_input(True)
            self.input.setEnabled(False)
            self.input.clearFocus()
            self.refresh_size()
            if self.owner.store.settings['animation'] and not self.workspace.isVisible():
                self.roam_timer.start()
                self.roam()
        else:
            self.input.setEnabled(True)
            self.roam_timer.stop()
            self.motion.stop()
            self.idle_timer.start()
            self.follow()
            if self.pending_alerts:
                QTimer.singleShot(250, self.show_pending_alerts)

    def sent(self, text):
        self.reply_dismissed = False
        self.workspace.results.clear()
        self.workspace.web.hide()
        self.workspace.add_user_message(text)

    def streaming(self, text):
        if not self.busy or self.reply_dismissed:
            return
        self.workspace.stream(text)
        self.workspace.status.setText('Replying…')
        if self.approval_request:
            return
        self.reply.setText(text[-320:])
        self.bubble.show()
        self.apply_button.hide()
        self.refresh_size()

    def progress(self, text):
        self.workspace.status.setText(text)
        if self.busy and not self.reply_dismissed and not self.approval_request:
            self.reply.setText(text)
            self.bubble.show()
            self.refresh_size()

    def show_approval(self):
        request = self.owner.approvals.current()
        self.approval_request = request
        if not request:
            self.approve_row.hide()
            if not self.busy:
                self.bubble.hide()
            self.refresh_size()
            return
        if self.workspace.isVisible():
            return  # The full-screen approval card handles it.
        self.wake()
        self.reply.setText(request['title'] + '\n\n' + request['detail'][:420])
        labels = {'email': 'Send', 'file': 'Create', 'whatsapp': 'Send', 'whatsapp-draft': 'Send reply'}
        self.approve_button.setText(labels.get(request['kind'], 'Approve'))
        self.decline_button.setText('Skip' if request['kind'] == 'whatsapp-draft' else 'Not now')
        self.details.setText('Review or edit in full screen')
        self.details.show()
        self.approve_row.show()
        self.bubble.show()
        self.show_input(True)
        self.refresh_size()
        self.follow()

    def answer_approval(self, approved):
        request = self.approval_request
        if request:
            self.approve_row.hide()
            self.details.hide()
            self.owner.approvals.answer(request, approved)

    def announce(self, text):
        """Short background updates (WhatsApp autopilot etc.). Never enters chat history."""
        if self.busy or self.approval_request or self.workspace.isVisible():
            return
        self.wake()
        self.reply.setText(text[:320])
        self.details.hide()
        self.apply_button.hide()
        self.bubble.show()
        self.refresh_size()
        self.follow()

    def receive(self, result):
        self.showing_notifications = False
        self.details.setText('Open conversation')
        self.details.hide()
        text = plain(result['text'])
        self.reply.setText(text[:320] + ('…' if len(text) > 320 else ''))
        self.bubble.setVisible(not self.reply_dismissed or bool(self.approval_request))
        self.show_input(True)
        proposed = bool(result.get('proposal') or result.get('mcp_proposal'))
        self.apply_button.setText('Review app action' if result.get('mcp_proposal') else 'Review file')
        self.apply_button.setVisible(proposed)
        self.workspace.apply_button.setVisible(proposed)
        self.workspace.apply_button.setText(self.owner.assistant_panel.apply_button.text())
        self.refresh_size()
        self.follow()
        self.workspace.error = result['text'] if result.get('error') else ''
        self.workspace.refresh_transcript()
        self.workspace.results.clear()
        source = self.owner.assistant_panel.results
        for index in range(source.count()):
            self.workspace.results.addItem(source.item(index).clone())
        self.workspace.results.setVisible(source.count() > 0)
        self.workspace.web.setVisible(bool(result.get('confirm_web') or result.get('web_query')))
        self.workspace.web.setText(self.owner.assistant_panel.web_button.text())
        self.workspace.refresh_library()

    def voice_text(self, text):
        if not self.busy and text:
            self.workspace.input.setText(text)
            self.workspace.input.setFocus()
        elif not text:
            self.workspace.status.setText('No speech heard. Try again.')

    def open_details(self):
        notifications = self.showing_notifications
        self.open_fullscreen()
        if notifications:
            self.workspace.inbox.show()

    def clear_notifications(self):
        self.alerts.clear()
        self.pending_alerts.clear()
        self.workspace.inbox.clear()
        self.workspace.inbox.hide()
        self.workspace.inbox_button.setText('Notifications')
        if self.showing_notifications:
            self.bubble.hide()
            self.showing_notifications = False
            self.refresh_size()

    def notify(self, rows):
        # Toast content is displayed locally; it never enters assistant history/model input.
        preview = self.owner.store.settings.get('notifications_preview', False)
        display = [dict(row, title=row['title'] if preview else '', body=row['body'] if preview else '') for row in rows]
        self.alerts = (self.alerts + display)[-20:]
        self.pending_alerts = (self.pending_alerts + display)[-20:]
        self.workspace.inbox.clear()
        for row in reversed(self.alerts):
            self.workspace.inbox.addItem(row['app'] + ('\n' + row['title'] + '\n' + row['body'] if preview else '\nNew notification'))
        self.workspace.inbox_button.setText('Notifications (%s)' % len(self.alerts))
        if not self.busy:
            self.show_pending_alerts()

    def show_pending_alerts(self):
        if self.busy or not self.pending_alerts:
            return
        rows, self.pending_alerts = self.pending_alerts, []
        if self.workspace.isVisible():
            self.workspace.inbox.show()
            return
        names = ', '.join(dict.fromkeys(row['app'] for row in rows))
        message = ('New notification from ' if len(rows) == 1 else '%s new notifications from ' % len(rows)) + names
        if len(rows) == 1 and rows[0]['title']:
            message += '\n' + rows[0]['title'] + '\n' + rows[0]['body']
        self.reply.setText(message[:420])
        self.showing_notifications = True
        self.details.setText('View notifications')
        self.details.show()
        self.bubble.show()
        self.expand_button.hide()
        self.refresh_size()
        self.follow()
        self.wake()  # Animate the mascot only; no Ollama request is made.

    def open_fullscreen(self):
        self.wake()
        self.motion.stop()
        self.roam_timer.stop()
        self.workspace.prepare()
        self.workspace.setScreen(self.screen())
        self.hide()
        self.workspace.showFullScreen()
        self.workspace.activateWindow()
        if self.owner.store.settings.get('user_name'):
            self.workspace.input.setFocus()
            self.prepare_model()
        else:
            self.workspace.name_input.setFocus()

    def follow(self, force=False):
        if (self.busy and not force) or self.drag_start is not None:
            return
        saved = self.owner.store.settings.get('snippy_position')
        if saved:
            point = QPoint(*saved)
            screen = QApplication.screenAt(point) or self.owner.screen()
            x, y = saved
        else:
            screen = self.owner.screen()
            x = self.owner.geometry().right()+6-(self.width()-self.face.width())//2
            y = screen.availableGeometry().top()+18
        bounds = screen.availableGeometry()
        self.move(max(bounds.left(), min(x, bounds.right()-self.width()+1)),
                  max(bounds.top(), min(y, bounds.bottom()-self.height()+1)))

    def roam(self):
        if self.drag_start is not None or self.input.hasFocus():
            return
        screens = QApplication.screens()
        bounds = screens[self.step % len(screens)].availableGeometry()
        self.step += 1
        fraction = (.68, .36, .78, .52)[self.step % 4]
        target = QPoint(bounds.x()+int((bounds.width()-self.width())*fraction),
                        bounds.y()+int(bounds.height()*(.17 if self.step % 2 else .28)))
        self.motion.stop()
        self.motion.setStartValue(self.pos())
        self.motion.setEndValue(target)
        self.motion.start()

    def closeEvent(self, event):
        self.voice.close()
        self.workspace.hide()
        self.idle_timer.stop()
        self.roam_timer.stop()
        self.motion.stop()
        event.accept()
