"""
Pet Diary — auto-generated daily summary of pet's activities and mood.
"""
import json
import os
from datetime import date, datetime
from PyQt6.QtCore import QTimer
from core.safe_json import safe_json_save

_DATA_PATH = "pet_diary.json"


class PetDiary:
    """Records daily events and generates summary entries."""

    def __init__(self):
        self._entries: dict[str, dict] = {}  # date_str -> {events: [...], summary: str}
        self._today_events: list[str] = []
        self._dirty = False
        self._load()
        # Flush to disk every 30s if dirty
        self._flush_timer = QTimer()
        self._flush_timer.timeout.connect(self._flush)
        self._flush_timer.start(30000)

    def log_event(self, event: str):
        """Log a noteworthy event for today."""
        today = date.today().isoformat()
        if today not in self._entries:
            self._entries[today] = {"events": [], "summary": ""}
        self._entries[today]["events"].append(
            f"[{datetime.now().strftime('%H:%M')}] {event}"
        )
        self._today_events.append(event)
        # Keep only last 50 events per day
        self._entries[today]["events"] = self._entries[today]["events"][-50:]
        self._dirty = True

    def get_today_summary(self) -> str:
        """Generate a summary for today."""
        today = date.today().isoformat()
        entry = self._entries.get(today, {})
        events = entry.get("events", [])
        if not events:
            return "📔 Nothing happened yet today. Let's make it productive!"

        lines = [f"📔 Diary for {date.today().strftime('%B %d, %Y')}:", ""]
        for ev in events[-20:]:  # show last 20
            lines.append(f"  {ev}")
        lines.append(f"\n📊 Total events today: {len(events)}")
        return "\n".join(lines)

    def get_entry(self, date_str: str) -> str:
        """Get diary entry for a specific date."""
        entry = self._entries.get(date_str)
        if not entry:
            return f"No diary entry for {date_str}"
        events = entry.get("events", [])
        lines = [f"📔 Diary for {date_str}:", ""]
        for ev in events:
            lines.append(f"  {ev}")
        return "\n".join(lines)

    def get_all_dates(self) -> list[str]:
        """Get all dates with diary entries, sorted newest first."""
        return sorted(self._entries.keys(), reverse=True)

    def _load(self):
        if os.path.exists(_DATA_PATH):
            try:
                with open(_DATA_PATH, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        try:
            # Keep only last 90 days
            dates = sorted(self._entries.keys())
            while len(dates) > 90:
                del self._entries[dates.pop(0)]
            safe_json_save(self._entries, _DATA_PATH)
            self._dirty = False
        except OSError:
            pass

    def _flush(self):
        if self._dirty:
            self._save()

    def stop(self):
        """Flush remaining data and stop the timer."""
        self._flush_timer.stop()
        if self._dirty:
            self._save()
