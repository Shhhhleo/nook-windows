"""Resolution-independent notch artwork and media controls."""
from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap, QIcon
from PySide6.QtWidgets import QLabel, QWidget


def media_icon(name, color='#f4f4f5'):
    pixmap = QPixmap(72, 72)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(3, 3)
    painter.setPen(QPen(QColor(color), 1.65, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QColor(color))
    def triangle(x, backwards=False):
        path = QPainterPath()
        path.moveTo(x + (8 if backwards else 0), 5)
        path.lineTo(x if backwards else x + 8, 12)
        path.lineTo(x + (8 if backwards else 0), 19)
        path.closeSubpath()
        painter.drawPath(path)
    if name == 'play':
        triangle(9)
    elif name == 'pause':
        painter.drawRoundedRect(QRectF(6, 5, 4, 14), 1, 1)
        painter.drawRoundedRect(QRectF(14, 5, 4, 14), 1, 1)
    elif name in ('previous', 'next'):
        triangle(3, name == 'previous')
        triangle(12, name == 'previous')
    elif name.startswith('repeat'):
        painter.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(4, 10); path.lineTo(4, 8); path.quadTo(4, 5, 7, 5); path.lineTo(20, 5)
        path.moveTo(17, 2); path.lineTo(20, 5); path.lineTo(17, 8)
        path.moveTo(20, 14); path.lineTo(20, 16); path.quadTo(20, 19, 17, 19); path.lineTo(4, 19)
        path.moveTo(7, 16); path.lineTo(4, 19); path.lineTo(7, 22)
        painter.drawPath(path)
        if name == 'repeat-one':
            painter.drawLine(11, 10, 13, 9)
            painter.drawLine(13, 9, 13, 15)
    elif name == 'settings':
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(4, 4, 16, 16))
        painter.drawEllipse(QRectF(9, 9, 6, 6))
        for angle in range(0, 360, 45):
            painter.save(); painter.translate(12, 12); painter.rotate(angle)
            painter.drawLine(0, -8, 0, -10); painter.restore()
    elif name == 'pin':
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(8, 4, 16, 4); painter.drawLine(9, 4, 9, 11)
        painter.drawLine(15, 4, 15, 11); painter.drawLine(9, 11, 6, 15)
        painter.drawLine(15, 11, 18, 15); painter.drawLine(6, 15, 18, 15)
        painter.drawLine(12, 15, 12, 22)
    else:
        for x, height in [(5, 6), (10, 14), (15, 10), (20, 5)]:
            painter.drawRoundedRect(QRectF(x, (24-height)/2, 2, height), 1, 1)
    painter.end()
    return QIcon(pixmap)


class TrackLabel(QLabel):
    """Elide at paint time, so long song names never resize the notch."""
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setMinimumWidth(0)

    def minimumSizeHint(self):
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self):
        return QSize(100, super().sizeHint().height())

    def setText(self, text):
        super().setText(text)
        self.setToolTip(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().windowText().color())
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignVCenter | Qt.AlignLeft,
                         self.fontMetrics().elidedText(self.text(), Qt.ElideRight, self.width()))


class AlbumArt(QWidget):
    def __init__(self, size):
        super().__init__()
        self.setFixedSize(size, size)
        self.cover = QPixmap()

    def setPixmap(self, pixmap):
        self.cover = pixmap
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), self.width() / 8, self.width() / 8)
        painter.setClipPath(path)
        painter.fillRect(self.rect(), QColor('#202023'))
        if not self.cover.isNull():
            scaled = self.cover.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap((self.width()-scaled.width())//2, (self.height()-scaled.height())//2, scaled)
        else:
            media_icon('wave', '#77777d').paint(painter, self.rect().adjusted(6, 6, -6, -6))
