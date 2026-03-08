"""Smart reminder system for the desktop pet.

Supports chat-based reminders: "remind me in 5 minutes to take a break"
Uses QTimer for scheduling and emits signals when reminders fire.
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta
from core.safe_json import safe_json_save

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger("toty.reminders")

REMINDERS_PATH = "reminders.json"


class ReminderManager(QObject):
    """Manages timed reminders with persistence."""

    reminder_fired = pyqtSignal(str)  # Emits the reminder text

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reminders: list[dict] = []  # {id, text, fire_at_iso, fired}
        self._timers: dict[int, QTimer] = {}
        self._next_id = 1
        self._load()
        self._schedule_pending()

    def _load(self):
        if os.path.exists(REMINDERS_PATH):
            try:
                with open(REMINDERS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._reminders = data.get("reminders", [])
                    self._next_id = data.get("next_id", 1)
            except (json.JSONDecodeError, IOError):
                pass

    def _save(self):
        data = {
            "reminders": self._reminders,
            "next_id": self._next_id,
        }
        safe_json_save(data, REMINDERS_PATH)

    def _schedule_pending(self):
        """Re-schedule any reminders that haven't fired yet."""
        now = datetime.now()
        for rem in self._reminders:
            if rem.get("fired"):
                continue
            fire_at = datetime.fromisoformat(rem["fire_at_iso"])
            if fire_at <= now:
                # Already past due, fire immediately
                self._fire(rem)
            else:
                delay_ms = int((fire_at - now).total_seconds() * 1000)
                self._start_timer(rem["id"], delay_ms, rem)

    def _start_timer(self, rid: int, delay_ms: int, rem: dict):
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._fire(rem))
        timer.start(delay_ms)
        self._timers[rid] = timer

    def _fire(self, rem: dict):
        rem["fired"] = True
        self._save()
        tid = rem["id"]
        if tid in self._timers:
            self._timers.pop(tid).stop()
        self.reminder_fired.emit(rem["text"])
        log.info("Reminder fired: %s", rem["text"])

    def add(self, text: str, minutes: float | None = None,
            fire_at: datetime | None = None) -> str:
        """Add a new reminder. Returns confirmation message."""
        if minutes is not None:
            fire_at = datetime.now() + timedelta(minutes=minutes)
        if fire_at is None:
            return "\u26a0\ufe0f Couldn't figure out when to remind you."

        rem = {
            "id": self._next_id,
            "text": text,
            "fire_at_iso": fire_at.isoformat(timespec="seconds"),
            "fired": False,
        }
        self._next_id += 1
        self._reminders.append(rem)
        self._save()

        delay_ms = max(0, int((fire_at - datetime.now()).total_seconds() * 1000))
        self._start_timer(rem["id"], delay_ms, rem)

        # Human-friendly time description
        if minutes is not None:
            if minutes >= 60:
                time_str = f"{minutes / 60:.1f} hour(s)"
            else:
                time_str = f"{int(minutes)} minute(s)"
        else:
            time_str = fire_at.strftime("%H:%M")

        log.info("Reminder set: '%s' in %s", text, time_str)
        return f"\u23f0 Reminder set! I'll remind you in {time_str}:\n\"{text}\""

    def list_active(self) -> str:
        """List pending reminders."""
        pending = [r for r in self._reminders if not r.get("fired")]
        if not pending:
            return "\u2705 No active reminders."

        lines = [f"\u23f0 Active Reminders ({len(pending)}):"]
        now = datetime.now()
        for rem in pending:
            fire_at = datetime.fromisoformat(rem["fire_at_iso"])
            diff = fire_at - now
            if diff.total_seconds() > 0:
                mins = int(diff.total_seconds() / 60)
                if mins >= 60:
                    time_str = f"{mins // 60}h {mins % 60}m left"
                else:
                    time_str = f"{mins}m left"
            else:
                time_str = "overdue"
            lines.append(f"  #{rem['id']} \u2022 {rem['text']}  ({time_str})")
        return "\n".join(lines)

    def cancel(self, rid: int | None = None, keyword: str = "") -> str:
        """Cancel a reminder by ID or keyword."""
        target = None
        for rem in self._reminders:
            if rem.get("fired"):
                continue
            if rid is not None and rem["id"] == rid:
                target = rem
                break
            if keyword and keyword.lower() in rem["text"].lower():
                target = rem
                break

        if not target:
            return "\u274c Couldn't find that reminder."

        target["fired"] = True
        tid = target["id"]
        if tid in self._timers:
            self._timers.pop(tid).stop()
        self._save()
        return f"\u274c Cancelled reminder: \"{target['text']}\""

    def clear_all(self) -> str:
        """Cancel all active reminders."""
        count = 0
        for rem in self._reminders:
            if not rem.get("fired"):
                rem["fired"] = True
                count += 1
        for timer in self._timers.values():
            timer.stop()
        self._timers.clear()
        self._save()
        return f"\U0001f9f9 Cleared {count} reminder(s)."

    def cleanup_old(self, days: int = 7):
        """Remove fired reminders older than X days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        self._reminders = [
            r for r in self._reminders
            if not r.get("fired") or r.get("fire_at_iso", "") > cutoff
        ]
        self._save()


def parse_reminder(text: str) -> tuple[str | None, float | None]:
    """Parse a reminder command from natural text.

    Returns (reminder_text, minutes) or (None, None) if not a reminder command.
    """
    patterns = [
        # "remind me in 5 minutes to take a break"
        r"remind\s+me\s+in\s+(\d+\.?\d*)\s*(min(?:ute)?s?|hour?s?|hr?s?|sec(?:ond)?s?)\s+(?:to\s+)?(.+)",
        # "remind me to take a break in 5 minutes"
        r"remind\s+me\s+(?:to\s+)?(.+?)\s+in\s+(\d+\.?\d*)\s*(min(?:ute)?s?|hour?s?|hr?s?|sec(?:ond)?s?)",
        # "set a reminder for 30 minutes: drink water"
        r"(?:set|create)\s+(?:a\s+)?reminder\s+(?:for|in)\s+(\d+\.?\d*)\s*(min(?:ute)?s?|hour?s?|hr?s?)\s*[:\-]?\s*(.+)",
        # "in 10 minutes remind me to ..."
        r"in\s+(\d+\.?\d*)\s*(min(?:ute)?s?|hour?s?|hr?s?)\s+remind\s+me\s+(?:to\s+)?(.+)",
    ]

    for i, pat in enumerate(patterns):
        m = re.match(pat, text.strip(), re.IGNORECASE)
        if m:
            groups = m.groups()
            if i == 1:
                # Pattern 2: text before the time
                reminder_text = groups[0]
                amount = float(groups[1])
                unit = groups[2].lower()
            else:
                amount = float(groups[0])
                unit = groups[1].lower()
                reminder_text = groups[2]

            # Convert to minutes
            if unit.startswith("h"):
                minutes = amount * 60
            elif unit.startswith("sec"):
                minutes = amount / 60
            else:
                minutes = amount

            return reminder_text.strip(), minutes

    return None, None
