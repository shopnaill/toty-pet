import os
import json


class Settings:
    DEFAULTS = {
        "pet_name": "Blobby",
        "speech_cooldown_sec": 8,
        "typing_fast_threshold": 5,
        "idle_sleep_timeout_sec": 20,
        "brain_tick_ms": 3000,
        "context_check_ms": 2000,
        "pomodoro_work_min": 25,
        "pomodoro_break_min": 5,
        "stretch_reminder_min": 30,
        "water_reminder_min": 45,
        "quiet_hours_start": 23,
        "quiet_hours_end": 7,
        "enable_keyboard_tracking": True,
        "enable_window_tracking": True,
        "enable_reminders": True,
        "mood_decay_rate": 0.5,
        "energy_decay_rate": 0.3,
        "enable_follow_cursor": False,
        "follow_cursor_speed": 4,
        "focus_mode": False,
        "burst_threshold": 12,
        "backspace_rage_threshold": 6,
        "app_switch_warn_count": 6,
        "app_switch_warn_window_sec": 600,
        "wander_to_mouse_chance": 0.08,
        "taskbar_gravity": True,
        "daily_goal_focus_min": 60,
        # v3 new settings
        "enable_system_tray": True,
        "enable_achievements": True,
        "enable_xp_system": True,
        "xp_per_focus_min": 10,
        "xp_per_pomodoro": 50,
        "xp_per_achievement": 100,
        "enable_time_awareness": True,
        "enable_mini_todo": True,
        "enable_interaction_combos": True,
        "pet_combo_window_sec": 2.0,
        "enable_multi_monitor": True,
        "bubble_mood_colors": True,
        # v5: Prayer times
        "enable_prayer_times": True,
        "prayer_reminder_min": 10,
        "prayer_latitude": 24.7136,
        "prayer_longitude": 46.6753,
        "prayer_calc_method": "umm_al_qura",
        "prayer_fajr_angle": 18.5,
        "prayer_isha_angle": 0,
        "prayer_isha_minutes": 90,
        # v8: Azkar reminders
        "enable_azkar": True,
        "azkar_reminder_min": 30,
        # v6: AI Brain (Ollama)
        "enable_ai": True,
        "ai_model": "phi3",
        "ai_base_url": "http://localhost:11434",
        "ai_personality": "cute, playful, caring, witty, sometimes sarcastic, loves to joke around",
        "ai_max_tokens": 200,
        "ai_temperature": 0.9,
        # v9: Desktop Auto-Organizer
        "enable_desktop_organizer": True,
        "organizer_check_sec": 10,
        # v10: Skin system
        "current_skin": "default",
        # v11: Progress monitor
        "enable_progress_monitor": True,
    }

    def __init__(self, path="settings.json"):
        self.path = path
        self.data = dict(self.DEFAULTS)
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass
        self.save()

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=4)

    def get(self, key):
        return self.data.get(key, self.DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value
        self.save()
