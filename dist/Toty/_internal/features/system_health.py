"""
System Health Monitor — tracks CPU, RAM, battery, disk, network.
Pet reacts visually to system state changes.
"""
import time
from PyQt6.QtCore import QTimer, pyqtSignal, QObject

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


class SystemHealthMonitor(QObject):
    """Periodically checks system health and emits alerts."""
    alert = pyqtSignal(str, str)  # (alert_type, message)

    # Alert types: "cpu_high", "ram_high", "battery_low", "battery_charging",
    #              "disk_low", "network_change", "cpu_cool"

    def __init__(self, interval_ms: int = 10000):
        super().__init__()
        self._last_cpu = 0.0
        self._last_ram = 0.0
        self._last_battery = 100
        self._last_battery_charging = False
        self._last_alert_time: dict[str, float] = {}
        self._alert_cooldown = 120.0  # Don't repeat same alert within 2 min

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        if _HAS_PSUTIL:
            self._timer.start(interval_ms)

    def stop(self):
        self._timer.stop()

    @staticmethod
    def available() -> bool:
        return _HAS_PSUTIL

    def get_snapshot(self) -> dict:
        """Get current system stats."""
        if not _HAS_PSUTIL:
            return {}
        try:
            cpu = psutil.cpu_percent(interval=0)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            battery = psutil.sensors_battery()
            net = psutil.net_io_counters()

            snapshot = {
                "cpu_percent": cpu,
                "ram_percent": ram.percent,
                "ram_used_gb": round(ram.used / (1024**3), 1),
                "ram_total_gb": round(ram.total / (1024**3), 1),
                "disk_percent": disk.percent,
                "disk_free_gb": round(disk.free / (1024**3), 1),
                "net_sent_mb": round(net.bytes_sent / (1024**2), 1),
                "net_recv_mb": round(net.bytes_recv / (1024**2), 1),
            }
            if battery:
                snapshot["battery_percent"] = battery.percent
                snapshot["battery_charging"] = battery.power_plugged
                snapshot["battery_secs_left"] = battery.secsleft if battery.secsleft > 0 else None
            return snapshot
        except Exception:
            return {}

    def _should_alert(self, alert_type: str) -> bool:
        now = time.time()
        last = self._last_alert_time.get(alert_type, 0)
        if now - last < self._alert_cooldown:
            return False
        self._last_alert_time[alert_type] = now
        return True

    def _check(self):
        if not _HAS_PSUTIL:
            return
        try:
            # CPU
            cpu = psutil.cpu_percent(interval=0)
            if cpu > 85 and self._last_cpu <= 85:
                if self._should_alert("cpu_high"):
                    self.alert.emit("cpu_high", f"CPU is at {cpu:.0f}%! Things are heating up!")
            elif cpu < 30 and self._last_cpu >= 85:
                if self._should_alert("cpu_cool"):
                    self.alert.emit("cpu_cool", "CPU cooled down. All good!")
            self._last_cpu = cpu

            # RAM
            ram = psutil.virtual_memory()
            if ram.percent > 85 and self._last_ram <= 85:
                if self._should_alert("ram_high"):
                    used_gb = ram.used / (1024**3)
                    self.alert.emit("ram_high", f"RAM at {ram.percent:.0f}% ({used_gb:.1f} GB used)!")
            self._last_ram = ram.percent

            # Battery
            battery = psutil.sensors_battery()
            if battery:
                pct = battery.percent
                charging = battery.power_plugged
                if pct <= 15 and self._last_battery > 15 and not charging:
                    if self._should_alert("battery_low"):
                        self.alert.emit("battery_low", f"Battery at {pct}%! Plug in soon!")
                elif pct <= 5 and not charging:
                    if self._should_alert("battery_critical"):
                        self.alert.emit("battery_critical", f"Battery CRITICAL at {pct}%!")
                if charging and not self._last_battery_charging:
                    if self._should_alert("battery_charging"):
                        self.alert.emit("battery_charging", f"Charging! Battery at {pct}%.")
                self._last_battery = pct
                self._last_battery_charging = charging

            # Disk
            disk = psutil.disk_usage("/")
            if disk.percent > 90:
                if self._should_alert("disk_low"):
                    free_gb = disk.free / (1024**3)
                    self.alert.emit("disk_low", f"Disk almost full! Only {free_gb:.1f} GB free.")

        except Exception:
            pass
