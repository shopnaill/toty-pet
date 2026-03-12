"""Text Tools — Base64, URL encode/decode, JSON prettify, hash, regex tester."""
import base64
import hashlib
import json
import re
import logging
import html
from urllib.parse import quote, unquote

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QComboBox, QApplication, QTabWidget, QWidget,
    QLineEdit, QTreeWidget, QTreeWidgetItem, QHeaderView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

log = logging.getLogger("toty.text_tools")

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"
_YELLOW = "#F9E2AF"

_SS = f"""
QDialog {{ background: {_BG}; }}
QTabWidget::pane {{ border: 1px solid #45475A; border-radius: 6px;
    background: {_BG}; }}
QTabBar::tab {{
    background: {_SURFACE}; color: {_TEXT}; padding: 8px 16px;
    border: 1px solid #45475A; border-bottom: none; border-radius: 6px 6px 0 0;
    margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {_BG}; color: {_BLUE}; border-bottom: 2px solid {_BLUE}; }}
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
QTreeWidget {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; font-size: 12px;
}}
QTreeWidget::item:selected {{ background: #45475A; }}
QHeaderView::section {{
    background: {_SURFACE}; color: {_BLUE}; border: none;
    font-weight: bold; padding: 4px;
}}
"""


class TextToolsDialog(QDialog):
    """Multi-tab text utility toolkit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔧 Text Tools")
        self.setMinimumSize(560, 500)
        self.resize(600, 540)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title = QLabel("🔧 Text Tools")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE};")
        lay.addWidget(title)

        tabs = QTabWidget()
        lay.addWidget(tabs)

        tabs.addTab(self._build_encode_tab(), "🔄 Encode/Decode")
        tabs.addTab(self._build_hash_tab(), "🔐 Hash")
        tabs.addTab(self._build_json_tab(), "📋 JSON")
        tabs.addTab(self._build_regex_tab(), "🔍 Regex")

    # ── Encode / Decode ───────────────────────────────────────────
    def _build_encode_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._enc_input = QTextEdit()
        self._enc_input.setPlaceholderText("Enter text here…")
        self._enc_input.setMaximumHeight(120)
        lay.addWidget(self._enc_input)

        row = QHBoxLayout()
        row.setSpacing(6)

        self._enc_type = QComboBox()
        self._enc_type.addItems([
            "Base64 Encode", "Base64 Decode",
            "URL Encode", "URL Decode",
            "HTML Encode", "HTML Decode",
            "ROT13",
            "Reverse Text",
            "UPPER CASE", "lower case", "Title Case",
            "Remove Whitespace", "Count Words",
        ])
        row.addWidget(self._enc_type)

        btn = QPushButton("▶ Convert")
        btn.clicked.connect(self._do_encode)
        btn.setStyleSheet(
            f"QPushButton {{ background: {_BLUE}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 8px 14px; font-weight: bold; }}")
        row.addWidget(btn)

        btn_copy = QPushButton("📋 Copy")
        btn_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self._enc_output.toPlainText()))
        row.addWidget(btn_copy)

        lay.addLayout(row)

        self._enc_output = QTextEdit()
        self._enc_output.setReadOnly(True)
        self._enc_output.setPlaceholderText("Output…")
        lay.addWidget(self._enc_output)

        return tab

    def _do_encode(self):
        text = self._enc_input.toPlainText()
        op = self._enc_type.currentText()
        try:
            if op == "Base64 Encode":
                result = base64.b64encode(text.encode()).decode()
            elif op == "Base64 Decode":
                result = base64.b64decode(text.encode()).decode()
            elif op == "URL Encode":
                result = quote(text, safe="")
            elif op == "URL Decode":
                result = unquote(text)
            elif op == "HTML Encode":
                result = html.escape(text)
            elif op == "HTML Decode":
                result = html.unescape(text)
            elif op == "ROT13":
                import codecs
                result = codecs.encode(text, "rot_13")
            elif op == "Reverse Text":
                result = text[::-1]
            elif op == "UPPER CASE":
                result = text.upper()
            elif op == "lower case":
                result = text.lower()
            elif op == "Title Case":
                result = text.title()
            elif op == "Remove Whitespace":
                result = "".join(text.split())
            elif op == "Count Words":
                words = len(text.split())
                chars = len(text)
                lines = text.count("\n") + 1
                result = f"Words: {words}\nCharacters: {chars}\nLines: {lines}"
            else:
                result = text
            self._enc_output.setPlainText(result)
        except Exception as e:
            self._enc_output.setPlainText(f"Error: {e}")

    # ── Hash ──────────────────────────────────────────────────────
    def _build_hash_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._hash_input = QTextEdit()
        self._hash_input.setPlaceholderText("Enter text to hash…")
        self._hash_input.setMaximumHeight(120)
        self._hash_input.textChanged.connect(self._do_hash)
        lay.addWidget(self._hash_input)

        lay.addWidget(QLabel("Hash Results:"))

        self._hash_tree = QTreeWidget()
        self._hash_tree.setHeaderLabels(["Algorithm", "Hash"])
        self._hash_tree.setColumnCount(2)
        hdr = self._hash_tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._hash_tree.setRootIsDecorated(False)
        self._hash_tree.itemDoubleClicked.connect(
            lambda item, _: QApplication.clipboard().setText(item.text(1)))
        lay.addWidget(self._hash_tree)

        info = QLabel("Double-click a hash to copy it")
        info.setStyleSheet(f"color: #585B70; font-size: 11px;")
        lay.addWidget(info)

        return tab

    def _do_hash(self):
        text = self._hash_input.toPlainText().encode()
        self._hash_tree.clear()
        for algo in ("md5", "sha1", "sha256", "sha384", "sha512"):
            h = hashlib.new(algo, text).hexdigest()
            row = QTreeWidgetItem([algo.upper(), h])
            self._hash_tree.addTopLevelItem(row)

    # ── JSON ──────────────────────────────────────────────────────
    def _build_json_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        self._json_input = QTextEdit()
        self._json_input.setPlaceholderText(
            'Paste JSON here…\n{"name": "Toty", "level": 14}')
        lay.addWidget(self._json_input)

        row = QHBoxLayout()
        row.setSpacing(6)

        btn_pretty = QPushButton("✨ Prettify")
        btn_pretty.clicked.connect(lambda: self._do_json("pretty"))
        btn_pretty.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 8px 14px; font-weight: bold; }}")
        row.addWidget(btn_pretty)

        btn_mini = QPushButton("📦 Minify")
        btn_mini.clicked.connect(lambda: self._do_json("mini"))
        row.addWidget(btn_mini)

        btn_valid = QPushButton("✅ Validate")
        btn_valid.clicked.connect(lambda: self._do_json("validate"))
        row.addWidget(btn_valid)

        btn_copy = QPushButton("📋 Copy")
        btn_copy.clicked.connect(
            lambda: QApplication.clipboard().setText(
                self._json_input.toPlainText()))
        row.addWidget(btn_copy)

        lay.addLayout(row)

        self._json_status = QLabel("")
        self._json_status.setStyleSheet(f"font-size: 12px;")
        lay.addWidget(self._json_status)

        return tab

    def _do_json(self, mode: str):
        text = self._json_input.toPlainText()
        try:
            data = json.loads(text)
            if mode == "pretty":
                self._json_input.setPlainText(
                    json.dumps(data, indent=2, ensure_ascii=False))
                self._json_status.setText("✅ Prettified")
                self._json_status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            elif mode == "mini":
                self._json_input.setPlainText(
                    json.dumps(data, separators=(",", ":"),
                               ensure_ascii=False))
                self._json_status.setText("✅ Minified")
                self._json_status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            elif mode == "validate":
                self._json_status.setText("✅ Valid JSON")
                self._json_status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
        except json.JSONDecodeError as e:
            self._json_status.setText(f"❌ Invalid: {e}")
            self._json_status.setStyleSheet(f"color: {_RED}; font-size: 12px;")

    # ── Regex ─────────────────────────────────────────────────────
    def _build_regex_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        lay.addWidget(QLabel("Pattern:"))
        self._rx_pattern = QLineEdit()
        self._rx_pattern.setPlaceholderText(r"e.g. \b\w+@\w+\.\w+\b")
        self._rx_pattern.textChanged.connect(self._do_regex)
        lay.addWidget(self._rx_pattern)

        lay.addWidget(QLabel("Test String:"))
        self._rx_input = QTextEdit()
        self._rx_input.setPlaceholderText("Enter text to test against…")
        self._rx_input.setMaximumHeight(100)
        self._rx_input.textChanged.connect(self._do_regex)
        lay.addWidget(self._rx_input)

        self._rx_status = QLabel("")
        self._rx_status.setStyleSheet(f"font-size: 12px;")
        lay.addWidget(self._rx_status)

        lay.addWidget(QLabel("Matches:"))
        self._rx_tree = QTreeWidget()
        self._rx_tree.setHeaderLabels(["#", "Match", "Start", "End"])
        self._rx_tree.setColumnCount(4)
        hdr = self._rx_tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._rx_tree.setRootIsDecorated(False)
        lay.addWidget(self._rx_tree)

        return tab

    def _do_regex(self):
        pat = self._rx_pattern.text()
        text = self._rx_input.toPlainText()
        self._rx_tree.clear()
        if not pat:
            self._rx_status.setText("")
            return
        try:
            matches = list(re.finditer(pat, text))
            self._rx_status.setText(
                f"✅ {len(matches)} match(es)")
            self._rx_status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            for i, m in enumerate(matches, 1):
                row = QTreeWidgetItem([
                    str(i), m.group(), str(m.start()), str(m.end())])
                self._rx_tree.addTopLevelItem(row)
        except re.error as e:
            self._rx_status.setText(f"❌ Invalid regex: {e}")
            self._rx_status.setStyleSheet(f"color: {_RED}; font-size: 12px;")
