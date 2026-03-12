"""
Timer Hub — consolidates many independent QTimers into fewer shared dispatchers.
Reduces the 35+ timer overhead to 3 tiered tick loops.
"""
from PyQt6.QtCore import QTimer


class TimerHub:
    """Routes callbacks through 3 tiered timers instead of many individual ones.

    Tiers:
        fast  — 50ms  (physics, movement, orbit animation)
        medium — 1000ms (countdowns, UI refresh)
        slow  — 5000ms (polling, scanning, periodic checks)
    """

    def __init__(self, parent=None):
        self._fast_cbs: list[callable] = []
        self._medium_cbs: list[callable] = []
        self._slow_cbs: list[callable] = []

        # Accumulator for sub-ticks (allows callbacks at non-native intervals)
        self._medium_tick = 0
        self._slow_tick = 0

        self._fast = QTimer(parent)
        self._fast.timeout.connect(self._on_fast)

        self._medium = QTimer(parent)
        self._medium.timeout.connect(self._on_medium)

        self._slow = QTimer(parent)
        self._slow.timeout.connect(self._on_slow)

    def start(self):
        if self._fast_cbs:
            self._fast.start(50)
        if self._medium_cbs:
            self._medium.start(1000)
        if self._slow_cbs:
            self._slow.start(5000)

    def stop(self):
        self._fast.stop()
        self._medium.stop()
        self._slow.stop()

    def register_fast(self, cb):
        """Register a callback to fire every 50ms."""
        self._fast_cbs.append(cb)
        if not self._fast.isActive() and self._fast_cbs:
            self._fast.start(50)

    def register_medium(self, cb):
        """Register a callback to fire every 1s."""
        self._medium_cbs.append(cb)
        if not self._medium.isActive() and self._medium_cbs:
            self._medium.start(1000)

    def register_slow(self, cb):
        """Register a callback to fire every 5s."""
        self._slow_cbs.append(cb)
        if not self._slow.isActive() and self._slow_cbs:
            self._slow.start(5000)

    def unregister(self, cb):
        """Remove a callback from any tier."""
        for lst in (self._fast_cbs, self._medium_cbs, self._slow_cbs):
            try:
                lst.remove(cb)
            except ValueError:
                pass

    def _on_fast(self):
        for cb in self._fast_cbs:
            try:
                cb()
            except Exception:
                pass

    def _on_medium(self):
        self._medium_tick += 1
        for cb in self._medium_cbs:
            try:
                cb()
            except Exception:
                pass

    def _on_slow(self):
        self._slow_tick += 1
        for cb in self._slow_cbs:
            try:
                cb()
            except Exception:
                pass
