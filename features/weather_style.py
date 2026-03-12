"""
Weather & Time-of-Day Style — automatically changes the pet's outfit,
tint, and particles based on current weather conditions and time of day.
"""
import logging
from datetime import datetime
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger("toty.weather_style")

# ── Time-of-day periods ────────────────────────────────────────
_TIME_PERIODS = {
    "dawn":      (5, 7),     # 05:00 – 06:59
    "morning":   (7, 12),    # 07:00 – 11:59
    "afternoon": (12, 17),   # 12:00 – 16:59
    "evening":   (17, 20),   # 17:00 – 19:59
    "night":     (20, 24),   # 20:00 – 23:59
    "midnight":  (0, 5),     # 00:00 – 04:59
}

# Period → (accessory, pet_tint_rgba, particles, mood_hint, speech)
_TIME_STYLES = {
    "dawn":      ("flower",     (255, 220, 160, 30), None,         "happy",    "Good morning! The sun is rising 🌅"),
    "morning":   ("sunglasses", None,                 None,         "happy",    None),
    "afternoon": ("sunglasses", None,                 None,         "neutral",  None),
    "evening":   (None,         (180, 140, 255, 25),  None,         "cozy",     "Getting cozy for the evening 🌆"),
    "night":     ("sleep_mask", (60, 60, 120, 35),    None,         "sleepy",   "It's getting late... rest well 🌙"),
    "midnight":  ("sleep_mask", (40, 40, 100, 40),    None,         "sleepy",   "Still awake? You're a night owl 🦉"),
}

# Weather condition → (accessory, particles, tint_rgba, speech)
_WEATHER_STYLES = {
    "sunny":     ("sunglasses",  None,         (255, 240, 180, 20), None),
    "clear":     ("sunglasses",  None,         None,                None),
    "cloudy":    (None,          None,         (160, 170, 190, 20), None),
    "overcast":  (None,          None,         (130, 140, 160, 25), None),
    "rain":      ("umbrella",    "rain",       (100, 130, 180, 20), "It's raining! ☔ Stay dry!"),
    "drizzle":   ("umbrella",    "rain_light", (120, 140, 180, 15), None),
    "snow":      ("winter_hat",  "snow",       (200, 220, 255, 25), "Snow! ❄️ So magical!"),
    "thunder":   ("blanket",     "lightning",  (80, 80, 100, 30),   "Thunder! ⛈️ Don't worry, I'm here!"),
    "fog":       ("cloak",       None,         (180, 180, 180, 30), "So foggy... mysterious 🌫️"),
    "wind":      (None,          "leaves",     None,                "Windy today! 💨"),
    "hot":       ("sunglasses",  None,         (255, 200, 150, 20), None),
    "cold":      ("winter_hat",  None,         (180, 200, 240, 20), None),
}

# Combined overrides: (time_period, weather_keyword) → special outfit
_COMBO_STYLES = {
    ("night", "rain"):      ("blanket",    "rain",  (60, 80, 120, 35),  "Rainy night... perfect for sleeping 🌧️🌙"),
    ("night", "thunder"):   ("blanket",    None,    (50, 50, 80, 40),   "Scary night storm! Let me hide 😨"),
    ("morning", "snow"):    ("winter_hat", "snow",  (200, 220, 255, 20), "Snow in the morning! Let's build a snowman ⛄"),
    ("midnight", "rain"):   ("blanket",    "rain",  (40, 60, 100, 40),  "Late night rain... so peaceful 🌧️"),
    ("afternoon", "hot"):   ("sunglasses", None,    (255, 200, 140, 25), "Scorching afternoon! 🥵 Stay hydrated!"),
}


def _get_time_period() -> str:
    h = datetime.now().hour
    for period, (start, end) in _TIME_PERIODS.items():
        if start <= h < end:
            return period
    return "night"


def _match_weather(description: str) -> str | None:
    """Find the best matching weather keyword from description."""
    desc = description.lower()
    # Check most specific first
    for key in ("thunder", "snow", "drizzle", "rain", "fog", "wind",
                "overcast", "cloudy", "sunny", "clear"):
        if key in desc:
            return key
    # Temperature-based (checked by caller)
    return None


class WeatherStyleEngine(QObject):
    """Periodically evaluates weather + time and emits style changes."""

    # (accessory_name: str, tint_rgba: tuple|None, particle_type: str|None)
    style_changed = pyqtSignal(str, object, str)
    # speech suggestion
    comment = pyqtSignal(str)

    def __init__(self, weather_reactor=None, check_interval_sec: int = 120):
        super().__init__()
        self._weather = weather_reactor
        self._last_period = ""
        self._last_weather_key = ""
        self._last_accessory = ""

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.evaluate)
        self._timer.start(check_interval_sec * 1000)

        # Initial evaluation after a short delay
        QTimer.singleShot(8000, self.evaluate)

    def evaluate(self):
        """Determine the current style and emit if changed."""
        period = _get_time_period()
        weather_data = self._weather.get_current() if self._weather else {}
        desc = weather_data.get("description", "")
        temp = weather_data.get("temp_c", 20)

        # Determine weather keyword
        weather_key = _match_weather(desc) or ""
        if not weather_key and temp >= 35:
            weather_key = "hot"
        elif not weather_key and temp <= 5:
            weather_key = "cold"

        # Skip if nothing changed
        if period == self._last_period and weather_key == self._last_weather_key:
            return

        self._last_period = period
        self._last_weather_key = weather_key

        # Check combo styles first
        combo = _COMBO_STYLES.get((period, weather_key))
        if combo:
            acc, particles, tint, speech = combo
            self._emit(acc, tint, particles, speech)
            return

        # Weather takes priority over time for accessories
        if weather_key and weather_key in _WEATHER_STYLES:
            w_acc, w_particles, w_tint, w_speech = _WEATHER_STYLES[weather_key]
            # Merge with time tint if weather has none
            t_acc, t_tint, t_particles, t_mood, t_speech = _TIME_STYLES.get(
                period, (None, None, None, "neutral", None))
            acc = w_acc or t_acc or ""
            tint = w_tint or t_tint
            particles = w_particles or t_particles
            speech = w_speech or t_speech
            self._emit(acc, tint, particles, speech)
        else:
            # Time-only style
            style = _TIME_STYLES.get(period)
            if style:
                acc, tint, particles, mood, speech = style
                self._emit(acc or "", tint, particles, speech)

    def _emit(self, accessory: str, tint, particles: str | None, speech: str | None):
        if accessory != self._last_accessory:
            self._last_accessory = accessory
        self.style_changed.emit(
            accessory,
            tint,
            particles or "",
        )
        if speech:
            self.comment.emit(speech)

    def get_current_style(self) -> dict:
        """Return the current style state for UI display."""
        return {
            "period": self._last_period,
            "weather_key": self._last_weather_key,
            "accessory": self._last_accessory,
        }

    def force_refresh(self):
        """Force re-evaluation (e.g., after weather update)."""
        self._last_period = ""
        self._last_weather_key = ""
        self.evaluate()

    def stop(self):
        self._timer.stop()
