"""Keyboard Heatmap — visualize typing activity by hour of day."""
import json
import os
import logging
from datetime import datetime, date
from core.safe_json import safe_json_save
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QGridLayout, QFrame
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QColor

log = logging.getLogger("toty.keyboard_heatmap")
_FILE = "keyboard_heatmap.json"


class KeyboardHeatmapTracker(QObject):
    """Tracks typing activity per hour. Relies on external key-count feed."""

    def __init__(self):
        super().__init__()
        # hour -> keypress count  (0-23)
        self._today: dict[int, int] = {}
        self._history: list[dict] = []  # [{date, hours: {h: count}}]
        self._load()

    def record_keys(self, count: int = 1):
        """Call this whenever keys are pressed (batched or single)."""
        h = datetime.now().hour
        self._today[h] = self._today.get(h, 0) + count

    def flush(self):
        """Persist today's counts."""
        today = date.today().isoformat()
        # update or append today
        for entry in self._history:
            if entry["date"] == today:
                entry["hours"] = {str(k): v for k, v in self._today.items()}
                self._save()
                return
        self._history.append({
            "date": today,
            "hours": {str(k): v for k, v in self._today.items()},
        })
        self._history = self._history[-30:]  # keep 30 days
        self._save()

    def get_today_hours(self) -> dict[int, int]:
        return dict(self._today)

    def get_week_hours(self) -> dict[int, int]:
        """Aggregate last 7 days by hour."""
        from datetime import timedelta
        cutoff = (date.today() - timedelta(days=6)).isoformat()
        agg: dict[int, int] = {}
        for entry in self._history:
            if entry["date"] >= cutoff:
                for h_str, c in entry["hours"].items():
                    h = int(h_str)
                    agg[h] = agg.get(h, 0) + c
        # include today
        for h, c in self._today.items():
            agg[h] = agg.get(h, 0) + c
        return agg

    def _save(self):
        try:
            safe_json_save({"history": self._history}, _FILE)
        except IOError:
            pass

    def _load(self):
        if os.path.exists(_FILE):
            try:
                with open(_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._history = data.get("history", [])
                # reload today's data
                today = date.today().isoformat()
                for entry in self._history:
                    if entry["date"] == today:
                        self._today = {int(k): v for k, v in entry["hours"].items()}
                        break
            except (json.JSONDecodeError, IOError):
                pass

    def stop(self):
        self.flush()


class KeyboardHeatmapDialog(QDialog):
    """Shows a 24-hour heatmap of typing activity."""

    def __init__(self, tracker: KeyboardHeatmapTracker, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⌨️ Typing Heatmap")
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("⌨️ Typing Activity by Hour")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #F9E2AF;")
        layout.addWidget(title)

        # Today
        layout.addWidget(self._build_section("Today", tracker.get_today_hours()))
        # Week
        layout.addWidget(self._build_section("Last 7 Days", tracker.get_week_hours()))

    def _build_section(self, label: str, hours: dict[int, int]) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame { background: #181825; border-radius: 8px; }")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(12, 8, 12, 8)
        fl.setSpacing(4)

        lbl = QLabel(label)
        lbl.setStyleSheet("color: #CDD6F4; font-weight: bold; font-size: 12px;")
        fl.addWidget(lbl)

        grid = QGridLayout()
        grid.setSpacing(3)

        max_val = max(hours.values(), default=1) or 1
        for h in range(24):
            count = hours.get(h, 0)
            intensity = count / max_val if max_val else 0
            color = self._heat_color(intensity)
            cell = QLabel(f"{h}")
            cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell.setFixedSize(32, 32)
            cell.setToolTip(f"{h}:00 — {count:,} keys")
            cell.setStyleSheet(
                f"QLabel {{ background: {color}; color: {'#1E1E2E' if intensity > 0.4 else '#6C7086'};"
                f"  border-radius: 4px; font-size: 10px; }}"
            )
            grid.addWidget(cell, h // 12, h % 12)

        fl.addLayout(grid)
        return frame

    @staticmethod
    def _heat_color(intensity: float) -> str:
        """Return hex color from dark blue to bright green/yellow/red."""
        if intensity <= 0:
            return "#313244"
        if intensity < 0.25:
            return "#45475A"
        if intensity < 0.50:
            return "#585B70"
        if intensity < 0.75:
            return "#A6E3A1"
        return "#F9E2AF"
