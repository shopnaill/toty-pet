"""App Time Report — tracks and displays daily per-app usage time."""
import json
import os
import time
import logging
from collections import defaultdict
from datetime import date
from core.safe_json import safe_json_save

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QFrame, QScrollArea, QWidget,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

log = logging.getLogger("toty.apptime")
_FILE = "app_time_report.json"


class AppTimeTracker:
    """Tracks per-app usage time during the session."""

    def __init__(self):
        self._current_app = ""
        self._current_start = time.time()
        self._daily: dict[str, float] = {}  # app_name -> seconds today
        self._date = date.today().isoformat()
        self._load()

    def switch_app(self, app_name: str):
        """Called when the active window changes."""
        now = time.time()
        if self._current_app:
            elapsed = now - self._current_start
            if elapsed > 0 and elapsed < 3600:  # ignore >1h gaps
                self._daily[self._current_app] = self._daily.get(self._current_app, 0) + elapsed
        self._current_app = app_name
        self._current_start = now
        # Reset on new day
        today = date.today().isoformat()
        if today != self._date:
            self._save()
            self._daily.clear()
            self._date = today

    def get_report(self) -> dict[str, float]:
        """Return {app_name: minutes} for today, sorted by usage."""
        # Flush current
        self.switch_app(self._current_app)
        result = {k: v / 60 for k, v in self._daily.items() if v > 30}
        return dict(sorted(result.items(), key=lambda x: -x[1]))

    def _save(self):
        try:
            data = {}
            if os.path.exists(_FILE):
                with open(_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
            data[self._date] = {k: round(v, 1) for k, v in self._daily.items()}
            # Keep last 30 days
            keys = sorted(data.keys())
            if len(keys) > 30:
                for old_key in keys[:-30]:
                    del data[old_key]
            safe_json_save(data, _FILE)
        except (IOError, json.JSONDecodeError):
            pass

    def _load(self):
        if os.path.exists(_FILE):
            try:
                with open(_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                today = date.today().isoformat()
                if today in data:
                    self._daily = {k: float(v) for k, v in data[today].items()}
            except (IOError, json.JSONDecodeError):
                pass

    def stop(self):
        self.switch_app("")
        self._save()


class AppTimeDialog(QDialog):
    """Dialog showing today's app usage breakdown."""

    def __init__(self, tracker: AppTimeTracker, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 App Time Report")
        self.setMinimumWidth(350)
        self.setMinimumHeight(300)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        title = QLabel("📊 Today's App Usage")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #89B4FA;")
        layout.addWidget(title)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,30);")
        layout.addWidget(sep)

        report = tracker.get_report()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        total_min = sum(report.values())
        for app, minutes in report.items():
            pct = minutes / max(total_min, 1) * 100
            bar_w = int(pct / 100 * 20)
            bar = "█" * bar_w + "░" * (20 - bar_w)
            if minutes >= 60:
                time_str = f"{minutes / 60:.1f}h"
            else:
                time_str = f"{minutes:.0f}m"
            row = QLabel(
                f"<span style='color:#CBA6F7'>{app[:25]}</span> "
                f"<span style='color:#585B70'>[{bar}]</span> "
                f"<span style='color:#A6E3A1'>{time_str}</span> "
                f"<span style='color:#6C7086'>({pct:.0f}%)</span>"
            )
            row.setTextFormat(Qt.TextFormat.RichText)
            row.setStyleSheet("font-size: 11px; padding: 2px; font-family: Consolas;")
            vbox.addWidget(row)

        if not report:
            empty = QLabel("No app usage data yet today.")
            empty.setStyleSheet("color: #6C7086; font-size: 12px;")
            vbox.addWidget(empty)

        scroll.setWidget(container)
        layout.addWidget(scroll)

        # Total
        total_lbl = QLabel(f"Total tracked: {total_min:.0f} min")
        total_lbl.setStyleSheet("color: #F9E2AF; font-size: 11px;")
        total_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(total_lbl)
