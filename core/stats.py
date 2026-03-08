import os
import json
from datetime import datetime, date
from core.safe_json import safe_json_save


STATS_PATH = "pet_stats.json"


def _xp_for_level(level: int) -> int:
    """XP needed to reach the *next* level from this one."""
    return 100 + level * 50


class PersistentStats:
    def __init__(self):
        self.data = {
            "current_streak": 0,
            "longest_streak": 0,
            "last_session_date": "",
            "total_focus_min": 0,
            "total_sessions": 0,
            "daily_focus_min": 0,
            "daily_date": "",
            "notes": [],
            # v3 additions
            "xp": 0,
            "level": 1,
            "achievements": [],
            "todo_items": [],
            "total_pomodoros": 0,
            "total_pets": 0,
            "total_keys": 0,
        }
        self._load()
        self._check_new_day()

    def _load(self):
        if os.path.exists(STATS_PATH):
            try:
                with open(STATS_PATH, "r") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        safe_json_save(self.data, STATS_PATH, indent=4)

    def _check_new_day(self):
        today = date.today().isoformat()
        last = self.data.get("daily_date", "")
        if last != today:
            yesterday = date.today().toordinal() - 1
            try:
                last_ord = date.fromisoformat(last).toordinal() if last else 0
            except ValueError:
                last_ord = 0
            if last_ord == yesterday:
                self.data["current_streak"] += 1
            elif last_ord < yesterday:
                self.data["current_streak"] = 1
            self.data["longest_streak"] = max(
                self.data["longest_streak"], self.data["current_streak"]
            )
            self.data["daily_focus_min"] = 0
            self.data["daily_date"] = today
            self.save()

    def record_session_end(self, focus_min):
        self.data["total_focus_min"] += focus_min
        self.data["daily_focus_min"] += focus_min
        self.data["total_sessions"] += 1
        self.data["last_session_date"] = date.today().isoformat()
        self.save()

    def add_note(self, text):
        self.data["notes"].append(
            {"text": text, "time": datetime.now().isoformat(timespec="minutes")}
        )
        self.data["notes"] = self.data["notes"][-50:]
        self.save()

    # --- v3: XP & Leveling ---
    def add_xp(self, amount: int) -> bool:
        """Add XP. Returns True if leveled up."""
        self.data["xp"] = self.data.get("xp", 0) + amount
        leveled = False
        while self.data["xp"] >= _xp_for_level(self.data.get("level", 1)):
            self.data["xp"] -= _xp_for_level(self.data["level"])
            self.data["level"] = self.data.get("level", 1) + 1
            leveled = True
        self.save()
        return leveled

    def get_level_info(self) -> str:
        lv = self.data.get("level", 1)
        xp = self.data.get("xp", 0)
        needed = _xp_for_level(lv)
        bar_len = 10
        filled = int(xp / max(needed, 1) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        return f"Lv.{lv}  [{bar}]  {xp}/{needed} XP"

    # --- v3: To-do list (v14: due dates + priorities) ---
    _PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "": 3}

    def add_todo(self, text: str, priority: str = "", due: str = ""):
        """Add a todo. priority: 'high','medium','low' or ''. due: ISO date or ''."""
        self.data.setdefault("todo_items", []).append(
            {"text": text, "done": False,
             "created": datetime.now().isoformat(timespec="minutes"),
             "priority": priority, "due": due}
        )
        self.save()

    def toggle_todo(self, index: int):
        items = self.data.get("todo_items", [])
        if 0 <= index < len(items):
            items[index]["done"] = not items[index]["done"]
            self.save()

    def remove_todo(self, index: int):
        items = self.data.get("todo_items", [])
        if 0 <= index < len(items):
            items.pop(index)
            self.save()

    def get_todos(self) -> list:
        return self.data.get("todo_items", [])

    def get_todos_sorted(self) -> list:
        """Return todos sorted: undone first (by priority then due), done last."""
        items = list(self.data.get("todo_items", []))
        today = date.today().isoformat()

        def _sort_key(t):
            done = 1 if t.get("done") else 0
            pri = self._PRIORITY_ORDER.get(t.get("priority", ""), 3)
            due = t.get("due", "") or "9999-99-99"
            return (done, pri, due)

        items_with_idx = [(i, t) for i, t in enumerate(items)]
        items_with_idx.sort(key=lambda x: _sort_key(x[1]))
        return items_with_idx

    def get_overdue_count(self) -> int:
        today = date.today().isoformat()
        return sum(1 for t in self.get_todos()
                   if not t.get("done") and t.get("due") and t["due"] < today)

    # --- v3: Achievement tracking helpers ---
    def has_achievement(self, aid: str) -> bool:
        return aid in self.data.get("achievements", [])

    def unlock_achievement(self, aid: str):
        achs = self.data.setdefault("achievements", [])
        if aid not in achs:
            achs.append(aid)
            self.save()

    def get_welcome_message(self):
        streak = self.data.get("current_streak", 0)
        total = self.data.get("total_sessions", 0)
        lv = self.data.get("level", 1)
        if total == 0:
            return "First time? Welcome! I'm your new pet!"
        if streak > 1:
            return f"Welcome back! {streak}-day streak! (Lv.{lv})"
        return f"Welcome back! Let's get productive! (Lv.{lv})"

    def get_summary(self):
        return (
            f"Streak: {self.data['current_streak']} days "
            f"(best: {self.data['longest_streak']})\n"
            f"Today's focus: {self.data['daily_focus_min']} min\n"
            f"All-time focus: {self.data['total_focus_min']} min\n"
            f"Sessions: {self.data['total_sessions']}\n"
            f"Pomodoros: {self.data.get('total_pomodoros', 0)}\n"
            f"{self.get_level_info()}"
        )
