"""
Tasbeeh Counter — Interactive digital dhikr counter.
Click the pet when tasbeeh accessory is active to increment.
Tracks daily/lifetime counts with persistence.
"""
import json
import os
from datetime import date
from core.safe_json import safe_json_save

_DATA_PATH = "tasbeeh_data.json"

# Common adhkar with their Arabic text and target counts
TASBEEH_PRESETS = {
    "subhanallah": {"ar": "سبحان الله", "en": "SubhanAllah", "target": 33},
    "alhamdulillah": {"ar": "الحمد لله", "en": "Alhamdulillah", "target": 33},
    "allahuakbar": {"ar": "الله أكبر", "en": "Allahu Akbar", "target": 34},
    "la_ilaha": {"ar": "لا إله إلا الله", "en": "La ilaha illallah", "target": 100},
    "astaghfirullah": {"ar": "أستغفر الله", "en": "Astaghfirullah", "target": 100},
    "salawat": {"ar": "اللهم صل على محمد", "en": "Salawat", "target": 100},
    "hawqala": {"ar": "لا حول ولا قوة إلا بالله", "en": "Hawqala", "target": 100},
    "free": {"ar": "تسبيح حر", "en": "Free Count", "target": 0},
}


class TasbeehCounter:
    def __init__(self):
        self.current_preset = "subhanallah"
        self.count = 0
        self.today_total = 0
        self.lifetime_total = 0
        self._last_date = date.today().isoformat()
        self._load()

    def _load(self):
        if os.path.exists(_DATA_PATH):
            try:
                with open(_DATA_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.current_preset = data.get("current_preset", "subhanallah")
                self.lifetime_total = data.get("lifetime_total", 0)
                saved_date = data.get("last_date", "")
                if saved_date == date.today().isoformat():
                    self.today_total = data.get("today_total", 0)
                    self.count = data.get("current_count", 0)
                else:
                    self.today_total = 0
                    self.count = 0
                self._last_date = date.today().isoformat()
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        data = {
            "current_preset": self.current_preset,
            "current_count": self.count,
            "today_total": self.today_total,
            "lifetime_total": self.lifetime_total,
            "last_date": self._last_date,
        }
        try:
            safe_json_save(data, _DATA_PATH)
        except OSError:
            pass

    def increment(self) -> dict:
        """Increment counter. Returns status dict with milestone info."""
        self.count += 1
        self.today_total += 1
        self.lifetime_total += 1
        self._last_date = date.today().isoformat()

        preset = TASBEEH_PRESETS.get(self.current_preset, TASBEEH_PRESETS["free"])
        target = preset["target"]
        completed = target > 0 and self.count >= target

        result = {
            "count": self.count,
            "target": target,
            "completed": completed,
            "today_total": self.today_total,
            "lifetime_total": self.lifetime_total,
            "ar": preset["ar"],
            "en": preset["en"],
        }

        if completed:
            self.count = 0  # Reset for next round

        self.save()
        return result

    def set_preset(self, key: str):
        if key in TASBEEH_PRESETS:
            self.current_preset = key
            self.count = 0
            self.save()

    def reset_count(self):
        self.count = 0
        self.save()

    def get_display(self) -> str:
        preset = TASBEEH_PRESETS.get(self.current_preset, TASBEEH_PRESETS["free"])
        if preset["target"] > 0:
            return f"{preset['ar']}  {self.count}/{preset['target']}"
        return f"{preset['ar']}  {self.count}"

    def get_summary(self) -> str:
        return (
            f"📿 Today: {self.today_total} | Lifetime: {self.lifetime_total}\n"
            f"Current: {self.get_display()}"
        )
