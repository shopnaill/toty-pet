"""Mood Journal — daily 'How are you?' prompt with mood tracking and history."""
import json
import os
import logging
from datetime import date, datetime
from core.safe_json import safe_json_save
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont

log = logging.getLogger("toty.mood_journal")
_FILE = "mood_journal.json"

_MOOD_OPTIONS = [
    ("😢", "Awful", 1),
    ("😔", "Bad", 2),
    ("😐", "Okay", 3),
    ("🙂", "Good", 4),
    ("😄", "Great", 5),
]

_PROMPTS = [
    "How are you feeling right now?",
    "What's on your mind today?",
    "Rate your day so far!",
    "How's your energy level?",
    "What made you smile today?",
    "Anything bothering you? Let it out.",
    "What are you grateful for right now?",
]


class MoodJournal(QObject):
    """Prompts the user daily to log their mood."""
    prompt_mood = pyqtSignal()  # signal to show the mood dialog

    def __init__(self, prompt_hour: int = 12):
        super().__init__()
        self._entries: list[dict] = []
        self._prompt_hour = prompt_hour
        self._prompted_today = False
        self._load()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_prompt)
        self._timer.start(300_000)  # check every 5 min

    def _check_prompt(self):
        now = datetime.now()
        today = date.today().isoformat()
        if (not self._prompted_today and now.hour >= self._prompt_hour
                and not any(e["date"] == today for e in self._entries)):
            self._prompted_today = True
            self.prompt_mood.emit()

    def log_mood(self, score: int, note: str = ""):
        """Log mood for today. score: 1-5."""
        self._entries.append({
            "date": date.today().isoformat(),
            "time": datetime.now().strftime("%H:%M"),
            "score": score,
            "note": note,
        })
        self._entries = self._entries[-90:]  # keep 90 days
        self._save()

    def get_today(self) -> dict | None:
        today = date.today().isoformat()
        for e in reversed(self._entries):
            if e["date"] == today:
                return e
        return None

    def get_week_summary(self) -> str:
        """7-day mood sparkline."""
        today = date.today()
        mood_map = {"😢": 1, "😔": 2, "😐": 3, "🙂": 4, "😄": 5}
        emojis = {1: "😢", 2: "😔", 3: "😐", 4: "🙂", 5: "😄"}
        from datetime import timedelta
        days = []
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).isoformat()
            entry = None
            for e in self._entries:
                if e["date"] == d:
                    entry = e
                    break
            if entry:
                days.append(emojis.get(entry["score"], "❓"))
            else:
                days.append("·")
        return "  ".join(days)

    def get_history(self, limit: int = 14) -> list[dict]:
        return self._entries[-limit:]

    def _save(self):
        try:
            safe_json_save({"entries": self._entries}, _FILE)
        except IOError:
            pass

    def _load(self):
        if os.path.exists(_FILE):
            try:
                with open(_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._entries = data.get("entries", [])
            except (json.JSONDecodeError, IOError):
                pass

    def stop(self):
        self._timer.stop()


class MoodJournalDialog(QDialog):
    """Dialog for logging mood."""

    def __init__(self, journal: MoodJournal, parent=None):
        super().__init__(parent)
        self._journal = journal
        self._score = 3
        self.setWindowTitle("💭 How are you feeling?")
        self.setMinimumWidth(350)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        import random
        prompt = random.choice(_PROMPTS)
        title = QLabel(f"💭 {prompt}")
        title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        title.setStyleSheet("color: #F9E2AF;")
        title.setWordWrap(True)
        layout.addWidget(title)

        # Mood buttons
        mood_row = QHBoxLayout()
        self._mood_btns = []
        for emoji, label, score in _MOOD_OPTIONS:
            btn = QPushButton(f"{emoji}\n{label}")
            btn.setFixedSize(60, 55)
            btn.setStyleSheet(
                "QPushButton { background: #313244; color: #CDD6F4; border: 2px solid transparent;"
                "  border-radius: 8px; font-size: 12px; }"
                "QPushButton:hover { border-color: #89B4FA; }"
            )
            sc = score
            btn.clicked.connect(lambda _, s=sc: self._select_mood(s))
            mood_row.addWidget(btn)
            self._mood_btns.append(btn)
        layout.addLayout(mood_row)

        # Note
        self._note = QTextEdit()
        self._note.setPlaceholderText("Any notes? (optional)")
        self._note.setMaximumHeight(80)
        self._note.setStyleSheet(
            "QTextEdit { background: #313244; color: #CDD6F4; border: 1px solid #45475A;"
            "  border-radius: 8px; padding: 8px; font-size: 12px; }"
        )
        layout.addWidget(self._note)

        # Week summary
        week = journal.get_week_summary()
        week_lbl = QLabel(f"This week: {week}")
        week_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        week_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(week_lbl)

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setStyleSheet(
            "QPushButton { background: #A6E3A1; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 8px 20px; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background: #94E2D5; }"
        )
        self._save_btn.clicked.connect(self._save)
        layout.addWidget(self._save_btn)

    def _select_mood(self, score: int):
        self._score = score
        for i, (_, _, s) in enumerate(_MOOD_OPTIONS):
            if s == score:
                self._mood_btns[i].setStyleSheet(
                    "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
                    "  border-radius: 8px; font-size: 12px; font-weight: bold; }"
                )
            else:
                self._mood_btns[i].setStyleSheet(
                    "QPushButton { background: #313244; color: #CDD6F4; border: 2px solid transparent;"
                    "  border-radius: 8px; font-size: 12px; }"
                    "QPushButton:hover { border-color: #89B4FA; }"
                )

    def _save(self):
        note = self._note.toPlainText().strip()
        self._journal.log_mood(self._score, note)
        self.accept()
