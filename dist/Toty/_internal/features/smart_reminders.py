"""
Smart Reminders — natural-language time-based reminders.
Supports "in X minutes/hours", "at HH:MM", recurring daily.
Persistent to JSON, fires via QTimer.
"""
import json
import os
import re
import logging
from datetime import datetime, timedelta
from core.safe_json import safe_json_save
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger("toty")
_FILE = "reminders_v2.json"


class SmartReminder:
    __slots__ = ("text", "fire_at", "recurring", "recur_time", "rid")

    def __init__(self, text: str, fire_at: str, recurring: bool = False,
                 recur_time: str | None = None, rid: int = 0):
        self.text = text
        self.fire_at = fire_at  # ISO format
        self.recurring = recurring
        self.recur_time = recur_time  # "HH:MM" for daily recurrence
        self.rid = rid

    def to_dict(self):
        return {"text": self.text, "fire_at": self.fire_at,
                "recurring": self.recurring, "recur_time": self.recur_time,
                "rid": self.rid}

    @classmethod
    def from_dict(cls, d):
        return cls(**d)

    def is_due(self) -> bool:
        return datetime.now() >= datetime.fromisoformat(self.fire_at)

    def reschedule(self):
        """Reschedule recurring reminder to next day same time."""
        if self.recurring and self.recur_time:
            now = datetime.now()
            h, m = map(int, self.recur_time.split(":"))
            next_fire = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if next_fire <= now:
                next_fire += timedelta(days=1)
            self.fire_at = next_fire.isoformat()


def parse_time_input(text: str) -> tuple[str, datetime] | None:
    """Parse natural language time expressions.
    Returns (reminder_text, fire_datetime) or None.
    """
    text = text.strip()

    # "in X min/minutes/hour/hours"
    m = re.match(
        r"(?:in\s+)?(\d+)\s*(min(?:ute)?s?|hr?s?|hours?|secs?|seconds?)\s+(.+)",
        text, re.IGNORECASE,
    )
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        msg = m.group(3)
        if unit.startswith("sec"):
            delta = timedelta(seconds=amount)
        elif unit.startswith("h"):
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(minutes=amount)
        return (msg, datetime.now() + delta)

    # "at HH:MM message"
    m = re.match(r"at\s+(\d{1,2}):(\d{2})\s+(.+)", text, re.IGNORECASE)
    if m:
        h, mi, msg = int(m.group(1)), int(m.group(2)), m.group(3)
        target = datetime.now().replace(hour=h, minute=mi, second=0, microsecond=0)
        if target <= datetime.now():
            target += timedelta(days=1)
        return (msg, target)

    # Fallback: "X min" at end
    m = re.match(r"(.+?)\s+in\s+(\d+)\s*(min(?:ute)?s?|hr?s?|hours?)", text, re.IGNORECASE)
    if m:
        msg = m.group(1)
        amount = int(m.group(2))
        unit = m.group(3).lower()
        delta = timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
        return (msg, datetime.now() + delta)

    return None


class SmartReminderManager(QObject):
    """Manages smart reminders with persistence and timed firing."""
    reminder_fired = pyqtSignal(str, int)  # (reminder text, rid) — rid for snooze

    def __init__(self):
        super().__init__()
        self._reminders: list[SmartReminder] = []
        self._next_id = 1
        self._history: list[dict] = []  # fired reminder log
        self._load()

        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(self._check)
        self._check_timer.start(10_000)  # check every 10s

    def add_raw(self, text: str) -> SmartReminder | None:
        """Parse natural language and add reminder. Returns reminder or None."""
        result = parse_time_input(text)
        if not result:
            return None
        msg, fire_at = result
        r = SmartReminder(msg, fire_at.isoformat(), rid=self._next_id)
        self._next_id += 1
        self._reminders.append(r)
        self._save()
        return r

    def add_recurring(self, text: str, time_str: str) -> SmartReminder:
        """Add a daily recurring reminder at HH:MM."""
        h, m = map(int, time_str.split(":"))
        now = datetime.now()
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        r = SmartReminder(text, target.isoformat(), recurring=True,
                          recur_time=time_str, rid=self._next_id)
        self._next_id += 1
        self._reminders.append(r)
        self._save()
        return r

    def remove(self, rid: int):
        self._reminders = [r for r in self._reminders if r.rid != rid]
        self._save()

    def get_all(self) -> list[SmartReminder]:
        return list(self._reminders)

    def get_pending_count(self) -> int:
        return len(self._reminders)

    def snooze(self, rid: int, minutes: int = 5):
        """Snooze a fired reminder by re-adding it with a delay."""
        # Find in history or create new
        text = f"Snoozed reminder #{rid}"
        for h in reversed(self._history):
            if h.get("rid") == rid:
                text = h["text"]
                break
        fire_at = (datetime.now() + timedelta(minutes=minutes)).isoformat()
        r = SmartReminder(text, fire_at, rid=self._next_id)
        self._next_id += 1
        self._reminders.append(r)
        self._save()
        return r

    def get_history(self, limit: int = 20) -> list[dict]:
        """Return recently fired reminders."""
        return self._history[-limit:]

    def _check(self):
        fired = []
        for r in self._reminders:
            if r.is_due():
                self.reminder_fired.emit(f"⏰ {r.text}", r.rid)
                self._history.append({
                    "text": r.text, "rid": r.rid,
                    "fired_at": datetime.now().isoformat(timespec="minutes"),
                })
                self._history = self._history[-50:]
                if r.recurring:
                    r.reschedule()
                else:
                    fired.append(r.rid)
        if fired:
            self._reminders = [r for r in self._reminders if r.rid not in fired]
            self._save()

    def _save(self):
        data = {"next_id": self._next_id,
                "reminders": [r.to_dict() for r in self._reminders],
                "history": self._history[-50:]}
        try:
            safe_json_save(data, _FILE)
        except IOError:
            pass

    def _load(self):
        if not os.path.exists(_FILE):
            return
        try:
            with open(_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self._next_id = data.get("next_id", 1)
            self._history = data.get("history", [])
            for d in data.get("reminders", []):
                self._reminders.append(SmartReminder.from_dict(d))
        except (json.JSONDecodeError, IOError, KeyError):
            pass

    def stop(self):
        self._check_timer.stop()
        self._save()
