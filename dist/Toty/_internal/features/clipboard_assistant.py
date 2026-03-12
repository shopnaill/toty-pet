"""
Clipboard Assistant — watches clipboard for useful content and offers help.
Detects: color hex codes, error messages, URLs, code snippets, math expressions.
"""
import re
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, pyqtSignal, QObject


class ClipboardEvent:
    """Represents a detected clipboard event with type and data."""
    def __init__(self, kind: str, text: str, detail: str = ""):
        self.kind = kind      # "color", "error", "url", "code", "math", "text"
        self.text = text      # original clipboard text
        self.detail = detail  # extracted/formatted info


class ClipboardAssistant(QObject):
    """Monitors clipboard and emits signals when interesting content is detected."""
    event_detected = pyqtSignal(object)  # ClipboardEvent

    # Patterns
    _HEX_COLOR = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
    _RGB_COLOR = re.compile(r"^rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)$", re.I)
    _URL = re.compile(r"^https?://[^\s]+$")
    _ERROR_KW = re.compile(
        r"(traceback|error|exception|failed|fatal|errno|segfault"
        r"|syntaxerror|typeerror|valueerror|keyerror|indexerror"
        r"|nullpointer|undefined is not|cannot read prop)", re.I
    )
    _CODE_HINTS = re.compile(
        r"(def |class |function |import |#include|public static|"
        r"const |let |var |=>|from .+ import|\{[\s\S]*\})", re.I
    )

    def __init__(self, check_interval_ms: int = 1500):
        super().__init__()
        self._last_text = ""
        self._last_check = 0.0
        self._cooldown = 5.0  # Don't fire for same text within 5s
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(check_interval_ms)

    def stop(self):
        self._timer.stop()

    def _check(self):
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text().strip()
        if not text or len(text) > 2000:
            return

        now = time.time()
        if text == self._last_text and (now - self._last_check) < self._cooldown:
            return
        if text == self._last_text:
            return  # Same text, already handled

        self._last_text = text
        self._last_check = now

        event = self._analyze(text)
        if event:
            self.event_detected.emit(event)

    def _analyze(self, text: str) -> ClipboardEvent | None:
        # Color hex
        if self._HEX_COLOR.match(text):
            return ClipboardEvent("color", text, f"Color: {text}")

        # RGB color
        if self._RGB_COLOR.match(text):
            return ClipboardEvent("color", text, f"Color: {text}")

        # URL
        if self._URL.match(text):
            domain = text.split("/")[2] if len(text.split("/")) > 2 else text
            return ClipboardEvent("url", text, domain)

        # Error / traceback
        if self._ERROR_KW.search(text):
            first_line = text.split("\n")[-1].strip()[:80]
            return ClipboardEvent("error", text, first_line)

        # Code snippet (multi-line with code-like patterns)
        lines = text.split("\n")
        if len(lines) >= 2 and self._CODE_HINTS.search(text):
            lang = self._guess_language(text)
            return ClipboardEvent("code", text, f"{len(lines)} lines of {lang}")

        return None

    @staticmethod
    def _guess_language(text: str) -> str:
        if "def " in text or "import " in text:
            return "Python"
        if "function " in text or "const " in text or "=>" in text:
            return "JavaScript"
        if "#include" in text:
            return "C/C++"
        if "public static" in text:
            return "Java/C#"
        return "code"
