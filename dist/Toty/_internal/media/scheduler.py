import os
import json
import webbrowser
from datetime import datetime
from core.safe_json import safe_json_save


MUSIC_SCHEDULE_PATH = "music_schedule.json"


class MusicScheduler:
    """Schedule YouTube music playback at specific times."""

    def __init__(self):
        self.schedules: list[dict] = []
        self._fired_today: set[str] = set()
        self._last_check_date = ""
        self._load()

    def _load(self):
        if os.path.exists(MUSIC_SCHEDULE_PATH):
            try:
                with open(MUSIC_SCHEDULE_PATH, "r", encoding="utf-8") as f:
                    self.schedules = json.load(f)
            except (json.JSONDecodeError, IOError, UnicodeDecodeError):
                pass

    def save(self):
        safe_json_save(self.schedules, MUSIC_SCHEDULE_PATH, indent=4)

    def add_schedule(self, time_str: str, url: str, label: str = ""):
        self.schedules.append({
            "time": time_str,
            "url": url,
            "label": label or url,
            "enabled": True,
        })
        self.save()

    def remove_schedule(self, index: int):
        if 0 <= index < len(self.schedules):
            self.schedules.pop(index)
            self.save()

    def toggle_schedule(self, index: int):
        if 0 <= index < len(self.schedules):
            self.schedules[index]["enabled"] = not self.schedules[index].get("enabled", True)
            self.save()

    def check_and_fire(self) -> list[dict]:
        """Check if any scheduled music should play now. Returns fired entries."""
        now = datetime.now()
        current_time = now.strftime("%I:%M %p")
        today = now.strftime("%Y-%m-%d")

        if today != self._last_check_date:
            self._fired_today.clear()
            self._last_check_date = today

        fired = []
        for i, entry in enumerate(self.schedules):
            if not entry.get("enabled", True):
                continue
            key = f"{i}_{entry['time']}"
            if entry["time"] == current_time and key not in self._fired_today:
                self._fired_today.add(key)
                webbrowser.open(entry["url"])
                fired.append(entry)
        return fired

    def get_schedules_text(self) -> str:
        if not self.schedules:
            return "No music scheduled."
        lines = []
        for i, entry in enumerate(self.schedules):
            status = "ON" if entry.get("enabled", True) else "OFF"
            label = entry.get("label", entry["url"])[:30]
            lines.append(f"{i+1}. [{status}] {entry['time']} — {label}")
        return "\n".join(lines)
