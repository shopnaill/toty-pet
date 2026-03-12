"""
Eye Care Mode (20-20-20 Rule) — every 20 min, remind user to
look 20 feet away for 20 seconds. Also tracks hydration and stretch breaks.
v14: Rich break content — stretch prompts, breathing exercises, motivational quotes.
"""
import random
import time
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

_STRETCH_PROMPTS = [
    "🧘 Roll your shoulders back 5 times, then forward 5 times.",
    "🧘 Stand up and touch your toes — hold for 10 seconds!",
    "🧘 Stretch your arms overhead and lean left, then right.",
    "🧘 Do 5 neck rolls — slowly, each direction.",
    "🧘 Stand up, hands on hips, twist left-right 5 times.",
    "🧘 Clasp your hands behind your back and stretch your chest open.",
    "🧘 Raise one arm overhead and bend sideways. Switch sides!",
]

_BREATHING_EXERCISES = [
    "🌬️ Box Breathing: Inhale 4s → Hold 4s → Exhale 4s → Hold 4s. Repeat 3x.",
    "🌬️ 4-7-8 Breath: Inhale 4s → Hold 7s → Exhale 8s. Feel the calm.",
    "🌬️ Deep breath: Inhale slowly through nose (5s), exhale through mouth (5s). 3x.",
    "🌬️ Belly breathing: Hand on stomach, breathe deeply so your hand rises. 5 breaths.",
]

_MOTIVATIONAL_QUOTES = [
    "💪 \"The only way to do great work is to love what you do.\"",
    "💪 \"Small progress is still progress.\"",
    "💪 \"You don't have to be perfect to be amazing.\"",
    "💪 \"Rest is productive. Taking care of yourself IS the work.\"",
    "💪 \"Focus on progress, not perfection.\"",
    "💪 \"One step at a time. You've got this!\"",
    "💪 \"Your future self will thank you for this break.\"",
]


class EyeCareManager(QObject):
    """Manages eye-care, hydration, and stretch reminders."""
    break_needed = pyqtSignal(str, str)  # (break_type, message)
    break_finished = pyqtSignal(str)     # break_type

    def __init__(self, eye_min: int = 20, water_min: int = 45,
                 stretch_min: int = 30):
        super().__init__()
        self._eye_interval = eye_min * 60_000
        self._water_interval = water_min * 60_000
        self._stretch_interval = stretch_min * 60_000

        self._eye_breaks_today = 0
        self._water_breaks_today = 0
        self._stretch_breaks_today = 0

        # Active break state
        self._in_break = False
        self._break_type = ""

        # Eye care timer (20-20-20)
        self._eye_timer = QTimer(self)
        self._eye_timer.timeout.connect(self._on_eye)
        self._eye_timer.start(self._eye_interval)

        # Water reminder
        self._water_timer = QTimer(self)
        self._water_timer.timeout.connect(self._on_water)
        self._water_timer.start(self._water_interval)

        # Stretch reminder
        self._stretch_timer = QTimer(self)
        self._stretch_timer.timeout.connect(self._on_stretch)
        self._stretch_timer.start(self._stretch_interval)

        # 20-second countdown timer for eye break
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setSingleShot(True)
        self._countdown_timer.timeout.connect(self._on_eye_done)

    def _on_eye(self):
        if self._in_break:
            return
        self._in_break = True
        self._break_type = "eye"
        extra = random.choice(_BREATHING_EXERCISES)
        self.break_needed.emit("eye",
            f"👁️ 20-20-20: Look 20 feet away for 20 seconds!\n{extra}")
        self._countdown_timer.start(20_000)

    def _on_eye_done(self):
        self._in_break = False
        self._eye_breaks_today += 1
        self.break_finished.emit("eye")

    def _on_water(self):
        if self._in_break:
            return
        self._water_breaks_today += 1
        quote = random.choice(_MOTIVATIONAL_QUOTES)
        self.break_needed.emit("water", f"💧 Time to drink some water!\n{quote}")

    def _on_stretch(self):
        if self._in_break:
            return
        self._stretch_breaks_today += 1
        prompt = random.choice(_STRETCH_PROMPTS)
        self.break_needed.emit("stretch", f"🧘 Stretch break!\n{prompt}")

    def skip_break(self):
        """User dismisses current break."""
        self._in_break = False
        self._countdown_timer.stop()

    def get_stats(self) -> dict:
        return {
            "eye_breaks": self._eye_breaks_today,
            "water_breaks": self._water_breaks_today,
            "stretch_breaks": self._stretch_breaks_today,
        }

    def set_intervals(self, eye_min: int = 20, water_min: int = 45,
                      stretch_min: int = 30):
        self._eye_timer.setInterval(eye_min * 60_000)
        self._water_timer.setInterval(water_min * 60_000)
        self._stretch_timer.setInterval(stretch_min * 60_000)

    def stop(self):
        self._eye_timer.stop()
        self._water_timer.stop()
        self._stretch_timer.stop()
        self._countdown_timer.stop()
