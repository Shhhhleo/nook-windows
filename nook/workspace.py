"""Snippy's full-screen workspace: animated sky, collapsible chat library, chat bubbles, approvals."""
import math
import random
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import (QColor, QPainter, QPen, QPainterPath, QLinearGradient, QRadialGradient,
                           QPixmap, QShortcut, QKeySequence, QTextDocument)
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
                               QListWidget, QListWidgetItem, QScrollArea, QSizePolicy, QMessageBox, QMenu,
                               QPlainTextEdit, QAbstractItemView)

from .snippy import CloudFace, greeting

INK = '#14263b'
SIDEBAR_WIDTH = 276
FRAME_MS = 40  # ~25 frames per second while visible.
LOBES = [(0, 48, 100, 84), (50, 22, 90, 98), (111, 0, 110, 128), (187, 32, 100, 102), (245, 64, 92, 72), (65, 75, 206, 90)]


def mix(a, b, k):
    a, b = QColor(a), QColor(b)
    return QColor(round(a.red() + (b.red() - a.red()) * k), round(a.green() + (b.green() - a.green()) * k),
                  round(a.blue() + (b.blue() - a.blue()) * k))


def cloud_path():
    path = QPainterPath()
    for rect in LOBES:
        lobe = QPainterPath()
        lobe.addEllipse(QRectF(*rect))
        path = path.united(lobe)
    return path


class Sky:
    """Drifting parallax clouds over a slowly breathing gradient. Cached sprites keep painting cheap."""
    LAYERS = [(.42, 7, .5, 5, (.06, .42)), (.72, 15, .78, 4, (.22, .7)), (1.12, 28, .97, 3, (.66, .93))]

    def __init__(self):
        self.path = cloud_path()
        self.size = (0, 0)
        self.sprites = []
        self.clouds = []
        self.start = time.monotonic()

    def resize(self, width, height, ratio):
        if (width, height) == self.size or width < 10:
            return
        self.size = (width, height)
        rng = random.Random(11)
        self.sprites = [self.render(scale * max(width, 900) / 1600, ratio) for scale, *_ in self.LAYERS]
        self.clouds = []
        for layer, (_, _, _, count, band) in enumerate(self.LAYERS):
            sprite_width = self.sprites[layer].width() / ratio
            for index in range(count):
                x = -sprite_width + (width + sprite_width) * (index + rng.uniform(.1, .9)) / count
                self.clouds.append([layer, x, rng.uniform(*band) * height, rng.uniform(0, 6.28)])

    def render(self, scale, ratio):
        bounds = self.path.boundingRect()
        pixmap = QPixmap(int(bounds.width() * scale * ratio) + 4, int(bounds.height() * scale * ratio) + 4)
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(scale, scale)
        painter.setPen(Qt.NoPen)
        shade = QLinearGradient(0, 0, 30, 170)
        shade.setColorAt(0, QColor('#ffffff'))
        shade.setColorAt(.5, QColor('#f3f8ff'))
        shade.setColorAt(1, QColor('#bcd6f0'))
        painter.setBrush(shade)
        painter.drawPath(self.path)
        painter.end()
        return pixmap

    def step(self, seconds):
        width = self.size[0]
        for cloud in self.clouds:
            sprite = self.sprites[cloud[0]]
            cloud[1] += self.LAYERS[cloud[0]][1] * seconds
            if cloud[1] > width:
                cloud[1] = -sprite.width() / sprite.devicePixelRatio()

    def paint(self, painter, rect):
        t = time.monotonic() - self.start
        k = (math.sin(t / 45) + 1) / 2
        gradient = QLinearGradient(0, 0, 0, rect.height())
        gradient.setColorAt(0, mix('#5b95e2', '#76a6ee', k))
        gradient.setColorAt(.55, mix('#8dbbf0', '#9cc6f3', 1 - k))
        gradient.setColorAt(1, mix('#c4e1f6', '#d9ecfb', k))
        painter.fillRect(rect, gradient)
        glow = QRadialGradient(QPointF(rect.width() * (.8 + .03 * math.sin(t / 30)), rect.height() * .1), rect.width() * .38)
        glow.setColorAt(0, QColor(255, 255, 255, 95))
        glow.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillRect(rect, glow)
        for layer in range(len(self.LAYERS)):
            painter.setOpacity(self.LAYERS[layer][2])
            for cloud in self.clouds:
                if cloud[0] == layer:
                    bob = math.sin(t * .35 + cloud[3]) * (2 + layer * 2)
                    painter.drawPixmap(QPointF(cloud[1], cloud[2] + bob), self.sprites[layer])
        painter.setOpacity(1)


class IconButton(QPushButton):
    """Painted icons: no emoji, crisp at any DPI."""

    def __init__(self, icon, tip, size=34, dark=False):
        super().__init__()
        self.icon_name = icon
        self.dark = dark
        self.setFixedSize(size, size)
        self.setToolTip(tip)
        self.setAccessibleName(tip)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet('QPushButton { background: %s; border: 0; border-radius: %spx; } QPushButton:hover { background: %s; }'
                           ' QPushButton:disabled { background: #9fb3c9; }' % (
                               '#1f4f8f' if dark else 'transparent', size // 2 if dark else 9, '#173f73' if dark else 'rgba(20,38,59,22)'))

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor('white' if self.dark else INK)
        if not self.isEnabled():
            color.setAlpha(120)
        painter.setPen(QPen(color, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        name = self.icon_name
        if name == 'sidebar':
            painter.drawRoundedRect(QRectF(cx - 9, cy - 7.5, 18, 15), 3.5, 3.5)
            painter.drawLine(QPointF(cx - 3, cy - 7.5), QPointF(cx - 3, cy + 7.5))
        elif name == 'send':
            painter.drawLine(QPointF(cx, cy + 6), QPointF(cx, cy - 6))
            painter.drawLine(QPointF(cx - 5, cy - 1), QPointF(cx, cy - 6))
            painter.drawLine(QPointF(cx + 5, cy - 1), QPointF(cx, cy - 6))
        elif name == 'mic':
            painter.drawRoundedRect(QRectF(cx - 3.5, cy - 8, 7, 11), 3.5, 3.5)
            painter.drawArc(QRectF(cx - 6.5, cy - 5, 13, 11), 200 * 16, 140 * 16)
            painter.drawLine(QPointF(cx, cy + 6), QPointF(cx, cy + 8.5))
        elif name == 'plus':
            painter.drawLine(QPointF(cx - 6, cy), QPointF(cx + 6, cy))
            painter.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))
        elif name == 'close':
            painter.drawLine(QPointF(cx - 5, cy - 5), QPointF(cx + 5, cy + 5))
            painter.drawLine(QPointF(cx + 5, cy - 5), QPointF(cx - 5, cy + 5))
        elif name == 'bell':
            path = QPainterPath()
            path.moveTo(cx - 6, cy + 4)
            path.cubicTo(cx - 5, cy - 9, cx + 5, cy - 9, cx + 6, cy + 4)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(QPointF(cx - 1.5, cy + 7), QPointF(cx + 1.5, cy + 7))


class Bubble(QFrame):
    def __init__(self, role, text):
        super().__init__()
        self.role = role
        user = role == 'user'
        self.setObjectName('userBubble' if user else 'snippyBubble')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 11, 16, 11)
        self.label = QLabel()
        self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.label.setOpenExternalLinks(True)
        self.label.setTextFormat(Qt.PlainText if user else Qt.MarkdownText)
        layout.addWidget(self.label)
        self.limit = 640
        self.set_text(text)

    def set_limit(self, width):
        self.limit = width
        self.setMaximumWidth(width)
        self.fit()

    def set_text(self, text):
        self.label.setText(text)
        self.fit()

    def fit(self):
        """Word-wrapped labels collapse to narrow columns; size to the text's natural width instead."""
        self.label.ensurePolished()
        document = QTextDocument()
        document.setDefaultFont(self.label.font())
        if self.role == 'user':
            document.setPlainText(self.label.text())
        else:
            document.setMarkdown(self.label.text())
        inner = self.limit - 32
        document.setTextWidth(inner)
        self.label.setMinimumWidth(min(inner, int(document.idealWidth()) + 6))

    def text(self):
        return self.label.text()


class ApprovalCard(QFrame):
    def __init__(self, workspace):
        super().__init__()
        self.workspace = workspace
        self.request = None
        self.setObjectName('approvalCard')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(8)
        self.title = QLabel()
        self.title.setStyleSheet('font-size: 15px; font-weight: 700;')
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.detail = QPlainTextEdit()
        self.detail.setMaximumHeight(170)
        layout.addWidget(self.detail)
        self.note = QLabel()
        self.note.setStyleSheet('color: #46607d; font-size: 12px;')
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        row = QHBoxLayout()
        row.addStretch()
        self.decline = QPushButton('Don’t send')
        self.decline.clicked.connect(lambda: self.answer(False))
        row.addWidget(self.decline)
        self.approve = QPushButton('Approve')
        self.approve.setObjectName('approve')
        self.approve.clicked.connect(lambda: self.answer(True))
        row.addWidget(self.approve)
        layout.addLayout(row)
        self.hide()

    def show_request(self, request, waiting):
        self.request = request
        if not request:
            self.hide()
            return
        editable = request['kind'] in ('whatsapp', 'whatsapp-draft')
        self.title.setText(request['title'])
        self.detail.setPlainText(request['detail'])
        self.detail.setReadOnly(not editable)
        labels = {'email': ('Send email', 'Don’t send'), 'file': ('Create file', 'Cancel'),
                  'whatsapp': ('Send message', 'Don’t send'), 'whatsapp-draft': ('Send reply', 'Skip')}
        approve, decline = labels.get(request['kind'], ('Approve', 'Decline'))
        self.approve.setText(approve)
        self.decline.setText(decline)
        self.note.setText(('You can edit the message before sending. ' if editable else '') +
                          ('%s more waiting.' % (waiting - 1) if waiting > 1 else ''))
        self.show()

    def answer(self, approved):
        if self.request:
            request, self.request = self.request, None
            self.workspace.approvals.answer(request, approved, self.detail.toPlainText().strip() if not self.detail.isReadOnly() else None)


class FullscreenChat(QWidget):
    def __init__(self, snippy):
        super().__init__()
        self.snippy = snippy
        self.owner = snippy.owner
        self.approvals = self.owner.approvals
        self.error = ''
        self.stream_bubble = None
        self.peeking = False
        self.sky = Sky()
        self.last_frame = time.monotonic()
        self.setWindowTitle('Snippy')
        self.setObjectName('snippyWorkspace')
        self.setMouseTracking(True)
        self.setStyleSheet('''
            QWidget#snippyWorkspace { color: %(ink)s; }
            QWidget#snippyWorkspace QLabel { color: %(ink)s; background: transparent; }
            QFrame#sidebar { background: rgba(255,255,255,150); border-right: 1px solid rgba(255,255,255,190); }
            QFrame#sidebar QLabel#brand { font-size: 19px; font-weight: 700; }
            QFrame#sidebar QLabel#caption { color: #4a6482; font-size: 12px; font-weight: 600; }
            QPushButton#newChat { background: #1f4f8f; color: white; border: 0; border-radius: 12px; padding: 10px 14px; font-weight: 600; text-align: left; }
            QPushButton#newChat:hover { background: #173f73; }
            QPushButton#side { background: transparent; color: %(ink)s; border: 0; border-radius: 10px; padding: 9px 12px; text-align: left; font-weight: 600; }
            QPushButton#side:hover { background: rgba(20,38,59,20); }
            QLineEdit#filter { background: rgba(255,255,255,200); color: %(ink)s; border: 1px solid rgba(20,38,59,25); border-radius: 10px; padding: 8px 10px; }
            QListWidget#library { background: transparent; border: 0; color: %(ink)s; outline: 0; font-weight: 500; }
            QListWidget#library::item { padding: 9px 10px; border-radius: 9px; margin: 1px 0; }
            QListWidget#library::item:hover { background: rgba(20,38,59,18); }
            QListWidget#library::item:selected { background: rgba(31,79,143,40); color: %(ink)s; }
            QFrame#userBubble { background: #1f4f8f; border-radius: 18px; }
            QFrame#userBubble QLabel { color: white; font-size: 15px; font-weight: 500; }
            QFrame#snippyBubble { background: rgba(255,255,255,235); border-radius: 18px; }
            QFrame#snippyBubble QLabel { color: %(ink)s; font-size: 15px; font-weight: 500; }
            QFrame#composer { background: rgba(255,255,255,245); border: 1px solid rgba(255,255,255,255); border-radius: 26px; }
            QFrame#composer QLineEdit { background: transparent; border: 0; padding: 8px 6px; color: %(ink)s; font-size: 16px; font-weight: 500; }
            QFrame#approvalCard { background: rgba(255,255,255,245); border: 2px solid #1f4f8f; border-radius: 18px; }
            QFrame#approvalCard QPlainTextEdit { background: #f3f7fc; color: %(ink)s; border: 0; border-radius: 10px; padding: 8px; font-size: 14px; }
            QFrame#approvalCard QPushButton { background: #e7eef7; color: %(ink)s; border: 0; border-radius: 11px; padding: 9px 16px; font-weight: 600; }
            QFrame#approvalCard QPushButton#approve { background: #1f4f8f; color: white; }
            QPushButton#pill { background: rgba(255,255,255,170); color: %(ink)s; border: 0; border-radius: 13px; padding: 7px 14px; font-weight: 600; }
            QPushButton#pill:hover { background: rgba(255,255,255,230); }
            QLineEdit#nameInput { background: white; color: %(ink)s; border: 0; border-radius: 18px; padding: 16px; font-size: 16px; }
            QListWidget#extras { background: rgba(255,255,255,225); color: %(ink)s; border: 0; border-radius: 14px; padding: 8px; }
            QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: 0; }
            QScrollBar:vertical { background: transparent; width: 8px; }
            QScrollBar::handle:vertical { background: rgba(20,38,59,60); border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        ''' % {'ink': INK})
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.build_sidebar())
        root.addWidget(self.build_main(), 1)
        self.edge = QWidget(self)  # Hover the left edge to peek at the chat library.
        self.edge.setFixedWidth(8)
        self.edge.setMouseTracking(True)
        self.edge.installEventFilter(self)
        self.sidebar.installEventFilter(self)
        self.slide = QPropertyAnimation(self.sidebar, b'maximumWidth', self)
        self.slide.setDuration(200)
        self.slide.setEasingCurve(QEasingCurve.OutCubic)
        pinned = self.owner.store.settings.get('snippy_sidebar', True)
        self.sidebar.setMaximumWidth(SIDEBAR_WIDTH if pinned else 0)
        self.open_sidebar.setVisible(not pinned)
        self.frame = QTimer(self)
        self.frame.setInterval(FRAME_MS)
        self.frame.timeout.connect(self.tick)
        self.approvals.changed.connect(self.refresh_approval)
        QShortcut(QKeySequence('Escape'), self, activated=self.close)
        QShortcut(QKeySequence('Ctrl+B'), self, activated=self.toggle_sidebar)
        QShortcut(QKeySequence('Ctrl+N'), self, activated=self.clear)

    # ------------------------------------------------------------------ construction
    def build_sidebar(self):
        self.sidebar = QFrame()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setMinimumWidth(0)
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(16, 18, 14, 16)
        layout.setSpacing(10)
        head = QHBoxLayout()
        brand = QLabel('Snippy')
        brand.setObjectName('brand')
        head.addWidget(brand)
        head.addStretch()
        self.collapse_button = IconButton('sidebar', 'Hide chat library (Ctrl+B)')
        self.collapse_button.clicked.connect(self.toggle_sidebar)
        head.addWidget(self.collapse_button)
        layout.addLayout(head)
        new_chat = QPushButton('New chat')
        new_chat.setObjectName('newChat')
        new_chat.setCursor(Qt.PointingHandCursor)
        new_chat.clicked.connect(self.clear)
        layout.addWidget(new_chat)
        self.filter = QLineEdit()
        self.filter.setObjectName('filter')
        self.filter.setPlaceholderText('Search chats')
        self.filter.textChanged.connect(self.refresh_library)
        layout.addWidget(self.filter)
        caption = QLabel('Recent chats')
        caption.setObjectName('caption')
        layout.addWidget(caption)
        self.library = QListWidget()
        self.library.setObjectName('library')
        self.library.setAccessibleName('Saved conversations')
        self.library.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.library.setTextElideMode(Qt.ElideRight)
        self.library.setSelectionMode(QAbstractItemView.SingleSelection)
        self.library.itemClicked.connect(self.select_chat)
        self.library.setContextMenuPolicy(Qt.CustomContextMenu)
        self.library.customContextMenuRequested.connect(self.library_menu)
        layout.addWidget(self.library, 1)
        self.inbox_button = QPushButton('Notifications')
        self.inbox_button.setObjectName('side')
        self.inbox_button.clicked.connect(self.toggle_inbox)
        layout.addWidget(self.inbox_button)
        settings = QPushButton('Settings')
        settings.setObjectName('side')
        settings.clicked.connect(self.owner.open_settings)
        layout.addWidget(settings)
        back = QPushButton('Back to desktop')
        back.setObjectName('side')
        back.clicked.connect(self.close)
        layout.addWidget(back)
        return self.sidebar

    def build_main(self):
        main = QWidget()
        outer = QVBoxLayout(main)
        outer.setContentsMargins(22, 16, 22, 18)
        outer.setSpacing(0)
        top = QHBoxLayout()
        self.open_sidebar = IconButton('sidebar', 'Show chat library (Ctrl+B)')
        self.open_sidebar.clicked.connect(self.toggle_sidebar)
        top.addWidget(self.open_sidebar)
        top.addStretch()
        self.engine_pill = QPushButton('')
        self.engine_pill.setObjectName('pill')
        self.engine_pill.setToolTip('Change Snippy’s brain in Settings → Assistant')
        self.engine_pill.clicked.connect(self.owner.open_settings)
        top.addWidget(self.engine_pill)
        close = IconButton('close', 'Back to desktop (Esc)')
        close.clicked.connect(self.close)
        top.addWidget(close)
        outer.addLayout(top)
        column_row = QHBoxLayout()
        column_row.addStretch(1)
        self.column = QWidget()
        self.column.setMaximumWidth(860)
        column_row.addWidget(self.column, 12)
        column_row.addStretch(1)
        outer.addLayout(column_row, 1)
        content = QVBoxLayout(self.column)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(14)
        self.content_layout = content
        self.spring_top = QWidget()
        self.spring_top.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        content.addWidget(self.spring_top)
        self.welcome = QWidget()
        welcome = QVBoxLayout(self.welcome)
        welcome.setSpacing(16)
        self.face = CloudFace(self.owner, 110)
        welcome.addWidget(self.face, 0, Qt.AlignHCenter)
        self.heading = QLabel()
        self.heading.setTextFormat(Qt.PlainText)
        self.heading.setAlignment(Qt.AlignCenter)
        self.heading.setWordWrap(True)
        self.heading.setStyleSheet('font-size: 40px; font-weight: 700;')
        welcome.addWidget(self.heading)
        self.subheading = QLabel('Ask anything, search the web, or have me handle a task.')
        self.subheading.setAlignment(Qt.AlignCenter)
        self.subheading.setStyleSheet('font-size: 15px; font-weight: 500; color: #2c4562;')
        welcome.addWidget(self.subheading)
        self.name_input = QLineEdit()
        self.name_input.setObjectName('nameInput')
        self.name_input.setMaxLength(40)
        self.name_input.setPlaceholderText('Your name')
        self.name_input.setAccessibleName('Your name')
        self.name_input.returnPressed.connect(self.save_name)
        welcome.addWidget(self.name_input)
        self.continue_button = QPushButton('Meet Snippy')
        self.continue_button.setObjectName('pill')
        self.continue_button.clicked.connect(self.save_name)
        welcome.addWidget(self.continue_button, 0, Qt.AlignHCenter)
        content.addWidget(self.welcome)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.messages_widget = QWidget()
        self.messages = QVBoxLayout(self.messages_widget)
        self.messages.setContentsMargins(4, 8, 10, 8)
        self.messages.setSpacing(12)
        self.messages.addStretch()
        self.scroll.setWidget(self.messages_widget)
        self.scroll.verticalScrollBar().rangeChanged.connect(lambda _, high: self.scroll.verticalScrollBar().setValue(high))
        content.addWidget(self.scroll, 1)
        self.inbox = QListWidget()
        self.inbox.setObjectName('extras')
        self.inbox.setAccessibleName('Recent Windows notifications')
        self.inbox.setMaximumHeight(160)
        self.inbox.hide()
        content.addWidget(self.inbox)
        self.results = QListWidget()
        self.results.setObjectName('extras')
        self.results.setMaximumHeight(130)
        self.results.itemClicked.connect(self.owner.assistant_panel.open_result)
        self.results.hide()
        content.addWidget(self.results)
        extras = QHBoxLayout()
        self.web = QPushButton('Look up this topic')
        self.web.setObjectName('pill')
        self.web.clicked.connect(self.owner.assistant_panel.web_action)
        self.web.hide()
        extras.addWidget(self.web)
        self.apply_button = QPushButton('Create this file')
        self.apply_button.setObjectName('pill')
        self.apply_button.clicked.connect(self.owner.assistant_panel.apply_proposal)
        self.apply_button.hide()
        extras.addWidget(self.apply_button)
        extras.addStretch()
        content.addLayout(extras)
        self.approval = ApprovalCard(self)
        content.addWidget(self.approval)
        self.composer = QFrame()
        self.composer.setObjectName('composer')
        row = QHBoxLayout(self.composer)
        row.setContentsMargins(18, 8, 8, 8)
        row.setSpacing(6)
        self.input = QLineEdit()
        self.input.setMaxLength(4000)
        self.input.setPlaceholderText('Message Snippy…')
        self.input.setAccessibleName('Message Snippy')
        self.input.setMinimumHeight(44)
        self.input.returnPressed.connect(self.send)
        row.addWidget(self.input, 1)
        self.voice = IconButton('mic', 'Talk once (review before sending)', 38)
        self.voice.clicked.connect(self.owner.assistant_panel.listen)
        row.addWidget(self.voice)
        self.send_button = IconButton('send', 'Send', 40, dark=True)
        self.send_button.clicked.connect(self.send)
        row.addWidget(self.send_button)
        content.addWidget(self.composer)
        self.status = QLabel('')
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet('font-size: 12px; font-weight: 600; color: #2c4562;')
        content.addWidget(self.status)
        self.spring_bottom = QWidget()
        self.spring_bottom.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        content.addWidget(self.spring_bottom)
        return main

    # ------------------------------------------------------------------ sky animation
    def animated(self):
        return self.owner.store.settings.get('animation', True)

    def tick(self):
        now = time.monotonic()
        self.sky.step(min(now - self.last_frame, .2))
        self.last_frame = now
        self.update()

    def showEvent(self, event):
        self.last_frame = time.monotonic()
        if self.animated():
            self.frame.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.frame.stop()
        super().hideEvent(event)

    def resizeEvent(self, event):
        self.sky.resize(self.width(), self.height(), self.devicePixelRatioF())
        self.edge.setGeometry(0, 0, 8, self.height())
        self.edge.raise_()
        self.fit_bubbles()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        self.sky.resize(self.width(), self.height(), self.devicePixelRatioF())
        self.sky.paint(painter, self.rect())

    # ------------------------------------------------------------------ sidebar
    def sidebar_pinned(self):
        return self.owner.store.settings.get('snippy_sidebar', True)

    def animate_sidebar(self, open_):
        self.slide.stop()
        self.slide.setStartValue(self.sidebar.maximumWidth())
        self.slide.setEndValue(SIDEBAR_WIDTH if open_ else 0)
        if self.animated():
            self.slide.start()
        else:
            self.sidebar.setMaximumWidth(SIDEBAR_WIDTH if open_ else 0)

    def toggle_sidebar(self):
        pinned = not (self.sidebar_pinned() and not self.peeking)
        self.peeking = False
        self.owner.store.settings['snippy_sidebar'] = pinned
        self.owner.store.save()
        self.open_sidebar.setVisible(not pinned)
        self.animate_sidebar(pinned)

    def eventFilter(self, watched, event):
        if watched is self.edge and event.type() == QEvent.Enter and not self.sidebar_pinned() and self.sidebar.maximumWidth() == 0:
            self.peeking = True
            self.animate_sidebar(True)
        elif watched is self.sidebar and event.type() == QEvent.Leave and self.peeking:
            self.peeking = False
            self.animate_sidebar(False)
        return super().eventFilter(watched, event)

    def refresh_library(self, *_):
        engine = self.owner.assistant_panel
        query = self.filter.text().strip().casefold()
        self.library.blockSignals(True)
        self.library.clear()
        for row in engine.archive.chats:
            if query and query not in row['title'].casefold():
                continue
            item = QListWidgetItem(row['title'])
            item.setData(Qt.UserRole, row['id'])
            item.setToolTip(row['title'] + '\n' + self.when(row.get('updated')))
            self.library.addItem(item)
            if row['id'] == engine.chat_id:
                item.setSelected(True)
                self.library.setCurrentItem(item)
        self.library.blockSignals(False)

    @staticmethod
    def when(stamp):
        try:
            moment = datetime.fromisoformat(stamp)
        except (TypeError, ValueError):
            return ''
        return moment.strftime('%d %b %Y, %H:%M')

    def select_chat(self, item):
        if isinstance(item, int):
            item = self.library.item(item)
        if item is None:
            return
        if self.snippy.busy:
            self.refresh_library()
            return
        identity = item.data(Qt.UserRole)
        if identity:
            self.owner.assistant_panel.load_chat(identity)
            self.error = ''
            self.results.clear()
            self.apply_button.hide()
            self.prepare()

    def library_menu(self, point):
        item = self.library.itemAt(point)
        if not item:
            return
        menu = QMenu(self)
        menu.addAction('Open', lambda: self.select_chat(item))
        menu.addAction('Delete chat', lambda: self.delete_chat(item.data(Qt.UserRole)))
        menu.exec(self.library.mapToGlobal(point))

    def delete_chat(self, identity=None):
        engine = self.owner.assistant_panel
        identity = identity or engine.chat_id
        if engine.busy or not identity:
            return
        if QMessageBox.question(self, 'Delete conversation', 'Delete this saved conversation from this PC?') == QMessageBox.Yes:
            engine.archive.delete(identity)
            if identity == engine.chat_id:
                self.clear()
            else:
                self.refresh_library()

    # ------------------------------------------------------------------ conversation view
    def prepare(self):
        self.refresh_library()
        settings = self.owner.store.settings
        known = bool(settings.get('user_name'))
        self.name_input.setVisible(not known)
        self.continue_button.setVisible(not known)
        self.composer.setVisible(known)
        self.subheading.setVisible(known)
        engine = self.owner.assistant_panel
        self.web.setVisible(known and bool(engine.web_query or engine.confirm_query))
        self.results.setVisible(known and self.results.count() > 0)
        if known:
            index = settings.get('greeting_index', 0)
            self.heading.setText(greeting(settings['user_name'], datetime.now(), index))
            settings['greeting_index'] = index + 1
            self.owner.store.save()
        else:
            self.heading.setText('What should I call you?')
        from . import brain
        cloud = brain.available(self.owner.store)
        model = next((name for name, value in brain.MODELS.items() if value == brain.model_id(self.owner.store)), 'Claude')
        self.engine_pill.setText(model + ' · live web' if cloud else 'Local AI · add a Claude key for live answers')
        self.refresh_transcript()
        self.refresh_approval()

    def clear_messages(self):
        while self.messages.count() > 1:
            item = self.messages.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                item.layout().deleteLater()
        self.stream_bubble = None

    def add_bubble(self, role, text):
        bubble = Bubble(role, text)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        if role == 'user':
            row.addStretch()
            row.addWidget(bubble)
        else:
            row.addWidget(bubble)
            row.addStretch()
        self.messages.insertLayout(self.messages.count() - 1, row)
        bubble.set_limit(self.bubble_width())
        return bubble

    def bubble_width(self):
        return max(260, int(min(self.column.width() or 760, 860) * .82))

    def fit_bubbles(self):
        width = self.bubble_width()
        for bubble in self.messages_widget.findChildren(Bubble):
            bubble.set_limit(width)

    def set_conversation_mode(self, active):
        self.welcome.setVisible(not active)
        self.scroll.setVisible(active)
        self.spring_top.setVisible(not active)
        self.spring_bottom.setVisible(not active)

    def refresh_transcript(self):
        rows = self.owner.assistant_panel.history
        known = bool(self.owner.store.settings.get('user_name'))
        self.clear_messages()
        for row in rows:
            self.add_bubble('user' if row['role'] == 'user' else 'assistant', row['content'])
        if self.error:
            self.add_bubble('assistant', self.error)
        self.set_conversation_mode(known and bool(rows or self.error))

    def transcript_text(self):
        return '\n'.join(bubble.text() for bubble in self.messages_widget.findChildren(Bubble))

    def add_user_message(self, text):
        self.set_conversation_mode(True)
        self.add_bubble('user', text)
        self.stream_bubble = self.add_bubble('assistant', '…')

    def stream(self, text):
        if self.stream_bubble is None:
            self.set_conversation_mode(True)
            self.stream_bubble = self.add_bubble('assistant', text)
        else:
            self.stream_bubble.set_text(text)

    def refresh_approval(self):
        self.approval.show_request(self.approvals.current(), len(self.approvals.pending))
        if self.approval.isVisible():
            self.set_conversation_mode(True) if self.owner.assistant_panel.history else None

    # ------------------------------------------------------------------ actions
    def save_name(self):
        name = self.name_input.text().strip()
        if not name:
            self.name_input.setFocus()
            return
        self.owner.store.settings['user_name'] = name
        self.owner.store.save()
        self.prepare()
        self.input.setFocus()
        self.snippy.prepare_model()

    def toggle_inbox(self):
        self.inbox.setVisible(not self.inbox.isVisible())
        if self.inbox.isVisible() and not self.snippy.alerts:
            self.inbox.clear()
            self.inbox.addItem('No new notifications. Connect in Settings → Assistant.')

    def send(self):
        if self.snippy.busy:
            return
        text = self.input.text().strip()
        if text:
            self.input.clear()
            self.snippy.submit(text)

    def clear(self):
        if not self.snippy.busy:
            self.owner.assistant_panel.clear_chat()
            self.results.clear()
            self.error = ''
            self.prepare()
            self.input.setFocus()

    def closeEvent(self, event):
        self.hide()
        self.snippy.wake()
        self.snippy.show()
        self.snippy.follow()
        if self.snippy.busy and self.owner.store.settings['animation']:
            self.snippy.roam_timer.start()
            self.snippy.roam()
        event.ignore()
