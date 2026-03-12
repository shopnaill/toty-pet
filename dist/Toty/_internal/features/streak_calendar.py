"""
Streak Calendar — GitHub-style green heatmap showing daily activity.
Reads data from HabitTracker and PersistentStats.
"""
import math
from datetime import date, timedelta
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QFont, QColor, QPainter, QPen


# Green intensity levels (0-4) mapped to colors
_LEVELS = [
    QColor("#2b2b2b"),   # 0 — no activity
    QColor("#0e4429"),   # 1 — low
    QColor("#006d32"),   # 2 — moderate
    QColor("#26a641"),   # 3 — good
    QColor("#39d353"),   # 4 — excellent
]

_CELL = 14
_GAP = 3
_WEEKS = 15  # ~3.5 months of history

# Module-level cache so we don't recompute on every dialog open
_cache: dict = {"date": None, "data": {}, "streak": 0, "total": 0}


class StreakCalendarDialog(QDialog):
    """Shows a heatmap of daily focus/habit activity."""

    def __init__(self, stats, habits, parent=None):
        super().__init__(parent)
        self._stats = stats
        self._habits = habits
        self._data: dict[str, int] = {}  # "YYYY-MM-DD" -> level 0-4
        self.setWindowTitle("🔥 Activity Streak Calendar")
        self.setFixedSize(
            _WEEKS * (_CELL + _GAP) + 60,
            7 * (_CELL + _GAP) + 100,
        )
        self.setStyleSheet("QDialog { background: #1e1e1e; }")
        self._build_data()
        streak, total_active = self._calc_streak()

        layout = QVBoxLayout(self)
        title = QLabel("🔥 Activity Streak Calendar")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #39d353;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Stats summary row
        summary = QLabel(
            f"Current streak: {streak} days  |  Active days (last {_WEEKS * 7}): {total_active}"
        )
        summary.setFont(QFont("Segoe UI", 10))
        summary.setStyleSheet("color: #aaa;")
        summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(summary)

        layout.addStretch()

        # Legend
        legend_row = QHBoxLayout()
        legend_row.addStretch()
        leg_label = QLabel("Less")
        leg_label.setStyleSheet("color: #666; font-size: 10px;")
        legend_row.addWidget(leg_label)
        for lvl in _LEVELS:
            sq = QLabel()
            sq.setFixedSize(_CELL, _CELL)
            sq.setStyleSheet(f"background: {lvl.name()}; border-radius: 2px;")
            legend_row.addWidget(sq)
        more_label = QLabel("More")
        more_label.setStyleSheet("color: #666; font-size: 10px;")
        legend_row.addWidget(more_label)
        legend_row.addStretch()
        layout.addLayout(legend_row)

    def _build_data(self):
        """Aggregate habit log + stats into a daily score → level. Uses cache if same day."""
        global _cache
        today = date.today()
        if _cache["date"] == today:
            self._data = _cache["data"]
            return

        habit_log = self._habits.data.get("log", {})
        habits_info = self._habits.data.get("habits", {})

        for offset in range(_WEEKS * 7):
            d = today - timedelta(days=offset)
            key = d.isoformat()
            day_log = habit_log.get(key, {})

            # Score: count how many habit goals were met
            score = 0
            for hname, hinfo in habits_info.items():
                goal = hinfo.get("goal", 1)
                done = day_log.get(hname, 0)
                if done >= goal:
                    score += 2
                elif done > 0:
                    score += 1

            # Add focus minutes contribution from stats
            sessions = self._stats.data.get("session_history", [])
            for sess in sessions:
                if sess.get("date", "")[:10] == key:
                    score += min(sess.get("focus_min", 0) // 15, 4)

            # Clamp to level 0-4
            if score == 0:
                level = 0
            elif score <= 1:
                level = 1
            elif score <= 3:
                level = 2
            elif score <= 6:
                level = 3
            else:
                level = 4
            self._data[key] = level

        # Update cache
        _cache["date"] = today
        _cache["data"] = dict(self._data)

    def _calc_streak(self) -> tuple[int, int]:
        """Return (current_streak_days, total_active_days). Uses cache if available."""
        global _cache
        today = date.today()
        if _cache["date"] == today and _cache["streak"] > 0:
            return _cache["streak"], _cache["total"]

        streak = 0
        total = 0
        for offset in range(_WEEKS * 7):
            d = today - timedelta(days=offset)
            lvl = self._data.get(d.isoformat(), 0)
            if lvl > 0:
                total += 1
                if offset == streak:
                    streak += 1

        _cache["streak"] = streak
        _cache["total"] = total
        return streak, total

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        today = date.today()
        # Start grid below title area
        x_offset = 40
        y_offset = 70

        # Draw day labels (Mon, Wed, Fri)
        painter.setPen(QColor("#666"))
        painter.setFont(QFont("Segoe UI", 8))
        day_labels = ["M", "", "W", "", "F", "", "S"]
        for i, lbl in enumerate(day_labels):
            if lbl:
                painter.drawText(5, y_offset + i * (_CELL + _GAP) + _CELL - 2, lbl)

        # Draw cells — columns are weeks, rows are days (Mon=0 .. Sun=6)
        for week in range(_WEEKS):
            for dow in range(7):
                days_ago = (_WEEKS - 1 - week) * 7 + (6 - dow)
                d = today - timedelta(days=days_ago)
                level = self._data.get(d.isoformat(), 0)
                color = _LEVELS[level]

                x = x_offset + week * (_CELL + _GAP)
                y = y_offset + dow * (_CELL + _GAP)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(QRectF(x, y, _CELL, _CELL), 2, 2)

        painter.end()
