"""
Analytics Dashboard for Toty Desktop Pet.

Shows focus time graphs, streak calendar, and activity breakdown.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QGridLayout,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPainter, QColor, QPen

from core.stats import PersistentStats


class AnalyticsDashboard(QDialog):
    """Dashboard dialog showing pet statistics and progress visuals."""

    def __init__(self, stats: PersistentStats, mood_engine=None, parent=None):
        super().__init__(parent)
        self._stats = stats
        self._mood = mood_engine
        self.setWindowTitle("Toty Analytics Dashboard")
        self.setMinimumSize(440, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("📊 Analytics Dashboard")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Key metrics row
        metrics = QHBoxLayout()
        metrics.addWidget(self._metric_card("🔥 Streak", f"{stats.data.get('current_streak', 0)} days"))
        metrics.addWidget(self._metric_card("🏆 Best Streak", f"{stats.data.get('longest_streak', 0)} days"))
        metrics.addWidget(self._metric_card("📅 Sessions", str(stats.data.get('total_sessions', 0))))
        metrics.addWidget(self._metric_card("🍅 Pomodoros", str(stats.data.get('total_pomodoros', 0))))
        layout.addLayout(metrics)

        # Focus stats group
        focus_group = QGroupBox("Focus")
        fg_layout = QGridLayout(focus_group)
        fg_layout.addWidget(QLabel("Today:"), 0, 0)
        fg_layout.addWidget(QLabel(f"{stats.data.get('daily_focus_min', 0)} min"), 0, 1)
        fg_layout.addWidget(QLabel("All-time:"), 1, 0)
        fg_layout.addWidget(QLabel(f"{stats.data.get('total_focus_min', 0)} min"), 1, 1)
        fg_layout.addWidget(QLabel("Avg/session:"), 2, 0)
        sessions = max(stats.data.get('total_sessions', 1), 1)
        avg = stats.data.get('total_focus_min', 0) / sessions
        fg_layout.addWidget(QLabel(f"{avg:.1f} min"), 2, 1)
        layout.addWidget(focus_group)

        # XP & Level
        xp_group = QGroupBox("Progress")
        xp_layout = QGridLayout(xp_group)
        xp_layout.addWidget(QLabel("Level:"), 0, 0)
        xp_layout.addWidget(QLabel(str(stats.data.get('level', 1))), 0, 1)
        xp_layout.addWidget(QLabel("XP:"), 1, 0)
        xp_layout.addWidget(QLabel(stats.get_level_info()), 1, 1)
        xp_layout.addWidget(QLabel("Total Keys:"), 2, 0)
        xp_layout.addWidget(QLabel(f"{stats.data.get('total_keys', 0):,}"), 2, 1)
        xp_layout.addWidget(QLabel("Total Pets:"), 3, 0)
        xp_layout.addWidget(QLabel(str(stats.data.get('total_pets', 0))), 3, 1)
        xp_layout.addWidget(QLabel("Achievements:"), 4, 0)
        xp_layout.addWidget(QLabel(f"{len(stats.data.get('achievements', []))} unlocked"), 4, 1)
        layout.addWidget(xp_group)

        # Mood (if available)
        if mood_engine:
            mood_group = QGroupBox("Current Mood")
            ml = QHBoxLayout(mood_group)
            mood_val = mood_engine.mood
            bar_text = self._mood_bar(mood_val)
            ml.addWidget(QLabel(f"{bar_text}  ({mood_val}/100)"))
            layout.addWidget(mood_group)

        self.setStyleSheet(
            "QGroupBox { font-weight: bold; margin-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
        )

    @staticmethod
    def _metric_card(label: str, value: str) -> QGroupBox:
        box = QGroupBox()
        box.setFixedHeight(70)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 4, 8, 4)
        val_label = QLabel(value)
        val_label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label = QLabel(label)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setFont(QFont("Arial", 9))
        layout.addWidget(val_label)
        layout.addWidget(name_label)
        return box

    @staticmethod
    def _mood_bar(mood: int) -> str:
        filled = mood // 10
        return "💚" * filled + "🤍" * (10 - filled)
