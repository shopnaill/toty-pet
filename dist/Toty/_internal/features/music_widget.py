"""
Music Player Desktop Widget — floating mini-player with media controls.
Shows current track, play/pause, next/prev, volume.
"""
from PyQt6.QtCore import QTimer, QPoint, Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QLinearGradient
from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QVBoxLayout, QLabel
from media.controller import MediaController
from features.widget_position import save_widget_pos, restore_widget_pos


class MusicPlayerWidget(QWidget):
    """Translucent floating music player widget."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(260, 100)
        self._dragging = False
        self._drag_pos = QPoint()

        self._track = "No music playing"
        self._is_playing = False

        # ── UI ──
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 10)
        root.setSpacing(4)

        # Track label
        self._track_label = QLabel(self._track)
        self._track_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._track_label.setStyleSheet("color: #cdd6f4; background: transparent;")
        self._track_label.setWordWrap(True)
        self._track_label.setMaximumHeight(36)
        root.addWidget(self._track_label)

        # Control buttons row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        btn_style = (
            "QPushButton { background: rgba(60,60,80,180); color: #cdd6f4; border: none;"
            " border-radius: 14px; font-size: 14px; }"
            "QPushButton:hover { background: rgba(137,180,250,200); color: #1e1e2e; }"
        )
        play_style = (
            "QPushButton { background: rgba(137,180,250,220); color: #1e1e2e; border: none;"
            " border-radius: 16px; font-size: 16px; font-weight: bold; }"
            "QPushButton:hover { background: rgba(180,208,251,240); }"
        )

        self._btn_prev = QPushButton("⏮")
        self._btn_prev.setFixedSize(28, 28)
        self._btn_prev.setStyleSheet(btn_style)
        self._btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_prev.clicked.connect(MediaController.prev_track)
        btn_row.addWidget(self._btn_prev)

        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedSize(32, 32)
        self._btn_play.setStyleSheet(play_style)
        self._btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_play.clicked.connect(self._on_play_pause)
        btn_row.addWidget(self._btn_play)

        self._btn_next = QPushButton("⏭")
        self._btn_next.setFixedSize(28, 28)
        self._btn_next.setStyleSheet(btn_style)
        self._btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_next.clicked.connect(MediaController.next_track)
        btn_row.addWidget(self._btn_next)

        btn_row.addStretch()

        self._btn_vol_dn = QPushButton("🔉")
        self._btn_vol_dn.setFixedSize(28, 28)
        self._btn_vol_dn.setStyleSheet(btn_style)
        self._btn_vol_dn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_vol_dn.clicked.connect(MediaController.volume_down)
        btn_row.addWidget(self._btn_vol_dn)

        self._btn_vol_up = QPushButton("🔊")
        self._btn_vol_up.setFixedSize(28, 28)
        self._btn_vol_up.setStyleSheet(btn_style)
        self._btn_vol_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_vol_up.clicked.connect(MediaController.volume_up)
        btn_row.addWidget(self._btn_vol_up)

        root.addLayout(btn_row)

    def show_at(self, pos: QPoint):
        saved = restore_widget_pos("music_player")
        self.move(QPoint(saved[0], saved[1]) if saved else pos)
        self.show()

    def set_state(self, is_playing: bool, track: str = ""):
        """Update from the main pet's music detector."""
        self._is_playing = is_playing
        if track:
            self._track = track
            self._track_label.setText(track)
        elif not is_playing:
            self._track = "No music playing"
            self._track_label.setText(self._track)
        self._btn_play.setText("⏸" if is_playing else "▶")
        self.update()

    def _on_play_pause(self):
        MediaController.play_pause()
        # Optimistically toggle — the main detector will correct if needed
        self._is_playing = not self._is_playing
        self._btn_play.setText("⏸" if self._is_playing else "▶")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background with gradient accent
        bg = QColor(18, 18, 28, 215)
        p.setBrush(bg)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 14, 14)

        # Top accent line
        accent = QLinearGradient(0, 0, self.width(), 0)
        accent.setColorAt(0, QColor(137, 180, 250, 180))
        accent.setColorAt(1, QColor(203, 166, 247, 180))
        p.setBrush(QBrush(accent))
        p.drawRoundedRect(0, 0, self.width(), 3, 2, 2)

        # Playing indicator dot
        if self._is_playing:
            p.setBrush(QColor(166, 227, 161))
            p.drawEllipse(self.width() - 18, 8, 8, 8)

        p.end()
        super().paintEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 50:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            save_widget_pos("music_player", self.x(), self.y())
        self._dragging = False
