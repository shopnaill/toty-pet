"""Snippet Manager — Save, organize, and quickly paste code/text snippets."""
import json
import os
import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QListWidget, QListWidgetItem,
    QApplication, QMessageBox, QComboBox, QSplitter, QWidget,
    QInputDialog,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

log = logging.getLogger("toty.snippet_manager")

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"
_YELLOW = "#F9E2AF"
_MAUVE = "#CBA6F7"

_SS = f"""
QDialog {{ background: {_BG}; }}
QListWidget {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; font-size: 13px; padding: 4px;
}}
QListWidget::item {{ padding: 6px 8px; border-radius: 4px; }}
QListWidget::item:selected {{ background: #45475A; color: {_BLUE}; }}
QTextEdit, QLineEdit {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px; font-family: Consolas; font-size: 13px;
}}
QPushButton {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 14px; font-size: 13px;
}}
QPushButton:hover {{ background: #45475A; border-color: {_BLUE}; }}
QPushButton:pressed {{ background: {_BLUE}; color: {_BG}; }}
QComboBox {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 6px 10px; font-size: 13px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {_SURFACE}; color: {_TEXT}; selection-background-color: #45475A;
}}
QLabel {{ color: {_TEXT}; }}
QSplitter::handle {{ background: #45475A; width: 2px; }}
"""

_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "snippets.json")

_DEFAULT_CATEGORIES = ["General", "Code", "Commands", "Templates", "Notes"]
_LANG_ICONS = {
    "General": "📝", "Code": "💻", "Commands": "⌨️",
    "Templates": "📄", "Notes": "🗒️",
}


class SnippetManagerDialog(QDialog):
    """Manage and quick-paste saved snippets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("✂️ Snippet Manager")
        self.setMinimumSize(700, 500)
        self.resize(740, 540)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)
        self._snippets: list[dict] = []
        self._load()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title = QLabel("✂️ Snippet Manager")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE};")
        lay.addWidget(title)

        # Search + filter
        top_row = QHBoxLayout()
        top_row.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍 Search snippets…")
        self._search.textChanged.connect(self._filter)
        top_row.addWidget(self._search)

        self._cat_filter = QComboBox()
        self._cat_filter.addItem("All Categories")
        for c in self._get_categories():
            self._cat_filter.addItem(f"{_LANG_ICONS.get(c, '📁')} {c}")
        self._cat_filter.currentIndexChanged.connect(self._filter)
        top_row.addWidget(self._cat_filter)

        lay.addLayout(top_row)

        # Splitter: list | editor
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: snippet list
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_select)
        splitter.addWidget(self._list)

        # Right: editor
        right = QWidget()
        r_lay = QVBoxLayout(right)
        r_lay.setContentsMargins(0, 0, 0, 0)
        r_lay.setSpacing(6)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        name_row.addWidget(QLabel("Title:"))
        self._name = QLineEdit()
        self._name.setPlaceholderText("Snippet name…")
        name_row.addWidget(self._name)

        self._cat = QComboBox()
        self._cat.setEditable(True)
        for c in _DEFAULT_CATEGORIES:
            self._cat.addItem(f"{_LANG_ICONS.get(c, '📁')} {c}", c)
        name_row.addWidget(self._cat)
        r_lay.addLayout(name_row)

        self._editor = QTextEdit()
        self._editor.setPlaceholderText("Snippet content…")
        r_lay.addWidget(self._editor)

        # Editor buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self._btn_save = QPushButton("💾 Save")
        self._btn_save.clicked.connect(self._save_snippet)
        self._btn_save.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 8px 14px; font-weight: bold; }}")
        btn_row.addWidget(self._btn_save)

        self._btn_copy = QPushButton("📋 Copy")
        self._btn_copy.clicked.connect(self._copy_snippet)
        btn_row.addWidget(self._btn_copy)

        self._btn_new = QPushButton("➕ New")
        self._btn_new.clicked.connect(self._new_snippet)
        btn_row.addWidget(self._btn_new)

        self._btn_del = QPushButton("🗑️ Delete")
        self._btn_del.clicked.connect(self._delete_snippet)
        self._btn_del.setStyleSheet(
            f"QPushButton {{ background: {_SURFACE}; color: {_RED}; "
            f"border: 1px solid {_RED}; border-radius: 6px; padding: 8px 14px; }}"
            f"QPushButton:hover {{ background: {_RED}; color: {_BG}; }}")
        btn_row.addWidget(self._btn_del)

        r_lay.addLayout(btn_row)

        self._status = QLabel("")
        self._status.setStyleSheet(f"font-size: 12px;")
        r_lay.addWidget(self._status)

        splitter.addWidget(right)
        splitter.setSizes([220, 500])
        lay.addWidget(splitter)

        self._refresh_list()

    def _load(self):
        if os.path.isfile(_DATA_FILE):
            try:
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    self._snippets = json.load(f)
            except Exception:
                self._snippets = []
        else:
            self._snippets = []

    def _save_data(self):
        try:
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._snippets, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("Cannot save snippets: %s", e)

    def _get_categories(self) -> list[str]:
        cats = set(_DEFAULT_CATEGORIES)
        for s in self._snippets:
            cats.add(s.get("category", "General"))
        return sorted(cats)

    def _refresh_list(self):
        self._list.clear()
        for s in self._snippets:
            icon = _LANG_ICONS.get(s.get("category", ""), "📝")
            item = QListWidgetItem(f"{icon} {s['name']}")
            item.setData(Qt.ItemDataRole.UserRole, s)
            self._list.addItem(item)

    def _filter(self):
        query = self._search.text().lower()
        cat_idx = self._cat_filter.currentIndex()
        cat_text = ""
        if cat_idx > 0:
            # Strip emoji prefix
            raw = self._cat_filter.currentText()
            cat_text = raw.split(" ", 1)[-1] if " " in raw else raw

        self._list.clear()
        for s in self._snippets:
            if query and query not in s["name"].lower() and \
               query not in s.get("content", "").lower():
                continue
            if cat_text and s.get("category", "General") != cat_text:
                continue
            icon = _LANG_ICONS.get(s.get("category", ""), "📝")
            item = QListWidgetItem(f"{icon} {s['name']}")
            item.setData(Qt.ItemDataRole.UserRole, s)
            self._list.addItem(item)

    def _on_select(self, row):
        item = self._list.item(row)
        if not item:
            return
        s = item.data(Qt.ItemDataRole.UserRole)
        self._name.setText(s["name"])
        self._editor.setPlainText(s.get("content", ""))
        cat = s.get("category", "General")
        for i in range(self._cat.count()):
            if self._cat.itemData(i) == cat:
                self._cat.setCurrentIndex(i)
                break

    def _save_snippet(self):
        name = self._name.text().strip()
        if not name:
            self._status.setText("❌ Enter a name")
            self._status.setStyleSheet(f"color: {_RED}; font-size: 12px;")
            return
        content = self._editor.toPlainText()
        cat_raw = self._cat.currentText()
        cat = cat_raw.split(" ", 1)[-1] if " " in cat_raw else cat_raw

        # Update existing or create new
        cur = self._list.currentItem()
        if cur:
            s = cur.data(Qt.ItemDataRole.UserRole)
            s["name"] = name
            s["content"] = content
            s["category"] = cat
            s["updated"] = datetime.now().isoformat()
        else:
            s = {
                "name": name,
                "content": content,
                "category": cat,
                "created": datetime.now().isoformat(),
                "updated": datetime.now().isoformat(),
            }
            self._snippets.append(s)

        self._save_data()
        self._refresh_list()
        self._status.setText(f"✅ Saved: {name}")
        self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")

    def _copy_snippet(self):
        content = self._editor.toPlainText()
        if content:
            QApplication.clipboard().setText(content)
            self._status.setText("✅ Copied to clipboard")
            self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")

    def _new_snippet(self):
        self._list.clearSelection()
        self._name.clear()
        self._editor.clear()
        self._name.setFocus()

    def _delete_snippet(self):
        cur = self._list.currentItem()
        if not cur:
            return
        s = cur.data(Qt.ItemDataRole.UserRole)
        ans = QMessageBox.question(
            self, "Delete Snippet",
            f"Delete '{s['name']}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            self._snippets = [x for x in self._snippets
                              if x is not s]
            self._save_data()
            self._refresh_list()
            self._name.clear()
            self._editor.clear()
            self._status.setText(f"🗑️ Deleted: {s['name']}")
            self._status.setStyleSheet(f"color: {_YELLOW}; font-size: 12px;")
