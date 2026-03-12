"""Color Picker — Screen eyedropper + color history with copy-to-clipboard."""
import ctypes
import logging

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QApplication, QFrame, QGridLayout, QToolTip,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import (
    QFont, QColor, QPixmap, QCursor, QScreen, QGuiApplication,
    QPainter, QPen,
)

log = logging.getLogger("toty.color_picker")

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"

_SS = f"""
QDialog {{ background: {_BG}; }}
QPushButton {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background: #45475A; border-color: {_BLUE}; }}
QPushButton:pressed {{ background: {_BLUE}; color: {_BG}; }}
QLabel {{ color: {_TEXT}; }}
"""


class _PickerOverlay(QDialog):
    """Fullscreen overlay that captures the pixel color under the cursor."""
    color_picked = pyqtSignal(QColor)

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Cover all screens
        geo = QGuiApplication.primaryScreen().virtualGeometry()
        self.setGeometry(geo)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(30)

    def paintEvent(self, _):
        painter = QPainter(self)
        # Semi-transparent overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

        # Magnifier near cursor
        pos = QCursor.pos()
        local = self.mapFromGlobal(pos)
        screen = QGuiApplication.screenAt(pos)
        if not screen:
            painter.end()
            return

        # Capture 15x15 pixel area around cursor
        cap_size = 15
        half = cap_size // 2
        pix = screen.grabWindow(0,
                                pos.x() - half, pos.y() - half,
                                cap_size, cap_size)
        if pix.isNull():
            painter.end()
            return

        # Draw magnified view (10x zoom)
        mag_size = 150
        mag_x = local.x() + 20
        mag_y = local.y() + 20
        # Keep on screen
        if mag_x + mag_size > self.width():
            mag_x = local.x() - mag_size - 20
        if mag_y + mag_size > self.height():
            mag_y = local.y() - mag_size - 20

        scaled = pix.scaled(mag_size, mag_size,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.FastTransformation)
        painter.drawPixmap(mag_x, mag_y, scaled)

        # Border and crosshair
        painter.setPen(QPen(QColor(_BLUE), 2))
        painter.drawRect(mag_x, mag_y, mag_size, mag_size)
        cx = mag_x + mag_size // 2
        cy = mag_y + mag_size // 2
        painter.setPen(QPen(QColor("#F38BA8"), 1))
        painter.drawLine(cx - 8, cy, cx + 8, cy)
        painter.drawLine(cx, cy - 8, cx, cy + 8)

        # Color info text
        img = pix.toImage()
        center_color = QColor(img.pixel(half, half))
        painter.setPen(QColor(_TEXT))
        painter.setFont(QFont("Consolas", 11))
        painter.drawText(mag_x, mag_y + mag_size + 18,
                         center_color.name().upper())
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = QCursor.pos()
            screen = QGuiApplication.screenAt(pos)
            if screen:
                pix = screen.grabWindow(0, pos.x(), pos.y(), 1, 1)
                img = pix.toImage()
                self.color_picked.emit(QColor(img.pixel(0, 0)))
            self._timer.stop()
            self.close()
        elif event.button() == Qt.MouseButton.RightButton:
            self._timer.stop()
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._timer.stop()
            self.close()


class ColorPickerDialog(QDialog):
    """Color picker with screen eyedropper and history."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎨 Color Picker")
        self.setFixedSize(360, 440)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)
        self._history: list[QColor] = []
        self._current: QColor | None = None
        self._overlay: _PickerOverlay | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title = QLabel("🎨 Color Picker")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE};")
        lay.addWidget(title)

        # Preview swatch
        self._preview = QLabel()
        self._preview.setFixedHeight(80)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet(
            f"background: {_SURFACE}; border: 2px solid #45475A; "
            f"border-radius: 8px; color: {_TEXT}; font-size: 14px;")
        self._preview.setText("Click 🔍 Pick to sample a color")
        lay.addWidget(self._preview)

        # Color values
        self._lbl_hex = QLabel("HEX: —")
        self._lbl_hex.setStyleSheet(f"color: {_TEXT}; font-family: Consolas; font-size: 13px;")
        self._lbl_rgb = QLabel("RGB: —")
        self._lbl_rgb.setStyleSheet(f"color: {_TEXT}; font-family: Consolas; font-size: 13px;")
        self._lbl_hsl = QLabel("HSL: —")
        self._lbl_hsl.setStyleSheet(f"color: {_TEXT}; font-family: Consolas; font-size: 13px;")
        lay.addWidget(self._lbl_hex)
        lay.addWidget(self._lbl_rgb)
        lay.addWidget(self._lbl_hsl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_pick = QPushButton("🔍 Pick from Screen")
        self._btn_pick.clicked.connect(self._start_pick)
        self._btn_pick.setStyleSheet(
            f"QPushButton {{ background: {_BLUE}; color: {_BG}; "
            f"border: none; border-radius: 6px; padding: 10px 16px; "
            f"font-weight: bold; font-size: 13px; }}"
            f"QPushButton:hover {{ background: #7BA4E8; }}")
        btn_row.addWidget(self._btn_pick)

        self._btn_copy_hex = QPushButton("📋 Copy HEX")
        self._btn_copy_hex.clicked.connect(lambda: self._copy("hex"))
        self._btn_copy_hex.setEnabled(False)
        btn_row.addWidget(self._btn_copy_hex)

        self._btn_copy_rgb = QPushButton("📋 Copy RGB")
        self._btn_copy_rgb.clicked.connect(lambda: self._copy("rgb"))
        self._btn_copy_rgb.setEnabled(False)
        btn_row.addWidget(self._btn_copy_rgb)

        lay.addLayout(btn_row)

        # History
        lay.addWidget(QLabel("Recent Colors:"))
        self._hist_grid = QGridLayout()
        self._hist_grid.setSpacing(4)
        lay.addLayout(self._hist_grid)
        lay.addStretch()

    def _start_pick(self):
        self.hide()
        QTimer.singleShot(200, self._do_pick)

    def _do_pick(self):
        self._overlay = _PickerOverlay()
        self._overlay.color_picked.connect(self._on_pick)
        self._overlay.destroyed.connect(lambda: self.show())
        self._overlay.show()

    def _on_pick(self, color: QColor):
        self._current = color
        self._preview.setStyleSheet(
            f"background: {color.name()}; border: 2px solid #45475A; "
            f"border-radius: 8px; color: {'#000' if color.lightness() > 128 else '#FFF'}; "
            f"font-size: 16px; font-weight: bold;")
        self._preview.setText(color.name().upper())

        self._lbl_hex.setText(f"HEX: {color.name().upper()}")
        self._lbl_rgb.setText(
            f"RGB: rgb({color.red()}, {color.green()}, {color.blue()})")
        h, s, l = color.hslHue(), color.hslSaturation(), color.lightness()
        self._lbl_hsl.setText(
            f"HSL: hsl({h}, {s * 100 // 255}%, {l * 100 // 255}%)")

        self._btn_copy_hex.setEnabled(True)
        self._btn_copy_rgb.setEnabled(True)

        # Add to history (max 12)
        self._history = [c for c in self._history
                         if c.name() != color.name()]
        self._history.insert(0, color)
        self._history = self._history[:12]
        self._rebuild_history()
        self.show()

    def _copy(self, fmt: str):
        if not self._current:
            return
        c = self._current
        if fmt == "hex":
            text = c.name().upper()
        else:
            text = f"rgb({c.red()}, {c.green()}, {c.blue()})"
        QApplication.clipboard().setText(text)
        self._preview.setText(f"✅ Copied: {text}")

    def _rebuild_history(self):
        # Clear grid
        while self._hist_grid.count():
            w = self._hist_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, c in enumerate(self._history):
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setStyleSheet(
                f"background: {c.name()}; border: 2px solid #45475A; "
                f"border-radius: 6px;")
            btn.setToolTip(c.name().upper())
            btn.clicked.connect(lambda _, col=c: self._on_pick(col))
            self._hist_grid.addWidget(btn, i // 6, i % 6)
