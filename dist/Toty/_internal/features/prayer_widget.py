"""Desktop Prayer Time Widget — always-on-top transparent panel.

Shows: Hijri date, all prayer times, live countdown, streak, progress bar.
Draggable, semi-transparent, auto-updates every second.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar,
    QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont, QColor, QPainter, QPainterPath, QBrush

from features.prayer import (
    PrayerTimeManager, PRAYER_PERIOD_COLORS, HIJRI_MONTHS_AR,
)
from datetime import datetime


class PrayerDesktopWidget(QWidget):
    """Floating desktop widget showing prayer times + live countdown."""

    def __init__(self, prayer_manager: PrayerTimeManager, parent=None):
        super().__init__(parent)
        self._pm = prayer_manager
        self._dragging = False
        self._drag_pos = QPoint()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(220)

        self._build_ui()

        # Update every second
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._update)
        self._tick_timer.start(1000)

        # Initial update
        QTimer.singleShot(100, self._update)

    # ── UI Construction ──

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Container for styling (painted in paintEvent)
        self._container = QWidget()
        self._container.setObjectName("prayer_widget_inner")
        inner = QVBoxLayout(self._container)
        inner.setContentsMargins(12, 10, 12, 10)
        inner.setSpacing(4)

        # ── Hijri date ──
        self._hijri_label = QLabel()
        self._hijri_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._hijri_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hijri_label.setStyleSheet("color: #e8b445; background: transparent;")
        inner.addWidget(self._hijri_label)

        # ── Countdown ──
        self._cd_label = QLabel()
        self._cd_label.setFont(QFont("Consolas", 18, QFont.Weight.Bold))
        self._cd_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cd_label.setStyleSheet("color: #ffffff; background: transparent;")
        inner.addWidget(self._cd_label)

        self._next_name_label = QLabel()
        self._next_name_label.setFont(QFont("Segoe UI", 9))
        self._next_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._next_name_label.setStyleSheet("color: #b0b0b0; background: transparent;")
        inner.addWidget(self._next_name_label)

        # ── Progress bar ──
        self._progress = QProgressBar()
        self._progress.setFixedHeight(4)
        self._progress.setRange(0, 1000)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { background: rgba(255,255,255,25); border: none;"
            " border-radius: 2px; }"
            "QProgressBar::chunk { background: #e8b445; border-radius: 2px; }"
        )
        inner.addWidget(self._progress)

        # ── Separator ──
        sep = QLabel()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: rgba(255,255,255,30);")
        inner.addWidget(sep)

        # ── Prayer time rows ──
        self._prayer_rows = {}
        for name in PrayerTimeManager.PRAYER_NAMES:
            row = QHBoxLayout()
            row.setSpacing(0)

            ar_idx = PrayerTimeManager.PRAYER_NAMES.index(name)
            ar_name = PrayerTimeManager.PRAYER_NAMES_AR[ar_idx]

            name_lbl = QLabel(f"{ar_name}  {name}")
            name_lbl.setFont(QFont("Segoe UI", 9))
            name_lbl.setStyleSheet("color: #d0d0d0; background: transparent;")
            row.addWidget(name_lbl)

            row.addStretch()

            time_lbl = QLabel("--:--")
            time_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            time_lbl.setStyleSheet("color: #ffffff; background: transparent;")
            time_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(time_lbl)

            status_lbl = QLabel("")
            status_lbl.setFixedWidth(20)
            status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_lbl.setStyleSheet("color: #66bb6a; background: transparent;")
            row.addWidget(status_lbl)

            inner.addLayout(row)
            self._prayer_rows[name] = {
                "name_lbl": name_lbl,
                "time_lbl": time_lbl,
                "status_lbl": status_lbl,
            }

        # ── Streak row ──
        sep2 = QLabel()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background: rgba(255,255,255,30);")
        inner.addWidget(sep2)

        self._streak_label = QLabel()
        self._streak_label.setFont(QFont("Segoe UI", 8))
        self._streak_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._streak_label.setStyleSheet("color: #ff9800; background: transparent;")
        inner.addWidget(self._streak_label)

        root.addWidget(self._container)

    # ── Paint background (rounded, semi-transparent) ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(0.0, 0.0, float(self.width()), float(self.height()), 14.0, 14.0)

        # Get current period color for subtle tint
        period = self._pm.get_current_period()
        if period:
            base = QColor(period["color"])
            base.setAlpha(35)
        else:
            base = QColor(0, 0, 0, 0)

        # Dark semi-transparent background
        bg = QColor(18, 18, 28, 210)
        painter.fillPath(path, QBrush(bg))

        # Subtle color tint overlay
        painter.fillPath(path, QBrush(base))

        # Border
        border_color = QColor(period["color"]) if period else QColor(100, 100, 100)
        border_color.setAlpha(80)
        painter.setPen(border_color)
        painter.drawPath(path)

        painter.end()

    # ── Update all data ──

    def _update(self):
        now = datetime.now()
        times = self._pm.get_times(now.date())

        # Hijri
        try:
            hijri = self._pm.get_hijri_date()
            jummah = " 🕌" if self._pm.is_jummah() else ""
            self._hijri_label.setText(f"📅 {hijri['display_ar']}{jummah}")
        except Exception:
            self._hijri_label.setText("")

        # Next prayer countdown
        nxt_name, nxt_ar, nxt_dt = self._pm.get_next_prayer()
        if nxt_dt:
            diff = max(0, (nxt_dt - now).total_seconds())
            hrs = int(diff // 3600)
            mins = int((diff % 3600) // 60)
            secs = int(diff % 60)
            if hrs > 0:
                self._cd_label.setText(f"{hrs}:{mins:02d}:{secs:02d}")
            else:
                self._cd_label.setText(f"{mins:02d}:{secs:02d}")
            self._next_name_label.setText(f"until {nxt_ar} {nxt_name}")
        else:
            self._cd_label.setText("--:--")
            self._next_name_label.setText("")

        # Period progress
        period = self._pm.get_current_period()
        if period:
            self._progress.setValue(int(period["progress"] * 1000))
            color = period["color"]
            self._progress.setStyleSheet(
                "QProgressBar { background: rgba(255,255,255,25); border: none;"
                " border-radius: 2px; }"
                f"QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}"
            )

        # Prayer rows
        streak = self._pm.get_streak()
        today_prayers = streak.get("today_prayers", [])

        # Find next prayer name for highlight
        for name in PrayerTimeManager.PRAYER_NAMES:
            row = self._prayer_rows[name]
            pt = times.get(name)
            if pt:
                row["time_lbl"].setText(pt.strftime("%I:%M %p"))
                if pt <= now:
                    row["status_lbl"].setText("✓")
                    row["name_lbl"].setStyleSheet("color: #777; background: transparent;")
                    row["time_lbl"].setStyleSheet("color: #777; background: transparent;")
                elif name == nxt_name:
                    # Highlight next prayer
                    row["status_lbl"].setText("◀")
                    row["status_lbl"].setStyleSheet("color: #e8b445; background: transparent;")
                    row["name_lbl"].setStyleSheet("color: #e8b445; background: transparent; font-weight: bold;")
                    row["time_lbl"].setStyleSheet("color: #e8b445; background: transparent; font-weight: bold;")
                else:
                    row["status_lbl"].setText("")
                    row["name_lbl"].setStyleSheet("color: #d0d0d0; background: transparent;")
                    row["time_lbl"].setStyleSheet("color: #ffffff; background: transparent;")

                # Prayed indicator
                if name in today_prayers and pt <= now:
                    row["status_lbl"].setText("🤲")
            else:
                row["time_lbl"].setText("--:--")

        # Streak
        s = streak
        if s["current"] > 0 or s["today_count"] > 0:
            self._streak_label.setText(
                f"🔥 {s['current']}d streak  |  Today: {s['today_count']}/5"
            )
        else:
            self._streak_label.setText(f"📿 Today: {s['today_count']}/5")

        self.update()  # trigger repaint for background tint

    # ── Drag support ──

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False

    # ── Public API ──

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self._update()

    def show_at(self, pos: QPoint):
        self.move(pos)
        self.show()
        self._update()
