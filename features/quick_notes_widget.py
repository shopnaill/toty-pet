"""
Quick Notes Desktop Widget — floating sticky-note pad.
"""
import json
import os
from PyQt6.QtCore import QPoint, Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout
from features.widget_position import save_widget_pos, restore_widget_pos

_NOTES_PATH = "quick_notes.json"


class QuickNotesWidget(QWidget):
    """Translucent floating notes widget."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(220, 260)
        self._dragging = False
        self._drag_pos = QPoint()

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)

        # Title bar
        title_bar = QHBoxLayout()
        from PyQt6.QtWidgets import QLabel
        title = QLabel("📝 Quick Notes")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #c8c8dc; background: transparent;")
        title_bar.addWidget(title)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "QPushButton { color: #aaa; background: rgba(60,60,80,150); border-radius: 11px; font-size: 14px; }"
            "QPushButton:hover { background: rgba(200,60,60,200); color: white; }")
        close_btn.clicked.connect(self.hide)
        title_bar.addWidget(close_btn)
        layout.addLayout(title_bar)

        # Text area
        self._text = QTextEdit()
        self._text.setFont(QFont("Segoe UI", 9))
        self._text.setStyleSheet(
            "QTextEdit { background: rgba(30,30,45,180); color: #e0e0e0;"
            " border: 1px solid rgba(100,100,140,80); border-radius: 8px; padding: 6px; }")
        self._text.setPlaceholderText("Type your notes here...")
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save)
        self._text.textChanged.connect(lambda: self._save_timer.start(1500))
        layout.addWidget(self._text)

        self._load()

    def show_at(self, pos: QPoint):
        saved = restore_widget_pos("quick_notes")
        self.move(QPoint(saved[0], saved[1]) if saved else pos)
        self.show()

    def _load(self):
        if os.path.exists(_NOTES_PATH):
            try:
                with open(_NOTES_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._text.setPlainText(data.get("text", ""))
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        try:
            from core.safe_json import safe_json_save
            safe_json_save({"text": self._text.toPlainText()}, _NOTES_PATH)
        except Exception:
            pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(18, 18, 28, 210))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        p.end()
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 50:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            save_widget_pos("quick_notes", self.x(), self.y())
        self._dragging = False
