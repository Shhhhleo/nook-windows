"""Reference-inspired clock faces, painted at native resolution."""
import math
from datetime import datetime
from zoneinfo import ZoneInfo
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtWidgets import QWidget

DESIGNS = ('Numeral', 'Analog', 'Bold analog', 'World row', 'World grid')
CITIES = [('Cupertino', 'America/Los_Angeles'), ('Paris', 'Europe/Paris'),
          ('Cape Town', 'Africa/Johannesburg'), ('New York', 'America/New_York')]


class ClockFace(QWidget):
    def __init__(self, design='Numeral'):
        super().__init__()
        self.design = design
        self.setMinimumSize(100, 100)

    def face(self, painter, rect, moment, bold=False, dark=False, digital=False):
        painter.save()
        painter.translate(rect.center())
        painter.scale(rect.width()/200, rect.height()/200)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#333437' if dark else '#fafaf7'))
        painter.drawRoundedRect(QRectF(-100, -100, 200, 200), 32 if digital else 100, 32 if digital else 100)
        ink = QColor('#ececea' if dark else '#171719')
        for index in range(60):
            if bold and index % 5:
                continue
            painter.save()
            angle = math.radians(index*6)
            if digital:
                radius = 88/(abs(math.sin(angle))**4+abs(math.cos(angle))**4)**.25
            else:
                radius = 89
            painter.rotate(index*6)
            painter.setPen(QPen(QColor('#8a8b8c'), 5 if bold else 2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(QPointF(0, -radius), QPointF(0, -radius+(9 if index % 5 == 0 else 5)))
            painter.restore()
        painter.setPen(ink)
        if digital:
            font = QFont('Bahnschrift Condensed', 58, QFont.Black)
            painter.setFont(font)
            while painter.fontMetrics().horizontalAdvance(moment.strftime('%I:%M').lstrip('0')) > 168:
                font.setPointSize(font.pointSize()-1)
                painter.setFont(font)
            painter.drawText(QRectF(-90, -60, 180, 120), Qt.AlignCenter, moment.strftime('%I:%M').lstrip('0'))
        else:
            if not bold:
                painter.setFont(QFont('Segoe UI', 14, QFont.DemiBold))
                for number in range(1, 13):
                    angle = math.radians(number*30-90)
                    x, y = math.cos(angle)*67, math.sin(angle)*67
                    painter.drawText(QRectF(x-16, y-14, 32, 28), Qt.AlignCenter, str(number))
            for angle, length, width, color in [((moment.hour % 12 + moment.minute/60)*30, 48, 7, ink),
                    (moment.minute*6 + moment.second/10, 72, 5, ink),
                    (moment.second*6, 78, 2, QColor('#d98c2b'))]:
                painter.save()
                painter.rotate(angle)
                painter.setPen(QPen(color, width, Qt.SolidLine, Qt.RoundCap))
                painter.drawLine(QPointF(0, 12), QPointF(0, -length))
                painter.restore()
            painter.setBrush(ink)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(-4, -4, 8, 8))
        painter.restore()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.design.startswith('World'):
            columns = 4 if self.design == 'World row' else 2
            rows = 1 if columns == 4 else 2
            width, height = self.width()/columns, self.height()/rows
            for index, (city, zone) in enumerate(CITIES):
                x, y = (index % columns)*width, (index // columns)*height
                size = min(width-10, height-32)
                moment = datetime.now(ZoneInfo(zone))
                self.face(painter, QRectF(x+(width-size)/2, y, size, size), moment, dark=moment.hour < 6 or moment.hour >= 18)
                painter.setPen(self.palette().windowText().color())
                painter.setFont(QFont('Segoe UI', 8))
                painter.drawText(QRectF(x, y+size+4, width, 27), Qt.AlignCenter, city + '\n' + moment.strftime('%H:%M'))
        else:
            size = min(self.width(), self.height())-4
            self.face(painter, QRectF((self.width()-size)/2, (self.height()-size)/2, size, size),
                      datetime.now(), bold=self.design == 'Bold analog', digital=self.design == 'Numeral')
