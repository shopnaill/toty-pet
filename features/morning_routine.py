"""Morning Routine Checklist — configurable daily startup checklist."""
import json
import os
import logging
from datetime import date
from core.safe_json import safe_json_save
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QPushButton, QLineEdit, QScrollArea, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

log = logging.getLogger("toty.routine")
_FILE = "morning_routine.json"

_DEFAULT_ITEMS = [
    "💧 Drink water",
    "🧘 Stretch / Exercise",
    "📋 Review today's tasks",
    "🎯 Set daily goal",
    "📧 Check email",
]


class MorningRoutine(QWidget):
    """Floating checklist for morning routine."""
    all_done = pyqtSignal()  # emitted when all items checked

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[str] = list(_DEFAULT_ITEMS)
        self._checked: set[str] = set()
        self._today = date.today().isoformat()
        self._load()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFixedWidth(280)
        self.setMaximumHeight(360)
        self.setStyleSheet(
            "QWidget { background: #1E1E2E; border: 1px solid #45475A;"
            "          border-radius: 10px; color: #CDD6F4; }"
            "QLabel { background: transparent; border: none; }"
            "QCheckBox { font-size: 12px; color: #CDD6F4; spacing: 6px; }"
            "QLineEdit { background: #313244; color: #CDD6F4; border: 1px solid #45475A;"
            "            border-radius: 6px; padding: 4px; font-size: 11px; }"
            "QPushButton { background: #45475A; color: #CDD6F4; border: none;"
            "              border-radius: 4px; padding: 4px 8px; font-size: 11px; }"
            "QPushButton:hover { background: #585B70; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title = QLabel("🌅 Morning Routine")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #F9E2AF;")
        layout.addWidget(title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._container = QWidget()
        self._list_layout = QVBoxLayout(self._container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

        # Add custom item
        add_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Add routine item...")
        self._input.returnPressed.connect(self._add_item)
        add_row.addWidget(self._input, stretch=1)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(28)
        add_btn.clicked.connect(self._add_item)
        add_row.addWidget(add_btn)
        layout.addLayout(add_row)

        self._rebuild()
        self.hide()

    def _rebuild(self):
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for text in self._items:
            row = QHBoxLayout()
            cb = QCheckBox(text)
            cb.setChecked(text in self._checked)
            if text in self._checked:
                cb.setStyleSheet("QCheckBox { color: #A6E3A1; }")
            item_text = text
            cb.toggled.connect(lambda checked, t=item_text: self._toggle(t, checked))
            row.addWidget(cb, stretch=1)

            del_btn = QPushButton("×")
            del_btn.setFixedSize(20, 20)
            del_btn.setStyleSheet("QPushButton { background: #F38BA8; font-size: 12px; }")
            del_btn.clicked.connect(lambda _, t=item_text: self._remove_item(t))
            row.addWidget(del_btn)

            container = QWidget()
            container.setLayout(row)
            self._list_layout.addWidget(container)

    def _toggle(self, text: str, checked: bool):
        if checked:
            self._checked.add(text)
        else:
            self._checked.discard(text)
        self._save()
        self._rebuild()
        if len(self._checked) == len(self._items) and self._items:
            self.all_done.emit()

    def _add_item(self):
        text = self._input.text().strip()
        if text and text not in self._items:
            self._items.append(text)
            self._input.clear()
            self._save()
            self._rebuild()

    def _remove_item(self, text: str):
        if text in self._items:
            self._items.remove(text)
            self._checked.discard(text)
            self._save()
            self._rebuild()

    def is_complete(self) -> bool:
        return len(self._checked) == len(self._items) and len(self._items) > 0

    def get_progress(self) -> str:
        return f"{len(self._checked)}/{len(self._items)}"

    def toggle(self):
        # Reset if new day
        today = date.today().isoformat()
        if today != self._today:
            self._checked.clear()
            self._today = today
            self._save()
            self._rebuild()
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

    def _save(self):
        try:
            safe_json_save({
                "items": self._items,
                "checked": list(self._checked),
                "date": self._today,
            }, _FILE)
        except IOError:
            pass

    def _load(self):
        if not os.path.exists(_FILE):
            return
        try:
            with open(_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._items = data.get("items", list(_DEFAULT_ITEMS))
            saved_date = data.get("date", "")
            if saved_date == self._today:
                self._checked = set(data.get("checked", []))
            else:
                self._checked.clear()
        except (json.JSONDecodeError, IOError):
            pass
