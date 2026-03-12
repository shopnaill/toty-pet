"""
Teach Toty — let users add custom phrases the pet will say.
Stored in teach_toty.json.
"""
import json
import os
import random
from core.safe_json import safe_json_save
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem
)

_DATA_PATH = "teach_toty.json"


class TeachToty:
    """Manages custom phrases the user teaches the pet."""

    def __init__(self):
        self._phrases: list[str] = []
        self._load()

    @property
    def phrases(self) -> list[str]:
        return self._phrases

    def add_phrase(self, phrase: str):
        if phrase.strip() and phrase not in self._phrases:
            self._phrases.append(phrase.strip())
            self._save()

    def remove_phrase(self, phrase: str):
        if phrase in self._phrases:
            self._phrases.remove(phrase)
            self._save()

    def get_random(self) -> str | None:
        if not self._phrases:
            return None
        return random.choice(self._phrases)

    def _load(self):
        if os.path.exists(_DATA_PATH):
            try:
                with open(_DATA_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._phrases = data.get("phrases", [])
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        try:
            safe_json_save({"phrases": self._phrases}, _DATA_PATH)
        except OSError:
            pass


class TeachTotyDialog(QDialog):
    """Dialog to add/remove custom phrases."""

    def __init__(self, teach: TeachToty, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎓 Teach Toty")
        self.setFixedSize(400, 400)
        self.setStyleSheet(
            "QDialog { background: #1e1e2e; }"
            "QLabel { color: #cdd6f4; }"
            "QLineEdit { background: #313244; color: #cdd6f4; border: 1px solid #45475a;"
            " border-radius: 6px; padding: 6px; }"
            "QPushButton { background: #89b4fa; color: #1e1e2e; border: none;"
            " border-radius: 6px; padding: 6px 14px; font-weight: bold; }"
            "QPushButton:hover { background: #b4d0fb; }"
            "QListWidget { background: #313244; color: #cdd6f4; border: 1px solid #45475a;"
            " border-radius: 6px; }"
        )
        self._teach = teach
        layout = QVBoxLayout(self)

        header = QLabel("🎓 Teach Toty New Phrases")
        header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(header)

        hint = QLabel("Add phrases Toty will randomly say during idle moments.")
        hint.setStyleSheet("color: #888;")
        layout.addWidget(hint)

        # Input row
        input_row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a phrase to teach Toty...")
        self._input.returnPressed.connect(self._add)
        input_row.addWidget(self._input)

        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add)
        input_row.addWidget(add_btn)
        layout.addLayout(input_row)

        # List
        self._list = QListWidget()
        for phrase in teach.phrases:
            self._list.addItem(phrase)
        layout.addWidget(self._list)

        # Remove button
        rm_btn = QPushButton("🗑️ Remove Selected")
        rm_btn.setStyleSheet(
            "QPushButton { background: #f38ba8; }"
            "QPushButton:hover { background: #f5a0b8; }")
        rm_btn.clicked.connect(self._remove)
        layout.addWidget(rm_btn)

    def _add(self):
        text = self._input.text().strip()
        if text:
            self._teach.add_phrase(text)
            self._list.addItem(text)
            self._input.clear()

    def _remove(self):
        item = self._list.currentItem()
        if item:
            self._teach.remove_phrase(item.text())
            self._list.takeItem(self._list.row(item))
