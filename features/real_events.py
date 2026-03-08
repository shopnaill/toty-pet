"""Pet Reacts to Real Events — battery, WiFi, system triggers pet reactions."""
import logging
import random
import ctypes
import subprocess
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger("toty.real_events")


class RealEventReactor(QObject):
    """Periodically checks system state and emits speech-worthy events."""
    real_event = pyqtSignal(str, str)  # (event_type, message)

    def __init__(self, interval_ms: int = 120_000):
        super().__init__()
        self._last_battery: int | None = None
        self._last_plugged: bool | None = None
        self._last_wifi: str | None = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(interval_ms)  # default 2 min
        # initial read
        QTimer.singleShot(5000, self._check)

    def _check(self):
        try:
            self._check_battery()
        except Exception:
            pass
        try:
            self._check_wifi()
        except Exception:
            pass

    # ── Battery ──────────────────────────────────────────────
    def _check_battery(self):
        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", ctypes.c_ulong),
                ("BatteryFullLifeTime", ctypes.c_ulong),
            ]

        status = SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            return

        pct = status.BatteryLifePercent
        plugged = status.ACLineStatus == 1

        if pct > 100:  # desktop / no battery
            return

        # Charger plugged/unplugged
        if self._last_plugged is not None and plugged != self._last_plugged:
            if plugged:
                self.real_event.emit("battery", random.choice([
                    "⚡ Charger plugged in! Time to power up!",
                    "🔌 Charging! I can feel the energy flowing!",
                ]))
            else:
                self.real_event.emit("battery", random.choice([
                    "🔋 Unplugged! Running on battery now.",
                    "⚠️ Charger disconnected — conserve power!",
                ]))

        # Low battery warnings
        if self._last_battery is not None:
            if pct <= 10 and self._last_battery > 10:
                self.real_event.emit("battery", "🪫 CRITICAL! Battery at 10%! Plug in NOW!")
            elif pct <= 20 and self._last_battery > 20:
                self.real_event.emit("battery", random.choice([
                    "🔋 Battery at 20%... I'm getting sleepy...",
                    "⚠️ Low battery! Save your work!",
                ]))

        # Full battery
        if self._last_battery is not None and pct >= 100 and self._last_battery < 100 and plugged:
            self.real_event.emit("battery", "🔋 Fully charged! You can unplug now 😊")

        self._last_battery = pct
        self._last_plugged = plugged

    # ── WiFi ─────────────────────────────────────────────────
    def _check_wifi(self):
        try:
            result = subprocess.run(
                ["netsh", "wlan", "show", "interfaces"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            ssid = ""
            for line in result.stdout.splitlines():
                stripped = line.strip()
                if stripped.startswith("SSID") and "BSSID" not in stripped:
                    ssid = stripped.split(":", 1)[1].strip()
                    break

            if self._last_wifi is not None:
                if ssid and not self._last_wifi:
                    self.real_event.emit("wifi", f"📶 Connected to WiFi: {ssid}")
                elif not ssid and self._last_wifi:
                    self.real_event.emit("wifi", random.choice([
                        "📡 WiFi disconnected! Are we going offline?",
                        "🚫 Lost WiFi connection...",
                    ]))
                elif ssid and self._last_wifi and ssid != self._last_wifi:
                    self.real_event.emit("wifi", f"📶 Switched WiFi → {ssid}")

            self._last_wifi = ssid
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    def stop(self):
        self._timer.stop()
