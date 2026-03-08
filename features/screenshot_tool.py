"""
Screenshot Tool — region-select screenshot capture.
Copies to clipboard and saves to file. Lightweight overlay selector.
"""
import os
import logging
from datetime import datetime
from PyQt6.QtWidgets import QWidget, QApplication
from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import (
    QPainter, QColor, QPixmap, QScreen, QGuiApplication, QPen, QFont,
)

log = logging.getLogger("toty")
_SAVE_DIR = "screenshots"


class _RegionSelector(QWidget):
    """Fullscreen transparent overlay for selecting a screen region."""
    region_selected = pyqtSignal(QRect)
    cancelled = pyqtSignal()

    def __init__(self, screenshot: QPixmap):
        super().__init__(None)
        self._screenshot = screenshot
        self._origin = QPoint()
        self._current = QPoint()
        self._selecting = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setGeometry(QGuiApplication.primaryScreen().geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.showFullScreen()

    def paintEvent(self, event):
        p = QPainter(self)
        p.drawPixmap(0, 0, self._screenshot)
        # Dark overlay
        p.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self._selecting:
            rect = QRect(self._origin, self._current).normalized()
            # Show selected region clearly
            p.drawPixmap(rect, self._screenshot, rect)
            p.setPen(QPen(QColor("#5599FF"), 2))
            p.drawRect(rect)
            # Size label
            p.setPen(QColor("#FFF"))
            p.setFont(QFont("Segoe UI", 10))
            p.drawText(rect.x(), rect.y() - 5,
                       f"{rect.width()} × {rect.height()}")
        else:
            p.setPen(QColor("#FFF"))
            p.setFont(QFont("Segoe UI", 14))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Click and drag to select region\nPress Esc to cancel")
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self._selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if self._selecting:
            self._selecting = False
            rect = QRect(self._origin, event.pos()).normalized()
            if rect.width() > 5 and rect.height() > 5:
                self.region_selected.emit(rect)
            else:
                self.cancelled.emit()
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()


class ScreenshotTool(QObject):
    """Manages screenshot capture workflow."""
    captured = pyqtSignal(str)   # saved file path
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._selector = None
        self._full_screenshot = None
        os.makedirs(_SAVE_DIR, exist_ok=True)

    def start_capture(self):
        """Begin region selection."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        self._full_screenshot = screen.grabWindow(0)
        self._selector = _RegionSelector(self._full_screenshot)
        self._selector.region_selected.connect(self._on_region)
        self._selector.cancelled.connect(self.cancelled.emit)

    def capture_fullscreen(self) -> str | None:
        """Capture full screen immediately."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return None
        pm = screen.grabWindow(0)
        return self._save_and_copy(pm)

    def _on_region(self, rect: QRect):
        if not self._full_screenshot:
            return
        cropped = self._full_screenshot.copy(rect)
        path = self._save_and_copy(cropped)
        if path:
            self.captured.emit(path)

    def _save_and_copy(self, pixmap: QPixmap) -> str | None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(_SAVE_DIR, f"screenshot_{ts}.png")
        if pixmap.save(path, "PNG"):
            # Copy to clipboard
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setPixmap(pixmap)
            log.info("Screenshot saved: %s", path)
            return path
        return None
