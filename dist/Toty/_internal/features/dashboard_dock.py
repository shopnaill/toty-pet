"""
Dashboard Dock — unified vertical sidebar that docks all desktop widgets
(system monitor, quick notes, pomodoro, prayer, music) into one draggable bar.
"""
from PyQt6.QtCore import QPoint, Qt, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QLinearGradient
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QScrollArea, QFrame,
    QHBoxLayout, QGraphicsOpacityEffect,
)
from features.widget_position import save_widget_pos, restore_widget_pos


class _DockSlot(QFrame):
    """A container slot that holds a child widget in the dock."""

    def __init__(self, title: str, widget: QWidget | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 4)
        layout.setSpacing(2)

        # Header
        hdr = QHBoxLayout()
        lbl = QLabel(title)
        lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        lbl.setStyleSheet("color: #89b4fa; background: transparent;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self._toggle_btn = QPushButton("—")
        self._toggle_btn.setFixedSize(18, 18)
        self._toggle_btn.setStyleSheet(
            "QPushButton { color: #888; background: rgba(60,60,80,120); border-radius: 9px;"
            " font-size: 10px; } QPushButton:hover { background: rgba(200,60,60,180); color: white; }")
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.clicked.connect(self._toggle_content)
        hdr.addWidget(self._toggle_btn)
        layout.addLayout(hdr)

        # Content area
        self._content = QFrame()
        self._content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        if widget:
            # Re-parent the widget into the dock slot
            widget.setParent(self._content)
            widget.setWindowFlags(Qt.WindowType.Widget)  # remove frameless/tool flags
            widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            widget.setStyleSheet(widget.styleSheet() + "; background: transparent;")
            content_layout.addWidget(widget)
            widget.show()
        layout.addWidget(self._content)
        self._collapsed = False

    def _toggle_content(self):
        self._collapsed = not self._collapsed
        self._content.setVisible(not self._collapsed)
        self._toggle_btn.setText("+" if self._collapsed else "—")


class DashboardDock(QWidget):
    """Floating vertical sidebar that groups all desktop widgets."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(240)
        self.setMinimumHeight(200)
        self._dragging = False
        self._drag_pos = QPoint()
        self._slots: dict[str, _DockSlot] = {}

        # Main layout
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(10, 10, 10, 10)
        self._root.setSpacing(6)

        # Title bar
        title_bar = QHBoxLayout()
        title_lbl = QLabel("📊 Dashboard")
        title_lbl.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_lbl.setStyleSheet("color: #cdd6f4; background: transparent;")
        title_bar.addWidget(title_lbl)
        title_bar.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "QPushButton { color: #aaa; background: rgba(60,60,80,150); border-radius: 11px; font-size: 14px; }"
            "QPushButton:hover { background: rgba(200,60,60,200); color: white; }")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.hide)
        title_bar.addWidget(close_btn)
        self._root.addLayout(title_bar)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(100,100,140,80);")
        self._root.addWidget(sep)

        # Scroll area for widget slots
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { width: 6px; background: transparent; }"
            "QScrollBar::handle:vertical { background: rgba(100,100,140,120); border-radius: 3px; }"
        )
        self._scroll_content = QWidget()
        self._scroll_layout = QVBoxLayout(self._scroll_content)
        self._scroll_layout.setContentsMargins(0, 0, 0, 0)
        self._scroll_layout.setSpacing(8)
        self._scroll_layout.addStretch()
        scroll.setWidget(self._scroll_content)
        self._root.addWidget(scroll)

    def add_widget(self, key: str, title: str, widget: QWidget):
        """Add a widget into the dock. If already present, replace it."""
        if key in self._slots:
            self.remove_widget(key)
        slot = _DockSlot(title, widget, self._scroll_content)
        self._slots[key] = slot
        # Insert before the stretch
        idx = max(0, self._scroll_layout.count() - 1)
        self._scroll_layout.insertWidget(idx, slot)
        self._adjust_height()

    def remove_widget(self, key: str):
        """Remove a widget from the dock."""
        slot = self._slots.pop(key, None)
        if slot:
            self._scroll_layout.removeWidget(slot)
            slot.deleteLater()
            self._adjust_height()

    def has_widget(self, key: str) -> bool:
        return key in self._slots

    def show_at(self, pos: QPoint):
        saved = restore_widget_pos("dashboard_dock")
        self.move(QPoint(saved[0], saved[1]) if saved else pos)
        self.show()

    def toggle(self, pos: QPoint | None = None):
        if self.isVisible():
            self.hide()
        else:
            if pos:
                self.move(pos)
            self.show()

    def _adjust_height(self):
        """Auto-size height based on content, capped at 600px."""
        total = 80  # title + margins
        for slot in self._slots.values():
            total += slot.sizeHint().height() + 8
        self.setFixedHeight(min(600, max(200, total)))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        p.setBrush(QColor(18, 18, 28, 220))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)

        # Left accent stripe
        accent = QLinearGradient(0, 0, 0, self.height())
        accent.setColorAt(0, QColor(137, 180, 250, 200))
        accent.setColorAt(0.5, QColor(203, 166, 247, 200))
        accent.setColorAt(1, QColor(166, 227, 161, 200))
        p.setBrush(QBrush(accent))
        p.drawRoundedRect(0, 10, 3, self.height() - 20, 2, 2)

        p.end()
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 40:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            save_widget_pos("dashboard_dock", self.x(), self.y())
        self._dragging = False
