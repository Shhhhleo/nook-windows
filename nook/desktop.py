"""Independent desktop tiles sharing the notch's data and worker pool."""
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QPixmap, QDesktopServices, QPainterPath, QLinearGradient
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QCheckBox, QLineEdit, QMenu, QFileDialog, QTextEdit, QScrollArea)
from .visuals import AlbumArt, TrackLabel, media_icon, VinylArt
from .presets import THEMES
from .clocks import ClockFace, DESIGNS
from .tiles import InfoFace

KINDS = ('Clock', 'Music', 'To do', 'Weather', 'Calendar', 'Note', 'Photo', 'Battery')
UNIT, WIDE, GAP, RADIUS = 222, 468, 24, 22   # macOS widget grid: small tile, double-wide tile, gap, corner radius
SIZES = {kind: (UNIT, UNIT) for kind in KINDS}
SIZES['Calendar'] = (WIDE, UNIT)
PALETTES = {'macOS': ('#1f1f22', '#ffffff', '#9d9da3', 232), 'Graphite': ('#2b2b2d', '#f7f7f8', '#b4b4b8', 235), 'Glass': ('#dce1e7', '#242a32', '#5a626d', 205),
            'Paper': ('#f2eee6', '#32302d', '#726b62', 246),
            'Midnight': ('#17181d', '#f4f4f7', '#b0b0bd', 235)}


def plain(text):
    widget = QLabel(text)
    widget.setTextFormat(Qt.PlainText)
    widget.setWordWrap(True)
    return widget


class DesktopTile(QWidget):
    def __init__(self, manager, config):
        super().__init__()
        self.manager, self.notch, self.config = manager, manager.notch, config
        self.kind = config['kind']
        self.drag_offset = None
        self.signature = None
        self.art_bytes = None
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnBottomHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle('Notch desktop · ' + self.kind)
        self.resize(*SIZES[self.kind])
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)
        self.heading = plain(self.kind)
        self.heading.setParent(self)
        self.heading.hide()
        self.setAccessibleName(self.kind + ' desktop widget')
        self.content = QVBoxLayout()
        self.content.setSpacing(8)
        root.addLayout(self.content, 1)
        if self.kind == 'Clock':
            self.face = ClockFace(config.get('design', 'Numeral'))
            self.resize(*self.clock_size())
            root.setContentsMargins(0, 0, 0, 0)
            self.content.addWidget(self.face, 1)
        elif self.kind == 'Music':
            self.art = VinylArt(96)
            self.content.addWidget(self.art, 0, Qt.AlignHCenter)
            self.title = TrackLabel('Nothing playing')
            self.title.setStyleSheet('font-weight: 600;')
            self.artist = TrackLabel('Start Spotify or Apple Music')
            self.content.addWidget(self.title)
            self.content.addWidget(self.artist)
            row = QHBoxLayout()
            row.addStretch()
            self.controls = {}
            for name in ('previous', 'play', 'next'):
                control = QPushButton()
                control.setFixedSize(32, 28)
                control.setIconSize(QSize(18, 18))
                control.setAccessibleName(name + ' track')
                control.clicked.connect(lambda checked=False, n=name: self.notch.refresh_media(n))
                self.controls[name] = control
                row.addWidget(control)
            row.addStretch()
            self.content.addLayout(row)
        elif self.kind == 'To do':
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            holder = QWidget()
            self.tasks = QVBoxLayout(holder)
            self.tasks.setContentsMargins(0, 0, 0, 0)
            scroll.setWidget(holder)
            self.content.addWidget(scroll, 1)
            self.task_input = QLineEdit()
            self.task_input.setPlaceholderText('Add a task…')
            self.task_input.setMaxLength(240)
            self.task_input.returnPressed.connect(self.add_task)
            self.content.addWidget(self.task_input)
        elif self.kind == 'Note':
            self.note = QTextEdit()
            self.note.setAcceptRichText(False)
            self.note.setPlaceholderText('A thought worth keeping…')
            self.note.setPlainText(config.get('text', ''))
            self.save_timer = QTimer(self)
            self.save_timer.setSingleShot(True)
            self.save_timer.timeout.connect(self.save_note)
            self.note.textChanged.connect(lambda: self.save_timer.start(500))
            self.content.addWidget(self.note)
        elif self.kind == 'Photo':
            self.photo = QLabel()
            self.photo.setAlignment(Qt.AlignCenter)
            self.photo.setWordWrap(True)
            self.photo.setMinimumSize(0, 0)
            self.content.addWidget(self.photo, 1)
            self.choose_button = QPushButton('Choose photo')
            self.choose_button.clicked.connect(self.choose_photo)
            self.content.addWidget(self.choose_button)
            root.setContentsMargins(0, 0, 0, 0)
            self.load_photo()
        elif self.kind in ('Weather', 'Calendar', 'Battery'):
            self.info = InfoFace(self.kind)
            self.content.addWidget(self.info, 1)
            root.setContentsMargins(0, 0, 0, 0)
        else:
            self.large = plain('')
            self.large.setStyleSheet('font-size: 42px; font-weight: 500;')
            self.content.addWidget(self.large)
            self.detail = plain('')
            self.detail.setStyleSheet('font-size: 12px;')
            self.content.addWidget(self.detail, 1)
            if self.kind == 'Weather':
                units = QHBoxLayout()
                for text, fahrenheit in [('°C', False), ('°F', True)]:
                    control = QPushButton(text)
                    control.setAccessibleName('Use Celsius' if not fahrenheit else 'Use Fahrenheit')
                    control.clicked.connect(lambda checked=False, f=fahrenheit: self.notch.set_weather_unit(f))
                    units.addWidget(control)
                self.content.addLayout(units)
        self.apply_theme()
        self.restore_position()
        self.refresh()

    def clock_size(self):
        return (WIDE, UNIT) if self.face.design == 'World row' else (UNIT, UNIT)

    def resizeEvent(self, event):
        if self.kind == 'Photo' and hasattr(self, 'choose_button'):
            self.load_photo()

    def apply_theme(self):
        theme = self.config.get('theme') or self.notch.store.settings['desktop_theme']
        self.theme_name = theme if theme in PALETTES else 'macOS'
        self.colors = PALETTES[self.theme_name]
        _, foreground, muted, _ = self.colors
        if hasattr(self, 'info'):
            self.info.ink, self.info.muted = foreground, muted
            self.info.update()
        self.setStyleSheet('''QWidget { color: %s; background: transparent; }
            QPushButton { border: 0; border-radius: 7px; padding: 2px; }
            QPushButton:hover { background: rgba(128,128,128,35); }
            QLineEdit, QTextEdit { background: rgba(128,128,128,34); border: 0; border-radius: 11px; padding: 6px 9px; }
            QLineEdit:focus, QTextEdit:focus { background: rgba(128,128,128,52); }
            QCheckBox { spacing: 6px; padding: 3px; }
            QScrollArea { border: 0; }
            QMenu { background: #25252c; color: white; }
            QMenu::item:selected { background: #494454; }''' % foreground)
        self.heading.setStyleSheet('color: %s; font-size: 11px; font-weight: 600;' % muted)
        if hasattr(self, 'note'):
            self.note.setStyleSheet('background: transparent; padding: 0;')
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        background, _, _, alpha = self.colors
        if self.kind == 'Clock' and self.face.design == 'Numeral':
            return  # The numeral face is itself the tile.
        if self.kind == 'Weather':
            background, alpha = '#28568a', 255
        color = QColor(background)
        color.setAlpha(alpha)
        if self.theme_name == 'macOS':
            painter.setBrush(color)
            painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        else:
            gradient = QLinearGradient(0, 0, self.width()*.6, self.height())
            gradient.setColorAt(0, color.lighter(103))
            gradient.setColorAt(1, color)
            painter.setBrush(gradient)
            painter.setPen(QPen(QColor(255, 255, 255, 48), .6))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), RADIUS, RADIUS)
        if self.kind == 'Note' and self.theme_name != 'macOS':
            painter.setPen(QPen(QColor(128, 128, 128, 50), 1))
            for y in range(47, self.height()-18, 25):
                painter.drawLine(20, y, self.width()-20, y)

    def restore_position(self):
        screens = QApplication.screens()
        x, y = self.config.get('x', 24), self.config.get('y', 80)
        screen = next((s for s in screens if s.availableGeometry().contains(x, y)), QApplication.primaryScreen())
        bounds = screen.availableGeometry()
        self.move(max(bounds.left(), min(x, bounds.right()-self.width()+1)),
                  max(bounds.top(), min(y, bounds.bottom()-self.height()+1)))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.notch.store.settings['desktop_locked']:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        elif event.button() == Qt.RightButton:
            self.options()

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None:
            self.drag_offset = None
            self.config.update(x=self.x(), y=self.y())
            self.notch.store.save()

    def options(self):
        menu = QMenu(self)
        if self.kind == 'Photo':
            menu.addAction('Change photo', self.choose_photo)
        if self.kind == 'Weather':
            fahrenheit = self.notch.store.settings.get('fahrenheit', False)
            menu.addAction('Show °C' if fahrenheit else 'Show °F', lambda: self.notch.set_weather_unit(not fahrenheit))
        if self.kind == 'Clock':
            faces = menu.addMenu('Clock face')
            for design in DESIGNS:
                faces.addAction(design, lambda d=design: self.set_design(d))
        styles = menu.addMenu('Style')
        for name in THEMES:
            styles.addAction(name, lambda n=name: self.set_theme(n))
        locked = self.notch.store.settings['desktop_locked']
        menu.addAction('Unlock positions' if locked else 'Lock positions', self.manager.toggle_lock)
        menu.addSeparator()
        menu.addAction('Remove widget', lambda: self.manager.remove(self.config['id']))
        menu.exec(self.mapToGlobal(self.rect().topRight()))

    def set_design(self, design):
        self.config['design'] = design
        self.face.design = design
        self.resize(*self.clock_size())
        self.face.update()
        self.notch.store.save()

    def set_theme(self, name):
        self.config['theme'] = name
        self.notch.store.save()
        self.apply_theme()

    def refresh(self):
        now = datetime.now()
        if self.kind == 'Clock':
            self.face.update()
        elif self.kind == 'Calendar':
            deadlines = self.notch.store.settings['deadlines']
            today = [r['title'] for r in deadlines if r['due'][:10] == now.strftime('%Y-%m-%d')]
            upcoming = [r['title'] for r in sorted(deadlines, key=lambda r:r['due']) if r['due'][:10] >= now.strftime('%Y-%m-%d')]
            events = self.notch.widget_data.get('Google Calendar', [])
            titles = [r[0] for r in events[:3]] if isinstance(events, list) else []
            following = [r for r in sorted(deadlines, key=lambda r: r['due']) if r['due'][:10] > now.strftime('%Y-%m-%d')]
            try:
                next_day = datetime.strptime(following[0]['due'][:10], '%Y-%m-%d') if following else now + timedelta(days=1)
            except ValueError:
                next_day = now + timedelta(days=1)
            self.info.data = {'today': today[0] if today else 'No Events Today', 'events': (titles+upcoming)[:3],
                              'next': next_day.strftime('%A, %d %b').upper()}
            self.info.update()
        elif self.kind == 'Weather':
            self.info.data = self.notch.widget_data.get('Weather', {})
            self.info.update()
        elif self.kind == 'Battery':
            self.info.refresh_battery()
            self.info.update()
        elif self.kind == 'Music':
            state = self.notch.media_state
            self.title.setText(state.get('title', 'Nothing playing'))
            self.artist.setText(state.get('artist', 'Start Spotify or Apple Music'))
            cover = state.get('artwork')
            if cover != self.art_bytes:
                self.art_bytes = cover
                pixmap = QPixmap()
                if cover:
                    pixmap.loadFromData(bytes(cover))
                self.art.setPixmap(pixmap)
            for name, control in self.controls.items():
                icon = 'pause' if name == 'play' and state.get('playing') else name
                control.setIcon(media_icon(icon, self.colors[1]))
                control.setEnabled(state.get('can_' + name, False))
        elif self.kind == 'To do':
            tasks = self.notch.store.settings['todos']
            signature = json.dumps(tasks)
            if signature == self.signature:
                return
            self.signature = signature
            while self.tasks.count():
                item = self.tasks.takeAt(0)
                if item.widget():
                    item.widget().hide()
                    item.widget().deleteLater()
            for index, task in enumerate(tasks):
                if task.get('done'):
                    continue
                check = QCheckBox()
                check.setText(check.fontMetrics().elidedText(task['text'], Qt.ElideRight, self.width()-78))
                check.setToolTip(task['text'])
                check.setChecked(task.get('done', False))
                check.toggled.connect(lambda value, i=index: self.toggle_task(i, value))
                self.tasks.addWidget(check)
            if not any(not task.get('done') for task in tasks):
                self.tasks.addWidget(plain('A clear desk. Add your first task below.'))
            self.tasks.addStretch()

    def toggle_task(self, index, value):
        self.notch.toggle_todo(index, value)
        if 'To do' in self.notch.store.settings['enabled']:
            self.notch.build_todos()

    def add_task(self):
        text = self.task_input.text().strip()
        if text:
            self.notch.store.settings['todos'].append({'text': text, 'done': False})
            self.notch.store.save()
            self.task_input.clear()
            if 'To do' in self.notch.store.settings['enabled']:
                self.notch.build_todos()
            self.refresh()

    def save_note(self):
        self.config['text'] = self.note.toPlainText()[:20000]
        self.notch.store.save()

    def choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose a desktop photo', '', 'Images (*.png *.jpg *.jpeg *.webp)')
        if path:
            self.config['path'] = path
            self.notch.store.save()
            self.load_photo()

    def load_photo(self):
        pixmap = QPixmap(self.config.get('path', ''))
        self.choose_button.setVisible(pixmap.isNull())
        if pixmap.isNull():
            self.photo.setText('A little inspiration.\nChoose a photo from your PC.')
        else:
            size = self.size()
            scaled = pixmap.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            cropped = scaled.copy((scaled.width()-size.width())//2, (scaled.height()-size.height())//2, size.width(), size.height())
            rounded = QPixmap(size)
            rounded.fill(Qt.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.Antialiasing)
            clip = QPainterPath()
            clip.addRoundedRect(QRectF(rounded.rect()), RADIUS, RADIUS)
            painter.setClipPath(clip)
            painter.drawPixmap(0, 0, cropped)
            painter.end()
            self.photo.setPixmap(rounded)


class DesktopManager:
    def __init__(self, notch):
        self.notch = notch
        self.windows = {}
        self.timer = QTimer(notch)
        self.timer.timeout.connect(self.refresh)
        self.sync()
        QApplication.instance().aboutToQuit.connect(self.flush)

    def sync(self):
        rows = self.notch.store.settings['desktop_widgets']
        ids = {row['id'] for row in rows}
        for identity in list(self.windows):
            if identity not in ids:
                window = self.windows.pop(identity)
                window.close()
                window.deleteLater()
        for row in rows[:20]:
            if row.get('kind') not in KINDS:
                continue
            if row['id'] not in self.windows:
                self.windows[row['id']] = DesktopTile(self, row)
                self.windows[row['id']].show()
            self.windows[row['id']].apply_theme()
        if self.windows:
            self.timer.start(1000)
        else:
            self.timer.stop()

    def add(self, kind, x=None, y=None, design=None, theme=None):
        if len(self.windows) >= 20:
            return
        bounds = QApplication.primaryScreen().availableGeometry()
        offset = len(self.windows) % 5 * 28
        self.notch.store.settings['desktop_widgets'].append({'id': uuid.uuid4().hex, 'kind': kind,
            'x': bounds.x() + GAP + offset if x is None else x,
            'y': bounds.y() + 80 + offset if y is None else y, 'design': design or 'Numeral', 'theme': theme})
        self.notch.store.save()
        self.sync()
        self.notch.refresh_widgets()
        self.notch.refresh_media()

    def add_layout(self, name):
        bounds = QApplication.primaryScreen().availableGeometry()
        left, top, right = bounds.left()+GAP, bounds.top()+80, bounds.right()-UNIT-GAP
        step = UNIT+GAP
        layouts = {'Reference desk': [('Battery', left, top), ('Clock', left+step, top), ('Weather', left+2*step, top), ('Calendar', left, top+step)],
                   'Focus desk': [('Clock', left, top), ('To do', left, top+step), ('Note', right, top)],
                   'Music desk': [('Music', left, top), ('Clock', right, top), ('Weather', right, top+step)],
                   'Daily desk': [('Clock', left, top), ('Calendar', left, top+step), ('To do', right, top)]}
        for kind, x, y in layouts[name]:
            self.add(kind, x, y)

    def remove(self, identity):
        self.notch.store.settings['desktop_widgets'] = [r for r in self.notch.store.settings['desktop_widgets'] if r['id'] != identity]
        self.notch.store.save()
        self.sync()

    def toggle_lock(self):
        self.notch.store.settings['desktop_locked'] = not self.notch.store.settings['desktop_locked']
        self.notch.store.save()

    def refresh(self):
        for window in self.windows.values():
            window.refresh()

    def flush(self):
        for window in self.windows.values():
            if window.kind == 'Note':
                window.save_note()
