"""
Typing Mini-Game — timed typing challenge with WPM scoring.
"""
import random
import time
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QLineEdit, QHBoxLayout, QPushButton
)

WORD_LISTS = {
    "easy": [
        "the", "be", "to", "of", "and", "a", "in", "that", "have", "it",
        "for", "not", "on", "with", "he", "as", "you", "do", "at", "this",
        "but", "his", "by", "from", "they", "we", "say", "her", "she", "or",
        "an", "will", "my", "one", "all", "would", "there", "their", "what",
        "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    ],
    "medium": [
        "python", "function", "variable", "keyboard", "monitor", "desktop",
        "window", "compile", "browser", "network", "database", "algorithm",
        "program", "terminal", "command", "module", "object", "class",
        "method", "return", "import", "export", "package", "server",
        "client", "request", "response", "template", "framework", "library",
    ],
    "hard": [
        "asynchronous", "encapsulation", "polymorphism", "authentication",
        "optimization", "infrastructure", "configuration", "documentation",
        "implementation", "architecture", "serialization", "concurrency",
        "middleware", "vulnerability", "abstraction", "recursion",
    ],
}


class TypingGame(QDialog):
    """Timed typing challenge — returns XP based on WPM."""

    game_finished = pyqtSignal(int, float)  # (xp_earned, wpm)

    def __init__(self, parent=None, difficulty: str = "medium", word_count: int = 10):
        super().__init__(parent)
        self.setWindowTitle("⌨️ Typing Challenge")
        self.setFixedSize(500, 300)
        self.setStyleSheet(
            "QDialog { background: #1e1e2e; }"
            "QLabel { color: #cdd6f4; }"
            "QLineEdit { background: #313244; color: #cdd6f4; border: 2px solid #45475a;"
            " border-radius: 8px; padding: 8px; font-size: 14px; }"
            "QLineEdit:focus { border-color: #89b4fa; }"
            "QPushButton { background: #89b4fa; color: #1e1e2e; border: none;"
            " border-radius: 8px; padding: 8px 16px; font-weight: bold; }"
            "QPushButton:hover { background: #b4d0fb; }"
        )

        layout = QVBoxLayout(self)

        # Header
        self._header = QLabel("⌨️ Type the words below as fast as you can!")
        self._header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._header)

        # Target text
        pool = WORD_LISTS.get(difficulty, WORD_LISTS["medium"])
        self._target_words = " ".join(random.choices(pool, k=word_count))
        self._target_label = QLabel(self._target_words)
        self._target_label.setFont(QFont("Cascadia Code", 13))
        self._target_label.setWordWrap(True)
        self._target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._target_label.setStyleSheet(
            "color: #89b4fa; background: #313244; border-radius: 8px; padding: 12px;")
        layout.addWidget(self._target_label)

        # Input
        self._input = QLineEdit()
        self._input.setFont(QFont("Cascadia Code", 13))
        self._input.setPlaceholderText("Start typing here...")
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input)

        # Stats bar
        stats_layout = QHBoxLayout()
        self._wpm_label = QLabel("WPM: --")
        self._wpm_label.setFont(QFont("Segoe UI", 10))
        stats_layout.addWidget(self._wpm_label)

        self._acc_label = QLabel("Accuracy: --")
        self._acc_label.setFont(QFont("Segoe UI", 10))
        stats_layout.addWidget(self._acc_label)

        self._time_label = QLabel("Time: 0.0s")
        self._time_label.setFont(QFont("Segoe UI", 10))
        stats_layout.addWidget(self._time_label)
        layout.addLayout(stats_layout)

        self._start_time = None
        self._finished = False

        # Timer for live WPM update
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._update_live_stats)
        self._live_timer.start(200)

    def _on_text_changed(self, text: str):
        if self._finished:
            return
        if self._start_time is None and text:
            self._start_time = time.time()

        # Color-code: green for correct chars, red for wrong
        if text == self._target_words:
            self._finish()

    def _update_live_stats(self):
        if self._start_time is None or self._finished:
            return
        elapsed = time.time() - self._start_time
        self._time_label.setText(f"Time: {elapsed:.1f}s")

        typed = self._input.text()
        words_typed = len(typed.split())
        if elapsed > 0:
            wpm = (words_typed / elapsed) * 60
            self._wpm_label.setText(f"WPM: {wpm:.0f}")

        # Accuracy
        correct = sum(1 for a, b in zip(typed, self._target_words) if a == b)
        total = max(1, len(typed))
        acc = (correct / total) * 100
        self._acc_label.setText(f"Accuracy: {acc:.0f}%")

    def _finish(self):
        self._finished = True
        elapsed = max(0.1, time.time() - self._start_time)
        words = len(self._target_words.split())
        wpm = (words / elapsed) * 60

        typed = self._input.text()
        correct = sum(1 for a, b in zip(typed, self._target_words) if a == b)
        acc = (correct / max(1, len(self._target_words))) * 100

        # XP: base 20 + WPM bonus + accuracy bonus
        xp = int(20 + wpm * 0.5 + acc * 0.3)

        self._header.setText(f"🎉 Done! WPM: {wpm:.0f} | Accuracy: {acc:.0f}% | +{xp} XP")
        self._header.setStyleSheet("color: #a6e3a1;")
        self._input.setEnabled(False)
        self._live_timer.stop()
        self._time_label.setText(f"Time: {elapsed:.1f}s")
        self._wpm_label.setText(f"WPM: {wpm:.0f}")
        self._acc_label.setText(f"Accuracy: {acc:.0f}%")

        self.game_finished.emit(xp, wpm)
