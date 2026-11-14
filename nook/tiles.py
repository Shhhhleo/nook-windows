"""Reference-inspired native tiles. Every displayed measurement comes from real data."""
from datetime import datetime
import psutil
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QLinearGradient
from PySide6.QtWidgets import QWidget


class InfoFace(QWidget):
    def __init__(self, kind):
        super().__init__()
        self.kind, self.data = kind, {}
        self.ink = '#f7f7f8'
        self.muted = '#b6b6ba'
        self.setMinimumSize(100, 100)
        self.battery = None
        self.last_battery = 0

    def refresh_battery(self):
        import time
        if time.monotonic()-self.last_battery > 30:
            self.last_battery = time.monotonic()
            self.battery = psutil.sensors_battery()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(self.width()/ (468 if self.kind == 'Calendar' else 222), self.height()/222)
        def text(x, y, w, h, value, size=14, color=None, weight=QFont.DemiBold):
            p.setPen(QColor(color or ('white' if self.kind == 'Weather' else self.ink))); p.setFont(QFont('Segoe UI', size, weight))
            clipped = p.fontMetrics().elidedText(str(value), Qt.ElideRight, int(w))
            p.drawText(QRectF(x,y,w,h), Qt.AlignLeft | Qt.AlignVCenter, clipped)
        if self.kind == 'Weather':
            gradient = QLinearGradient(0,0,80,220)
            gradient.setColorAt(0, QColor('#183b71')); gradient.setColorAt(1, QColor('#508ac2'))
            p.setBrush(gradient); p.setPen(QPen(QColor('#83a8d0'),1))
            p.drawRoundedRect(QRectF(.5,.5,221,221),22,22)
            data = self.data
            if not isinstance(data, dict) or 'temperature' not in data:
                text(22,22,180,28,'Weather',18)
                text(22,65,180,30,'Connect a location',12)
                text(22,110,180,30,'Settings → Connections',10)
                return
            text(22,17,180,30,data['name'],17)
            text(20,45,190,70,f"{data['temperature']:g}°",46,weight=QFont.Normal)
            p.setPen(Qt.NoPen); p.setBrush(QColor('#ffce35'))
            p.drawEllipse(QRectF(33,131,19,19))
            p.setBrush(QColor('white'))
            p.drawEllipse(QRectF(22,140,20,15)); p.drawEllipse(QRectF(31,136,18,20))
            if data.get('code',0) > 3:
                p.setPen(QPen(QColor('#b6dcff'),2))
                for x in (28,38,48): p.drawLine(x,158,x-3,165)
            text(22,164,184,24,data['condition'],14)
            high, low = data.get('high'),data.get('low')
            text(22,188,175,20,f'H:{high:g}°  L:{low:g}°' if high is not None and low is not None else 'Forecast unavailable',12)
        elif self.kind == 'Calendar':
            now = datetime.now()
            text(24,22,190,22,now.strftime('%A').upper(),11,'#ff565e')
            text(24,44,170,56,str(now.day),38,weight=QFont.Normal)
            text(24,150,200,28,self.data.get('today','No Events Today'),11,self.muted)
            text(262,22,190,20,self.data.get('next',''),10,self.muted)
            events = self.data.get('events',[])[:4]
            if not events:
                text(262,48,190,24,'No connected events',11,self.muted)
            for i,title in enumerate(events):
                p.setPen(Qt.NoPen); p.setBrush(QColor('#47374d'))
                p.drawRoundedRect(QRectF(258,48+i*34,186,27),8,8)
                text(268,48+i*34,170,27,title,11,'#d78be8')
        elif self.kind == 'Battery':
            for i in range(4):
                x,y = 15+(i%2)*104, 15+(i//2)*104
                p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor('#3a3a3e'),8,Qt.SolidLine,Qt.RoundCap))
                p.drawEllipse(QRectF(x,y,88,88))
                if i == 0 and self.battery:
                    p.setPen(QPen(QColor('#2cce56'),8,Qt.SolidLine,Qt.RoundCap))
                    p.drawArc(QRectF(x,y,88,88),90*16,-int(self.battery.percent*3.6*16))
                if i == 0:
                    p.setBrush(Qt.NoBrush); p.setPen(QPen(QColor(self.ink),2.4,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
                    p.drawRoundedRect(QRectF(x+29,y+29,30,20),3,3)
                    p.drawLine(x+24,y+57,x+64,y+57)
                    if self.battery:
                        text(x+14,y+60,60,18,f'{self.battery.percent:g}%',8,self.muted)
                    else:
                        text(x+14,y+60,60,18,'AC',8,self.muted)
            self.setToolTip('PC battery' if self.battery else 'No battery reported by Windows. Empty rings are unconnected devices.')
