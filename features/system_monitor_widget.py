"""
System Monitor Desktop Widget — shows CPU, RAM, disk on a floating panel.
"""
import psutil
from PyQt6.QtCore import QTimer, QPoint, Qt
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PyQt6.QtWidgets import QWidget
from features.widget_position import save_widget_pos, restore_widget_pos


class SystemMonitorWidget(QWidget):
    """Translucent desktop widget showing live system stats."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(200, 140)
        self._dragging = False
        self._drag_pos = QPoint()

        self._cpu = 0.0
        self._ram = 0.0
        self._disk = 0.0
        self._net_sent = 0
        self._net_recv = 0

        # Prime psutil CPU snapshot so first real read isn't 0%
        psutil.cpu_percent(interval=None)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(2000)
        self._refresh()

    def show_at(self, pos: QPoint):
        saved = restore_widget_pos("sys_monitor")
        self.move(QPoint(saved[0], saved[1]) if saved else pos)
        self.show()

    def _refresh(self):
        try:
            self._cpu = psutil.cpu_percent(interval=0)
            mem = psutil.virtual_memory()
            self._ram = mem.percent
            disk = psutil.disk_usage("/")
            self._disk = disk.percent
            net = psutil.net_io_counters()
            self._net_sent = net.bytes_sent
            self._net_recv = net.bytes_recv
        except Exception:
            pass
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.setBrush(QColor(18, 18, 28, 210))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)

        # Title
        p.setPen(QColor(200, 200, 220))
        p.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        p.drawText(12, 22, "🖥️ System Monitor")

        # Stats
        p.setFont(QFont("Segoe UI", 9))
        y = 42
        for label, value, color in [
            ("CPU", self._cpu, QColor(137, 180, 250)),
            ("RAM", self._ram, QColor(166, 227, 161)),
            ("Disk", self._disk, QColor(249, 226, 175)),
        ]:
            # Label
            p.setPen(QColor(180, 180, 200))
            p.drawText(12, y, f"{label}: {value:.0f}%")

            # Bar background
            bar_x, bar_y, bar_w, bar_h = 90, y - 10, 95, 10
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(40, 40, 60))
            p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 4, 4)

            # Bar fill
            fill_w = int(bar_w * value / 100)
            p.setBrush(color)
            p.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 4, 4)

            y += 26

        # Network
        p.setPen(QColor(160, 160, 180))
        p.setFont(QFont("Segoe UI", 8))
        sent_mb = self._net_sent / (1024 * 1024)
        recv_mb = self._net_recv / (1024 * 1024)
        p.drawText(12, y + 4, f"↑ {sent_mb:.0f} MB  ↓ {recv_mb:.0f} MB")

        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            save_widget_pos("sys_monitor", self.x(), self.y())
        self._dragging = False

    def stop(self):
        self._timer.stop()
