from datetime import datetime

from core.stats import PersistentStats
from core.settings import Settings


ACHIEVEMENTS = {
    "first_pet":       {"name": "First Pet!",        "desc": "Pet your buddy for the first time"},
    "pet_10":          {"name": "Pet Lover",          "desc": "Pet 10 times total"},
    "pet_50":          {"name": "Best Friends",       "desc": "Pet 50 times total"},
    "focus_30":        {"name": "Deep Focus",         "desc": "Accumulate 30 min of focus"},
    "focus_120":       {"name": "Flow State",         "desc": "Accumulate 120 min of focus"},
    "focus_300":       {"name": "Focus Master",       "desc": "Accumulate 300 min of focus"},
    "pomodoro_1":      {"name": "First Pomodoro",     "desc": "Complete your first Pomodoro"},
    "pomodoro_10":     {"name": "Pomodoro Pro",       "desc": "Complete 10 Pomodoros"},
    "streak_3":        {"name": "3-Day Streak",       "desc": "Use your pet 3 days in a row"},
    "streak_7":        {"name": "Week Warrior",       "desc": "7-day streak"},
    "streak_30":       {"name": "Monthly Master",     "desc": "30-day streak"},
    "level_5":         {"name": "Rising Star",        "desc": "Reach level 5"},
    "level_10":        {"name": "Veteran",            "desc": "Reach level 10"},
    "level_25":        {"name": "Legend",              "desc": "Reach level 25"},
    "keys_1000":       {"name": "Keyboard Warrior",   "desc": "Type 1,000 keys in a session"},
    "keys_10000":      {"name": "Typing Machine",     "desc": "Type 10,000 keys in a session"},
    "note_1":          {"name": "Note Taker",         "desc": "Save your first note"},
    "todo_done_5":     {"name": "Task Master",        "desc": "Complete 5 to-do items"},
    "daily_goal":      {"name": "Goal Crusher",       "desc": "Hit your daily focus goal"},
    "night_owl":       {"name": "Night Owl",          "desc": "Use the pet after midnight"},
    "early_bird":      {"name": "Early Bird",         "desc": "Use the pet before 7 AM"},
    "combo_triple":    {"name": "Triple Pet!",        "desc": "Triple-combo pet your buddy"},
}


class AchievementEngine:
    def __init__(self, stats: PersistentStats, settings: Settings):
        self.stats = stats
        self.settings = settings
        self._pending: list[str] = []

    def check_all(self, session_keys: int = 0, session_focus_min: int = 0):
        """Run all achievement checks. Call periodically."""
        d = self.stats.data
        checks = {
            "first_pet":    d.get("total_pets", 0) >= 1,
            "pet_10":       d.get("total_pets", 0) >= 10,
            "pet_50":       d.get("total_pets", 0) >= 50,
            "focus_30":     d.get("total_focus_min", 0) + session_focus_min >= 30,
            "focus_120":    d.get("total_focus_min", 0) + session_focus_min >= 120,
            "focus_300":    d.get("total_focus_min", 0) + session_focus_min >= 300,
            "pomodoro_1":   d.get("total_pomodoros", 0) >= 1,
            "pomodoro_10":  d.get("total_pomodoros", 0) >= 10,
            "streak_3":     d.get("current_streak", 0) >= 3,
            "streak_7":     d.get("current_streak", 0) >= 7,
            "streak_30":    d.get("current_streak", 0) >= 30,
            "level_5":      d.get("level", 1) >= 5,
            "level_10":     d.get("level", 1) >= 10,
            "level_25":     d.get("level", 1) >= 25,
            "keys_1000":    session_keys >= 1000,
            "keys_10000":   session_keys >= 10000,
            "note_1":       len(d.get("notes", [])) >= 1,
            "daily_goal":   (d.get("daily_focus_min", 0) + session_focus_min)
                            >= self.settings.get("daily_goal_focus_min"),
        }
        # Time-based
        hour = datetime.now().hour
        checks["night_owl"]  = hour >= 0 and hour < 4
        checks["early_bird"] = hour >= 4 and hour < 7

        # Check completed todos
        done_count = sum(1 for t in d.get("todo_items", []) if t.get("done"))
        checks["todo_done_5"] = done_count >= 5

        for aid, condition in checks.items():
            if condition and not self.stats.has_achievement(aid):
                self._unlock(aid)

    def check_combo(self, combo_count: int):
        if combo_count >= 3 and not self.stats.has_achievement("combo_triple"):
            self._unlock("combo_triple")

    def _unlock(self, aid: str):
        self.stats.unlock_achievement(aid)
        self._pending.append(aid)
        if self.settings.get("enable_xp_system"):
            self.stats.add_xp(self.settings.get("xp_per_achievement"))

    def pop_pending(self) -> list[str]:
        out = list(self._pending)
        self._pending.clear()
        return out

    def get_achievements_text(self) -> str:
        unlocked = self.stats.data.get("achievements", [])
        lines = []
        for aid, info in ACHIEVEMENTS.items():
            mark = "✓" if aid in unlocked else "○"
            lines.append(f"{mark} {info['name']}: {info['desc']}")
        return "\n".join(lines)

    def get_unlocked_count(self) -> tuple[int, int]:
        return len(self.stats.data.get("achievements", [])), len(ACHIEVEMENTS)
