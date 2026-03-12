"""
Command Palette — searchable quick-access overlay for all pet features.
Press Ctrl+Space (or open from menu) to search and trigger any feature.
"""
from PyQt6.QtCore import Qt, QPoint, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QApplication,
)


class CommandPalette(QWidget):
    """Floating searchable command palette (VS Code style)."""

    def __init__(self, commands: list[tuple[str, callable]] | None = None):
        """
        Args:
            commands: list of (label, callback) tuples.
                      Labels should include emoji prefix for discoverability.
        """
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 370)

        self._commands: list[tuple[str, callable]] = commands or []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Search input
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type to search commands...")
        self._input.setFont(QFont("Segoe UI", 11))
        self._input.setStyleSheet(
            "QLineEdit { background: rgba(30,30,50,240); color: #cdd6f4;"
            " border: 2px solid rgba(137,180,250,150); border-radius: 10px;"
            " padding: 8px 12px; }"
        )
        self._input.textChanged.connect(self._filter)
        layout.addWidget(self._input)

        # Results list
        self._list = QListWidget()
        self._list.setFont(QFont("Segoe UI", 10))
        self._list.setStyleSheet(
            "QListWidget { background: rgba(25,25,40,230); color: #cdd6f4;"
            " border: 1px solid rgba(100,100,140,80); border-radius: 8px;"
            " padding: 4px; }"
            "QListWidget::item { padding: 6px 10px; border-radius: 6px; }"
            "QListWidget::item:selected { background: rgba(137,180,250,180); color: #1e1e2e; }"
            "QListWidget::item:hover { background: rgba(137,180,250,80); }"
        )
        self._list.itemActivated.connect(self._execute)
        layout.addWidget(self._list)

        self._populate()

    def set_commands(self, commands: list[tuple[str, callable]]):
        """Update the command list."""
        self._commands = commands
        self._populate()

    def _populate(self, filter_text: str = ""):
        self._list.clear()
        needle = filter_text.lower()
        for label, callback in self._commands:
            if needle and needle not in label.lower():
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, callback)
            self._list.addItem(item)
        if self._list.count() > 0:
            self._list.setCurrentRow(0)

    def _filter(self, text: str):
        self._populate(text)

    def _execute(self, item: QListWidgetItem):
        cb = item.data(Qt.ItemDataRole.UserRole)
        self.hide()
        if callable(cb):
            cb()

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            screen = QApplication.primaryScreen()
            if screen:
                geo = screen.availableGeometry()
                x = geo.x() + (geo.width() - self.width()) // 2
                y = geo.y() + int(geo.height() * 0.2)
                self.move(x, y)
            self._input.clear()
            self._populate()
            self.show()
            self._input.setFocus()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            current = self._list.currentItem()
            if current:
                self._execute(current)
        elif event.key() == Qt.Key.Key_Down:
            row = self._list.currentRow()
            if row < self._list.count() - 1:
                self._list.setCurrentRow(row + 1)
        elif event.key() == Qt.Key.Key_Up:
            row = self._list.currentRow()
            if row > 0:
                self._list.setCurrentRow(row - 1)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(14, 14, 24, 230))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)
        p.end()
        super().paintEvent(event)
