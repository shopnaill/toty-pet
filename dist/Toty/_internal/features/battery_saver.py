"""Battery Saver — Automatically reduce timers and animations when battery is low."""
import logging

from PyQt6.QtCore import QTimer

log = logging.getLogger("toty.battery_saver")


class BatterySaver:
    """Monitor battery and slow down timers when battery is low.

    When battery drops below the threshold (default 20%) and the PC is
    unplugged, this will double the interval of registered timers and
    signal the pet to reduce animations.  When power is restored or
    battery rises above the threshold, timers return to normal.
    """

    def __init__(self, threshold: int = 20):
        self._threshold = threshold
        self._active = False
        self._registered: list[tuple[QTimer, int]] = []  # (timer, original_ms)
        self._check_timer = QTimer()
        self._check_timer.timeout.connect(self._check)
        self._check_timer.start(30000)  # check every 30s
        self._on_activate_cb = None
        self._on_deactivate_cb = None

    def register_timer(self, timer: QTimer):
        """Register a timer to be slowed when battery saving is active."""
        self._registered.append((timer, timer.interval()))

    def set_callbacks(self, on_activate=None, on_deactivate=None):
        """Set callbacks for when battery saver toggles."""
        self._on_activate_cb = on_activate
        self._on_deactivate_cb = on_deactivate

    @property
    def is_active(self) -> bool:
        return self._active

    def _check(self):
        try:
            import psutil
            bat = psutil.sensors_battery()
            if bat is None:
                return  # Desktop PC, no battery
            low = bat.percent <= self._threshold and not bat.power_plugged
            if low and not self._active:
                self._activate()
            elif not low and self._active:
                self._deactivate()
        except ImportError:
            pass  # psutil not available
        except Exception as e:
            log.debug("Battery check error: %s", e)

    def _activate(self):
        """Slow down all registered timers by 2x."""
        self._active = True
        for timer, orig_ms in self._registered:
            if timer.isActive():
                timer.setInterval(orig_ms * 2)
        log.info("Battery saver activated (timers slowed 2x)")
        if self._on_activate_cb:
            try:
                self._on_activate_cb()
            except Exception:
                pass

    def _deactivate(self):
        """Restore all timers to original intervals."""
        self._active = False
        for timer, orig_ms in self._registered:
            if timer.isActive():
                timer.setInterval(orig_ms)
        log.info("Battery saver deactivated (timers restored)")
        if self._on_deactivate_cb:
            try:
                self._on_deactivate_cb()
            except Exception:
                pass

    def stop(self):
        self._check_timer.stop()
        if self._active:
            self._deactivate()
