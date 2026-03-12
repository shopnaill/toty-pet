"""Clipboard History — stores last 20 clipboard entries with search and quick paste."""
import time
from collections import deque
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont


class ClipboardHistory(QWidget):
    """Floating panel showing recent clipboard entries."""
    paste_requested = pyqtSignal(str)

    def __init__(self, max_entries: int = 20, parent=None):
        super().__init__(parent)
        self._entries: deque[dict] = deque(maxlen=max_entries)
        self._last_text = ""

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFixedWidth(320)
        self.setMaximumHeight(420)
        self.setStyleSheet(
            "QWidget { background: #1E1E2E; border: 1px solid #45475A;"
            "          border-radius: 10px; color: #CDD6F4; }"
            "QLabel { background: transparent; border: none; }"
            "QLineEdit { background: #313244; color: #CDD6F4; border: 1px solid #45475A;"
            "            border-radius: 6px; padding: 6px; font-size: 12px; }"
            "QPushButton { background: #45475A; color: #CDD6F4; border: none;"
            "              border-radius: 4px; padding: 4px 8px; font-size: 11px; }"
            "QPushButton:hover { background: #585B70; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("📋 Clipboard History")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #89B4FA;")
        layout.addWidget(title)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search clipboard...")
        self._search.textChanged.connect(self._rebuild)
        layout.addWidget(self._search)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMaximumHeight(300)
        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

        # Clipboard polling timer (500ms)
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._check_clipboard)
        self._poll.start(500)

        self.hide()

    def _check_clipboard(self):
        cb = QApplication.clipboard()
        if cb is None:
            return
        text = cb.text().strip()
        if not text or text == self._last_text or len(text) > 5000:
            return
        self._last_text = text
        self._entries.appendleft({
            "text": text,
            "time": time.strftime("%H:%M"),
        })
        if self.isVisible():
            self._rebuild()

    def _rebuild(self, _filter: str = ""):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self._search.text().lower()
        for entry in self._entries:
            text = entry["text"]
            if query and query not in text.lower():
                continue
            row = QHBoxLayout()
            preview = text[:60].replace("\n", " ")
            if len(text) > 60:
                preview += "..."
            lbl = QLabel(f"<span style='color:#6C7086;font-size:10px'>{entry['time']}</span> {preview}")
            lbl.setTextFormat(Qt.TextFormat.RichText)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("font-size: 11px; padding: 2px;")
            row.addWidget(lbl, stretch=1)

            copy_btn = QPushButton("📋")
            copy_btn.setFixedSize(28, 24)
            copy_btn.setToolTip("Copy to clipboard")
            t = text
            copy_btn.clicked.connect(lambda _, t=t: self._copy(t))
            row.addWidget(copy_btn)

            container = QWidget()
            container.setLayout(row)
            self._list_layout.addWidget(container)

    def _copy(self, text: str):
        cb = QApplication.clipboard()
        if cb:
            self._last_text = text  # prevent re-recording
            cb.setText(text)
        self.paste_requested.emit(text)

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self._rebuild()
            self.show()
            self.raise_()

    def stop(self):
        self._poll.stop()
