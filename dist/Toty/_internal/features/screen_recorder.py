"""Screen Recorder — pro screen capture with ffmpeg (auto-detected)."""
import os
import sys
import re
import time
import json
import logging
import subprocess
import shutil
import glob
import threading
import ctypes
from ctypes import wintypes
from datetime import datetime
from features.auto_deps import find_ffmpeg, ensure_ffmpeg
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QWidget, QApplication,
    QListWidget, QListWidgetItem, QFrame, QScrollArea, QSlider,
)
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint, pyqtSignal, QObject, QSize
from PyQt6.QtGui import (
    QFont, QPainter, QColor, QPen, QPixmap, QImage, QCursor,
    QPainterPath, QBrush,
)

log = logging.getLogger("toty.screen_recorder")

_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "TotyCatch")


# _find_ffmpeg is now in features.auto_deps


def _human_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


# ── Device enumeration (mic & camera) ────────────────────────────────
def _list_dshow_devices(ffmpeg_path: str | None) -> tuple[list[str], list[str]]:
    """Return (audio_devices, video_devices) available via DirectShow."""
    audio, video = [], []
    if not ffmpeg_path:
        return audio, video
    try:
        r = subprocess.run(
            [ffmpeg_path, "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=10,
        )
        text = r.stderr or ""
        for line in text.splitlines():
            if "Alternative name" in line:
                continue
            # Format: [dshow @ ...] "Device Name" (type)
            m = re.search(r'"(.+?)"\s*\((\w+)\)', line)
            if m:
                name, dtype = m.group(1), m.group(2).lower()
                if dtype == "audio":
                    audio.append(name)
                elif dtype == "video":
                    video.append(name)
    except Exception:
        pass
    return audio, video


def _list_windows() -> list[str]:
    """Return titles of visible top-level windows."""
    titles = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    def _cb(hwnd, _lp):
        if ctypes.windll.user32.IsWindowVisible(hwnd):
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                t = buf.value.strip()
                if t and t not in titles:
                    titles.append(t)
        return True
    ctypes.windll.user32.EnumWindows(WNDENUMPROC(_cb), 0)
    return sorted(titles)


def _find_window_rect(title: str) -> tuple[int, int, int, int] | None:
    """Find a window by title, bring it to foreground, return (x, y, w, h)."""
    user32 = ctypes.windll.user32
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        # Partial match fallback
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
        found = [0]
        def _cb(h, _lp):
            if user32.IsWindowVisible(h):
                length = user32.GetWindowTextLengthW(h)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buf, length + 1)
                    if title.lower() in buf.value.lower():
                        found[0] = h
                        return False  # stop enumeration
            return True
        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        hwnd = found[0]
    if not hwnd:
        return None
    # Restore if minimized (SW_RESTORE = 9)
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    # Bring to foreground
    user32.SetForegroundWindow(hwnd)
    # Get window rect (DPI-aware via DwmGetWindowAttribute if possible)
    rect = wintypes.RECT()
    try:
        dwm = ctypes.windll.dwmapi
        # DWMWA_EXTENDED_FRAME_BOUNDS = 9 — gives the actual visible rect
        dwm.DwmGetWindowAttribute(
            hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    except Exception:
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
    x, y = rect.left, rect.top
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w < 10 or h < 10:
        return None
    return (x, y, w, h)


# ── Global hotkey listener ────────────────────────────────────────────
class _HotkeyListener(QObject):
    """Registers Ctrl+Shift+F9/F10 as global hotkeys via Windows API."""
    toggle_record = pyqtSignal()
    toggle_pause = pyqtSignal()

    _ID_RECORD = 1
    _ID_PAUSE = 2

    def __init__(self):
        super().__init__()
        self._thread: threading.Thread | None = None
        self._thread_id = 0

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread_id, 0x0012, 0, 0)  # WM_QUIT
            except Exception:
                pass

    def _loop(self):
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        MOD = 0x0002 | 0x0004  # CTRL + SHIFT
        user32.RegisterHotKey(None, self._ID_RECORD, MOD, 0x78)  # F9
        user32.RegisterHotKey(None, self._ID_PAUSE, MOD, 0x79)   # F10
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:  # WM_HOTKEY
                if msg.wParam == self._ID_RECORD:
                    self.toggle_record.emit()
                elif msg.wParam == self._ID_PAUSE:
                    self.toggle_pause.emit()
        user32.UnregisterHotKey(None, self._ID_RECORD)
        user32.UnregisterHotKey(None, self._ID_PAUSE)


# ── Webcam overlay (PiP) ─────────────────────────────────────────────
class _WebcamOverlay(QWidget):
    """Small draggable webcam preview circle shown during recording."""

    def __init__(self, ffmpeg_path: str, device_name: str, size: int = 160):
        super().__init__()
        self._ffmpeg = ffmpeg_path
        self._device = device_name
        self._cam_size = size
        self._process: subprocess.Popen | None = None
        self._frame: QPixmap | None = None
        self._running = False

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(size + 8, size + 8)

        # Position bottom-right
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - size - 30, screen.height() - size - 80)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._grab_frame)

    def start(self):
        """Start capturing webcam frames via ffmpeg."""
        cmd = [
            self._ffmpeg,
            "-f", "dshow",
            "-video_size", "320x240",
            "-framerate", "15",
            "-i", f"video={self._device}",
            "-vf", f"scale={self._cam_size}:{self._cam_size}",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-",
        ]
        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._running = True
            self._timer.start(67)  # ~15fps
            self.show()
        except Exception as e:
            log.error("Webcam overlay failed: %s", e)

    def stop(self):
        self._running = False
        self._timer.stop()
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                pass
            self._process = None
        self.close()

    def _grab_frame(self):
        if not self._running or not self._process:
            return
        try:
            raw = self._process.stdout.read(self._cam_size * self._cam_size * 3)
            if len(raw) == self._cam_size * self._cam_size * 3:
                img = QImage(raw, self._cam_size, self._cam_size,
                             self._cam_size * 3, QImage.Format.Format_RGB888)
                self._frame = QPixmap.fromImage(img)
                self.update()
        except Exception:
            pass

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._cam_size
        cx, cy = 4, 4
        # Circular clip
        from PyQt6.QtGui import QPainterPath, QBrush
        path = QPainterPath()
        path.addEllipse(cx, cy, s, s)
        p.setClipPath(path)
        if self._frame:
            p.drawPixmap(cx, cy, s, s, self._frame)
        else:
            p.fillRect(cx, cy, s, s, QColor(30, 30, 46))
            p.setPen(QColor("#6C7086"))
            p.setFont(QFont("Arial", 20))
            p.drawText(QRect(cx, cy, s, s), Qt.AlignmentFlag.AlignCenter, "📷")
        p.setClipping(False)
        # Circle border
        p.setPen(QPen(QColor("#F38BA8"), 3))
        p.setBrush(QColor(0, 0, 0, 0))
        p.drawEllipse(cx, cy, s, s)
        p.end()

    # Draggable
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag_pos") and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)


# ── Cursor Magnifier ──────────────────────────────────────────────────
class _CursorMagnifier(QWidget):
    """Circular magnifying glass that follows the cursor."""

    def __init__(self, size: int = 200, zoom: float = 3.0):
        super().__init__()
        self._size = size
        self._zoom = zoom
        self._grab_r = int(size / zoom / 2)  # radius of area to capture
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(size + 8, size + 8)
        self._frame: QPixmap | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_grab)

    def start(self):
        self.show()
        self._timer.start(33)  # ~30fps

    def stop(self):
        self._timer.stop()
        self.close()

    def _update_grab(self):
        pos = QCursor.pos()
        screen = QApplication.screenAt(pos)
        if not screen:
            screen = QApplication.primaryScreen()
        r = self._grab_r
        grab = screen.grabWindow(
            0, pos.x() - r, pos.y() - r, r * 2, r * 2,
        )
        self._frame = grab.scaled(
            self._size, self._size,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Position lens offset from cursor so it doesn't block clicking area
        self.move(pos.x() + 20, pos.y() + 20)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size
        cx, cy = 4, 4
        # Circular clip
        path = QPainterPath()
        path.addEllipse(cx, cy, s, s)
        p.setClipPath(path)
        if self._frame:
            p.drawPixmap(cx, cy, s, s, self._frame)
        else:
            p.fillRect(cx, cy, s, s, QColor(30, 30, 46))
        p.setClipping(False)
        # Border
        p.setPen(QPen(QColor("#89B4FA"), 3))
        p.setBrush(QColor(0, 0, 0, 0))
        p.drawEllipse(cx, cy, s, s)
        # Crosshair
        cx2, cy2 = cx + s // 2, cy + s // 2
        p.setPen(QPen(QColor(255, 255, 255, 100), 1))
        p.drawLine(cx2 - 10, cy2, cx2 + 10, cy2)
        p.drawLine(cx2, cy2 - 10, cx2, cy2 + 10)
        # Zoom label
        p.setPen(QColor("#CDD6F4"))
        p.setFont(QFont("Consolas", 8))
        p.drawText(cx + 6, cy + s - 6, f"{self._zoom:.0f}×")
        p.end()


# ── Screen Draw / Annotate overlay ───────────────────────────────────
class _DrawOverlay(QWidget):
    """Fullscreen transparent overlay for freehand drawing annotations."""

    _COLORS = [
        QColor("#F38BA8"),  # red/pink
        QColor("#A6E3A1"),  # green
        QColor("#89B4FA"),  # blue
        QColor("#F9E2AF"),  # yellow
        QColor("#FFFFFF"),  # white
    ]

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self._strokes: list[tuple[QColor, int, list[QPoint]]] = []  # (color, width, points)
        self._current_points: list[QPoint] = []
        self._color_idx = 0
        self._pen_width = 3
        self._drawing = False

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Draw all completed strokes
        for color, width, points in self._strokes:
            if len(points) < 2:
                continue
            p.setPen(QPen(color, width, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            for i in range(1, len(points)):
                p.drawLine(points[i - 1], points[i])
        # Draw current stroke
        if self._current_points and len(self._current_points) >= 2:
            color = self._COLORS[self._color_idx % len(self._COLORS)]
            p.setPen(QPen(color, self._pen_width, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            for i in range(1, len(self._current_points)):
                p.drawLine(self._current_points[i - 1], self._current_points[i])
        # Toolbar hint at top
        p.setPen(QColor(150, 150, 170, 180))
        p.setFont(QFont("Consolas", 9))
        c = self._COLORS[self._color_idx % len(self._COLORS)]
        bar = f"  ✏ Draw Mode  |  RightClick: color  |  Ctrl+Z: undo  |  C: clear  |  Esc: close  |  Pen: {self._pen_width}px  "
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(bar)
        bx = self.width() // 2 - tw // 2
        p.setBrush(QColor(30, 30, 46, 200))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(bx - 8, 4, tw + 16, fm.height() + 8, 6, 6)
        # Color dot
        p.setBrush(c)
        p.setPen(QPen(QColor("#CDD6F4"), 1))
        p.drawEllipse(bx - 2, 8, fm.height(), fm.height())
        p.setPen(QColor("#CDD6F4"))
        p.drawText(bx + fm.height() + 4, 4 + fm.ascent() + 3, bar)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._color_idx = (self._color_idx + 1) % len(self._COLORS)
            self.update()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drawing = True
            self._current_points = [event.pos()]

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._current_points.append(event.pos())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drawing:
            self._drawing = False
            if len(self._current_points) >= 2:
                c = self._COLORS[self._color_idx % len(self._COLORS)]
                self._strokes.append((c, self._pen_width, list(self._current_points)))
            self._current_points = []
            self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() == Qt.Key.Key_C:
            self._strokes.clear()
            self.update()
        elif event.key() == Qt.Key.Key_Z and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self._strokes:
                self._strokes.pop()
                self.update()
        elif event.key() == Qt.Key.Key_BracketLeft:
            self._pen_width = max(1, self._pen_width - 1)
            self.update()
        elif event.key() == Qt.Key.Key_BracketRight:
            self._pen_width = min(20, self._pen_width + 1)
            self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self._pen_width = min(20, self._pen_width + 1)
        else:
            self._pen_width = max(1, self._pen_width - 1)
        self.update()


# ── Preset system ────────────────────────────────────────────────────
_PRESETS = {
    "Gameplay 60fps": {"fps": 60, "crf": 20, "preset": "ultrafast"},
    "Tutorial 30fps": {"fps": 30, "crf": 23, "preset": "fast"},
    "Meeting 15fps": {"fps": 15, "crf": 28, "preset": "ultrafast"},
    "GIF-ready 10fps": {"fps": 10, "crf": 18, "preset": "fast"},
    "Custom": None,
}


# ── Region selector overlay ──────────────────────────────────────────
class _RegionOverlay(QWidget):
    """Transparent fullscreen overlay for selecting a recording region."""
    region_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._origin = QPoint()
        self._current = QPoint()
        self._drawing = False

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self._drawing:
            rect = QRect(self._origin, self._current).normalized()
            # Crosshairs
            painter.setPen(QPen(QColor(255, 255, 255, 60), 1, Qt.PenStyle.DashLine))
            painter.drawLine(0, self._current.y(), self.width(), self._current.y())
            painter.drawLine(self._current.x(), 0, self._current.x(), self.height())
            # Selection box
            painter.setPen(QPen(QColor("#F38BA8"), 2))
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawRect(rect)
            painter.fillRect(rect, QColor(255, 255, 255, 20))
            # Dimension badge
            dim_text = f" {rect.width()} × {rect.height()} "
            painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(dim_text)
            th = fm.height()
            bx = rect.center().x() - tw // 2
            by = rect.bottom() + 4
            painter.setBrush(QColor(30, 30, 46, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bx - 4, by, tw + 8, th + 6, 4, 4)
            painter.setPen(QColor("#CDD6F4"))
            painter.drawText(bx, by + th, dim_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._origin = event.pos()
            self._current = event.pos()
            self._drawing = True

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._drawing:
            self._drawing = False
            rect = QRect(self._origin, event.pos()).normalized()
            if rect.width() > 20 and rect.height() > 20:
                global_rect = QRect(
                    self.mapToGlobal(rect.topLeft()),
                    rect.size(),
                )
                self.region_selected.emit(global_rect)
            self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()


# ── Countdown overlay (3-2-1) ────────────────────────────────────────
class _CountdownOverlay(QWidget):
    """Full-screen countdown before recording starts."""
    countdown_done = pyqtSignal()

    def __init__(self, seconds: int = 3):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self._count = seconds
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self.show()
        self._timer.start(1000)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        # Circle behind number
        cx, cy = self.width() // 2, self.height() // 2
        painter.setBrush(QColor(30, 30, 46, 180))
        painter.setPen(QPen(QColor("#F38BA8"), 4))
        painter.drawEllipse(cx - 80, cy - 80, 160, 160)
        # Number
        painter.setPen(QColor("#F38BA8"))
        painter.setFont(QFont("Arial", 100, QFont.Weight.Bold))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._count))

    def _tick(self):
        self._count -= 1
        if self._count <= 0:
            self._timer.stop()
            self.close()
            self.countdown_done.emit()
        else:
            self.update()


# ── Floating recording indicator ─────────────────────────────────────
class _FloatingIndicator(QWidget):
    """Always-on-top recording toolbar with pro controls."""
    stop_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()
    mute_clicked = pyqtSignal()
    marker_clicked = pyqtSignal()
    snapshot_clicked = pyqtSignal()
    zoom_clicked = pyqtSignal()
    draw_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(420, 44)

        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() // 2 - 210, 8)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(4)

        self._dot = QLabel("🔴")
        self._dot.setStyleSheet("font-size: 14px; border: none; background: transparent;")
        lay.addWidget(self._dot)

        self._time_lbl = QLabel("00:00")
        self._time_lbl.setStyleSheet(
            "color: #F38BA8; font-family: Consolas; font-size: 13px;"
            " font-weight: bold; border: none; background: transparent;")
        lay.addWidget(self._time_lbl)

        self._size_lbl = QLabel("")
        self._size_lbl.setStyleSheet(
            "color: #6C7086; font-family: Consolas; font-size: 10px;"
            " border: none; background: transparent;")
        lay.addWidget(self._size_lbl)

        lay.addStretch()

        btn_css = ("QPushButton { border: none; font-size: 14px; padding: 2px 4px;"
                   "  border-radius: 5px; background: transparent; }"
                   "QPushButton:hover { background: rgba(255,255,255,30); }")
        btn_active = ("QPushButton { border: none; font-size: 14px; padding: 2px 4px;"
                      "  border-radius: 5px; background: rgba(137,180,250,50); }"
                      "QPushButton:hover { background: rgba(137,180,250,80); }")
        btn_sz = QSize(28, 28)

        # Mic mute
        self._btn_mute = QPushButton("🎙")
        self._btn_mute.setStyleSheet(btn_css)
        self._btn_mute.setFixedSize(btn_sz)
        self._btn_mute.clicked.connect(self.mute_clicked.emit)
        self._btn_mute.setToolTip("Mute / Unmute mic")
        lay.addWidget(self._btn_mute)
        self._btn_mute_css = btn_css
        self._btn_mute_active = btn_active

        # Marker
        self._btn_marker = QPushButton("📌")
        self._btn_marker.setStyleSheet(btn_css)
        self._btn_marker.setFixedSize(btn_sz)
        self._btn_marker.clicked.connect(self.marker_clicked.emit)
        self._btn_marker.setToolTip("Add marker")
        lay.addWidget(self._btn_marker)

        # Snapshot
        self._btn_snap = QPushButton("📸")
        self._btn_snap.setStyleSheet(btn_css)
        self._btn_snap.setFixedSize(btn_sz)
        self._btn_snap.clicked.connect(self.snapshot_clicked.emit)
        self._btn_snap.setToolTip("Take screenshot")
        lay.addWidget(self._btn_snap)

        # Zoom toggle
        self._btn_zoom = QPushButton("🔍")
        self._btn_zoom.setStyleSheet(btn_css)
        self._btn_zoom.setFixedSize(btn_sz)
        self._btn_zoom.clicked.connect(self.zoom_clicked.emit)
        self._btn_zoom.setToolTip("Toggle zoom lens")
        lay.addWidget(self._btn_zoom)
        self._btn_zoom_css = btn_css
        self._btn_zoom_active = btn_active

        # Draw toggle
        self._btn_draw = QPushButton("✏")
        self._btn_draw.setStyleSheet(btn_css)
        self._btn_draw.setFixedSize(btn_sz)
        self._btn_draw.clicked.connect(self.draw_clicked.emit)
        self._btn_draw.setToolTip("Draw on screen")
        lay.addWidget(self._btn_draw)
        self._btn_draw_css = btn_css
        self._btn_draw_active = btn_active

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet("color: #45475A; font-size: 16px; background: transparent; border: none;")
        lay.addWidget(sep)

        # Pause
        self._btn_pause = QPushButton("⏸")
        self._btn_pause.setStyleSheet(btn_css)
        self._btn_pause.setFixedSize(btn_sz)
        self._btn_pause.clicked.connect(self.pause_clicked.emit)
        self._btn_pause.setToolTip("Pause / Resume")
        lay.addWidget(self._btn_pause)

        # Stop
        self._btn_stop = QPushButton("⏹")
        self._btn_stop.setStyleSheet(
            "QPushButton { border: none; font-size: 14px; padding: 2px 4px;"
            "  border-radius: 5px; background: rgba(243,139,168,40); }"
            "QPushButton:hover { background: rgba(243,139,168,80); }")
        self._btn_stop.setFixedSize(btn_sz)
        self._btn_stop.clicked.connect(self.stop_clicked.emit)
        self._btn_stop.setToolTip("Stop recording")
        lay.addWidget(self._btn_stop)

        self._blink = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._do_blink)
        self._blink_timer.start(500)

    def set_mic_visible(self, vis: bool):
        self._btn_mute.setVisible(vis)

    def set_muted(self, muted: bool):
        self._btn_mute.setText("🔇" if muted else "🎙")
        self._btn_mute.setStyleSheet(
            self._btn_mute_active if muted else self._btn_mute_css)

    def set_zoom_active(self, on: bool):
        self._btn_zoom.setStyleSheet(
            self._btn_zoom_active if on else self._btn_zoom_css)

    def set_draw_active(self, on: bool):
        self._btn_draw.setStyleSheet(
            self._btn_draw_active if on else self._btn_draw_css)

    def flash_marker(self):
        """Quick flash the marker button to confirm."""
        self._btn_marker.setStyleSheet(
            "QPushButton { border: none; font-size: 14px; padding: 2px 4px;"
            "  border-radius: 5px; background: rgba(166,227,161,80); }")
        QTimer.singleShot(400, lambda: self._btn_marker.setStyleSheet(
            self._btn_mute_css))  # reuse same base css

    def flash_snapshot(self):
        self._btn_snap.setStyleSheet(
            "QPushButton { border: none; font-size: 14px; padding: 2px 4px;"
            "  border-radius: 5px; background: rgba(137,180,250,80); }")
        QTimer.singleShot(400, lambda: self._btn_snap.setStyleSheet(
            self._btn_mute_css))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(30, 30, 46, 230))
        painter.setPen(QPen(QColor("#F38BA8"), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 12, 12)

    def update_time(self, secs: int, paused: bool = False, file_path: str = ""):
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        self._time_lbl.setText(f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}")
        self._btn_pause.setText("▶" if paused else "⏸")
        if file_path and os.path.exists(file_path):
            try:
                self._size_lbl.setText(_human_size(os.path.getsize(file_path)))
            except OSError:
                pass
        self._is_paused = paused

    def _do_blink(self):
        self._blink = not self._blink
        is_paused = getattr(self, "_is_paused", False)
        if is_paused:
            self._dot.setText("⏸" if self._blink else " ")
        else:
            self._dot.setText("🔴" if self._blink else "⚫")

    # Draggable
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if hasattr(self, "_drag_pos") and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)


# ── Core recorder ────────────────────────────────────────────────────
class ScreenRecorder(QObject):
    """Records screen to MP4 using ffmpeg (gdigrab on Windows)."""
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(str)  # file path
    recording_paused = pyqtSignal(bool)  # is_paused

    def __init__(self):
        super().__init__()
        self._process: subprocess.Popen | None = None
        self._recording = False
        self._paused = False
        self._output_path = ""
        self._start_time = 0.0
        self._pause_total = 0.0
        self._pause_start = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._elapsed = 0
        self._ffmpeg = find_ffmpeg()
        self._overlay: _RegionOverlay | None = None
        self._countdown: _CountdownOverlay | None = None
        self._indicator: _FloatingIndicator | None = None
        self._audio = False
        self._mic_device: str | None = None  # selected microphone name
        self._cam_device: str | None = None  # selected camera name
        self._cam_size = 160  # webcam overlay size
        self._crf = 23
        self._preset_name = "ultrafast"
        self._pending_params: dict | None = None
        self._recordings: list[dict] = []  # history
        self._webcam: _WebcamOverlay | None = None
        self._draw_mouse = True
        self._output_format = "mp4"  # mp4, mkv, webm
        self._auto_stop = 0  # seconds, 0 = disabled
        self._monitor_idx = 0  # 0 = primary
        self._magnifier: _CursorMagnifier | None = None
        self._draw_overlay: _DrawOverlay | None = None
        self._markers: list[dict] = []  # {"time": sec, "label": str}
        self._mic_muted = False
        self._load_history()
        # Global hotkeys
        self._hotkeys = _HotkeyListener()
        self._hotkeys.toggle_record.connect(self._hotkey_toggle)
        self._hotkeys.toggle_pause.connect(self.toggle_pause)
        self._hotkeys.start()

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def elapsed_sec(self) -> int:
        return self._elapsed

    @property
    def recordings(self) -> list[dict]:
        return list(self._recordings)

    def has_ffmpeg(self) -> bool:
        return self._ffmpeg is not None

    def set_audio(self, enabled: bool):
        self._audio = enabled

    def set_mic(self, device: str | None):
        self._mic_device = device

    def set_camera(self, device: str | None, size: int = 160):
        self._cam_device = device
        self._cam_size = size

    def list_devices(self) -> tuple[list[str], list[str]]:
        """Return (audio_devices, video_devices)."""
        return _list_dshow_devices(self._ffmpeg)

    @staticmethod
    def list_windows() -> list[str]:
        return _list_windows()

    def set_draw_mouse(self, on: bool):
        self._draw_mouse = on

    def set_output_format(self, fmt: str):
        self._output_format = fmt.lower()

    def set_auto_stop(self, secs: int):
        self._auto_stop = max(0, secs)

    def set_monitor(self, idx: int):
        self._monitor_idx = idx

    def set_quality(self, crf: int, preset: str):
        self._crf = crf
        self._preset_name = preset

    def start_fullscreen(self, fps: int = 15, countdown: bool = True):
        screens = QApplication.screens()
        idx = min(self._monitor_idx, len(screens) - 1)
        scr = screens[idx]
        geo = scr.geometry()
        dpr = scr.devicePixelRatio()
        self._pending_params = dict(
            x=int(geo.x() * dpr), y=int(geo.y() * dpr),
            w=int(geo.width() * dpr), h=int(geo.height() * dpr), fps=fps,
        )
        if countdown:
            self._show_countdown()
        else:
            self._start_recording(**self._pending_params)

    def start_region_select(self, fps: int = 15):
        self._pending_fps = fps
        self._overlay = _RegionOverlay()
        self._overlay.region_selected.connect(self._on_region)
        self._overlay.show()

    def start_window(self, title: str, fps: int = 15):
        """Record a specific window by finding its rect on screen."""
        rect = _find_window_rect(title)
        if not rect:
            log.warning("Window not found: %s", title)
            return
        x, y, w, h = rect
        self._pending_params = dict(x=x, y=y, w=w, h=h, fps=fps)
        self._show_countdown()

    def _on_region(self, rect: QRect):
        dpr = QApplication.primaryScreen().devicePixelRatio()
        self._pending_params = dict(
            x=int(rect.x() * dpr), y=int(rect.y() * dpr),
            w=int(rect.width() * dpr), h=int(rect.height() * dpr),
            fps=self._pending_fps,
        )
        self._show_countdown()

    def _show_countdown(self):
        self._countdown = _CountdownOverlay(3)
        self._countdown.countdown_done.connect(self._after_countdown)
        self._countdown.start()

    def _after_countdown(self):
        if self._pending_params:
            self._start_recording(**self._pending_params)
            self._pending_params = None

    def _start_recording(self, x: int, y: int, w: int, h: int, fps: int):
        if self._recording or not self._ffmpeg:
            return

        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = self._output_format
        self._output_path = os.path.join(_OUTPUT_DIR, f"toty_rec_{ts}.{ext}")

        w = w if w % 2 == 0 else w - 1
        h = h if h % 2 == 0 else h - 1

        cmd = [
            self._ffmpeg,
            "-f", "gdigrab",
            "-framerate", str(fps),
            "-draw_mouse", "1" if self._draw_mouse else "0",
            "-offset_x", str(x),
            "-offset_y", str(y),
            "-video_size", f"{w}x{h}",
            "-i", "desktop",
        ]
        if self._audio and self._mic_device:
            cmd += ["-f", "dshow", "-i", f"audio={self._mic_device}"]
        # Video codec
        if ext == "webm":
            cmd += ["-c:v", "libvpx-vp9", "-crf", str(self._crf),
                    "-b:v", "0", "-deadline", "realtime", "-cpu-used", "4"]
        else:
            cmd += ["-c:v", "libx264", "-preset", self._preset_name,
                    "-crf", str(self._crf), "-pix_fmt", "yuv420p"]
        # Audio codec
        if self._audio and self._mic_device:
            cmd += ["-c:a", "libopus", "-b:a", "128k"] if ext == "webm" \
                else ["-c:a", "aac", "-b:a", "128k"]
        cmd += ["-y", self._output_path]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._recording = True
            self._paused = False
            self._pause_total = 0.0
            self._start_time = time.time()
            self._elapsed = 0
            self._timer.start(500)
            self._markers = []
            self._mic_muted = False
            self._indicator = _FloatingIndicator()
            self._indicator.stop_clicked.connect(self.stop)
            self._indicator.pause_clicked.connect(self.toggle_pause)
            self._indicator.mute_clicked.connect(self.toggle_mute)
            self._indicator.marker_clicked.connect(self.add_marker)
            self._indicator.snapshot_clicked.connect(self.take_snapshot)
            self._indicator.zoom_clicked.connect(self.toggle_magnifier)
            self._indicator.draw_clicked.connect(self.toggle_draw)
            self._indicator.set_mic_visible(self._audio and self._mic_device is not None)
            self._indicator.show()
            # Start webcam overlay if a camera is selected
            if self._cam_device and self._ffmpeg:
                self._webcam = _WebcamOverlay(self._ffmpeg, self._cam_device, self._cam_size)
                self._webcam.start()
            self.recording_started.emit()
            log.info("Screen recording started: %s", self._output_path)
        except Exception as e:
            log.error("Failed to start recording: %s", e)

    def toggle_pause(self):
        if not self._recording or not self._process:
            return
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1F0FFF, False, self._process.pid)
        if self._paused:
            ctypes.windll.ntdll.NtResumeProcess(handle)
            self._pause_total += time.time() - self._pause_start
            self._paused = False
        else:
            ctypes.windll.ntdll.NtSuspendProcess(handle)
            self._pause_start = time.time()
            self._paused = True
        kernel32.CloseHandle(handle)
        self.recording_paused.emit(self._paused)

    def stop(self):
        if not self._recording or not self._process:
            return
        self._timer.stop()
        if self._paused:
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1F0FFF, False, self._process.pid)
                ctypes.windll.ntdll.NtResumeProcess(handle)
                kernel32.CloseHandle(handle)
            except Exception:
                pass
            self._paused = False
        try:
            self._process.stdin.write(b"q")
            self._process.stdin.flush()
            self._process.wait(timeout=10)
        except Exception:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                pass

        self._recording = False
        self._process = None
        # Clean up overlays
        if self._webcam:
            self._webcam.stop()
            self._webcam = None
        if self._magnifier:
            self._magnifier.stop()
            self._magnifier = None
        if self._draw_overlay:
            self._draw_overlay.close()
            self._draw_overlay = None
        if self._indicator:
            self._indicator.close()
            self._indicator = None

        path = self._output_path
        if os.path.exists(path):
            duration = self._elapsed
            size = os.path.getsize(path)
            self._recordings.insert(0, {
                "path": path,
                "name": os.path.basename(path),
                "date": datetime.now().isoformat(),
                "duration": duration,
                "size": size,
                "markers": list(self._markers),
            })
            self._save_history()
            log.info("Recording saved: %s (%s, %ds)", path, _human_size(size), duration)
            self.recording_stopped.emit(path)
        else:
            log.warning("Recording file not found")

    def convert_to_gif(self, mp4_path: str, callback=None):
        """Convert MP4 to GIF in background."""
        if not self._ffmpeg or not os.path.exists(mp4_path):
            return
        gif_path = mp4_path.rsplit(".", 1)[0] + ".gif"
        cmd = [
            self._ffmpeg,
            "-i", mp4_path,
            "-vf", "fps=10,scale=640:-1:flags=lanczos",
            "-y", gif_path,
        ]
        try:
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            log.info("GIF conversion started: %s", gif_path)
        except Exception as e:
            log.error("GIF conversion failed: %s", e)

    def toggle_mute(self):
        """Toggle mic mute/unmute by suspending/resuming dshow audio."""
        self._mic_muted = not self._mic_muted
        if self._indicator:
            self._indicator.set_muted(self._mic_muted)
        log.info("Mic %s", "muted" if self._mic_muted else "unmuted")

    def add_marker(self, label: str = ""):
        """Bookmark the current timestamp."""
        ts = self._elapsed
        m, s = divmod(ts, 60)
        self._markers.append({"time": ts, "label": label or f"Marker @ {m:02d}:{s:02d}"})
        if self._indicator:
            self._indicator.flash_marker()
        log.info("Marker added at %ds", ts)

    def take_snapshot(self):
        """Capture screenshot of primary screen and save to output dir."""
        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_path = os.path.join(_OUTPUT_DIR, f"toty_snap_{ts_str}.png")
        screen = QApplication.primaryScreen()
        if screen:
            px = screen.grabWindow(0)
            px.save(snap_path, "PNG")
            if self._indicator:
                self._indicator.flash_snapshot()
            log.info("Snapshot saved: %s", snap_path)

    def toggle_magnifier(self):
        """Toggle cursor magnifier on/off."""
        if self._magnifier:
            self._magnifier.stop()
            self._magnifier = None
            if self._indicator:
                self._indicator.set_zoom_active(False)
        else:
            self._magnifier = _CursorMagnifier(200, 3.0)
            self._magnifier.start()
            if self._indicator:
                self._indicator.set_zoom_active(True)

    def toggle_draw(self):
        """Toggle draw/annotate overlay on/off."""
        if self._draw_overlay and self._draw_overlay.isVisible():
            self._draw_overlay.close()
            self._draw_overlay = None
            if self._indicator:
                self._indicator.set_draw_active(False)
        else:
            self._draw_overlay = _DrawOverlay()
            self._draw_overlay.show()
            if self._indicator:
                self._indicator.set_draw_active(True)

    @property
    def markers(self) -> list[dict]:
        return list(self._markers)

    def _hotkey_toggle(self):
        """Called by global hotkey — toggles recording on/off."""
        if self._recording:
            self.stop()
        else:
            self.start_fullscreen(countdown=True)

    def delete_recording(self, path: str):
        """Remove a recording from history and delete the file."""
        self._recordings = [r for r in self._recordings if r.get("path") != path]
        self._save_history()
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    def _tick(self):
        if not self._paused:
            self._elapsed = int(time.time() - self._start_time - self._pause_total)
        if self._auto_stop > 0 and self._elapsed >= self._auto_stop:
            self.stop()
            return
        if self._indicator:
            self._indicator.update_time(self._elapsed, self._paused, self._output_path)

    def _save_history(self):
        try:
            path = os.path.join(_OUTPUT_DIR, ".recording_history.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._recordings[:50], f)
        except Exception:
            pass

    def _load_history(self):
        try:
            path = os.path.join(_OUTPUT_DIR, ".recording_history.json")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    self._recordings = json.load(f)
        except Exception:
            self._recordings = []


# ── Recording card widget ────────────────────────────────────────────
class _RecordingCard(QFrame):
    """Single recording entry in the history list."""
    delete_requested = pyqtSignal(str)  # emits path

    def __init__(self, info: dict, ffmpeg: str | None, parent=None):
        super().__init__(parent)
        self._path = info["path"]
        self._ffmpeg = ffmpeg
        self.setStyleSheet(
            "QFrame { background: #313244; border-radius: 8px; }"
            "QFrame:hover { background: #3B3B52; }")
        self.setFixedHeight(60)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(10)

        # Thumbnail placeholder (colored icon)
        thumb = QLabel("🎬")
        thumb.setFixedSize(40, 40)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("font-size: 22px; background: #45475A; border-radius: 6px;")
        lay.addWidget(thumb)

        # Info
        info_lay = QVBoxLayout()
        info_lay.setSpacing(2)
        name_lbl = QLabel(info["name"])
        name_lbl.setStyleSheet("color: #CDD6F4; font-size: 12px; font-weight: bold;")
        info_lay.addWidget(name_lbl)
        m, s = divmod(info.get("duration", 0), 60)
        markers = info.get("markers", [])
        marker_str = f"  📌{len(markers)}" if markers else ""
        meta = f"⏱ {m:02d}:{s:02d}   📐 {_human_size(info.get('size', 0))}{marker_str}"
        meta_lbl = QLabel(meta)
        meta_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        info_lay.addWidget(meta_lbl)
        lay.addLayout(info_lay, 1)

        # Action buttons
        btn_css = ("QPushButton { border: none; font-size: 13px; padding: 4px;"
                   "  border-radius: 4px; background: transparent; }"
                   "QPushButton:hover { background: rgba(255,255,255,20); }")
        btn_play = QPushButton("▶")
        btn_play.setToolTip("Play")
        btn_play.setStyleSheet(btn_css)
        btn_play.setFixedSize(28, 28)
        btn_play.clicked.connect(lambda: os.startfile(self._path) if os.path.exists(self._path) else None)
        lay.addWidget(btn_play)

        btn_folder = QPushButton("📂")
        btn_folder.setToolTip("Show in folder")
        btn_folder.setStyleSheet(btn_css)
        btn_folder.setFixedSize(28, 28)
        btn_folder.clicked.connect(self._open_folder)
        lay.addWidget(btn_folder)

        btn_gif = QPushButton("🎞")
        btn_gif.setToolTip("Convert to GIF")
        btn_gif.setStyleSheet(btn_css)
        btn_gif.setFixedSize(28, 28)
        btn_gif.clicked.connect(self._to_gif)
        lay.addWidget(btn_gif)

        btn_del = QPushButton("🗑")
        btn_del.setToolTip("Delete recording")
        btn_del.setStyleSheet(
            "QPushButton { border: none; font-size: 13px; padding: 4px;"
            "  border-radius: 4px; background: transparent; }"
            "QPushButton:hover { background: rgba(243,139,168,40); }")
        btn_del.setFixedSize(28, 28)
        btn_del.clicked.connect(lambda: self.delete_requested.emit(self._path))
        lay.addWidget(btn_del)

    def _open_folder(self):
        if os.path.exists(self._path):
            subprocess.run(
                ["explorer", "/select,", self._path],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

    def _to_gif(self):
        if not self._ffmpeg or not os.path.exists(self._path):
            return
        gif = self._path.rsplit(".", 1)[0] + ".gif"
        subprocess.Popen(
            [self._ffmpeg, "-i", self._path,
             "-vf", "fps=10,scale=640:-1:flags=lanczos", "-y", gif],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )


# ── Record dialog ────────────────────────────────────────────────────
class RecordDialog(QDialog):
    """Pro recording configuration dialog with presets and history."""

    def __init__(self, recorder: ScreenRecorder, parent=None):
        super().__init__(parent)
        self._recorder = recorder
        self.setWindowTitle("🎬 Screen Recorder")
        self.setMinimumWidth(380)
        self.setMinimumHeight(300)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("🎬 Screen Recorder")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #F38BA8;")
        layout.addWidget(title)

        if not recorder.has_ffmpeg():
            warn = QLabel("⚠️ ffmpeg not found.\n\n"
                          "Click below to install automatically,\n"
                          "or install manually:\n"
                          "  winget install Gyan.FFmpeg")
            warn.setStyleSheet("color: #F9E2AF; font-size: 12px; font-family: Consolas;")
            warn.setWordWrap(True)
            layout.addWidget(warn)
            self._install_btn = QPushButton("📥 Install ffmpeg Now")
            self._install_btn.setStyleSheet(
                "QPushButton { background: #A6E3A1; color: #1E1E2E; border: none;"
                " border-radius: 8px; padding: 12px; font-weight: bold; font-size: 13px; }"
                "QPushButton:hover { background: #94E2D5; }"
                "QPushButton:disabled { background: #45475A; color: #6C7086; }")
            self._install_btn.clicked.connect(self._auto_install_ffmpeg)
            layout.addWidget(self._install_btn)
            self._install_status = QLabel("")
            self._install_status.setStyleSheet("color: #89B4FA; font-size: 12px;")
            self._install_status.setWordWrap(True)
            layout.addWidget(self._install_status)
            return

        lbl_css = "color: #CDD6F4; font-size: 12px;"
        spin_css = ("QSpinBox { background: #313244; color: #CDD6F4;"
                    " border: 1px solid #45475A; border-radius: 4px; padding: 4px; }")
        combo_css = ("QComboBox { background: #313244; color: #CDD6F4;"
                     " border: 1px solid #45475A; border-radius: 4px; padding: 4px; }"
                     "QComboBox QAbstractItemView { background: #313244; color: #CDD6F4; }")
        check_css = "QCheckBox { color: #CDD6F4; font-size: 12px; }"

        # ── Preset row ──
        preset_row = QHBoxLayout()
        preset_lbl = QLabel("Preset:")
        preset_lbl.setStyleSheet(lbl_css)
        preset_row.addWidget(preset_lbl)
        self._preset_cb = QComboBox()
        self._preset_cb.addItems(list(_PRESETS.keys()))
        self._preset_cb.setCurrentText("Tutorial 30fps")
        self._preset_cb.setStyleSheet(combo_css)
        self._preset_cb.currentTextChanged.connect(self._apply_preset)
        preset_row.addWidget(self._preset_cb, 1)
        layout.addLayout(preset_row)

        # ── Custom settings (FPS + Quality) ──
        self._custom_frame = QFrame()
        self._custom_frame.setStyleSheet("QFrame { background: transparent; }")
        cf_lay = QHBoxLayout(self._custom_frame)
        cf_lay.setContentsMargins(0, 0, 0, 0)
        cf_lay.setSpacing(8)

        fps_lbl = QLabel("FPS:")
        fps_lbl.setStyleSheet(lbl_css)
        self._fps = QSpinBox()
        self._fps.setRange(5, 60)
        self._fps.setValue(30)
        self._fps.setStyleSheet(spin_css)
        cf_lay.addWidget(fps_lbl)
        cf_lay.addWidget(self._fps)

        q_lbl = QLabel("Quality:")
        q_lbl.setStyleSheet(lbl_css)
        self._quality = QComboBox()
        self._quality.addItems(["Low (fast)", "Medium", "High (slow)"])
        self._quality.setCurrentIndex(1)
        self._quality.setStyleSheet(combo_css)
        cf_lay.addWidget(q_lbl)
        cf_lay.addWidget(self._quality)
        layout.addWidget(self._custom_frame)

        # ── Output format ──
        fmt_row = QHBoxLayout()
        fmt_lbl = QLabel("Format:")
        fmt_lbl.setStyleSheet(lbl_css)
        fmt_row.addWidget(fmt_lbl)
        self._format_cb = QComboBox()
        self._format_cb.addItems(["MP4", "MKV", "WebM"])
        self._format_cb.setStyleSheet(combo_css)
        fmt_row.addWidget(self._format_cb, 1)

        # Monitor selector (same row)
        mon_lbl = QLabel("  Monitor:")
        mon_lbl.setStyleSheet(lbl_css)
        fmt_row.addWidget(mon_lbl)
        self._monitor_cb = QComboBox()
        screens = QApplication.screens()
        for i, s in enumerate(screens):
            g = s.geometry()
            self._monitor_cb.addItem(f"💻 {i+1} — {g.width()}×{g.height()}")
        self._monitor_cb.setStyleSheet(combo_css)
        fmt_row.addWidget(self._monitor_cb, 1)
        layout.addLayout(fmt_row)

        # ── Microphone ──
        mic_row = QHBoxLayout()
        self._mic_cb = QCheckBox("🎙 Microphone")
        self._mic_cb.setStyleSheet(check_css)
        mic_row.addWidget(self._mic_cb)

        self._mic_combo = QComboBox()
        self._mic_combo.setStyleSheet(combo_css)
        self._mic_combo.setEnabled(False)
        self._mic_combo.setMinimumWidth(160)
        mic_row.addWidget(self._mic_combo, 1)
        layout.addLayout(mic_row)

        self._mic_cb.toggled.connect(self._on_mic_toggled)

        # ── Camera ──
        cam_row = QHBoxLayout()
        self._cam_cb = QCheckBox("📷 Camera (PiP)")
        self._cam_cb.setStyleSheet(check_css)
        cam_row.addWidget(self._cam_cb)

        self._cam_combo = QComboBox()
        self._cam_combo.setStyleSheet(combo_css)
        self._cam_combo.setEnabled(False)
        self._cam_combo.setMinimumWidth(160)
        cam_row.addWidget(self._cam_combo, 1)
        layout.addLayout(cam_row)

        self._cam_cb.toggled.connect(self._on_cam_toggled)

        # Camera size slider
        cam_size_row = QHBoxLayout()
        cam_size_lbl = QLabel("  Cam size:")
        cam_size_lbl.setStyleSheet("color: #6C7086; font-size: 11px;")
        cam_size_row.addWidget(cam_size_lbl)
        self._cam_slider = QSlider(Qt.Orientation.Horizontal)
        self._cam_slider.setRange(80, 280)
        self._cam_slider.setValue(160)
        self._cam_slider.setStyleSheet(
            "QSlider::groove:horizontal { background: #313244; height: 4px; border-radius: 2px; }"
            "QSlider::handle:horizontal { background: #F38BA8; width: 14px; margin: -5px 0; border-radius: 7px; }")
        cam_size_row.addWidget(self._cam_slider, 1)
        self._cam_size_val = QLabel("160px")
        self._cam_size_val.setStyleSheet("color: #6C7086; font-size: 11px;")
        self._cam_size_val.setFixedWidth(40)
        cam_size_row.addWidget(self._cam_size_val)
        layout.addLayout(cam_size_row)
        self._cam_slider.valueChanged.connect(
            lambda v: self._cam_size_val.setText(f"{v}px"))
        self._cam_slider.setVisible(False)
        cam_size_lbl.setVisible(False)
        self._cam_size_val.setVisible(False)
        self._cam_size_lbl = cam_size_lbl  # keep ref for show/hide

        # ── Mouse cursor ──
        self._cursor_cb = QCheckBox("🖱 Show mouse cursor")
        self._cursor_cb.setStyleSheet(check_css)
        self._cursor_cb.setChecked(True)
        layout.addWidget(self._cursor_cb)

        # ── Auto-stop timer ──
        auto_row = QHBoxLayout()
        self._autostop_cb = QCheckBox("⏱ Auto-stop after")
        self._autostop_cb.setStyleSheet(check_css)
        auto_row.addWidget(self._autostop_cb)
        self._autostop_spin = QSpinBox()
        self._autostop_spin.setRange(5, 7200)
        self._autostop_spin.setValue(300)
        self._autostop_spin.setSuffix(" sec")
        self._autostop_spin.setEnabled(False)
        self._autostop_spin.setStyleSheet(spin_css)
        auto_row.addWidget(self._autostop_spin)
        auto_row.addStretch()
        layout.addLayout(auto_row)
        self._autostop_cb.toggled.connect(self._autostop_spin.setEnabled)

        # Load devices in background so dialog doesn't freeze
        self._audio_devices: list[str] = []
        self._video_devices: list[str] = []
        self._devices_loaded = False
        threading.Thread(target=self._load_devices, daemon=True).start()

        # ── Hotkey hint ──
        hk_lbl = QLabel("⌨ Ctrl+Shift+F9: Record  |  Ctrl+Shift+F10: Pause")
        hk_lbl.setStyleSheet("color: #585B70; font-size: 10px;")
        hk_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hk_lbl)

        # Status
        self._status = QLabel("Ready — choose a recording mode")
        self._status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)

        # ── Record buttons ──
        btn_style = (
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 10px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #B4BEFE; }"
        )
        stop_style = (
            "QPushButton { background: #F38BA8; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 10px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #EBA0AC; }"
        )
        green_style = (
            "QPushButton { background: #A6E3A1; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 10px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #94E2D5; }"
        )

        rec_row = QHBoxLayout()
        self._btn_full = QPushButton("🖥️ Fullscreen")
        self._btn_full.setStyleSheet(btn_style)
        self._btn_full.clicked.connect(self._start_full)
        rec_row.addWidget(self._btn_full)

        self._btn_region = QPushButton("✂️ Region")
        self._btn_region.setStyleSheet(btn_style)
        self._btn_region.clicked.connect(self._start_region)
        rec_row.addWidget(self._btn_region)

        self._btn_window = QPushButton("🪟 Window")
        self._btn_window.setStyleSheet(btn_style)
        self._btn_window.clicked.connect(self._start_window)
        rec_row.addWidget(self._btn_window)
        layout.addLayout(rec_row)

        ctrl_row = QHBoxLayout()
        self._btn_pause = QPushButton("⏸ Pause")
        self._btn_pause.setStyleSheet(btn_style)
        self._btn_pause.clicked.connect(self._toggle_pause)
        self._btn_pause.setVisible(False)
        ctrl_row.addWidget(self._btn_pause)

        self._btn_stop = QPushButton("⏹ Stop")
        self._btn_stop.setStyleSheet(stop_style)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_stop.setVisible(False)
        ctrl_row.addWidget(self._btn_stop)
        layout.addLayout(ctrl_row)

        # Post-recording actions
        post_row = QHBoxLayout()
        self._btn_open = QPushButton("📂 Open Folder")
        self._btn_open.setStyleSheet(green_style)
        self._btn_open.clicked.connect(lambda: os.startfile(_OUTPUT_DIR))
        self._btn_open.setVisible(False)
        post_row.addWidget(self._btn_open)

        self._btn_gif = QPushButton("🎞 Convert to GIF")
        self._btn_gif.setStyleSheet(green_style)
        self._btn_gif.clicked.connect(self._convert_gif)
        self._btn_gif.setVisible(False)
        post_row.addWidget(self._btn_gif)
        layout.addLayout(post_row)

        # ── Recording history ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #45475A;")
        layout.addWidget(sep)

        hist_lbl = QLabel("📁 Recent Recordings")
        hist_lbl.setStyleSheet("color: #6C7086; font-size: 11px; font-weight: bold;")
        layout.addWidget(hist_lbl)

        self._history_area = QVBoxLayout()
        self._history_area.setSpacing(6)
        scroll_widget = QWidget()
        scroll_widget.setLayout(self._history_area)
        scroll_widget.setStyleSheet("background: transparent;")
        scroll = QScrollArea()
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(180)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 6px; background: #1E1E2E; }"
            "QScrollBar::handle:vertical { background: #45475A; border-radius: 3px; }")
        layout.addWidget(scroll)

        self._refresh_history()

        # Timer
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_status)

        self._recorder.recording_started.connect(self._on_started)
        self._recorder.recording_stopped.connect(self._on_stopped)
        self._recorder.recording_paused.connect(self._on_paused)
        self._last_path = ""

        # Apply default preset
        self._apply_preset("Tutorial 30fps")

    # ── Device handling ──
    def _load_devices(self):
        """Enumerate audio/video devices in background thread."""
        a, v = self._recorder.list_devices()
        self._audio_devices = a
        self._video_devices = v
        self._devices_loaded = True
        QTimer.singleShot(0, self._populate_devices)

    def _populate_devices(self):
        self._mic_combo.clear()
        if self._audio_devices:
            self._mic_combo.addItems(self._audio_devices)
        else:
            self._mic_combo.addItem("(no microphone found)")
            self._mic_cb.setEnabled(False)

        self._cam_combo.clear()
        if self._video_devices:
            self._cam_combo.addItems(self._video_devices)
        else:
            self._cam_combo.addItem("(no camera found)")
            self._cam_cb.setEnabled(False)

    def _on_mic_toggled(self, on: bool):
        self._mic_combo.setEnabled(on)
        if on and self._audio_devices:
            self._recorder.set_audio(True)
            self._recorder.set_mic(self._mic_combo.currentText())
        else:
            self._recorder.set_audio(False)
            self._recorder.set_mic(None)

    def _on_cam_toggled(self, on: bool):
        self._cam_combo.setEnabled(on)
        self._cam_slider.setVisible(on)
        self._cam_size_lbl.setVisible(on)
        self._cam_size_val.setVisible(on)
        if on and self._video_devices:
            self._recorder.set_camera(
                self._cam_combo.currentText(), self._cam_slider.value())
        else:
            self._recorder.set_camera(None)

    def _auto_install_ffmpeg(self):
        """Auto-install ffmpeg via winget, then refresh recorder."""
        self._install_btn.setEnabled(False)
        self._install_btn.setText("⏳ Installing ffmpeg...")
        self._install_status.setText("Downloading via winget — this may take a minute...")

        def _on_done(path):
            if path:
                self._recorder._ffmpeg = path
                self._install_status.setText(f"✅ Installed: {path}\nReopen this dialog to start recording.")
                self._install_btn.setText("✅ Installed!")
            else:
                self._install_status.setText("❌ Auto-install failed.\nTry manually: winget install Gyan.FFmpeg")
                self._install_btn.setEnabled(True)
                self._install_btn.setText("🔄 Retry Install")

        ensure_ffmpeg(callback=lambda p: QTimer.singleShot(0, lambda: _on_done(p)))

    def _apply_preset(self, name: str):
        cfg = _PRESETS.get(name)
        if cfg is None:
            self._custom_frame.setVisible(True)
            return
        self._fps.setValue(cfg["fps"])
        crf = cfg["crf"]
        if crf >= 26:
            self._quality.setCurrentIndex(0)
        elif crf >= 21:
            self._quality.setCurrentIndex(1)
        else:
            self._quality.setCurrentIndex(2)
        self._custom_frame.setVisible(name == "Custom")

    def _get_crf(self) -> int:
        return [28, 23, 18][self._quality.currentIndex()]

    def _apply_quality(self):
        crf = self._get_crf()
        preset = "ultrafast" if crf >= 26 else ("fast" if crf >= 21 else "slow")
        self._recorder.set_quality(crf, preset)

    def _sync_device_settings(self):
        """Push all UI settings to recorder before starting."""
        # Mic
        if self._mic_cb.isChecked() and self._audio_devices:
            self._recorder.set_audio(True)
            self._recorder.set_mic(self._mic_combo.currentText())
        else:
            self._recorder.set_audio(False)
            self._recorder.set_mic(None)
        # Camera
        if self._cam_cb.isChecked() and self._video_devices:
            self._recorder.set_camera(
                self._cam_combo.currentText(), self._cam_slider.value())
        else:
            self._recorder.set_camera(None)
        # Format, monitor, cursor, auto-stop
        self._recorder.set_output_format(self._format_cb.currentText().lower())
        self._recorder.set_monitor(self._monitor_cb.currentIndex())
        self._recorder.set_draw_mouse(self._cursor_cb.isChecked())
        if self._autostop_cb.isChecked():
            self._recorder.set_auto_stop(self._autostop_spin.value())
        else:
            self._recorder.set_auto_stop(0)

    def _start_full(self):
        self._apply_quality()
        self._sync_device_settings()
        self.hide()
        QTimer.singleShot(200, lambda: self._recorder.start_fullscreen(self._fps.value()))

    def _start_region(self):
        self._apply_quality()
        self._sync_device_settings()
        self.hide()
        QTimer.singleShot(200, lambda: self._recorder.start_region_select(self._fps.value()))

    def _start_window(self):
        self._apply_quality()
        self._sync_device_settings()
        titles = self._recorder.list_windows()
        if not titles:
            self._status.setText("⚠ No capturable windows found")
            self._status.setStyleSheet("color: #F9E2AF; font-size: 12px;")
            return
        from PyQt6.QtWidgets import QInputDialog
        title, ok = QInputDialog.getItem(
            self, "Select Window", "Pick a window to record:",
            titles, 0, False)
        if ok and title:
            self.hide()
            QTimer.singleShot(200, lambda: self._recorder.start_window(
                title, self._fps.value()))

    def _toggle_pause(self):
        self._recorder.toggle_pause()

    def _stop(self):
        self._recorder.stop()

    def _convert_gif(self):
        if self._last_path:
            self._recorder.convert_to_gif(self._last_path)
            self._status.setText("🎞 Converting to GIF...")
            self._status.setStyleSheet("color: #89B4FA; font-size: 12px;")

    def _on_started(self):
        self._btn_full.setVisible(False)
        self._btn_region.setVisible(False)
        self._btn_window.setVisible(False)
        self._btn_pause.setVisible(True)
        self._btn_stop.setVisible(True)
        self._btn_open.setVisible(False)
        self._btn_gif.setVisible(False)
        self._preset_cb.setEnabled(False)
        self._tick.start(500)
        self.show()

    def _on_paused(self, paused: bool):
        self._btn_pause.setText("▶ Resume" if paused else "⏸ Pause")

    def _on_stopped(self, path: str):
        self._last_path = path
        self._btn_full.setVisible(True)
        self._btn_region.setVisible(True)
        self._btn_window.setVisible(True)
        self._btn_pause.setVisible(False)
        self._btn_stop.setVisible(False)
        self._preset_cb.setEnabled(True)
        self._tick.stop()
        size_mb = os.path.getsize(path) / (1024 * 1024)
        dur = self._recorder.elapsed_sec
        m, s = divmod(dur, 60)
        name = os.path.basename(path)
        markers = self._recorder.markers
        marker_txt = f"  📌 {len(markers)} markers" if markers else ""
        self._status.setText(f"✅ {name}\n⏱ {m:02d}:{s:02d}  📐 {size_mb:.1f} MB{marker_txt}")
        self._status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._btn_open.setVisible(True)
        self._btn_gif.setVisible(True)
        self._refresh_history()

    def _update_status(self):
        secs = self._recorder.elapsed_sec
        m, s = divmod(secs, 60)
        h, m = divmod(m, 60)
        t = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        prefix = "⏸ Paused" if self._recorder.is_paused else "🔴 REC"
        # Live file size
        sz = ""
        if os.path.exists(self._recorder._output_path):
            try:
                sz = f"  📐 {_human_size(os.path.getsize(self._recorder._output_path))}"
            except OSError:
                pass
        self._status.setText(f"{prefix}  {t}{sz}")
        clr = "#F9E2AF" if self._recorder.is_paused else "#F38BA8"
        self._status.setStyleSheet(f"color: {clr}; font-size: 12px; font-weight: bold;")

    def _refresh_history(self):
        # Clear existing
        while self._history_area.count():
            item = self._history_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        history = self._recorder.recordings
        if not history:
            empty = QLabel("No recordings yet")
            empty.setStyleSheet("color: #45475A; font-size: 11px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._history_area.addWidget(empty)
        else:
            for info in history[:10]:
                if os.path.exists(info.get("path", "")):
                    card = _RecordingCard(info, self._recorder._ffmpeg, self)
                    card.delete_requested.connect(self._delete_recording)
                    self._history_area.addWidget(card)
        self._history_area.addStretch()

    def _delete_recording(self, path: str):
        self._recorder.delete_recording(path)
        self._refresh_history()
