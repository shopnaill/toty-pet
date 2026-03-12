"""
Pomodoro Timer Desktop Widget — floating timer with visual countdown arc.
"""
from PyQt6.QtCore import QTimer, QPoint, Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen
from PyQt6.QtWidgets import QWidget
from features.widget_position import save_widget_pos, restore_widget_pos


class PomodoroWidget(QWidget):
    """Translucent desktop widget showing Pomodoro countdown arc."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(160, 160)
        self._dragging = False
        self._drag_pos = QPoint()

        self._active = False
        self._is_break = False
        self._remaining = 0
        self._total = 1500  # 25 min default

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def show_at(self, pos: QPoint):
        saved = restore_widget_pos("pomodoro")
        self.move(QPoint(saved[0], saved[1]) if saved else pos)
        self.show()

    def set_state(self, active: bool, remaining: int, total: int, is_break: bool):
        """Update from the main pet's pomodoro system."""
        self._active = active
        self._remaining = remaining
        self._total = max(1, total)
        self._is_break = is_break
        self.update()

    def start_updates(self):
        self._timer.start(1000)

    def stop_updates(self):
        self._timer.stop()

    def _tick(self):
        if self._active and self._remaining > 0:
            self._remaining -= 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background circle
        p.setBrush(QColor(18, 18, 28, 210))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, w, h, w // 2, h // 2)

        # Arc
        margin = 15
        rect = QRectF(margin, margin, w - 2 * margin, h - 2 * margin)

        # Background arc
        pen = QPen(QColor(40, 40, 60), 6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        # Progress arc
        if self._active and self._total > 0:
            ratio = self._remaining / self._total
            color = QColor(166, 227, 161) if not self._is_break else QColor(137, 180, 250)
            pen = QPen(color, 6)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            span = int(ratio * 360 * 16)
            p.drawArc(rect, 90 * 16, span)

        # Center text
        p.setPen(QColor(220, 220, 240))
        if self._active:
            mins = self._remaining // 60
            secs = self._remaining % 60
            p.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{mins:02d}:{secs:02d}")

            # Label below
            label_rect = QRectF(0, h // 2 + 15, w, 20)
            p.setFont(QFont("Segoe UI", 8))
            p.setPen(QColor(160, 160, 180))
            label = "☕ Break" if self._is_break else "🍅 Focus"
            p.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter, label)
        else:
            p.setFont(QFont("Segoe UI", 12))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "🍅\nReady")

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
            save_widget_pos("pomodoro", self.x(), self.y())
        self._dragging = False
