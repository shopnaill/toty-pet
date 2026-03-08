"""Quick Timer / Stopwatch — one-click countdown or count-up timer."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont


class QuickTimer(QWidget):
    """Floating mini timer with countdown and stopwatch modes."""
    timer_finished = pyqtSignal(str)  # "Timer done!" message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._remaining = 0  # seconds for countdown
        self._elapsed = 0    # seconds for stopwatch
        self._mode = "idle"  # "idle", "countdown", "stopwatch"

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setFixedSize(200, 150)
        self.setStyleSheet(
            "QWidget { background: #1E1E2E; border: 1px solid #45475A;"
            "          border-radius: 10px; color: #CDD6F4; }"
            "QLabel { background: transparent; border: none; }"
            "QPushButton { background: #45475A; color: #CDD6F4; border: none;"
            "              border-radius: 6px; padding: 6px 12px; font-size: 11px; }"
            "QPushButton:hover { background: #585B70; }"
            "QSpinBox { background: #313244; color: #CDD6F4; border: 1px solid #45475A;"
            "           border-radius: 4px; padding: 4px; font-size: 12px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("⏱️ Quick Timer")
        title.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #89B4FA;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self._display = QLabel("00:00")
        self._display.setFont(QFont("Consolas", 22, QFont.Weight.Bold))
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setStyleSheet("color: #A6E3A1;")
        layout.addWidget(self._display)

        # Minutes spinner + buttons
        ctrl = QHBoxLayout()
        self._spin = QSpinBox()
        self._spin.setRange(1, 180)
        self._spin.setValue(5)
        self._spin.setSuffix(" min")
        self._spin.setFixedWidth(70)
        ctrl.addWidget(self._spin)

        self._start_btn = QPushButton("▶ Start")
        self._start_btn.clicked.connect(self._start_countdown)
        ctrl.addWidget(self._start_btn)

        self._sw_btn = QPushButton("⏱ SW")
        self._sw_btn.setToolTip("Stopwatch")
        self._sw_btn.clicked.connect(self._toggle_stopwatch)
        ctrl.addWidget(self._sw_btn)

        layout.addLayout(ctrl)

        self._tick = QTimer(self)
        self._tick.timeout.connect(self._on_tick)
        self.hide()

    def _start_countdown(self):
        if self._mode == "countdown":
            # Stop
            self._tick.stop()
            self._mode = "idle"
            self._start_btn.setText("▶ Start")
            return
        self._remaining = self._spin.value() * 60
        self._mode = "countdown"
        self._start_btn.setText("⏹ Stop")
        self._update_display()
        self._tick.start(1000)

    def _toggle_stopwatch(self):
        if self._mode == "stopwatch":
            self._tick.stop()
            self._mode = "idle"
            self._sw_btn.setText("⏱ SW")
            return
        self._elapsed = 0
        self._mode = "stopwatch"
        self._sw_btn.setText("⏹ Stop")
        self._start_btn.setEnabled(False)
        self._update_display()
        self._tick.start(1000)

    def _on_tick(self):
        if self._mode == "countdown":
            self._remaining -= 1
            if self._remaining <= 0:
                self._remaining = 0
                self._tick.stop()
                self._mode = "idle"
                self._start_btn.setText("▶ Start")
                self.timer_finished.emit(f"⏰ Timer done! ({self._spin.value()} min)")
            self._update_display()
        elif self._mode == "stopwatch":
            self._elapsed += 1
            self._update_display()

    def _update_display(self):
        if self._mode == "countdown":
            m, s = divmod(self._remaining, 60)
            self._display.setText(f"{m:02d}:{s:02d}")
            self._display.setStyleSheet("color: #F38BA8;" if self._remaining < 30 else "color: #A6E3A1;")
        elif self._mode == "stopwatch":
            m, s = divmod(self._elapsed, 60)
            self._display.setText(f"{m:02d}:{s:02d}")
            self._display.setStyleSheet("color: #F9E2AF;")
        else:
            self._display.setText("00:00")
            self._display.setStyleSheet("color: #A6E3A1;")
            self._start_btn.setEnabled(True)
            self._sw_btn.setText("⏱ SW")

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

    def stop(self):
        self._tick.stop()
