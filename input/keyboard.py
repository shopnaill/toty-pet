import time
from collections import deque

from PyQt6.QtCore import QObject, pyqtSignal

from core.settings import Settings


class KeyboardBridge(QObject):
    key_pressed = pyqtSignal(str)


class TypingPatternAnalyzer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._timestamps = deque(maxlen=200)
        self._backspace_count = 0
        self._burst_count = 0
        self._last_key_time = 0.0
        self._pause_detected = False
        self._idle_returned = False
        self._total_keys_session = 0

    def record_key(self, key_name: str):
        now = time.time()
        gap = now - self._last_key_time if self._last_key_time else 0
        if gap > 30 and self._last_key_time > 0:
            self._idle_returned = True
        elif gap > 5:
            self._pause_detected = True
        self._last_key_time = now
        self._timestamps.append(now)
        self._total_keys_session += 1
        if key_name == "backspace":
            self._backspace_count += 1
        else:
            self._backspace_count = 0

    def consume_events(self):
        events = {
            "idle_returned": self._idle_returned,
            "pause": self._pause_detected,
            "backspace_rage": self._backspace_count >= self.settings.get("backspace_rage_threshold"),
        }
        now = time.time()
        recent = [t for t in self._timestamps if now - t < 3]
        events["burst"] = len(recent) >= self.settings.get("burst_threshold")
        events["kps"] = self._kps()
        self._idle_returned = False
        self._pause_detected = False
        return events

    def _kps(self):
        now = time.time()
        recent = [t for t in self._timestamps if now - t < 5]
        return len(recent) / 5.0

    def get_total_keys(self):
        return self._total_keys_session
