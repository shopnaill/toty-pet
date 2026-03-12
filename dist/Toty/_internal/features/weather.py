"""
Weather Reactions — fetches local weather from wttr.in and
triggers pet accessory/mood changes based on conditions.
"""
import json
import logging
import threading
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QThread

log = logging.getLogger("toty")

# Condition → (accessory_suggestion, mood_hint)
WEATHER_MAP = {
    "sunny":       ("glasses",    "happy"),
    "clear":       ("glasses",    "happy"),
    "cloudy":      (None,         "neutral"),
    "overcast":    (None,         "neutral"),
    "rain":        (None,         "cozy"),
    "drizzle":     (None,         "cozy"),
    "snow":        (None,         "excited"),
    "thunder":     (None,         "startled"),
    "fog":         (None,         "sleepy"),
    "hot":         (None,         "tired"),
    "cold":        (None,         "cozy"),
    "wind":        (None,         "excited"),
}


class _WeatherWorker(QObject):
    """Fetches weather in background thread."""
    result = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, lat: float, lon: float):
        super().__init__()
        self._lat = lat
        self._lon = lon

    def fetch(self):
        try:
            url = f"https://wttr.in/{self._lat},{self._lon}?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "Toty/13.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            current = data.get("current_condition", [{}])[0]

            # Parse hourly forecast from today's weather data
            hourly = []
            now_hour = datetime.now().hour
            for day in data.get("weather", []):
                for h in day.get("hourly", []):
                    hour_val = int(h.get("time", "0")) // 100
                    desc = h.get("weatherDesc", [{}])[0].get("value", "")
                    chance_rain = int(h.get("chanceofrain", 0))
                    temp = int(h.get("tempC", 0))
                    hourly.append({
                        "hour": hour_val,
                        "desc": desc,
                        "chance_rain": chance_rain,
                        "temp_c": temp,
                    })

            result = {
                "temp_c": int(current.get("temp_C", 0)),
                "feels_like": int(current.get("FeelsLikeC", 0)),
                "humidity": int(current.get("humidity", 0)),
                "description": current.get("weatherDesc", [{}])[0].get("value", "Unknown"),
                "wind_kmph": int(current.get("windspeedKmph", 0)),
                "uv_index": int(current.get("uvIndex", 0)),
                "fetched_at": datetime.now().isoformat(),
                "hourly": hourly,
            }
            self.result.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class WeatherReactor(QObject):
    """Fetches weather and emits pet reactions."""
    weather_updated = pyqtSignal(dict)      # full weather data
    accessory_suggest = pyqtSignal(str)     # accessory name
    weather_comment = pyqtSignal(str)       # speech text
    rain_warning = pyqtSignal(str)          # upcoming rain alert

    def __init__(self, lat: float = 24.7136, lon: float = 46.6753,
                 check_interval_min: int = 30):
        super().__init__()
        self._lat = lat
        self._lon = lon
        self._current: dict = {}
        self._current_lock = threading.Lock()  # guards _current dict
        self._thread = None
        self._worker = None
        self._last_comment = ""
        self._last_rain_warned = ""

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._fetch)
        self._timer.start(check_interval_min * 60_000)

        # Initial fetch after 5 seconds
        QTimer.singleShot(5000, self._fetch)

    def _fetch(self):
        if self._thread and self._thread.isRunning():
            return
        self._thread = QThread()
        self._worker = _WeatherWorker(self._lat, self._lon)
        self._worker.moveToThread(self._thread)
        self._worker.result.connect(self._on_result)
        self._worker.error.connect(self._on_error)
        self._thread.started.connect(self._worker.fetch)
        self._thread.start()

    def _on_result(self, data: dict):
        with self._current_lock:
            self._current = data
        self.weather_updated.emit(data)
        self._react(data)
        self._check_rain_ahead(data)
        self._cleanup_thread()

    def _on_error(self, msg: str):
        log.warning("WeatherReactor: %s", msg)
        self._cleanup_thread()

    def _cleanup_thread(self):
        if self._thread:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
            self._worker = None

    def _react(self, data: dict):
        desc = data.get("description", "").lower()
        temp = data.get("temp_c", 20)

        # Temperature-based
        comment = ""
        if temp >= 38:
            comment = f"🌡️ {temp}°C — It's scorching outside! Stay hydrated! 🥵"
        elif temp >= 30:
            comment = f"☀️ {temp}°C — Hot day! {data.get('description', '')}"
            self.accessory_suggest.emit("glasses")
        elif temp <= 5:
            comment = f"🥶 {temp}°C — Brrr, it's freezing out there!"
        elif temp <= 15:
            comment = f"🧣 {temp}°C — A bit chilly today."

        # Description-based
        if not comment:
            for key, (acc, _mood) in WEATHER_MAP.items():
                if key in desc:
                    if acc:
                        self.accessory_suggest.emit(acc)
                    comment = f"🌤️ {data.get('description', '')} — {temp}°C outside"
                    break

        if not comment:
            comment = f"🌤️ {data.get('description', '')} — {temp}°C"

        # Don't repeat the same comment
        if comment != self._last_comment:
            self._last_comment = comment
            self.weather_comment.emit(comment)

    def get_current(self) -> dict:
        with self._current_lock:
            return dict(self._current)

    def get_display(self) -> str:
        with self._current_lock:
            if not self._current:
                return "Weather: checking..."
            d = self._current
            return f"{d.get('description', '?')} {d.get('temp_c', '?')}°C | Humidity {d.get('humidity', '?')}%"

    def set_location(self, lat: float, lon: float):
        self._lat = lat
        self._lon = lon
        self._fetch()

    def _check_rain_ahead(self, data: dict):
        """Warn if rain is expected in next few hours."""
        hourly = data.get("hourly", [])
        if not hourly:
            return
        now_hour = datetime.now().hour
        for h in hourly:
            hr = h.get("hour", 0)
            diff = hr - now_hour
            if diff <= 0 or diff > 6:
                continue
            if h.get("chance_rain", 0) >= 60:
                key = f"{datetime.now().date()}_{hr}"
                if key == self._last_rain_warned:
                    continue
                self._last_rain_warned = key
                self.rain_warning.emit(
                    f"🌧️ Rain likely in ~{diff}h ({h['chance_rain']}% chance at {hr}:00)"
                )
                return

    def get_hourly_summary(self) -> str:
        """Return a short hourly forecast string."""
        with self._current_lock:
            hourly = self._current.get("hourly", [])
        if not hourly:
            return "No hourly forecast available"
        now_hour = datetime.now().hour
        lines = ["⏰ Hourly Forecast:"]
        count = 0
        for h in hourly:
            hr = h.get("hour", 0)
            if hr < now_hour:
                continue
            lines.append(f"  {hr:02d}:00 — {h['temp_c']}°C {h['desc']}  🌧{h['chance_rain']}%")
            count += 1
            if count >= 6:
                break
        return "\n".join(lines) if count else "No upcoming forecast data"

    def stop(self):
        self._timer.stop()
        self._cleanup_thread()
