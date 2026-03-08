"""Focus Session Planner — plan a focus block with auto-pomodoro scheduling."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
    QLineEdit, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont


class FocusPlanner(QWidget):
    """Plan a focus session: 'Focus 2h on coding' with auto pomodoro cycles."""
    session_started = pyqtSignal(str, int)  # (task_name, total_minutes)
    session_ended = pyqtSignal(str, int)    # (task_name, minutes_completed)
    break_time = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task = ""
        self._total_min = 0
        self._elapsed_sec = 0
        self._pomo_min = 25
        self._break_min = 5
        self._in_break = False
        self._active = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFixedWidth(260)
        self.setStyleSheet(
            "QWidget { background: #1E1E2E; border: 1px solid #45475A;"
            "          border-radius: 10px; color: #CDD6F4; }"
            "QLabel { background: transparent; border: none; }"
            "QLineEdit { background: #313244; color: #CDD6F4; border: 1px solid #45475A;"
            "            border-radius: 6px; padding: 6px; font-size: 12px; }"
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "              border-radius: 6px; padding: 6px 12px; font-weight: bold; font-size: 11px; }"
            "QPushButton:hover { background: #74C7EC; }"
            "QSpinBox { background: #313244; color: #CDD6F4; border: 1px solid #45475A;"
            "           border-radius: 4px; padding: 4px; font-size: 12px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        title = QLabel("🎯 Focus Session Planner")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        title.setStyleSheet("color: #89B4FA;")
        layout.addWidget(title)

        self._task_input = QLineEdit()
        self._task_input.setPlaceholderText("What to focus on...")
        layout.addWidget(self._task_input)

        row = QHBoxLayout()
        row.addWidget(QLabel("Duration:"))
        self._dur_spin = QSpinBox()
        self._dur_spin.setRange(10, 480)
        self._dur_spin.setValue(60)
        self._dur_spin.setSuffix(" min")
        row.addWidget(self._dur_spin)
        layout.addLayout(row)

        self._start_btn = QPushButton("▶ Start Focus")
        self._start_btn.clicked.connect(self._toggle)
        layout.addWidget(self._start_btn)

        self._progress = QProgressBar()
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(
            "QProgressBar { background: #313244; border-radius: 6px; text-align: center;"
            "               color: #CDD6F4; font-size: 11px; }"
            "QProgressBar::chunk { background: #A6E3A1; border-radius: 6px; }"
        )
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setStyleSheet("color: #F9E2AF; font-size: 11px;")
        layout.addWidget(self._status)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self.hide()

    def _toggle(self):
        if self._active:
            self._stop()
        else:
            self._start()

    def _start(self):
        self._task = self._task_input.text().strip() or "Focus"
        self._total_min = self._dur_spin.value()
        self._elapsed_sec = 0
        self._in_break = False
        self._active = True
        self._start_btn.setText("⏹ Stop")
        self._start_btn.setStyleSheet(
            "QPushButton { background: #F38BA8; color: #1E1E2E; border: none;"
            "              border-radius: 6px; padding: 6px 12px; font-weight: bold; }"
        )
        self._progress.setMaximum(self._total_min * 60)
        self._progress.setValue(0)
        self.session_started.emit(self._task, self._total_min)
        self._tick.start(1000)

    def _stop(self):
        self._tick.stop()
        completed = self._elapsed_sec // 60
        self.session_ended.emit(self._task, completed)
        self._active = False
        self._start_btn.setText("▶ Start Focus")
        self._start_btn.setStyleSheet(
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "              border-radius: 6px; padding: 6px 12px; font-weight: bold; }"
        )
        self._status.setText(f"Completed {completed} min of {self._task}")

    def _on_tick(self):
        self._elapsed_sec += 1
        self._progress.setValue(self._elapsed_sec)

        elapsed_min = self._elapsed_sec // 60
        remaining = self._total_min - elapsed_min
        m, s = divmod(self._total_min * 60 - self._elapsed_sec, 60)

        # Check pomodoro break cycle
        cycle = self._pomo_min + self._break_min
        pos_in_cycle = elapsed_min % cycle
        if not self._in_break and pos_in_cycle == self._pomo_min and self._elapsed_sec % 60 == 0:
            self._in_break = True
            self._status.setText(f"☕ Break time! ({self._break_min} min)")
            self.break_time.emit()
        elif self._in_break and pos_in_cycle == 0 and self._elapsed_sec % 60 == 0:
            self._in_break = False
            self._status.setText(f"🎯 Back to {self._task}!")

        if not self._in_break:
            self._status.setText(f"🎯 {self._task} — {m:02d}:{s:02d} left")

        if self._elapsed_sec >= self._total_min * 60:
            self._stop()

    def is_active(self) -> bool:
        return self._active

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
