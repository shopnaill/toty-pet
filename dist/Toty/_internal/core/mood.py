import time
from collections import deque
from datetime import datetime

from core.settings import Settings


class MoodEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.mood   = 70.0
        self.energy = 80.0
        self.focus  = 50.0
        self._target_mood = 70.0
        self._target_energy = 80.0
        self._target_focus = 50.0
        self._lerp_speed = 0.15
        self.session_start  = time.time()
        self.focus_seconds  = 0
        self.app_switches   = 0
        self.last_active_window = ""
        self._app_time: dict[str, float] = {}
        self._switch_times: deque = deque(maxlen=50)
        self._last_context_category = ""

    def tick(self, is_typing: bool, is_working: bool):
        decay_mood   = self.settings.get("mood_decay_rate")
        decay_energy = self.settings.get("energy_decay_rate")

        tod_energy_mod = self._time_of_day_energy_mod()

        self._target_energy = max(0, self._target_energy - decay_energy * 0.1 * tod_energy_mod)
        if not is_typing and not is_working:
            self._target_mood = max(0, self._target_mood - decay_mood * 0.05)
        if is_working:
            self._target_focus = min(100, self._target_focus + 0.5)
            self.focus_seconds += 1
        else:
            self._target_focus = max(0, self._target_focus - 0.2)
        if is_typing:
            self._target_energy = min(100, self._target_energy + 0.3)

        self.mood   += (self._target_mood   - self.mood)   * self._lerp_speed
        self.energy += (self._target_energy - self.energy) * self._lerp_speed
        self.focus  += (self._target_focus  - self.focus)  * self._lerp_speed

        if self._last_context_category:
            self._app_time[self._last_context_category] = (
                self._app_time.get(self._last_context_category, 0) + 1
            )

    def _time_of_day_energy_mod(self) -> float:
        """Energy drains faster late at night, slower in morning."""
        if not self.settings.get("enable_time_awareness"):
            return 1.0
        hour = datetime.now().hour
        if 6 <= hour < 10:
            return 0.6
        elif 10 <= hour < 14:
            return 0.8
        elif 14 <= hour < 17:
            return 1.0
        elif 17 <= hour < 21:
            return 1.2
        else:
            return 1.6

    def get_time_of_day_label(self) -> str:
        hour = datetime.now().hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def boost_mood(self, amount):
        self._target_mood = min(100, self._target_mood + amount)

    def boost_energy(self, amount):
        self._target_energy = min(100, self._target_energy + amount)

    def drain_mood(self, amount):
        self._target_mood = max(0, self._target_mood - amount)

    def pet_interaction(self):
        self.boost_mood(15)
        self.boost_energy(5)

    def get_dominant_state(self):
        if self.energy < 20:
            return "exhausted"
        if self.energy < 40:
            return "tired"
        if self.mood > 80:
            return "happy"
        if self.mood < 30:
            return "sad"
        if self.focus > 70:
            return "focused"
        return "neutral"

    def get_session_minutes(self):
        return int((time.time() - self.session_start) / 60)

    def get_focus_minutes(self):
        return self.focus_seconds // 60

    def record_app_switch(self, new_window):
        if new_window != self.last_active_window:
            self.app_switches += 1
            self._switch_times.append(time.time())
            self.last_active_window = new_window

    def set_context_category(self, category: str):
        self._last_context_category = category

    def get_app_time_minutes(self, category: str) -> int:
        return int(self._app_time.get(category, 0)) // 60

    def is_switching_too_fast(self) -> bool:
        window = self.settings.get("app_switch_warn_window_sec")
        threshold = self.settings.get("app_switch_warn_count")
        now = time.time()
        recent = [t for t in self._switch_times if now - t < window]
        return len(recent) >= threshold

    def get_mood_color(self) -> str:
        """Return a hex color based on current mood for bubble tinting."""
        dominant = self.get_dominant_state()
        return {
            "happy": "#E8FFE8",
            "sad": "#E0E8FF",
            "tired": "#F5F0E0",
            "exhausted": "#FFE8E0",
            "focused": "#E0F8FF",
            "neutral": "#FFFFFF",
        }.get(dominant, "#FFFFFF")

    def get_mood_border_color(self) -> str:
        dominant = self.get_dominant_state()
        return {
            "happy": "#2E8B57",
            "sad": "#4169E1",
            "tired": "#DAA520",
            "exhausted": "#CD5C5C",
            "focused": "#4682B4",
            "neutral": "#000000",
        }.get(dominant, "#000000")

    def get_stats_text(self):
        parts = [
            f"Session: {self.get_session_minutes()} min",
            f"Focus time: {self.get_focus_minutes()} min",
            f"Mood: {int(self.mood)}%  Energy: {int(self.energy)}%",
            f"App switches: {self.app_switches}",
        ]
        for cat, secs in sorted(self._app_time.items(), key=lambda x: -x[1]):
            mins = int(secs) // 60
            if mins > 0:
                parts.append(f"  {cat}: {mins} min")
        return "\n".join(parts)
