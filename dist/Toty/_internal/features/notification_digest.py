"""
Smart Notification Digest — batches notifications and delivers summaries.
Instead of showing every notification, groups them every N minutes.
"""
import time
from collections import defaultdict
from PyQt6.QtCore import QTimer, pyqtSignal, QObject


class NotificationDigest(QObject):
    """Batches notifications and emits periodic digests."""
    digest_ready = pyqtSignal(str)  # formatted digest text

    def __init__(self, interval_min: int = 15):
        super().__init__()
        self._queue: list[dict] = []
        self._interval_ms = interval_min * 60 * 1000
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._emit_digest)
        self._timer.start(self._interval_ms)
        self._dnd_mode = False

    def set_interval(self, minutes: int):
        self._interval_ms = minutes * 60 * 1000
        self._timer.start(self._interval_ms)

    def set_dnd(self, enabled: bool):
        """Do Not Disturb mode — queues everything, shows on disable."""
        self._dnd_mode = enabled
        if not enabled and self._queue:
            self._emit_digest()

    @property
    def is_dnd(self) -> bool:
        return self._dnd_mode

    def add(self, app: str, title: str, body: str = "", priority: str = "normal"):
        """Add a notification to the queue."""
        self._queue.append({
            "app": app,
            "title": title,
            "body": body,
            "priority": priority,
            "time": time.time(),
        })

        # Urgent notifications bypass batching (unless DND)
        if priority == "urgent" and not self._dnd_mode:
            text = f"🔴 {app}: {title}"
            if body:
                text += f"\n{body[:100]}"
            self.digest_ready.emit(text)

    def peek_count(self) -> int:
        return len(self._queue)

    def _emit_digest(self):
        if not self._queue:
            return

        # Group by app
        by_app: dict[str, list[dict]] = defaultdict(list)
        for n in self._queue:
            by_app[n["app"]].append(n)

        lines = [f"📬 Notification Digest ({len(self._queue)} new):"]
        for app, notifs in by_app.items():
            if len(notifs) == 1:
                lines.append(f"  • {app}: {notifs[0]['title']}")
            else:
                lines.append(f"  • {app}: {len(notifs)} notifications")
                # Show first 2
                for n in notifs[:2]:
                    lines.append(f"      - {n['title'][:50]}")
                if len(notifs) > 2:
                    lines.append(f"      ... +{len(notifs) - 2} more")

        self._queue.clear()
        self.digest_ready.emit("\n".join(lines))

    def get_queue_summary(self) -> str:
        if not self._queue:
            return "No pending notifications."
        by_app: dict[str, int] = defaultdict(int)
        for n in self._queue:
            by_app[n["app"]] += 1
        parts = [f"{app}: {count}" for app, count in by_app.items()]
        return f"📬 Pending: {', '.join(parts)} ({len(self._queue)} total)"
