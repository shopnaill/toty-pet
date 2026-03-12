"""
Productivity Dashboard — a hoverable/dockable mini panel near the pet
showing today's focus time, streak, habits, prayer times, etc.
"""
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont, QColor


class ProductivityDashboard(QWidget):
    """Small floating panel showing today's productivity at a glance."""

    def __init__(self, stats, mood_engine, habits, settings, parent=None):
        super().__init__(parent)
        self._stats = stats
        self._mood = mood_engine
        self._habits = habits
        self._settings = settings

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(220)

        self._build_ui()

        # Auto-refresh every 30s
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start(30000)

        self.hide()

    def _build_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)

        self._frame = QFrame()
        self._frame.setStyleSheet(
            "QFrame { background: rgba(30,30,40,220); border-radius: 12px; "
            "border: 1px solid rgba(255,255,255,30); }"
        )
        frame_layout = QVBoxLayout(self._frame)
        frame_layout.setContentsMargins(12, 10, 12, 10)
        frame_layout.setSpacing(6)

        # Title
        title = QLabel("📊 Dashboard")
        title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #88bbff; background: transparent;")
        frame_layout.addWidget(title)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,40); background: transparent;")
        frame_layout.addWidget(sep)

        # Focus time
        self._focus_label = QLabel("🎯 Focus: 0 min")
        self._focus_label.setStyleSheet("color: #ccc; background: transparent;")
        self._focus_label.setFont(QFont("Arial", 9))
        frame_layout.addWidget(self._focus_label)

        # Focus bar
        self._focus_bar = QProgressBar()
        self._focus_bar.setMaximum(100)
        self._focus_bar.setFixedHeight(8)
        self._focus_bar.setTextVisible(False)
        self._focus_bar.setStyleSheet(
            "QProgressBar { background: #333; border-radius: 4px; }"
            "QProgressBar::chunk { background: #4CAF50; border-radius: 4px; }"
        )
        frame_layout.addWidget(self._focus_bar)

        # Streak
        self._streak_label = QLabel("🔥 Streak: 0 days")
        self._streak_label.setStyleSheet("color: #ccc; background: transparent;")
        self._streak_label.setFont(QFont("Arial", 9))
        frame_layout.addWidget(self._streak_label)

        # Mood
        self._mood_label = QLabel("😊 Mood: --")
        self._mood_label.setStyleSheet("color: #ccc; background: transparent;")
        self._mood_label.setFont(QFont("Arial", 9))
        frame_layout.addWidget(self._mood_label)

        # Level / XP
        self._level_label = QLabel("⭐ Level 1")
        self._level_label.setStyleSheet("color: #ccc; background: transparent;")
        self._level_label.setFont(QFont("Arial", 9))
        frame_layout.addWidget(self._level_label)

        # Habits today
        self._habits_label = QLabel("✅ Habits: 0/0")
        self._habits_label.setStyleSheet("color: #ccc; background: transparent;")
        self._habits_label.setFont(QFont("Arial", 9))
        frame_layout.addWidget(self._habits_label)

        # Keys today
        self._keys_label = QLabel("⌨️ Keys: 0")
        self._keys_label.setStyleSheet("color: #ccc; background: transparent;")
        self._keys_label.setFont(QFont("Arial", 9))
        frame_layout.addWidget(self._keys_label)

        # Focus prediction
        self._predict_label = QLabel("")
        self._predict_label.setStyleSheet("color: #89B4FA; background: transparent;")
        self._predict_label.setFont(QFont("Arial", 8))
        frame_layout.addWidget(self._predict_label)

        # Time
        self._time_label = QLabel("")
        self._time_label.setStyleSheet("color: #888; background: transparent;")
        self._time_label.setFont(QFont("Arial", 8))
        self._time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        frame_layout.addWidget(self._time_label)

        main.addWidget(self._frame)

    def refresh(self):
        """Update all dashboard values."""
        # Focus
        focus_min = self._mood.get_focus_minutes()
        goal = self._settings.get("daily_goal_focus_min")
        self._focus_label.setText(f"🎯 Focus: {focus_min} min / {goal} min")
        pct = min(100, int(focus_min / max(goal, 1) * 100))
        self._focus_bar.setValue(pct)

        # Streak
        streak = self._stats.data.get("streak", 0)
        self._streak_label.setText(f"🔥 Streak: {streak} day{'s' if streak != 1 else ''}")

        # Mood
        mood_val = self._mood.mood
        energy = self._mood.energy
        dom = self._mood.get_dominant_state()
        self._mood_label.setText(f"😊 Mood: {dom.title()} ({mood_val:.0f}/100)")

        # Level
        lv = self._stats.data.get("level", 1)
        xp = self._stats.data.get("xp", 0)
        self._level_label.setText(f"⭐ Level {lv}  (XP: {xp})")

        # Habits
        try:
            all_habits = self._habits.list_habits()
            done = sum(1 for h in all_habits if self._habits.is_done_today(h["name"]))
            self._habits_label.setText(f"✅ Habits: {done}/{len(all_habits)}")
        except Exception:
            self._habits_label.setText("✅ Habits: --")

        # Keys
        total_keys = self._stats.data.get("total_keys", 0)
        self._keys_label.setText(f"⌨️ Keys: {total_keys:,}")

        # Focus prediction
        if focus_min > 0 and focus_min < goal:
            now = datetime.now()
            session_start_h = 9  # assume day starts at 9 AM
            elapsed_h = max((now.hour - session_start_h) + now.minute / 60, 0.1)
            rate = focus_min / elapsed_h  # min per hour
            remaining = goal - focus_min
            if rate > 0:
                eta_h = remaining / rate
                if eta_h < 8:
                    self._predict_label.setText(f"📈 Goal in ~{eta_h:.1f}h at this pace")
                else:
                    self._predict_label.setText("📈 Push harder to hit today's goal!")
            else:
                self._predict_label.setText("")
        elif focus_min >= goal:
            self._predict_label.setText("🎉 Daily goal reached!")
        else:
            self._predict_label.setText("")

        # Time
        self._time_label.setText(datetime.now().strftime("%I:%M %p"))

    def show_near(self, pet_pos: QPoint, pet_width: int):
        """Show dashboard near the pet."""
        x = pet_pos.x() + pet_width + 10
        y = pet_pos.y() - 50

        # Keep on screen
        screen = None
        from PyQt6.QtWidgets import QApplication
        for s in QApplication.screens():
            if s.geometry().contains(pet_pos):
                screen = s
                break
        if screen:
            sg = screen.geometry()
            if x + self.width() > sg.right():
                x = pet_pos.x() - self.width() - 10
            if y < sg.top():
                y = sg.top() + 10
            if y + self.height() > sg.bottom():
                y = sg.bottom() - self.height() - 10

        self.move(x, y)
        self.refresh()
        self.show()
        self.raise_()

    def toggle(self, pet_pos: QPoint, pet_width: int):
        if self.isVisible():
            self.hide()
        else:
            self.show_near(pet_pos, pet_width)
