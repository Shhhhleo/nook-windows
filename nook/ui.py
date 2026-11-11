import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRect, QPropertyAnimation, QEasingCurve, QThreadPool, QUrl
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont, QPixmap, QIcon, QDesktopServices, QCursor, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QTabWidget, QListWidget, QListWidgetItem, QCheckBox,
    QSpinBox, QComboBox, QFormLayout, QFileDialog, QColorDialog, QFontComboBox,
    QSystemTrayIcon, QMenu, QMessageBox, QAbstractItemView, QGridLayout)
from . import services
from .storage import WIDGETS


STYLE = '''
QWidget { color: #f4f4f7; font-family: "Segoe UI"; font-size: 13px; }
QWidget#settings { background: #151518; }
QLabel { background: transparent; }
QLabel#muted { color: #9999a5; }
QLabel#title { font-size: 27px; font-weight: 600; }
QLabel#section { font-size: 15px; font-weight: 600; }
QFrame#card { background: #141417; border: 1px solid #252529; border-radius: 18px; }
QPushButton { background: #25252c; border: 1px solid #36363f; border-radius: 10px; padding: 8px 12px; }
QPushButton:hover { background: #393943; }
QPushButton:focus { border: 1px solid #b7b0ff; }
QPushButton:disabled { color: #595963; background: #161619; }
QPushButton#primary { background: #b7b0ff; color: #171324; border: 0; font-weight: 600; }
QLineEdit, QSpinBox, QComboBox, QListWidget { background: #202025; border: 1px solid #373740; border-radius: 8px; padding: 8px; selection-background-color: #555079; }
QLineEdit:focus { border-color: #b7b0ff; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: transparent; width: 7px; }
QScrollBar::handle:vertical { background: #42424a; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QTabWidget::pane { border: 0; }
QTabBar::tab { background: transparent; color: #9797a3; padding: 11px 14px; }
QTabBar::tab:selected { color: #e1dcff; background: #2c293b; border-radius: 8px; }
QCheckBox { spacing: 10px; padding: 5px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #6c6c78; border-radius: 5px; }
QCheckBox::indicator:checked { background: #b7b0ff; border-color: #b7b0ff; }
QToolTip { background: #282830; color: white; border: 1px solid #555; }
'''


def label(text, name='', wrap=False):
    result = QLabel(text)
    result.setTextFormat(Qt.PlainText)
    result.setObjectName(name)
    result.setWordWrap(wrap)
    return result


def button(text, callback, tip='', primary=False):
    result = QPushButton(text)
    result.clicked.connect(callback)
    result.setCursor(Qt.PointingHandCursor)
    result.setToolTip(tip or text)
    result.setAccessibleName(tip or text)
    if primary:
        result.setObjectName('primary')
    return result


def clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())


def open_url(url):
    if QUrl(url).scheme() in ('https', 'http', 'spotify', 'whatsapp', 'zoommtg'):
        QDesktopServices.openUrl(QUrl(url))


class Settings(QWidget):
    def __init__(self, notch):
        super().__init__()
        self.notch = notch
        self.store = notch.store
        self.setWindowTitle('Nook · Settings')
        self.setObjectName('settings')
        self.resize(760, 680)
        self.setMinimumSize(640, 500)
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 25, 30, 25)
        head = QHBoxLayout()
        head.addWidget(label('Make room for your day.', 'title'))
        head.addStretch()
        head.addWidget(label('NOOK', 'muted'))
        root.addLayout(head)
        root.addWidget(label('Your notch. Your essentials.', 'muted'))
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.fields = {}
        self.widget_page()
        self.appearance_page()
        self.connections_page()
        self.general_page()
        self.status = label('', 'muted', True)
        root.addWidget(self.status)
        footer = QHBoxLayout()
        footer.addWidget(button('Preview notch', lambda: notch.expand(True)))
        footer.addStretch()
        footer.addWidget(button('Save settings', self.save, primary=True))
        root.addLayout(footer)

    def page(self, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        widget.setStyleSheet('background: #151518;')
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 20, 12, 20)
        scroll.setWidget(widget)
        self.tabs.addTab(scroll, title)
        return layout

    def widget_page(self):
        layout = self.page('Widgets')
        layout.addWidget(label('Choose what lives in your notch', 'section'))
        layout.addWidget(label('Tick to enable. Drag to reorder.', 'muted'))
        self.widget_list = QListWidget()
        self.widget_list.setMinimumHeight(405)
        self.widget_list.setDragDropMode(QAbstractItemView.InternalMove)
        for name in self.store.settings['order']:
            if name not in WIDGETS:
                continue
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name in self.store.settings['enabled'] else Qt.Unchecked)
            self.widget_list.addItem(item)
        layout.addWidget(self.widget_list)
        layout.addWidget(label('Account widgets show connection guidance until configured.', 'muted'))

    def field(self, form, key, title, kind='text', choices=None, limits=None, secret=False):
        value = self.store.secret(key) if secret else self.store.settings.get(key, '')
        if kind == 'check':
            control = QCheckBox()
            control.setChecked(bool(value))
        elif kind == 'spin':
            control = QSpinBox()
            control.setRange(*limits)
            control.setValue(int(value))
        elif kind == 'combo':
            control = QComboBox()
            control.addItems(choices)
            control.setCurrentText(str(value))
        elif kind == 'font':
            control = QFontComboBox()
            control.setCurrentFont(QFont(value))
        else:
            control = QLineEdit(str(value))
            if secret:
                control.setEchoMode(QLineEdit.Password)
        control.setAccessibleName(title)
        form.addRow(title, control)
        self.fields[key] = (control, kind, secret)
        return control

    def appearance_page(self):
        layout = self.page('Appearance')
        form = QFormLayout()
        form.setVerticalSpacing(16)
        self.field(form, 'width', 'Expanded width', 'spin', limits=(460, 1100))
        self.field(form, 'compact_width', 'Collapsed width', 'spin', limits=(200, 450))
        self.field(form, 'height', 'Expanded height', 'spin', limits=(300, 850))
        self.field(form, 'radius', 'Corner radius', 'spin', limits=(8, 48))
        self.field(form, 'opacity', 'Opacity (%)', 'spin', limits=(65, 100))
        self.field(form, 'font', 'Clock font', 'font')
        self.field(form, 'clock_style', 'Clock layout', 'combo', choices=['Minimal', 'Large', 'Editorial'])
        self.field(form, 'weather_style', 'Weather layout', 'combo', choices=['Detailed', 'Compact'])
        self.field(form, 'hour24', '24-hour clock', 'check')
        self.field(form, 'seconds', 'Show seconds', 'check')
        self.field(form, 'animation', 'Animate expansion', 'check')
        accent = self.field(form, 'accent', 'Accent colour')
        form.addRow('', button('Choose colour', lambda: self.choose_color(accent)))
        layout.addLayout(form)
        layout.addStretch()

    def choose_color(self, field):
        color = QColorDialog.getColor(QColor(field.text()), self)
        if color.isValid():
            field.setText(color.name())

    def connections_page(self):
        layout = self.page('Connections')
        form = QFormLayout()
        form.setVerticalSpacing(13)
        self.field(form, 'city', 'Weather city')
        self.field(form, 'fahrenheit', 'Fahrenheit', 'check')
        self.field(form, 'notion_token', 'Notion integration token', secret=True)
        self.field(form, 'finnhub_token', 'Finnhub API key', secret=True)
        self.field(form, 'symbols', 'Stock symbols (up to 8)')
        self.field(form, 'google_client_id', 'Google Desktop client ID')
        self.field(form, 'google_client_secret', 'Google client secret', secret=True)
        layout.addLayout(form)
        layout.addWidget(label('Notion shows pages shared with your integration. Google requires a Desktop OAuth client with the Calendar API enabled.', 'muted', True))
        actions = QHBoxLayout()
        actions.addWidget(button('Connect Google Calendar', self.connect_google))
        actions.addWidget(button('Disconnect Google', self.disconnect_google))
        layout.addLayout(actions)
        layout.addWidget(label('Academia deadlines', 'section'))
        layout.addWidget(label('Sign in on Academia in your browser. Automatic deadline sync requires an API from Academia. You can import a JSON deadline export here.', 'muted', True))
        row = QHBoxLayout()
        row.addWidget(button('Open Academia', lambda: open_url('https://academia-ib.vercel.app/dashboard')))
        row.addWidget(button('Import deadlines', self.import_deadlines))
        layout.addLayout(row)
        layout.addWidget(label('Usage limits and calls', 'section'))
        layout.addWidget(label('Claude and Codex provide shortcuts to their account usage pages. Subscription limit telemetry is not connected. Calls open WhatsApp, Zoom or Instagram; in-call controls require provider support.', 'muted', True))
        layout.addStretch()

    def general_page(self):
        layout = self.page('Behaviour')
        form = QFormLayout()
        self.screen_combo = QComboBox()
        for screen in QApplication.screens():
            self.screen_combo.addItem(screen.name())
        self.screen_combo.setCurrentIndex(min(self.store.settings['screen'], self.screen_combo.count() - 1))
        form.addRow('Display', self.screen_combo)
        self.field(form, 'collapse_ms', 'Collapse delay (ms)', 'spin', limits=(150, 3000))
        root = self.field(form, 'search_root', 'File search folder')
        form.addRow('', button('Choose search folder', lambda: self.choose_folder(root)))
        layout.addLayout(form)
        layout.addWidget(label('Search scans filenames on demand, stops after 8 seconds or 50 results, and skips dependency and system folders. Choose a narrower folder for deeper results.', 'muted', True))
        layout.addWidget(label('Right-click the notch or use the tray icon for Settings and Quit. Escape collapses the notch. Pin keeps it open. Closing Settings leaves the notch running.', 'muted', True))
        layout.addWidget(label('Account credentials are encrypted for your Windows user. Settings and tasks are saved locally in %LOCALAPPDATA%\\Nook.', 'muted', True))
        layout.addStretch()

    def choose_folder(self, field):
        folder = QFileDialog.getExistingDirectory(self, 'Choose file search folder', field.text())
        if folder:
            field.setText(folder)

    def save(self):
        if not QColor(self.fields['accent'][0].text()).isValid():
            self.status.setText('Enter a valid accent colour, such as #b7b0ff.')
            return False
        if not Path(self.fields['search_root'][0].text()).is_dir():
            self.status.setText('Choose an existing search folder.')
            return False
        for key, (control, kind, secret) in self.fields.items():
            if kind == 'check':
                value = control.isChecked()
            elif kind == 'spin':
                value = control.value()
            elif kind == 'font':
                value = control.currentFont().family()
            elif kind == 'combo':
                value = control.currentText()
            else:
                value = control.text().strip()
            if secret:
                self.store.secret(key, value)
            else:
                self.store.settings[key] = value
        items = [self.widget_list.item(i) for i in range(self.widget_list.count())]
        self.store.settings['order'] = [item.text() for item in items]
        self.store.settings['enabled'] = [item.text() for item in items if item.checkState() == Qt.Checked]
        self.store.settings['screen'] = self.screen_combo.currentIndex()
        self.store.save()
        self.notch.rebuild()
        self.status.setText('Saved. Changes are live.')
        return True

    def connect_google(self):
        if self.save():
            self.status.setText('Complete Google sign-in in your browser. Waiting up to 3 minutes…')
            self.notch.run_job('google-auth', lambda: services.google_connect(self.store), self.status.setText, self.status.setText)

    def disconnect_google(self):
        self.store.secret('google_tokens', '')
        self.status.setText('Google credentials removed from this device.')
        self.notch.rebuild()

    def import_deadlines(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import deadlines', '', 'JSON (*.json)')
        if not path:
            return
        try:
            rows = json.loads(Path(path).read_text('utf-8'))
            if not isinstance(rows, list) or len(rows) > 500:
                raise ValueError('Expected an array of up to 500 deadlines.')
            for row in rows:
                if not isinstance(row.get('title'), str) or not isinstance(row.get('due'), str):
                    raise ValueError('Each deadline needs title and due strings.')
                datetime.fromisoformat(row['due'].replace('Z', '+00:00'))
            self.store.settings['deadlines'] = rows
            self.store.save()
            self.notch.rebuild()
            self.status.setText('Imported %s deadlines. These are local snapshots.' % len(rows))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            self.status.setText('Import failed. ' + str(error))


class Notch(QWidget):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.expanded = False
        self.pinned = False
        self.settings_window = None
        self.jobs = {}
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(4)
        self.generation = 0
        self.search_cancel = threading.Event()
        self.media_state = {}
        self.preferred_player = ''
        self.setWindowTitle('Nook')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.animation = QPropertyAnimation(self, b'geometry', self)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.setDuration(190)
        self.animation.finished.connect(self.animation_finished)
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.timeout.connect(self.maybe_collapse)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.search)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(18, 0, 18, 14)
        self.root.setSpacing(8)
        self.header = QWidget()
        self.header.setFixedHeight(38)
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        self.compact = label('●  Nook')
        header.addWidget(self.compact, 1)
        self.clock = label('')
        header.addWidget(self.clock)
        self.root.addWidget(self.header)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        self.root.addWidget(self.body, 1)
        self.body.hide()
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.media_timer = QTimer(self)
        self.media_timer.timeout.connect(self.refresh_media)
        self.media_timer.start(5000)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_widgets)
        self.refresh_timer.start(300000)
        self.task_timer = QTimer(self)
        self.task_timer.timeout.connect(self.refresh_tasks)
        self.task_timer.start(15000)
        self.menu = QMenu()
        self.menu.addAction('Expand', lambda: self.expand(True))
        self.menu.addAction('Settings', self.open_settings)
        self.menu.addSeparator()
        self.menu.addAction('Quit Nook', QApplication.quit)
        icon = QPixmap(64, 64)
        icon.fill(Qt.transparent)
        painter = QPainter(icon)
        painter.setBrush(QColor('#b7b0ff'))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(5, 9, 54, 38, 12, 12)
        painter.setPen(QColor('#141217'))
        painter.setFont(QFont('Segoe UI', 23, QFont.Bold))
        painter.drawText(icon.rect(), Qt.AlignCenter, 'n')
        painter.end()
        self.setWindowIcon(QIcon(icon))
        self.tray = QSystemTrayIcon(QIcon(icon), self)
        self.tray.setToolTip('Nook · Your desktop essentials')
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason: self.open_settings() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()
        QShortcut(QKeySequence('Escape'), self, activated=lambda: self.expand(False))
        for screen in QApplication.screens():
            screen.geometryChanged.connect(self.reposition)
        QApplication.instance().screenAdded.connect(lambda *_: self.reposition())
        QApplication.instance().screenRemoved.connect(lambda *_: self.reposition())
        self.rebuild()

    def run_job(self, key, work, done, failed=None):
        if key in self.jobs:
            return
        job = services.Job(work)
        self.jobs[key] = job
        def finish(value, error=False):
            self.jobs.pop(key, None)
            if error:
                (failed or self.message.setText)(value)
            else:
                done(value)
        job.signals.done.connect(lambda value: finish(value))
        job.signals.failed.connect(lambda value: finish(value, True))
        self.pool.start(job)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.store.settings['radius']
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(self.width(), 0)
        path.lineTo(self.width(), self.height() - r)
        path.quadTo(self.width(), self.height(), self.width() - r, self.height())
        path.lineTo(r, self.height())
        path.quadTo(0, self.height(), 0, self.height() - r)
        path.closeSubpath()
        painter.fillPath(path, QColor(3, 3, 5, int(255 * self.store.settings['opacity'] / 100)))

    def target_geometry(self):
        screens = QApplication.screens()
        screen = screens[min(max(0, self.store.settings['screen']), len(screens) - 1)]
        bounds = screen.geometry()
        width = min(self.store.settings['width' if self.expanded else 'compact_width'], bounds.width() - 20)
        height = min(self.store.settings['height'], bounds.height() - 40) if self.expanded else 38
        return QRect(bounds.x() + (bounds.width() - width) // 2, bounds.y(), width, height)

    def reposition(self, *_):
        self.animation.stop()
        self.setGeometry(self.target_geometry())

    def expand(self, expanded):
        self.collapse_timer.stop()
        if not expanded:
            self.pinned = False
            self.pin.setText('Pin')
        if self.expanded == expanded:
            return
        self.expanded = expanded
        self.body.hide()
        self.animation.stop()
        if self.store.settings['animation']:
            self.animation.setStartValue(self.geometry())
            self.animation.setEndValue(self.target_geometry())
            self.animation.start()
        else:
            self.reposition()
            self.animation_finished()
        self.update_clock()

    def animation_finished(self):
        self.body.setVisible(self.expanded)
        if self.expanded:
            self.refresh_media()
            self.refresh_tasks()

    def enterEvent(self, event):
        self.expand(True)

    def leaveEvent(self, event):
        self.collapse_timer.start(self.store.settings['collapse_ms'])

    def maybe_collapse(self):
        if not self.pinned and not self.geometry().contains(QCursor.pos()) and not self.search_input.hasFocus():
            self.expand(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.menu.exec(event.globalPosition().toPoint())
        elif not self.expanded:
            self.expand(True)

    def open_settings(self):
        if self.settings_window is None:
            self.settings_window = Settings(self)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def toggle_pin(self):
        self.pinned = not self.pinned
        self.pin.setText('Pinned' if self.pinned else 'Pin')

    def card(self, title):
        frame = QFrame()
        frame.setObjectName('card')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 15, 18, 16)
        layout.setSpacing(10)
        layout.addWidget(label(title, 'section'))
        if self.pair_music_time and title in ('Music', 'Time'):
            self.cards.addWidget(frame, 0, 0 if title == 'Music' else 1)
        else:
            self.cards.addWidget(frame, self.card_row, 0, 1, 2)
            self.card_row += 1
        return layout

    def rebuild(self):
        self.generation += 1
        self.search_cancel.set()
        clear(self.body_layout)
        toolbar = QHBoxLayout()
        toolbar.addWidget(label('Your day, within reach.', 'muted'), 1)
        self.pin = button('Pinned' if self.pinned else 'Pin', self.toggle_pin)
        toolbar.addWidget(self.pin)
        toolbar.addWidget(button('Settings', self.open_settings))
        self.body_layout.addLayout(toolbar)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search files on this PC…')
        self.search_input.setAccessibleName('Search files on this PC')
        self.search_input.textChanged.connect(self.queue_search)
        self.body_layout.addWidget(self.search_input)
        self.message = label(self.store.warning, 'muted', True)
        self.body_layout.addWidget(self.message)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        content = QWidget()
        enabled = [n for n in self.store.settings['order'] if n in self.store.settings['enabled']]
        self.pair_music_time = enabled[:2] == ['Music', 'Time'] and self.store.settings['width'] >= 660
        self.card_row = 1 if self.pair_music_time else 0
        self.cards = QGridLayout(content)
        self.cards.setColumnStretch(0, 3)
        self.cards.setColumnStretch(1, 2)
        self.cards.setContentsMargins(0, 0, 5, 0)
        self.cards.setSpacing(10)
        self.scroll.setWidget(content)
        self.body_layout.addWidget(self.scroll, 1)
        self.search_results = QListWidget()
        self.search_results.itemActivated.connect(lambda item: QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.UserRole))))
        self.search_results.hide()
        self.body_layout.addWidget(self.search_results, 1)
        self.widget_labels = {}
        self.link_layouts = {}
        for name in self.store.settings['order']:
            if name not in self.store.settings['enabled']:
                continue
            layout = self.card(name)
            if name == 'Music':
                self.build_music(layout)
            elif name == 'Time':
                self.time_label = label('')
                size = {'Minimal': 26, 'Large': 38, 'Editorial': 30}[self.store.settings['clock_style']]
                self.time_label.setFont(QFont(self.store.settings['font'], size))
                self.time_label.setStyleSheet('font-family: "%s"; font-size: %spx; color: %s;' % (self.store.settings['font'], size, self.store.settings['accent']))
                layout.addWidget(self.time_label)
                self.date_label = label('', 'muted', True)
                layout.addWidget(self.date_label)
                layout.addStretch()
            elif name == 'To do':
                self.todo_layout = layout
                self.build_todos()
            elif name in ('Google Calendar', 'Notion'):
                self.link_layouts[name] = layout
                self.widget_labels[name] = label('Connect in Settings to see your ' + ('events.' if name == 'Google Calendar' else 'pages.'), 'muted', True)
                layout.addWidget(self.widget_labels[name])
            elif name in ('Claude usage', 'Codex usage'):
                layout.addWidget(label('Live subscription limits are not connected.', 'muted'))
                url = 'https://claude.ai/settings/usage' if name == 'Claude usage' else 'https://chatgpt.com/codex/settings/usage'
                layout.addWidget(button('Open usage page', lambda checked=False, u=url: open_url(u)))
            elif name == 'Calls':
                layout.addWidget(label('Open a call app. Call status and in-call controls are not connected.', 'muted', True))
                row = QHBoxLayout()
                for title, url in [('WhatsApp', 'https://web.whatsapp.com/'), ('Zoom', 'https://zoom.us/join'), ('Instagram', 'https://www.instagram.com/direct/inbox/')]:
                    row.addWidget(button(title, lambda checked=False, u=url: open_url(u)))
                layout.addLayout(row)
            elif name == 'Academia':
                rows = self.store.settings['deadlines']
                layout.addWidget(label('Imported snapshot · automatic sync unavailable', 'muted'))
                for row in sorted(rows, key=lambda r: r['due'])[:12]:
                    layout.addWidget(label(row['title'] + '\n' + row['due'], wrap=True))
                if not rows:
                    layout.addWidget(label('Import your deadline export in Settings.', 'muted'))
                layout.addWidget(button('Open my dashboard', lambda: open_url('https://academia-ib.vercel.app/dashboard')))
            else:
                text = {'Weather': 'Set your city in Settings.', 'Stocks': 'Add a Finnhub key in Settings.', 'Running tasks': 'Checking running apps…'}.get(name, '')
                self.widget_labels[name] = label(text, 'muted', True)
                layout.addWidget(self.widget_labels[name])
                if name == 'Running tasks':
                    layout.addWidget(label('Process presence only. Task completion requires an agent integration.', 'muted', True))
        self.cards.setRowStretch(self.card_row, 1)
        self.reposition()
        self.update_clock()
        self.refresh_widgets()
        self.refresh_media()

    def build_music(self, layout):
        row = QHBoxLayout()
        self.artwork = label('♫')
        self.artwork.setFixedSize(70, 70)
        self.artwork.setAlignment(Qt.AlignCenter)
        self.artwork.setStyleSheet('background: #272332; border-radius: 14px; font-size: 32px; color: #b7b0ff;')
        row.addWidget(self.artwork)
        details = QVBoxLayout()
        self.track = label('Nothing playing', 'section', True)
        self.artist = label('Start Spotify or Apple Music', 'muted', True)
        details.addWidget(self.track)
        details.addWidget(self.artist)
        row.addLayout(details, 1)
        self.players = QComboBox()
        self.players.setMaximumWidth(150)
        self.players.setAccessibleName('Media player')
        self.players.activated.connect(lambda: self.choose_player())
        row.addWidget(self.players)
        layout.addLayout(row)
        controls = QHBoxLayout()
        self.media_buttons = {}
        for key, text, tip in [('previous', '⏮', 'Previous track'), ('play', '▶', 'Play or pause'), ('next', '⏭', 'Next track'), ('repeat', 'Repeat off', 'Cycle repeat off, playlist, song')]:
            control = button(text, lambda checked=False, action=key: self.refresh_media(action), tip)
            control.setEnabled(False)
            self.media_buttons[key] = control
            controls.addWidget(control)
        layout.addLayout(controls)
        self.timeline = label('', 'muted')
        layout.addWidget(self.timeline)

    def choose_player(self):
        self.preferred_player = self.players.currentText()
        self.refresh_media()

    def build_todos(self):
        # Preserve the section heading while replacing task controls.
        while self.todo_layout.count() > 1:
            item = self.todo_layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                clear(item.layout())
        for index, task in enumerate(self.store.settings['todos']):
            row = QHBoxLayout()
            check = QCheckBox(task['text'])
            check.setChecked(task.get('done', False))
            check.toggled.connect(lambda value, i=index: self.toggle_todo(i, value))
            row.addWidget(check, 1)
            row.addWidget(button('×', lambda checked=False, i=index: self.remove_todo(i), 'Delete task'))
            self.todo_layout.addLayout(row)
        row = QHBoxLayout()
        self.todo_input = QLineEdit()
        self.todo_input.setPlaceholderText('Add a task…')
        self.todo_input.setAccessibleName('New task')
        self.todo_input.setMaxLength(240)
        self.todo_input.returnPressed.connect(self.add_todo)
        row.addWidget(self.todo_input)
        row.addWidget(button('Add', self.add_todo))
        self.todo_layout.addLayout(row)

    def toggle_todo(self, index, value):
        self.store.settings['todos'][index]['done'] = value
        self.store.save()

    def remove_todo(self, index):
        self.store.settings['todos'].pop(index)
        self.store.save()
        self.build_todos()

    def add_todo(self):
        text = self.todo_input.text().strip()
        if text:
            self.store.settings['todos'].append({'text': text, 'done': False})
            self.store.save()
            self.build_todos()
            self.todo_input.setFocus()

    def update_clock(self):
        now = datetime.now()
        pattern = '%H:%M' if self.store.settings['hour24'] else '%I:%M'
        if self.store.settings['seconds']:
            pattern += ':%S'
        text = now.strftime(pattern)
        if not self.store.settings['hour24']:
            text = text.lstrip('0') + now.strftime(' %p')
        self.clock.setText(text if 'Time' in self.store.settings['enabled'] else '')
        self.compact.setText('Nook' if self.expanded else ('♫  ' + self.media_state.get('title', '')[:18] if self.media_state.get('playing') else '●  Nook'))
        if 'Time' in self.store.settings['enabled']:
            self.time_label.setText(text)
            self.date_label.setText(now.strftime('%A\n%d %B'))

    def refresh_media(self, action=None):
        if 'Music' not in self.store.settings['enabled']:
            return
        generation = self.generation
        def done(state):
            if generation != self.generation:
                return
            self.media_state = state
            self.track.setText(state['title'])
            self.artist.setText(state['artist'])
            self.media_buttons['play'].setText('Ⅱ' if state.get('playing') else '▶')
            self.media_buttons['repeat'].setText({0: 'Repeat off', 1: 'Repeat song', 2: 'Repeat playlist'}.get(state.get('repeat'), 'Repeat off'))
            for key, control in self.media_buttons.items():
                control.setEnabled(state.get('can_' + key, False))
            self.players.blockSignals(True)
            self.players.clear()
            self.players.addItems(state.get('sessions', []))
            self.players.setCurrentText(state.get('source', ''))
            self.players.blockSignals(False)
            self.players.setVisible(len(state.get('sessions', [])) > 1)
            if state.get('artwork'):
                pixmap = QPixmap()
                pixmap.loadFromData(bytes(state['artwork']))
                self.artwork.setPixmap(pixmap.scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            else:
                self.artwork.setPixmap(QPixmap())
                self.artwork.setText('♫')
            position, duration = int(state.get('position', 0)), int(state.get('duration', 0))
            self.timeline.setText('%d:%02d / %d:%02d' % (position // 60, position % 60, duration // 60, duration % 60) if duration else '')
            self.update_clock()
        def failed(message):
            if generation == self.generation:
                self.artist.setText(message)
        self.run_job('media', lambda: services.media(action, self.preferred_player), done, failed)

    def refresh_widgets(self):
        s = self.store.settings
        jobs = {}
        if s['city']:
            jobs['Weather'] = lambda: services.weather(s['city'], s['fahrenheit'])
        if self.store.secret('notion_token'):
            jobs['Notion'] = lambda: services.notion(self.store.secret('notion_token'))
        if self.store.secret('finnhub_token'):
            jobs['Stocks'] = lambda: services.stocks(s['symbols'], self.store.secret('finnhub_token'))
        if self.store.secret('google_tokens'):
            jobs['Google Calendar'] = lambda: services.calendar(self.store)
        generation = self.generation
        for name, work in jobs.items():
            if name not in s['enabled']:
                continue
            def done(value, name=name):
                if generation != self.generation:
                    return
                if name in self.link_layouts:
                    layout = self.link_layouts[name]
                    while layout.count() > 2:
                        item = layout.takeAt(2)
                        item.widget().deleteLater()
                    self.widget_labels[name].setText('Updated ' + datetime.now().strftime('%H:%M') if value else 'No shared pages or upcoming events.')
                    for title, url in value:
                        layout.addWidget(button(title, lambda checked=False, u=url: open_url(u)))
                else:
                    if name == 'Weather' and s['weather_style'] == 'Compact':
                        value = value.split('\n')[0]
                    self.widget_labels[name].setText(value)
            def failed(message, name=name):
                if generation == self.generation:
                    self.widget_labels[name].setText(message)
            self.run_job(name, work, done, failed)
        self.refresh_tasks()

    def refresh_tasks(self):
        if self.expanded and 'Running tasks' in self.widget_labels:
            generation = self.generation
            self.run_job('tasks', services.running_tasks, lambda result: self.widget_labels['Running tasks'].setText(result) if generation == self.generation else None)

    def queue_search(self):
        self.search_cancel.set()
        self.search_timer.start()

    def search(self):
        term = self.search_input.text().strip()
        self.scroll.setVisible(not term)
        self.search_results.setVisible(bool(term))
        if len(term) < 2:
            self.message.setText('Type at least two characters.' if term else '')
            self.search_results.clear()
            return
        self.search_cancel = threading.Event()
        cancel = self.search_cancel
        self.message.setText('Searching filenames…')
        generation = self.generation
        def done(result):
            if cancel.is_set() or generation != self.generation:
                return
            paths, limited = result
            self.search_results.clear()
            for path in paths:
                item = QListWidgetItem(Path(path).name + '\n' + path)
                item.setData(Qt.UserRole, path)
                self.search_results.addItem(item)
            self.message.setText('%s results%s. Double-click or press Enter to open.' % (len(paths), ' · Search limit reached; narrow your folder' if limited else ''))
        self.run_job('search-' + str(id(cancel)), lambda: services.search_files(self.store.settings['search_root'], term, cancel), done)

    def closeEvent(self, event):
        event.ignore()
        self.expand(False)
