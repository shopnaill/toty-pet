"""
Daily Journal / Mood Log — end-of-day mood tracking with optional notes.
Persistent to JSON. Weekly mood graph data. Ties into analytics.
"""
import json
import os
import logging
from datetime import datetime, date
from core.safe_json import safe_json_save
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont

log = logging.getLogger("toty")
_FILE = "journal.json"

MOODS = [
    ("😊", "Great",   5),
    ("🙂", "Good",    4),
    ("😐", "Okay",    3),
    ("😔", "Low",     2),
    ("😢", "Bad",     1),
]


class JournalDialog(QDialog):
    """End-of-day journal entry dialog."""
    submitted = pyqtSignal(int, str)  # (mood_score, note_text)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📓 Daily Journal")
        self.setFixedSize(380, 340)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Dialog
        )
        self.setStyleSheet(
            "QDialog { background: #1E1E2E; border: 2px solid #5599FF; "
            "border-radius: 12px; }"
        )
        self._mood_score = 3

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("How was your day?")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #EEE;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Mood buttons
        mood_row = QHBoxLayout()
        self._mood_buttons: list[QPushButton] = []
        for emoji, label, score in MOODS:
            btn = QPushButton(f"{emoji}\n{label}")
            btn.setFixedSize(60, 60)
            btn.setFont(QFont("Segoe UI", 10))
            btn.setStyleSheet(
                "QPushButton { background: #333; color: #CCC; border: 2px solid #555; "
                "border-radius: 8px; }"
                "QPushButton:hover { border-color: #5599FF; }"
            )
            btn.clicked.connect(lambda _, s=score, b=btn: self._select_mood(s, b))
            mood_row.addWidget(btn)
            self._mood_buttons.append(btn)
        layout.addLayout(mood_row)

        # Select default (Okay)
        self._select_mood(3, self._mood_buttons[2])

        # Note area
        note_label = QLabel("Optional note:")
        note_label.setStyleSheet("color: #AAA;")
        note_label.setFont(QFont("Segoe UI", 10))
        layout.addWidget(note_label)

        self._note = QTextEdit()
        self._note.setPlaceholderText("What happened today?...")
        self._note.setFont(QFont("Segoe UI", 10))
        self._note.setMaximumHeight(100)
        self._note.setStyleSheet(
            "background: #2A2A3A; color: #EEE; border: 1px solid #555; "
            "border-radius: 6px; padding: 6px;"
        )
        layout.addWidget(self._note)

        # Submit
        btn_row = QHBoxLayout()
        save_btn = QPushButton("✅ Save Entry")
        save_btn.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        save_btn.setStyleSheet(
            "QPushButton { background: #5599FF; color: white; border: none; "
            "border-radius: 8px; padding: 8px 24px; }"
            "QPushButton:hover { background: #3377DD; }"
        )
        save_btn.clicked.connect(self._submit)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _select_mood(self, score: int, btn: QPushButton):
        self._mood_score = score
        for b in self._mood_buttons:
            b.setStyleSheet(
                "QPushButton { background: #333; color: #CCC; border: 2px solid #555; "
                "border-radius: 8px; }"
                "QPushButton:hover { border-color: #5599FF; }"
            )
        btn.setStyleSheet(
            "QPushButton { background: #5599FF; color: white; border: 2px solid #77BBFF; "
            "border-radius: 8px; }"
        )

    def _submit(self):
        self.submitted.emit(self._mood_score, self._note.toPlainText().strip())
        self.accept()


class DailyJournal(QObject):
    """Manages daily journal entries with persistence."""
    entry_saved = pyqtSignal(int, str)       # (mood, note)
    prompt_journal = pyqtSignal()            # time to journal!

    def __init__(self, prompt_hour: int = 21):
        super().__init__()
        self._entries: list[dict] = []
        self._prompt_hour = prompt_hour
        self._prompted_today = False
        self._load()

        # Check if it's time to prompt
        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._check_prompt)
        self._check_timer.start(60_000)  # every minute

    def add_entry(self, mood: int, note: str = ""):
        today = date.today().isoformat()
        # Remove existing entry for today
        self._entries = [e for e in self._entries if e.get("date") != today]
        entry = {
            "date": today,
            "mood": mood,
            "note": note,
            "time": datetime.now().strftime("%H:%M"),
        }
        self._entries.append(entry)
        self._save()
        self.entry_saved.emit(mood, note)

    def get_today(self) -> dict | None:
        today = date.today().isoformat()
        for e in reversed(self._entries):
            if e.get("date") == today:
                return e
        return None

    def get_week(self) -> list[dict]:
        """Get last 7 days of entries."""
        return self._entries[-7:] if len(self._entries) >= 7 else list(self._entries)

    def get_mood_trend(self) -> str:
        week = self.get_week()
        if len(week) < 2:
            return "Not enough data yet"
        avg = sum(e["mood"] for e in week) / len(week)
        recent = week[-1]["mood"]
        if recent > avg:
            return f"📈 Trending up! (avg {avg:.1f})"
        elif recent < avg:
            return f"📉 Trending down (avg {avg:.1f})"
        return f"➡️ Steady (avg {avg:.1f})"

    def get_streak(self) -> int:
        """How many consecutive days with entries."""
        if not self._entries:
            return 0
        streak = 0
        check = date.today()
        for e in reversed(self._entries):
            if e.get("date") == check.isoformat():
                streak += 1
                check = date.fromisoformat(e["date"])
                check = check.replace(day=check.day - 1) if check.day > 1 else check
            else:
                break
        return streak

    def _check_prompt(self):
        now = datetime.now()
        if now.hour == self._prompt_hour and not self._prompted_today:
            today = date.today().isoformat()
            if not any(e.get("date") == today for e in self._entries):
                self._prompted_today = True
                self.prompt_journal.emit()
        # Reset flag at midnight
        if now.hour == 0:
            self._prompted_today = False

    def _save(self):
        try:
            safe_json_save(self._entries, _FILE)
        except IOError:
            pass

    def _load(self):
        if not os.path.exists(_FILE):
            return
        try:
            with open(_FILE, encoding="utf-8") as f:
                self._entries = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    def stop(self):
        self._check_timer.stop()
        self._save()
