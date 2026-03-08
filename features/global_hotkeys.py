"""
Global Hotkeys — system-wide keyboard shortcuts for quick access.
Uses pynput for cross-platform hotkey registration.
v14: Added help dialog showing all registered hotkeys.
"""
import logging
from typing import Callable
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QFrame
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont

try:
    from pynput import keyboard
    _HAS_PYNPUT = True
except ImportError:
    _HAS_PYNPUT = False

log = logging.getLogger("toty")

_HOTKEY_DESCRIPTIONS = {
    "launcher": "Open Quick Launcher",
    "sticky_note": "New Sticky Note",
    "reminder": "Quick Reminder",
    "screenshot": "Screenshot (region)",
    "dashboard": "Toggle Dashboard",
    "journal": "Open Journal",
    "tasbeeh": "Open Tasbeeh Counter",
    "clipboard_history": "Clipboard History",
    "timer": "Quick Timer",
    "help": "Show This Help",
}


class GlobalHotkeys(QObject):
    """Register and manage system-wide hotkeys."""
    triggered = pyqtSignal(str)  # action name

    # Default key combos → action name
    DEFAULT_BINDINGS = {
        "<ctrl>+<space>":       "launcher",
        "<ctrl>+<shift>+n":     "sticky_note",
        "<ctrl>+<shift>+r":     "reminder",
        "<ctrl>+<shift>+s":     "screenshot",
        "<ctrl>+<shift>+d":     "dashboard",
        "<ctrl>+<shift>+j":     "journal",
        "<ctrl>+<shift>+t":     "tasbeeh",
        "<ctrl>+<shift>+v":     "clipboard_history",
        "<ctrl>+<shift>+w":     "timer",
        "<f1>":                 "help",
    }

    def __init__(self, bindings: dict[str, str] | None = None):
        super().__init__()
        self._bindings = bindings or dict(self.DEFAULT_BINDINGS)
        self._listener = None
        self._hotkeys: dict = {}
        self._active = False

    def start(self):
        if not _HAS_PYNPUT or self._active:
            return
        try:
            handler_map = {}
            for combo, action in self._bindings.items():
                handler_map[combo] = self._make_handler(action)
            self._listener = keyboard.GlobalHotKeys(handler_map)
            self._listener.daemon = True
            self._listener.start()
            self._active = True
            log.info("GlobalHotkeys: registered %d hotkeys", len(handler_map))
        except Exception as exc:
            log.warning("GlobalHotkeys: failed to start — %s", exc)

    def stop(self):
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._active = False

    def _make_handler(self, action: str) -> Callable:
        def _handler():
            self.triggered.emit(action)
        return _handler

    def is_active(self) -> bool:
        return self._active

    def get_bindings(self) -> dict[str, str]:
        return dict(self._bindings)


class HotkeyHelpDialog(QDialog):
    """Shows all registered global hotkeys in a cheatsheet dialog."""

    def __init__(self, bindings: dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("⌨️ Keyboard Shortcuts")
        self.setMinimumWidth(340)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("⌨️ Global Hotkeys")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #89B4FA;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,30);")
        layout.addWidget(sep)

        for combo, action in sorted(bindings.items(), key=lambda x: x[1]):
            desc = _HOTKEY_DESCRIPTIONS.get(action, action.replace("_", " ").title())
            pretty_combo = combo.replace("<", "").replace(">", "").replace("+", " + ").title()
            row = QLabel(f"<b style='color:#CBA6F7'>{pretty_combo}</b>"
                         f"<span style='color:#CDD6F4'>  —  {desc}</span>")
            row.setStyleSheet("font-size: 12px; padding: 3px 0;")
            row.setTextFormat(Qt.TextFormat.RichText)
            layout.addWidget(row)

        layout.addStretch()
