import json
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QRect, QPropertyAnimation, QEasingCurve, QThreadPool, QUrl, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QFont, QPixmap, QIcon, QDesktopServices, QCursor, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QStackedWidget, QListWidget, QListWidgetItem, QCheckBox,
    QSpinBox, QComboBox, QFormLayout, QFileDialog, QColorDialog, QFontComboBox,
    QSystemTrayIcon, QMenu, QMessageBox, QAbstractItemView, QGridLayout, QSlider, QLayout, QProgressBar)
from .visuals import media_icon, AlbumArt, TrackLabel, WeekStrip, TemplatePreview
from . import services
from .storage import WIDGETS
from .presets import PRESETS, DESCRIPTIONS, read_template, write_template
from .clocks import ClockFace, DESIGNS
from .desktop import DesktopManager, KINDS


STYLE = '''
QWidget { color: #f4f4f7; font-family: "Segoe UI"; font-size: 13px; font-weight: 500; }
QWidget#notch QLabel, QWidget#notch QPushButton { font-weight: 600; }
QWidget#settings { background: #151518; }
QFrame#settingsGroup { background: #202024; border: 1px solid #303036; border-radius: 14px; }
QListWidget#settingsNavigation { background: transparent; border: 0; padding: 16px 0; }
QListWidget#settingsNavigation::item { padding: 12px 14px; margin: 3px 0; border-radius: 9px; }
QListWidget#settingsNavigation::item:selected { background: #353143; color: #e7e3ff; }
QListWidget#settingsNavigation::item:hover { background: #29292f; }
QLabel { background: transparent; }
QLabel#muted { color: #9999a5; }
QLabel#title { font-size: 27px; font-weight: 600; }
QLabel#section { font-size: 15px; font-weight: 600; }
QFrame#card { background: #080808; border: 0; border-radius: 12px; }
QPushButton#mediaControl { background: transparent; border: 0; border-radius: 8px; padding: 0; }
QPushButton#mediaControl:hover { background: #202022; }
QPushButton#mediaControl:focus { border: 1px solid #888; }
QSlider::groove:horizontal { height: 4px; background: #333336; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #dedee2; border-radius: 2px; }
QSlider::handle:horizontal { width: 8px; margin: -2px 0; background: #eee; border-radius: 4px; }
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
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout():
            clear(item.layout())
            item.layout().deleteLater()


def open_url(url):
    if QUrl(url).scheme() in ('https', 'http', 'spotify', 'whatsapp', 'zoommtg'):
        QDesktopServices.openUrl(QUrl(url))


class Settings(QWidget):
    def __init__(self, notch):
        super().__init__()
        self.notch = notch
        self.store = notch.store
        self.setWindowTitle('Notch · Settings')
        self.setObjectName('settings')
        self.resize(980, 720)
        self.setMinimumSize(850, 550)
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 25, 30, 25)
        body = QHBoxLayout()
        body.setSpacing(28)
        rail = QVBoxLayout()
        rail.addWidget(label('Notch', 'title'))
        rail.addWidget(label('A place for your day', 'muted'))
        self.navigation = QListWidget()
        self.navigation.setObjectName('settingsNavigation')
        self.navigation.setFixedWidth(165)
        rail.addWidget(self.navigation, 1)
        body.addLayout(rail)
        content = QVBoxLayout()
        self.page_title = label('Widgets', 'title')
        content.addWidget(self.page_title)
        content.addWidget(label('Make it feel like yours.', 'muted'))
        self.tabs = QStackedWidget()
        content.addWidget(self.tabs, 1)
        body.addLayout(content, 1)
        root.addLayout(body, 1)
        self.navigation.currentRowChanged.connect(self.select_page)
        self.fields = {}
        self.widget_page()
        self.appearance_page()
        self.desktop_page()
        self.connections_page()
        self.general_page()
        self.navigation.setCurrentRow(0)
        self.status = label('', 'muted', True)
        root.addWidget(self.status)
        footer = QHBoxLayout()
        footer.addWidget(button('Preview notch', notch.preview))
        footer.addStretch()
        footer.addWidget(button('Save settings', self.save, primary=True))
        root.addLayout(footer)

    def select_page(self, index):
        self.tabs.setCurrentIndex(index)
        item = self.navigation.item(index)
        if item:
            self.page_title.setText(item.text())

    def form_card(self, layout, form):
        card = QFrame()
        card.setObjectName('settingsGroup')
        form.setContentsMargins(18, 18, 18, 18)
        form.setVerticalSpacing(17)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        card.setLayout(form)
        layout.addWidget(card)

    def page(self, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        widget = QWidget()
        widget.setObjectName('settingsPage')
        widget.setStyleSheet('QWidget#settingsPage { background: #151518; }')
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 20, 12, 20)
        scroll.setWidget(widget)
        self.tabs.addWidget(scroll)
        self.navigation.addItem(title)
        return layout

    def widget_page(self):
        layout = self.page('Widgets')
        layout.addWidget(label('Choose what lives in your notch', 'section'))
        layout.addWidget(label('Tick to enable. Drag to reorder.', 'muted'))
        layout.addWidget(label('With no active or paused song, Notch shows the first two enabled non-music widgets. Reorder them here to choose your idle layout.', 'muted', True))
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
        layout.addWidget(label('Start with a template', 'section'))
        layout.addWidget(label('Choose a comfortable size. Fine adjustments are optional.', 'muted'))
        presets = QHBoxLayout()
        for name in PRESETS:
            tile = QFrame()
            tile.setObjectName('card')
            box = QVBoxLayout(tile)
            box.addWidget(TemplatePreview(PRESETS[name]['width']))
            box.addWidget(label(name, 'section'))
            description = label(DESCRIPTIONS[name], 'muted', True)
            description.setFixedHeight(60)
            box.addWidget(description)
            box.addWidget(button('Use ' + name, lambda checked=False, n=name: self.apply_preset(PRESETS[n])))
            presets.addWidget(tile, 1)
        layout.addLayout(presets)
        transfer = QHBoxLayout()
        transfer.addWidget(button('Import template…', self.import_template))
        transfer.addWidget(button('Save template…', self.export_template))
        transfer.addWidget(button('Template downloads', lambda: open_url('https://github.com/Dabomb1221/nook-windows/tree/main/templates')))
        layout.addLayout(transfer)
        advanced = QCheckBox('Fine-tune sizes and appearance')
        layout.addWidget(advanced)
        details = QWidget()
        form = QFormLayout()
        details.setLayout(form)
        details.hide()
        advanced.toggled.connect(details.setVisible)
        form.setVerticalSpacing(16)
        self.field(form, 'width', 'Expanded width', 'spin', limits=(460, 1100))
        self.field(form, 'compact_width', 'Resting width', 'spin', limits=(320, 1100))
        self.field(form, 'compact_height', 'Resting height', 'spin', limits=(36, 90))
        self.field(form, 'music_height', 'Music panel height', 'spin', limits=(128, 240))
        self.field(form, 'height', 'Widgets height', 'spin', limits=(300, 850))
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
        layout.addWidget(details)
        layout.addStretch()

    def apply_preset(self, values):
        for key, value in values.items():
            control, kind, _ = self.fields[key]
            if kind == 'spin':
                control.setValue(value)
            elif kind == 'combo':
                control.setCurrentText(value)
        if self.save():
            self.notch.switch_view('Music')
            self.notch.expand(False)
            self.status.setText('Template applied. Hover over the notch to expand it.')

    def import_template(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import Notch appearance', '', 'Notch template (*.json)')
        if path:
            try:
                self.apply_preset(read_template(path))
            except (ValueError, OSError) as error:
                self.status.setText(str(error))

    def export_template(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save Notch appearance', 'My Notch.json', 'Notch template (*.json)')
        if path and self.save():
            try:
                write_template(path, self.store.settings)
                self.status.setText('Appearance saved. Templates contain no accounts, files or personal data.')
            except (ValueError, OSError) as error:
                self.status.setText(str(error))

    def desktop_page(self):
        layout = self.page('Desktop')
        layout.addWidget(label('Give your desktop a little purpose', 'section'))
        layout.addWidget(label('Tiles sit behind normal app windows. Drag a tile by its empty space. Hover to reveal its ··· menu for style, position and removal.', 'muted', True))
        form = QFormLayout()
        theme = self.field(form, 'desktop_theme', 'Default tile style', 'combo', choices=['macOS', 'Glass', 'Paper', 'Midnight', 'Graphite'])
        self.form_card(layout, form)
        row = QHBoxLayout()
        self.desktop_kind = QComboBox()
        self.desktop_kind.addItems(KINDS)
        row.addWidget(self.desktop_kind)
        row.addWidget(button('Add to desktop', lambda: self.add_desktop(self.desktop_kind.currentText())))
        layout.addLayout(row)
        layout.addWidget(label('Ready-made desktop layouts', 'section'))
        gallery = QGridLayout()
        for index, design in enumerate(DESIGNS):
            preview = ClockFace(design)
            preview.setFixedSize(150, 110)
            gallery.addWidget(preview, (index // 3)*2, index % 3)
            gallery.addWidget(button(design, lambda checked=False, d=design: self.notch.desktop.add('Clock', design=d)), (index // 3)*2+1, index % 3)
        layout.addLayout(gallery)
        for name in ('Reference desk', 'Focus desk', 'Music desk', 'Daily desk'):
            layout.addWidget(button('Add ' + name, lambda checked=False, n=name: self.add_desktop_layout(n)))
        layout.addWidget(label('macOS is dark and translucent like Mac widgets, Glass is translucent, Paper is soft and light, Midnight is dark. Layouts add three tiles without removing your existing ones.', 'muted', True))
        self.desktop_list = QListWidget()
        layout.addWidget(self.desktop_list)
        layout.addWidget(button('Remove selected widget', self.remove_desktop))
        self.refresh_desktop_list()

    def refresh_desktop_list(self):
        self.desktop_list.clear()
        for row in self.store.settings['desktop_widgets']:
            item = QListWidgetItem(row['kind'])
            item.setData(Qt.UserRole, row['id'])
            self.desktop_list.addItem(item)

    def add_desktop(self, kind):
        if self.save():
            self.notch.desktop.add(kind)
            self.refresh_desktop_list()

    def add_desktop_layout(self, name):
        if self.save():
            self.notch.desktop.add_layout(name)
            self.refresh_desktop_list()

    def remove_desktop(self):
        item = self.desktop_list.currentItem()
        if item:
            self.notch.desktop.remove(item.data(Qt.UserRole))
            self.refresh_desktop_list()

    def choose_color(self, field):
        color = QColorDialog.getColor(QColor(field.text()), self)
        if color.isValid():
            field.setText(color.name())

    def connections_page(self):
        layout = self.page('Connections')
        form = QFormLayout()
        form.setVerticalSpacing(13)
        self.field(form, 'city', 'Weather city')
        self.field(form, 'weather_source', 'Weather location', 'combo', choices=['City', 'Windows location'])
        self.field(form, 'fahrenheit', 'Fahrenheit', 'check')
        self.field(form, 'finnhub_token', 'Finnhub API key', secret=True)
        self.field(form, 'symbols', 'Stock symbols (up to 8)')
        self.field(form, 'google_client_id', 'Google Desktop client ID')
        self.field(form, 'google_client_secret', 'Google client secret', secret=True)
        self.form_card(layout, form)
        layout.addWidget(label('Windows location requires Windows permission. Forecasts are supplied by Open-Meteo, not the Windows Weather app. Units can also be changed on the widget. Google requires a Desktop OAuth client with the Calendar API enabled.', 'muted', True))
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
        layout.addWidget(label('Claude usage reads live plan limits through the Claude Code sign-in on this PC (run \"claude\" once to sign in). Codex opens its usage page. Calls open WhatsApp, Zoom or Instagram; in-call controls require provider support.', 'muted', True))
        layout.addStretch()

    def general_page(self):
        layout = self.page('Behaviour')
        form = QFormLayout()
        self.screen_combo = QComboBox()
        for screen in QApplication.screens():
            self.screen_combo.addItem(screen.name())
        self.screen_combo.setCurrentIndex(min(self.store.settings['screen'], self.screen_combo.count() - 1))
        form.addRow('Display', self.screen_combo)
        self.field(form, 'collapse_ms', 'Collapse delay (ms)', 'spin', limits=(0, 1000))
        root = self.field(form, 'search_root', 'File search folder')
        form.addRow('', button('Choose search folder', lambda: self.choose_folder(root)))
        self.form_card(layout, form)
        layout.addWidget(label('Search scans filenames on demand, stops after 8 seconds or 50 results, and skips dependency and system folders. Choose a narrower folder for deeper results.', 'muted', True))
        layout.addWidget(label('The notch expands on hover and collapses when you leave. Right-click it or use the tray icon for Settings and Quit.', 'muted', True))
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
        QApplication.instance().setStyleSheet(STYLE.replace('#b7b0ff', self.store.settings['accent']))
        self.notch.rebuild()
        self.notch.desktop.sync()
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
        self.setObjectName('notch')
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
        self.widget_data = {}
        self.media_received = time.monotonic()
        self.view = 'Music'
        self.cover_bytes = None
        self.pending_media_actions = []
        self.preferred_player = ''
        self.setWindowTitle('Notch')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.animation = QPropertyAnimation(self, b'geometry', self)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.setDuration(150)
        self.animation.finished.connect(self.animation_finished)
        self.collapse_timer = QTimer(self)
        self.collapse_timer.setSingleShot(True)
        self.collapse_timer.timeout.connect(self.maybe_collapse)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.search)
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(20, 0, 20, 6)
        self.root.setSizeConstraint(QLayout.SetNoConstraint)
        self.root.setSpacing(6)
        self.header = QWidget()
        self.header.setFixedHeight(self.store.settings['compact_height'])
        header = QHBoxLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        self.compact_art = AlbumArt(26)
        header.addWidget(self.compact_art)
        compact_text = QVBoxLayout()
        compact_text.setSpacing(1)
        self.compact = TrackLabel('Notch')
        self.compact_artist = TrackLabel('Your desktop essentials')
        self.compact_artist.setStyleSheet('font-size: 10px; color: #99999f;')
        compact_text.addWidget(self.compact)
        compact_text.addWidget(self.compact_artist)
        header.addLayout(compact_text, 1)
        self.compact_state = label('')
        self.compact_state.setPixmap(media_icon('wave').pixmap(18, 18))
        header.addWidget(self.compact_state)
        self.clock = label('')
        header.addWidget(self.clock)
        self.root.addWidget(self.header)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(6)
        self.root.addWidget(self.body, 1)
        self.body.hide()
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.media_timer = QTimer(self)
        self.media_timer.timeout.connect(self.refresh_media)
        self.media_timer.start(1500)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_widgets)
        self.refresh_timer.start(300000)
        self.claude_timer = QTimer(self)
        self.claude_timer.timeout.connect(self.refresh_claude_usage)
        self.claude_timer.start(60000)
        self.task_timer = QTimer(self)
        self.task_timer.timeout.connect(self.refresh_tasks)
        self.task_timer.start(15000)
        self.menu = QMenu()
        self.menu.addAction('Settings', self.open_settings)
        self.menu.addSeparator()
        self.menu.addAction('Quit Notch', lambda: QApplication.exit(0))
        icon = QPixmap(64, 64)
        icon.fill(Qt.transparent)
        painter = QPainter(icon)
        painter.setBrush(QColor(self.store.settings['accent']))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(5, 9, 54, 38, 12, 12)
        painter.setPen(QColor('#141217'))
        painter.setFont(QFont('Segoe UI', 23, QFont.Bold))
        painter.drawText(icon.rect(), Qt.AlignCenter, 'n')
        painter.end()
        self.setWindowIcon(QIcon(icon))
        self.tray = QSystemTrayIcon(QIcon(icon), self)
        self.tray.setToolTip('Notch · Your desktop essentials')
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(lambda reason: self.open_settings() if reason == QSystemTrayIcon.DoubleClick else None)
        self.tray.show()
        QShortcut(QKeySequence('Escape'), self, activated=lambda: self.expand(False))
        for screen in QApplication.screens():
            screen.geometryChanged.connect(self.reposition)
        QApplication.instance().screenAdded.connect(lambda *_: self.reposition())
        QApplication.instance().screenRemoved.connect(lambda *_: self.reposition())
        self.rebuild()
        self.desktop = DesktopManager(self)

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
        path.quadTo(self.width() - 10, 0, self.width() - 10, 12)
        path.lineTo(self.width() - 10, self.height() - r)
        path.quadTo(self.width() - 10, self.height(), self.width() - r - 10, self.height())
        path.lineTo(r + 10, self.height())
        path.quadTo(10, self.height(), 10, self.height() - r)
        path.lineTo(10, 12)
        path.quadTo(10, 0, 0, 0)
        path.closeSubpath()
        painter.fillPath(path, QColor(0, 0, 0, int(255 * self.store.settings['opacity'] / 100)))

    def target_geometry(self):
        screens = QApplication.screens()
        screen = screens[min(max(0, self.store.settings['screen']), len(screens) - 1)]
        bounds = screen.geometry()
        width = min(self.store.settings['width' if self.expanded else 'compact_width'], bounds.width() - 110)
        expanded_height = self.store.settings['music_height'] if self.view == 'Music' else self.store.settings['height']
        height = min(expanded_height if self.expanded else self.store.settings['compact_height'], bounds.height() - 40)
        return QRect(bounds.x() + (bounds.width() - width) // 2, bounds.y(), width, height)

    def reposition(self, *_):
        self.animation.stop()
        self.body.setMinimumSize(0, 0)
        self.body.setMaximumSize(16777215, 16777215)
        self.body.setVisible(self.expanded)
        self.setGeometry(self.target_geometry())

    def expand(self, expanded):
        start_geometry = self.geometry()
        self.collapse_timer.stop()
        if self.expanded == expanded:
            return
        self.animation.stop()
        self.expanded = expanded
        if not expanded:
            self.pinned = False
            self.switch_view('Music')
        self.update_clock()
        self.body.setVisible(expanded)
        header_space = 0 if self.header.isHidden() else self.header.height() + 6
        if expanded:
            self.body.setFixedSize(self.target_geometry().width() - 40,
                                   max(0, self.target_geometry().height() - header_space - 6))
        if self.store.settings['animation']:
            self.animation.setDuration(150 if expanded else 120)
            self.animation.setStartValue(start_geometry)
            self.animation.setEndValue(self.target_geometry())
            self.animation.start()
        else:
            self.reposition()
            self.animation_finished()
        self.update_clock()

    def animation_finished(self):
        self.body.setVisible(self.expanded)
        self.body.setMinimumSize(0, 0)
        self.body.setMaximumSize(16777215, 16777215)
        if self.expanded:
            self.body.setMinimumSize(0, 0)
            self.body.setMaximumSize(16777215, 16777215)
            self.refresh_media()
            self.refresh_tasks()

    def enterEvent(self, event):
        self.expand(True)

    def leaveEvent(self, event):
        self.collapse_timer.start(self.store.settings['collapse_ms'])

    def maybe_collapse(self):
        if not self.geometry().contains(QCursor.pos()):
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
        self.expand(False)

    def preview(self):
        self.expand(False)
        self.reposition()

    def card(self, title):
        frame = QFrame()
        frame.setObjectName('card')
        if title in ('Music', 'Time'):
            frame.setStyleSheet('QFrame#card { background: transparent; border: 0; }')
        self.card_frames[title] = frame
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 10, 4)
        layout.setSpacing(5)
        heading = label(title, 'section')
        heading.hide()
        layout.addWidget(heading)
        if self.pair_music_time and title in ('Music', 'Time'):
            self.cards.addWidget(frame, 0, 0 if title == 'Music' else 1)
        else:
            self.cards.addWidget(frame, self.card_row, 0, 1, 2)
            self.card_row += 1
        return layout

    def rebuild(self):
        self.generation += 1
        self._cards_signature = None
        self.search_cancel.set()
        clear(self.body_layout)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)
        self.view_buttons = {}
        for name in ('Music', 'Widgets', 'Files'):
            tab = button(name, lambda checked=False, name=name: self.switch_view(name))
            tab.setFixedHeight(26)
            self.view_buttons[name] = tab
            toolbar.addWidget(tab)
        toolbar.addStretch()
        self.pin = button('', self.toggle_pin, 'Pin notch')
        self.pin.setIcon(media_icon('pin', '#88888e'))
        self.pin.setObjectName('mediaControl')
        self.pin.setFixedSize(26, 26)
        toolbar.addWidget(self.pin)
        self.pin.hide()
        settings = button('', self.open_settings, 'Settings')
        settings.setIcon(media_icon('settings', '#88888e'))
        settings.setObjectName('mediaControl')
        settings.setFixedSize(26, 26)
        toolbar.addWidget(settings)
        self.body_layout.addLayout(toolbar)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('Search files on this PC…')
        self.search_input.setAccessibleName('Search files on this PC')
        self.search_input.textChanged.connect(self.queue_search)
        self.body_layout.addWidget(self.search_input)
        self.message = label(self.store.warning, 'muted', True)
        self.message.setVisible(bool(self.store.warning))
        self.body_layout.addWidget(self.message)
        self.empty_idle = label('Choose calendar, tasks or another idle widget in Settings → Widgets.', 'muted', True)
        self.empty_idle.hide()
        self.body_layout.addWidget(self.empty_idle)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.viewport().setStyleSheet('background: transparent;')
        content = QWidget()
        content.setStyleSheet('background: transparent;')
        enabled = [n for n in self.store.settings['order'] if n in self.store.settings['enabled']]
        self.pair_music_time = 'Music' in enabled and 'Time' in enabled
        self.card_frames = {}
        self.card_row = 1 if self.pair_music_time else 0
        self.cards = QGridLayout(content)
        self.cards.setColumnStretch(0, 7)
        self.cards.setColumnStretch(1, 4)
        self.cards.setContentsMargins(0, 0, 0, 0)
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
                size = {'Minimal': 22, 'Large': 30, 'Editorial': 26}[self.store.settings['clock_style']]
                self.time_label.setFont(QFont(self.store.settings['font'], size))
                self.time_label.setStyleSheet('font-family: "%s"; font-size: %spx; color: #f5f5f7;' % (self.store.settings['font'], size))
                calendar_header = QHBoxLayout()
                calendar_header.addWidget(self.time_label)
                calendar_header.addWidget(WeekStrip(self.store.settings['accent']), 1)
                layout.addLayout(calendar_header)
                self.date_label = label('', 'muted', True)
                layout.addWidget(self.date_label)
                layout.addStretch()
            elif name == 'To do':
                self.todo_layout = layout
                self.build_todos()
            elif name == 'Google Calendar':
                self.link_layouts[name] = layout
                self.widget_labels[name] = label('Connect in Settings to see your ' + ('events.' if name == 'Google Calendar' else 'pages.'), 'muted', True)
                layout.addWidget(self.widget_labels[name])
            elif name == 'Claude usage':
                self.claude_bar = QProgressBar()
                self.claude_bar.setRange(0, 100)
                self.claude_bar.setTextVisible(False)
                self.claude_bar.setFixedHeight(8)
                self.claude_bar.setAccessibleName('Claude session usage')
                self.claude_bar.setStyleSheet('QProgressBar { background: #3a3a3e; border: 0; border-radius: 4px; } QProgressBar::chunk { background: #d97757; border-radius: 4px; }')
                layout.addWidget(self.claude_bar)
                self.widget_labels[name] = label('Loading Claude usage…', 'muted', True)
                layout.addWidget(self.widget_labels[name])
            elif name == 'Codex usage':
                layout.addWidget(label('Notch cannot read this account’s private plan allowance. Use the official usage page for the current value and reset time.', 'muted', True))
                layout.addWidget(button('Open Codex usage', lambda checked=False: open_url('https://chatgpt.com/codex/settings/usage')))
                layout.addWidget(label('Workspace administrators may use the Codex Compliance API. Personal plans show usage in Codex / ChatGPT settings.', 'muted', True))
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
                if name == 'Weather':
                    units = QHBoxLayout()
                    for text, fahrenheit in [('°C', False), ('°F', True)]:
                        units.addWidget(button(text, lambda checked=False, f=fahrenheit: self.set_weather_unit(f)))
                    layout.addLayout(units)
                if name == 'Running tasks':
                    layout.addWidget(label('Process presence only. Task completion requires an agent integration.', 'muted', True))
        self.cards.setRowStretch(self.card_row, 1)
        self.body.setVisible(self.expanded)
        self.switch_view(self.view)
        self.reposition()
        self.update_clock()
        self.refresh_widgets()
        self.refresh_media()

    def switch_view(self, name):
        self.view = name
        self.layout_cards()
        for title, tab in self.view_buttons.items():
            tab.setStyleSheet('background: %s; color: %s; border: 0; padding: 3px 12px; border-radius: 12px;' % ('#252527' if title == name else 'transparent', '#f5f5f5' if title == name else '#89898e'))
        self.search_input.setVisible(name == 'Files')
        self.search_results.setVisible(name == 'Files')
        self.scroll.setVisible(name in ('Music', 'Widgets'))
        self.message.setVisible(name == 'Files' or bool(self.store.warning))
        if name == 'Files':
            self.search_input.setFocus()
        self.update_clock()
        self.reposition()

    def layout_cards(self):
        available = bool(self.media_state.get('has_track', self.media_state.get('source'))) and 'Music' in self.card_frames
        idle = [title for title in self.card_frames if title != 'Music']
        if self.view == 'Music':
            visible = (['Music'] + (['Time'] if 'Time' in idle else idle[:1])) if available and 'Music' in self.card_frames else idle[:2]
        else:
            visible = idle if self.view == 'Widgets' else []
        signature = (self.view, available, tuple(visible))
        if signature == self._cards_signature:
            return
        self._cards_signature = signature
        self.empty_idle.setVisible(self.view == 'Music' and not visible)
        self.view_buttons['Music'].setText('Music' if available else 'Notch')
        for row in range(self.cards.rowCount()):
            self.cards.setRowStretch(row, 0)
        for title, frame in self.card_frames.items():
            self.cards.removeWidget(frame)
            frame.setVisible(title in visible)
        for index, title in enumerate(visible):
            if self.view == 'Music':
                self.cards.addWidget(self.card_frames[title], 0, index, 1, 2 if len(visible) == 1 else 1)
            else:
                self.cards.addWidget(self.card_frames[title], index, 0, 1, 2)
        self.cards.setColumnStretch(0, 1)
        self.cards.setColumnStretch(1, 1)
        self.cards.setRowStretch(1 if self.view == 'Music' else len(visible), 1)

    def build_music(self, layout):
        row = QHBoxLayout()
        row.setSpacing(10)
        self.artwork = AlbumArt(72)
        row.addWidget(self.artwork)
        details = QVBoxLayout()
        details.setSpacing(2)
        self.track = TrackLabel('Nothing playing')
        self.track.setStyleSheet('font-size: 13px; font-weight: 600;')
        self.artist = TrackLabel('Start Spotify or Apple Music')
        self.album = TrackLabel('')
        self.album.setStyleSheet('font-size: 12px; color: #b8b8bd;')
        self.artist.setStyleSheet('color: #939397; font-size: 12px;')
        details.addWidget(self.track)
        details.addWidget(self.album)
        details.addWidget(self.artist)
        row.addLayout(details, 1)
        self.players = QComboBox()
        self.players.setMaximumWidth(110)
        self.players.setAccessibleName('Media player')
        self.players.activated.connect(self.choose_player)
        self.players.hide()
        row.addWidget(self.players)
        layout.addLayout(row)
        progress = QHBoxLayout()
        progress.setSpacing(9)
        self.elapsed = label('0:00', 'muted')
        self.remaining = label('−0:00', 'muted')
        self.progress = QSlider(Qt.Horizontal)
        self.progress.setRange(0, 1000)
        self.progress.setAccessibleName('Playback position')
        self.progress.sliderReleased.connect(self.seek)
        progress.addWidget(self.elapsed)
        progress.addWidget(self.progress, 1)
        progress.addWidget(self.remaining)
        layout.addLayout(progress)
        self.elapsed.hide()
        self.remaining.hide()
        self.progress.hide()
        controls = QHBoxLayout()
        controls.setSpacing(8)
        self.media_buttons = {}
        for key, tip in [('previous', 'Previous track'), ('play', 'Play or pause'), ('next', 'Next track'), ('repeat', 'Repeat off')]:
            control = button('', lambda checked=False, action=key: self.refresh_media(action), tip)
            control.setObjectName('mediaControl')
            control.setIcon(media_icon(key))
            control.setIconSize(QSize(17, 17))
            control.setFixedSize(24, 24)
            control.setEnabled(False)
            self.media_buttons[key] = control
            controls.addWidget(control)
        controls.addStretch()
        details.addLayout(controls)
        self.timeline = label('')
        self.timeline.hide()
        layout.addWidget(self.timeline)

    def seek(self):
        duration = self.media_state.get('duration', 0)
        if duration:
            self.refresh_media(('seek', duration * self.progress.value() / 1000))

    def choose_player(self):
        self.preferred_player = self.players.currentText()
        self.refresh_media()

    def build_todos(self):
        # Preserve the section heading while replacing task controls.
        while self.todo_layout.count() > 1:
            item = self.todo_layout.takeAt(1)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
            elif item.layout():
                clear(item.layout())
                item.layout().deleteLater()
        for index, task in enumerate(self.store.settings['todos']):
            if task.get('done'):
                continue
            row = QHBoxLayout()
            check = QCheckBox()
            check.setText(check.fontMetrics().elidedText(task['text'], Qt.ElideRight, 190))
            check.setToolTip(task['text'])
            check.setStyleSheet('padding: 0;')
            check.setChecked(task.get('done', False))
            check.toggled.connect(lambda value, i=index: self.toggle_todo(i, value))
            row.addWidget(check, 1)
            remove = button('×', lambda checked=False, i=index: self.remove_todo(i), 'Delete task')
            remove.setFixedSize(24, 24)
            remove.setStyleSheet('padding: 0; border: 0; background: transparent;')
            row.addWidget(remove)
            self.todo_layout.addLayout(row)
        row = QHBoxLayout()
        self.todo_input = QLineEdit()
        self.todo_input.setFixedHeight(26)
        self.todo_input.setStyleSheet('padding: 3px 7px;')
        self.todo_input.setPlaceholderText('Add a task…')
        self.todo_input.setAccessibleName('New task')
        self.todo_input.setMaxLength(240)
        self.todo_input.returnPressed.connect(self.add_todo)
        row.addWidget(self.todo_input)
        add = button('Add', self.add_todo)
        add.setFixedSize(40, 26)
        add.setStyleSheet('padding: 0;')
        row.addWidget(add)
        self.todo_layout.addLayout(row)

    def toggle_todo(self, index, value):
        self.store.settings['todos'][index]['done'] = value
        self.store.save()
        QTimer.singleShot(0, self.refresh_todos)

    def refresh_todos(self):
        if hasattr(self, 'todo_layout'):
            self.build_todos()
        self.desktop.refresh()

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
        compact_visible = not self.expanded or self.view != 'Music'
        self.header.setVisible(compact_visible)
        self.header.setFixedHeight(36 if self.expanded else self.store.settings['compact_height'] - 6)
        self.clock.setVisible(compact_visible)
        active = bool(self.media_state.get('has_track', self.media_state.get('source'))) and 'Music' in self.store.settings['enabled']
        self.compact.setText(self.media_state.get('title', 'Notch') if active else now.strftime('%a, %d %b'))
        self.compact.setVisible(compact_visible)
        tasks = [row['text'] for row in self.store.settings['todos'] if not row.get('done')]
        self.compact_artist.setText(self.media_state.get('artist', '') if active else (tasks[0] if tasks and 'To do' in self.store.settings['enabled'] else 'Hover for your widgets'))
        self.compact_artist.setVisible(compact_visible)
        self.compact_art.setVisible(active and compact_visible)
        self.compact_state.setVisible(active and compact_visible)
        self.compact_state.setPixmap(media_icon('wave' if self.media_state.get('playing') else 'pause', '#a6a6ac').pixmap(16, 16))
        self.update_progress()
        if 'Time' in self.store.settings['enabled']:
            self.time_label.setText(now.strftime('%b'))
            today = now.strftime('%Y-%m-%d')
            deadlines = [r['title'] for r in self.store.settings['deadlines'] if r['due'][:10] == today]
            events = self.widget_data.get('Google Calendar', [])
            titles = deadlines + ([r[0] for r in events[:1]] if isinstance(events, list) else [])
            self.date_label.setText(titles[0] if titles else 'Nothing scheduled' if self.store.secret('google_tokens') or self.store.settings['deadlines'] else 'Connect your calendar')

    def update_progress(self):
        if 'Music' not in self.store.settings['enabled'] or not hasattr(self, 'progress'):
            return
        duration = self.media_state.get('duration', 0)
        elapsed = self.media_state.get('position', 0)
        if self.media_state.get('playing'):
            elapsed += time.monotonic() - self.media_received
        elapsed = max(0, min(duration, elapsed))
        remaining = max(0, int(duration - elapsed))
        self.elapsed.setText('%d:%02d' % (int(elapsed) // 60, int(elapsed) % 60))
        self.remaining.setText('−%d:%02d' % (remaining // 60, remaining % 60))
        if not self.progress.isSliderDown():
            self.progress.setValue(round(elapsed / duration * 1000) if duration else 0)
        self.progress.setEnabled(bool(duration and self.media_state.get('can_seek')))

    def refresh_media(self, action=None):
        if 'Music' not in self.store.settings['enabled'] and not any(r['kind'] == 'Music' for r in self.store.settings['desktop_widgets']):
            return
        if 'media' in self.jobs:
            if action is not None:
                self.pending_media_actions.append(action)
            return
        if self.pending_media_actions:
            if action is not None:
                self.pending_media_actions.append(action)
            action = self.pending_media_actions.pop(0)
        generation = self.generation
        def done(state):
            if generation != self.generation:
                return
            self.media_state = state
            self.layout_cards()
            self.media_received = time.monotonic()
            if 'Music' not in self.store.settings['enabled']:
                if self.pending_media_actions:
                    QTimer.singleShot(0, self.refresh_media)
                return
            self.track.setText(state['title'])
            self.artist.setText(state['artist'])
            self.album.setText(state.get('album', ''))
            self.media_buttons['play'].setIcon(media_icon('pause' if state.get('playing') else 'play'))
            repeat = state.get('repeat', 0)
            self.media_buttons['repeat'].setIcon(media_icon('repeat-one' if repeat == 1 else 'repeat', self.store.settings['accent'] if repeat else '#88888e'))
            self.media_buttons['repeat'].setToolTip({0: 'Repeat off', 1: 'Repeat song', 2: 'Repeat playlist'}.get(repeat, 'Repeat off'))
            for key, control in self.media_buttons.items():
                control.setEnabled(state.get('can_' + key, False))
            self.players.blockSignals(True)
            self.players.clear()
            self.players.addItems(state.get('sessions', []))
            self.players.setCurrentText(state.get('source', ''))
            self.players.blockSignals(False)
            self.players.setVisible(len(state.get('sessions', [])) > 1)
            artwork = bytes(state.get('artwork') or b'')
            if artwork != self.cover_bytes:
                self.cover_bytes = artwork
                self.cover = QPixmap()
                if artwork:
                    self.cover.loadFromData(artwork)
            if hasattr(self, 'cover'):
                self.artwork.setPixmap(self.cover)
                self.compact_art.setPixmap(self.cover)
            position, duration = int(state.get('position', 0)), int(state.get('duration', 0))
            self.timeline.setText('%d:%02d / %d:%02d' % (position // 60, position % 60, duration // 60, duration % 60) if duration else '')
            self.update_clock()
            if self.pending_media_actions:
                QTimer.singleShot(0, self.refresh_media)
        def failed(message):
            if generation == self.generation and 'Music' in self.store.settings['enabled']:
                self.artist.setText(message)
            if self.pending_media_actions:
                QTimer.singleShot(0, self.refresh_media)
        self.run_job('media', lambda: services.media(action, self.preferred_player), done, failed)

    def refresh_claude_usage(self):
        self.refresh_widgets('Claude usage')

    def refresh_widgets(self, only=None):
        s = self.store.settings
        jobs = {}
        if services.CLAUDE_CREDENTIALS.exists():
            jobs['Claude usage'] = services.claude_usage
        if s['city'] or s.get('weather_source') == 'Windows location':
            jobs['Weather'] = lambda: services.weather(s['city'], s['fahrenheit'], s.get('weather_source') == 'Windows location', structured=True)
        if self.store.secret('finnhub_token'):
            jobs['Stocks'] = lambda: services.stocks(s['symbols'], self.store.secret('finnhub_token'))
        if self.store.secret('google_tokens'):
            jobs['Google Calendar'] = lambda: services.calendar(self.store)
        if only:
            jobs = {only: jobs[only]} if only in jobs else {}
        generation = self.generation
        for name, work in jobs.items():
            desktop_names = {'Google Calendar' if r['kind'] == 'Calendar' else r['kind'] for r in s['desktop_widgets']}
            if name not in s['enabled'] and name not in desktop_names:
                continue
            def done(value, name=name):
                self.widget_data[name] = value
                if generation != self.generation:
                    return
                if name not in self.widget_labels:
                    return
                if name == 'Claude usage':
                    self.claude_bar.setValue(int(min(value[0][1], 100)) if value else 0)
                    self.widget_labels[name].setText('   '.join('%s %.0f%% · resets %s' % (n, pct, services.format_reset(r)) for n, pct, r in value) or 'No usage limits reported.')
                elif name in self.link_layouts:
                    layout = self.link_layouts[name]
                    while layout.count() > 2:
                        item = layout.takeAt(2)
                        item.widget().deleteLater()
                    self.widget_labels[name].setText('Updated ' + datetime.now().strftime('%H:%M') if value else 'No shared pages or upcoming events.')
                    for title, url in value:
                        layout.addWidget(button(title, lambda checked=False, u=url: open_url(u)))
                else:
                    if name == 'Weather' and isinstance(value, dict):
                        value = services.format_weather(value)
                    if name == 'Weather' and s['weather_style'] == 'Compact':
                        value = value.split('\n')[0]
                    self.widget_labels[name].setText(value)
            def failed(message, name=name):
                self.widget_data[name] = message
                if generation == self.generation and name in self.widget_labels:
                    self.widget_labels[name].setText(message)
            self.run_job(name, work, done, failed)
        if not only:
            self.refresh_tasks()

    def set_weather_unit(self, fahrenheit):
        self.store.settings['fahrenheit'] = fahrenheit
        self.store.save()
        self.refresh_widgets()

    def refresh_tasks(self):
        if self.expanded and 'Running tasks' in self.widget_labels:
            generation = self.generation
            self.run_job('tasks', services.running_tasks, lambda result: self.widget_labels['Running tasks'].setText(result) if generation == self.generation else None)

    def queue_search(self):
        self.search_cancel.set()
        self.search_timer.start()

    def search(self):
        term = self.search_input.text().strip()
        self.scroll.setVisible(False)
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
