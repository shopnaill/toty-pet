"""Habit tracker for the desktop pet.

Track daily habits like water intake, exercise, reading, etc.
Supports streaks, daily progress, and stats.
"""

import json
import logging
import os
import re
from datetime import date, datetime, timedelta

log = logging.getLogger("toty.habits")

HABITS_PATH = "habits.json"


class HabitTracker:
    """Track daily habits with streak counting."""

    def __init__(self):
        self.data: dict = {
            "habits": {},       # name -> {goal, icon, created}
            "log": {},          # "YYYY-MM-DD" -> {habit_name: count}
        }
        self._load()

    def _load(self):
        if os.path.exists(HABITS_PATH):
            try:
                with open(HABITS_PATH, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass

    def _save(self):
        with open(HABITS_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _today(self) -> str:
        return date.today().isoformat()

    def add_habit(self, name: str, goal: int = 1, icon: str = "\u2705") -> str:
        """Register a new habit to track."""
        key = name.lower().strip()
        if key in self.data["habits"]:
            return f"Already tracking \"{name}\""
        self.data["habits"][key] = {
            "goal": goal,
            "icon": icon,
            "created": self._today(),
        }
        self._save()
        return f"{icon} Now tracking \"{name}\" (daily goal: {goal}x)"

    def remove_habit(self, name: str) -> str:
        """Stop tracking a habit."""
        key = name.lower().strip()
        if key not in self.data["habits"]:
            return f"\u274c Not tracking \"{name}\""
        info = self.data["habits"].pop(key)
        self._save()
        return f"\U0001f5d1\ufe0f Stopped tracking \"{name}\""

    def log_habit(self, name: str, count: int = 1) -> str:
        """Log a habit for today."""
        key = name.lower().strip()
        # Auto-create common habits
        if key not in self.data["habits"]:
            auto = self._auto_detect_habit(key)
            if auto:
                self.data["habits"][key] = auto
            else:
                self.data["habits"][key] = {"goal": 1, "icon": "\u2705", "created": self._today()}

        today = self._today()
        day_log = self.data["log"].setdefault(today, {})
        day_log[key] = day_log.get(key, 0) + count

        info = self.data["habits"][key]
        current = day_log[key]
        goal = info.get("goal", 1)
        streak = self._get_streak(key)
        self._save()

        icon = info.get("icon", "\u2705")
        if current >= goal:
            return (f"{icon} {name.title()} logged! ({current}/{goal}) \u2014 Goal reached! "
                    f"\U0001f525 {streak} day streak!")
        return f"{icon} {name.title()} logged! ({current}/{goal}) \U0001f525 {streak} day streak"

    def _get_streak(self, habit_key: str) -> int:
        """Calculate current streak for a habit."""
        streak = 0
        d = date.today()
        goal = self.data["habits"].get(habit_key, {}).get("goal", 1)
        while True:
            day_str = d.isoformat()
            day_log = self.data["log"].get(day_str, {})
            if day_log.get(habit_key, 0) >= goal:
                streak += 1
                d -= timedelta(days=1)
            else:
                # Allow today to not be done yet
                if d == date.today() and streak == 0:
                    d -= timedelta(days=1)
                    continue
                break
        return streak

    def status(self) -> str:
        """Show today's habit status."""
        habits = self.data.get("habits", {})
        if not habits:
            return ("\U0001f4cb No habits tracked yet!\n"
                    "Try: \"I drank water\" or \"track exercise\"")

        today = self._today()
        day_log = self.data["log"].get(today, {})

        lines = [f"\U0001f4ca Today's Habits ({today}):"]
        for key, info in sorted(habits.items()):
            icon = info.get("icon", "\u2705")
            goal = info.get("goal", 1)
            current = day_log.get(key, 0)
            streak = self._get_streak(key)
            bar = self._progress_bar(current, goal)
            check = "\u2705" if current >= goal else "\u2b1c"
            lines.append(f"  {check} {icon} {key.title()}: {bar} {current}/{goal}  "
                         f"\U0001f525{streak}d")
        return "\n".join(lines)

    def weekly_report(self) -> str:
        """Show habit stats for the past 7 days."""
        habits = self.data.get("habits", {})
        if not habits:
            return "\U0001f4cb No habits tracked yet!"

        lines = ["\U0001f4c5 Weekly Habit Report:"]
        today = date.today()
        for key, info in sorted(habits.items()):
            icon = info.get("icon", "\u2705")
            goal = info.get("goal", 1)
            days_hit = 0
            for i in range(7):
                d = (today - timedelta(days=i)).isoformat()
                if self.data["log"].get(d, {}).get(key, 0) >= goal:
                    days_hit += 1
            lines.append(f"  {icon} {key.title()}: {days_hit}/7 days  "
                         f"\U0001f525{self._get_streak(key)}d streak")
        return "\n".join(lines)

    def _progress_bar(self, current: int, goal: int, width: int = 8) -> str:
        ratio = min(current / max(goal, 1), 1.0)
        filled = int(ratio * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    def _auto_detect_habit(self, key: str) -> dict | None:
        """Auto-detect common habits and assign icons/goals."""
        presets = {
            "water": {"goal": 8, "icon": "\U0001f4a7"},
            "exercise": {"goal": 1, "icon": "\U0001f3cb\ufe0f"},
            "read": {"goal": 1, "icon": "\U0001f4d6"},
            "reading": {"goal": 1, "icon": "\U0001f4d6"},
            "walk": {"goal": 1, "icon": "\U0001f6b6"},
            "stretch": {"goal": 1, "icon": "\U0001f9d8"},
            "meditate": {"goal": 1, "icon": "\U0001f9d8"},
            "meditation": {"goal": 1, "icon": "\U0001f9d8"},
            "sleep": {"goal": 1, "icon": "\U0001f634"},
            "prayer": {"goal": 5, "icon": "\U0001f54c"},
            "pray": {"goal": 5, "icon": "\U0001f54c"},
            "study": {"goal": 1, "icon": "\U0001f4da"},
            "code": {"goal": 1, "icon": "\U0001f4bb"},
            "coding": {"goal": 1, "icon": "\U0001f4bb"},
            "vitamins": {"goal": 1, "icon": "\U0001f48a"},
            "breakfast": {"goal": 1, "icon": "\U0001f373"},
            "fruit": {"goal": 1, "icon": "\U0001f34e"},
            "journal": {"goal": 1, "icon": "\U0001f4d3"},
        }
        if key in presets:
            return {**presets[key], "created": self._today()}
        return None


def parse_habit_command(text: str) -> tuple[str | None, str | None, int]:
    """Parse habit-related commands from chat text.

    Returns (action, habit_name, count):
      action: 'log', 'track', 'untrack', 'status', 'weekly', or None
    """
    t = text.strip().lower()

    # Status checks
    if re.match(r"(?:my\s+)?habits?(?:\s+status)?$", t):
        return "status", None, 0
    if re.match(r"(?:weekly|week)\s+(?:habits?|report)", t):
        return "weekly", None, 0
    if re.match(r"habits?\s+(?:weekly|report|week)", t):
        return "weekly", None, 0

    # Track new habit: "track water 8x"
    m = re.match(r"track\s+(.+?)(?:\s+(\d+)x?)?$", t)
    if m:
        return "track", m.group(1).strip(), int(m.group(2) or 1)

    # Untrack: "untrack water"
    m = re.match(r"(?:un ?track|stop\s+tracking|remove\s+habit)\s+(.+)", t)
    if m:
        return "untrack", m.group(1).strip(), 0

    # Log patterns: "I drank water", "drank 3 waters", "did exercise"
    log_patterns = [
        r"i\s+(?:drank|had|ate|did|took|went\s+for|finished|completed)\s+(?:a?\s*)?(\d*)\s*(.+)",
        r"(?:drank|had|ate|did|took|went\s+for|finished|completed)\s+(?:a?\s*)?(\d*)\s*(.+)",
        r"log\s+(\d*)\s*(.+)",
    ]
    for pat in log_patterns:
        m = re.match(pat, t)
        if m:
            count_str = m.group(1).strip()
            count = int(count_str) if count_str else 1
            name = m.group(2).strip()
            # Clean common words
            name = re.sub(r"\b(glasses?\s+of|cups?\s+of|a\s+)\b", "", name).strip()
            if name:
                return "log", name, count

    return None, None, 0
