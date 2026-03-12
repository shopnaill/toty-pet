"""
Web Search Assistant — helps the pet react to web activity,
provide quick search bubbles, clipboard search, and smart suggestions.
"""
import json
import logging
import re
import threading
import urllib.request
import urllib.parse
import urllib.error
import webbrowser
from PyQt6.QtCore import Qt, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QTextEdit, QApplication, QWidget,
)

log = logging.getLogger("toty.web_search")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Quick Search Bubble (floating mini-search)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class QuickSearchBubble(QWidget):
    """Floating search bar near the pet — type a query, get results."""

    search_requested = pyqtSignal(str)  # emitted with query text
    closed = pyqtSignal()

    _BG = "#1e1e2e"
    _CARD = "#313244"
    _ACCENT = "#89b4fa"
    _TEXT = "#cdd6f4"
    _SUB = "#a6adc8"

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(380, 160)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(
            f"QWidget#search_bubble {{ background: {self._BG};"
            f" border: 2px solid {self._ACCENT}; border-radius: 14px; }}"
        )

        container = QFrame(self)
        container.setObjectName("search_bubble")
        container.setGeometry(0, 0, 380, 160)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        title = QLabel("🔍 Quick Search")
        title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {self._ACCENT};")
        lay.addWidget(title)

        # Search input
        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask me anything...")
        self._input.setStyleSheet(
            f"QLineEdit {{ background: {self._CARD}; color: {self._TEXT};"
            f" border: 1px solid #585b70; border-radius: 8px;"
            f" padding: 8px 12px; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: {self._ACCENT}; }}"
        )
        self._input.returnPressed.connect(self._on_search)
        lay.addWidget(self._input)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        btn_style = (
            f"QPushButton {{ background: {self._CARD}; color: {self._TEXT};"
            f" border: none; border-radius: 6px; padding: 6px 12px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: {self._ACCENT}; color: #1e1e2e; }}"
        )

        for label, callback in [
            ("🔍 Google", lambda: self._open_search("google")),
            ("📺 YouTube", lambda: self._open_search("youtube")),
            ("📚 Wikipedia", lambda: self._open_search("wikipedia")),
            ("🤖 AI", self._on_ai_search),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(callback)
            btn_row.addWidget(btn)

        close_btn = QPushButton("✕")
        close_btn.setStyleSheet(
            f"QPushButton {{ background: #f38ba8; color: #1e1e2e;"
            f" border: none; border-radius: 6px; padding: 6px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ background: #eba0ac; }}"
        )
        close_btn.clicked.connect(self._close)
        btn_row.addWidget(close_btn)

        lay.addLayout(btn_row)

        # Result label
        self._result = QLabel("")
        self._result.setStyleSheet(f"color: {self._SUB}; font-size: 11px;")
        self._result.setWordWrap(True)
        lay.addWidget(self._result)

    def show_at(self, x: int, y: int):
        self.move(x, y)
        self.show()
        self._input.setFocus()
        self._input.clear()
        self._result.setText("")

    def set_result(self, text: str):
        self._result.setText(text)

    def _on_search(self):
        query = self._input.text().strip()
        if query:
            self.search_requested.emit(query)
            self._open_search("google")

    def _on_ai_search(self):
        query = self._input.text().strip()
        if query:
            self.search_requested.emit(query)

    def _open_search(self, engine: str):
        query = self._input.text().strip()
        if not query:
            return

        urls = {
            "google": f"https://www.google.com/search?q={urllib.parse.quote(query)}",
            "youtube": f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}",
            "wikipedia": f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote(query)}",
        }
        url = urls.get(engine)
        if url:
            webbrowser.open(url)
            self._result.setText(f"Opened {engine.title()} for: {query}")

    def _close(self):
        self.hide()
        self.closed.emit()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Clipboard Search Detector
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class ClipboardSearchDetector(QObject):
    """Watches clipboard for searchable content and offers search."""

    suggest_search = pyqtSignal(str, str)  # (query_text, detected_type)

    def __init__(self, enabled: bool = True):
        super().__init__()
        self._enabled = enabled
        self._last_text = ""
        self._cooldown_text = ""

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        if enabled:
            self._timer.start(2000)

    def set_enabled(self, on: bool):
        self._enabled = on
        if on and not self._timer.isActive():
            self._timer.start(2000)
        elif not on:
            self._timer.stop()

    def _check(self):
        if not self._enabled:
            return
        clip = QApplication.clipboard()
        if not clip:
            return
        text = (clip.text() or "").strip()
        if not text or text == self._last_text or text == self._cooldown_text:
            return
        self._last_text = text

        # Detect searchable content
        if len(text) < 3 or len(text) > 500:
            return

        detected = self._classify(text)
        if detected:
            self._cooldown_text = text
            self.suggest_search.emit(text[:200], detected)

    def _classify(self, text: str) -> str | None:
        """Classify clipboard text for search suggestion."""
        # Skip URLs (already handled by clipboard assistant)
        if re.match(r'https?://', text, re.I):
            return None
        # Skip file paths
        if re.match(r'[A-Z]:\\|/', text) and len(text) < 100:
            return None
        # Error messages → suggest searching for fix
        if any(kw in text.lower() for kw in [
            "error", "exception", "traceback", "failed", "cannot", "undefined",
            "null", "segfault", "crash", "denied", "timeout",
        ]):
            return "error"
        # Code snippet → suggest docs
        if any(kw in text for kw in [
            "def ", "function ", "class ", "import ", "const ", "var ", "let ",
            "async ", "=>", "->", "public ", "private ",
        ]):
            return "code"
        # Question-like
        if text.endswith("?") or text.lower().startswith(("how ", "what ", "why ", "where ", "when ")):
            return "question"
        # General text (2+ words)
        if " " in text:
            return "text"

        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Web Search Action Panel (shown for clipboard suggestions)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class SearchSuggestionPopup(QWidget):
    """Small floating popup to offer search actions for copied text."""

    action_chosen = pyqtSignal(str, str)  # (engine, query)

    _BG = "#1e1e2e"
    _ACCENT = "#89b4fa"
    _TEXT = "#cdd6f4"

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool
                         | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(320, 80)
        self._query = ""
        self._auto_hide = QTimer(self)
        self._auto_hide.setSingleShot(True)
        self._auto_hide.timeout.connect(self.hide)
        self._build_ui()

    def _build_ui(self):
        self.setStyleSheet(
            f"QWidget#suggest_popup {{ background: {self._BG};"
            f" border: 2px solid {self._ACCENT}; border-radius: 10px; }}"
        )
        container = QFrame(self)
        container.setObjectName("suggest_popup")
        container.setGeometry(0, 0, 320, 80)

        lay = QVBoxLayout(container)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(4)

        self._label = QLabel("🔍 Search this?")
        self._label.setStyleSheet(f"color: {self._TEXT}; font-size: 11px;")
        self._label.setWordWrap(True)
        lay.addWidget(self._label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_style = (
            f"QPushButton {{ background: #313244; color: {self._TEXT};"
            f" border: none; border-radius: 5px; padding: 4px 10px; font-size: 10px; }}"
            f"QPushButton:hover {{ background: {self._ACCENT}; color: #1e1e2e; }}"
        )

        for label, engine in [
            ("Google", "google"), ("YouTube", "youtube"),
            ("Stack Overflow", "stackoverflow"), ("AI", "ai"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(btn_style)
            btn.clicked.connect(lambda _, e=engine: self._on_choice(e))
            btn_row.addWidget(btn)

        dismiss = QPushButton("✕")
        dismiss.setStyleSheet(
            f"QPushButton {{ background: #f38ba8; color: #1e1e2e;"
            f" border: none; border-radius: 5px; padding: 4px 8px; font-size: 10px; }}"
        )
        dismiss.clicked.connect(self.hide)
        btn_row.addWidget(dismiss)

        lay.addLayout(btn_row)

    def show_suggestion(self, text: str, kind: str, x: int, y: int):
        self._query = text
        preview = text[:60] + ("..." if len(text) > 60 else "")
        type_hints = {
            "error": "🐛 Error detected! Search for a fix?",
            "code": "💻 Code snippet copied. Look up docs?",
            "question": "❓ Question copied. Search for answers?",
            "text": f"🔍 Search: \"{preview}\"?",
        }
        self._label.setText(type_hints.get(kind, f"🔍 \"{preview}\""))
        self.move(x, y)
        self.show()
        self._auto_hide.start(8000)

    def _on_choice(self, engine: str):
        self.action_chosen.emit(engine, self._query)
        self.hide()

    @staticmethod
    def open_search(engine: str, query: str):
        """Open a web search in the default browser."""
        q = urllib.parse.quote(query[:200])
        urls = {
            "google": f"https://www.google.com/search?q={q}",
            "youtube": f"https://www.youtube.com/results?search_query={q}",
            "wikipedia": f"https://en.wikipedia.org/wiki/Special:Search?search={q}",
            "stackoverflow": f"https://stackoverflow.com/search?q={q}",
        }
        url = urls.get(engine)
        if url:
            webbrowser.open(url)
