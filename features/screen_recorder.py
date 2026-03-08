"""Screen Recorder — record screen area to MP4 using ffmpeg with pro features."""
import os
import sys
import time
import logging
import subprocess
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QWidget, QApplication,
)
from PyQt6.QtCore import Qt, QTimer, QRect, QPoint, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QPainter, QColor, QPen

log = logging.getLogger("toty.screen_recorder")

_OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Desktop", "TotyCatch")


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
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self._drawing:
            rect = QRect(self._origin, self._current).normalized()
            painter.setPen(QPen(QColor("#F38BA8"), 2))
            painter.setBrush(QColor(0, 0, 0, 0))
            painter.drawRect(rect)
            painter.fillRect(rect, QColor(255, 255, 255, 20))
            # Draw dimension label
            painter.setPen(QColor("#CDD6F4"))
            painter.setFont(QFont("Consolas", 10))
            painter.drawText(
                rect.adjusted(4, 4, 0, 0),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                f"{rect.width()} × {rect.height()}",
            )

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
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))
        painter.setPen(QColor("#F38BA8"))
        painter.setFont(QFont("Arial", 120, QFont.Weight.Bold))
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
    """Small always-on-top widget showing recording status."""
    stop_clicked = pyqtSignal()
    pause_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(200, 40)

        # Position top-center
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() // 2 - 100, 8)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(6)

        self._dot = QLabel("🔴")
        self._dot.setStyleSheet("font-size: 14px;")
        lay.addWidget(self._dot)

        self._time_lbl = QLabel("00:00")
        self._time_lbl.setStyleSheet(
            "color: #F38BA8; font-family: Consolas; font-size: 13px; font-weight: bold;")
        lay.addWidget(self._time_lbl)

        lay.addStretch()

        btn_css = ("QPushButton { border: none; font-size: 14px; padding: 2px 4px;"
                   "  border-radius: 4px; }"
                   "QPushButton:hover { background: rgba(255,255,255,30); }")
        self._btn_pause = QPushButton("⏸")
        self._btn_pause.setStyleSheet(btn_css)
        self._btn_pause.setFixedSize(28, 28)
        self._btn_pause.clicked.connect(self.pause_clicked.emit)
        lay.addWidget(self._btn_pause)

        self._btn_stop = QPushButton("⏹")
        self._btn_stop.setStyleSheet(btn_css)
        self._btn_stop.setFixedSize(28, 28)
        self._btn_stop.clicked.connect(self.stop_clicked.emit)
        lay.addWidget(self._btn_stop)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(30, 30, 46, 220))
        painter.setPen(QPen(QColor("#F38BA8"), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)

    def update_time(self, secs: int, paused: bool = False):
        m, s = divmod(secs, 60)
        self._time_lbl.setText(f"{m:02d}:{s:02d}")
        self._dot.setText("⏸" if paused else "🔴")
        self._btn_pause.setText("▶" if paused else "⏸")

    # Allow dragging the indicator
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
    recording_paused = pyqtSignal(bool)   # is_paused

    def __init__(self):
        super().__init__()
        self._process: subprocess.Popen | None = None
        self._recording = False
        self._paused = False
        self._output_path = ""
        self._start_time = 0.0
        self._pause_total = 0.0          # accumulated pause time
        self._pause_start = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._elapsed = 0
        self._ffmpeg = shutil.which("ffmpeg")
        self._overlay: _RegionOverlay | None = None
        self._countdown: _CountdownOverlay | None = None
        self._indicator: _FloatingIndicator | None = None
        self._audio = False
        self._pending_params: dict | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def elapsed_sec(self) -> int:
        return self._elapsed

    def has_ffmpeg(self) -> bool:
        return self._ffmpeg is not None

    def set_audio(self, enabled: bool):
        self._audio = enabled

    def start_fullscreen(self, fps: int = 15, countdown: bool = True):
        """Record the entire primary screen."""
        screen = QApplication.primaryScreen().geometry()
        self._pending_params = dict(
            x=screen.x(), y=screen.y(),
            w=screen.width(), h=screen.height(), fps=fps,
        )
        if countdown:
            self._show_countdown()
        else:
            self._start_recording(**self._pending_params)

    def start_region_select(self, fps: int = 15):
        """Show overlay to pick a region, then start recording."""
        self._pending_fps = fps
        self._overlay = _RegionOverlay()
        self._overlay.region_selected.connect(self._on_region)
        self._overlay.show()

    def _on_region(self, rect: QRect):
        self._pending_params = dict(
            x=rect.x(), y=rect.y(),
            w=rect.width(), h=rect.height(), fps=self._pending_fps,
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
        self._output_path = os.path.join(_OUTPUT_DIR, f"toty_rec_{ts}.mp4")

        # Ensure even dimensions (required by many codecs)
        w = w if w % 2 == 0 else w - 1
        h = h if h % 2 == 0 else h - 1

        cmd = [
            self._ffmpeg,
            "-f", "gdigrab",
            "-framerate", str(fps),
            "-offset_x", str(x),
            "-offset_y", str(y),
            "-video_size", f"{w}x{h}",
            "-i", "desktop",
        ]

        # Optional audio capture (Windows loopback via dshow virtual-audio-capturer)
        if self._audio:
            cmd += ["-f", "dshow", "-i", "audio=virtual-audio-capturer"]

        cmd += [
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-y",
            self._output_path,
        ]

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
            self._timer.start(1000)
            # Show floating indicator
            self._indicator = _FloatingIndicator()
            self._indicator.stop_clicked.connect(self.stop)
            self._indicator.pause_clicked.connect(self.toggle_pause)
            self._indicator.show()
            self.recording_started.emit()
            log.info("Screen recording started: %s", self._output_path)
        except Exception as e:
            log.error("Failed to start recording: %s", e)

    def toggle_pause(self):
        """Pause/resume recording via SIGSTOP/SIGCONT (Windows: suspend/resume)."""
        if not self._recording or not self._process:
            return
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1F0FFF, False, self._process.pid)
        if self._paused:
            # Resume: NtResumeProcess
            ctypes.windll.ntdll.NtResumeProcess(handle)
            self._pause_total += time.time() - self._pause_start
            self._paused = False
        else:
            # Suspend: NtSuspendProcess
            ctypes.windll.ntdll.NtSuspendProcess(handle)
            self._pause_start = time.time()
            self._paused = True
        kernel32.CloseHandle(handle)
        self.recording_paused.emit(self._paused)
        if self._indicator:
            self._indicator.update_time(self._elapsed, self._paused)

    def stop(self):
        """Stop recording and return output path."""
        if not self._recording or not self._process:
            return
        self._timer.stop()
        # If paused, resume first so ffmpeg can exit
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
        # Hide floating indicator
        if self._indicator:
            self._indicator.close()
            self._indicator = None
        path = self._output_path
        if os.path.exists(path):
            log.info("Recording saved: %s", path)
            self.recording_stopped.emit(path)
        else:
            log.warning("Recording file not found")

    def _tick(self):
        if not self._paused:
            self._elapsed = int(time.time() - self._start_time - self._pause_total)
        if self._indicator:
            self._indicator.update_time(self._elapsed, self._paused)


# ── Record dialog ────────────────────────────────────────────────────
class RecordDialog(QDialog):
    """Pro recording configuration dialog."""

    def __init__(self, recorder: ScreenRecorder, parent=None):
        super().__init__(parent)
        self._recorder = recorder
        self.setWindowTitle("🎬 Screen Recorder")
        self.setMinimumWidth(320)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("🎬 Screen Recorder")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #F38BA8;")
        layout.addWidget(title)

        if not recorder.has_ffmpeg():
            warn = QLabel("⚠️ ffmpeg not found in PATH.\n"
                          "Install ffmpeg to enable recording.")
            warn.setStyleSheet("color: #F9E2AF; font-size: 12px;")
            warn.setWordWrap(True)
            layout.addWidget(warn)
            return

        lbl_css = "color: #CDD6F4; font-size: 12px;"
        spin_css = ("QSpinBox { background: #313244; color: #CDD6F4;"
                    " border: 1px solid #45475A; border-radius: 4px; padding: 4px; }")
        combo_css = ("QComboBox { background: #313244; color: #CDD6F4;"
                     " border: 1px solid #45475A; border-radius: 4px; padding: 4px; }"
                     "QComboBox QAbstractItemView { background: #313244; color: #CDD6F4; }")
        check_css = "QCheckBox { color: #CDD6F4; font-size: 12px; }"

        # Row: FPS + Quality
        row1 = QHBoxLayout()
        fps_lbl = QLabel("FPS:")
        fps_lbl.setStyleSheet(lbl_css)
        self._fps = QSpinBox()
        self._fps.setRange(5, 60)
        self._fps.setValue(15)
        self._fps.setStyleSheet(spin_css)
        row1.addWidget(fps_lbl)
        row1.addWidget(self._fps)

        q_lbl = QLabel("Quality:")
        q_lbl.setStyleSheet(lbl_css)
        self._quality = QComboBox()
        self._quality.addItems(["Low (fast)", "Medium", "High (slow)"])
        self._quality.setCurrentIndex(1)
        self._quality.setStyleSheet(combo_css)
        row1.addWidget(q_lbl)
        row1.addWidget(self._quality)
        layout.addLayout(row1)

        # Audio toggle
        self._audio_cb = QCheckBox("🔊 Capture system audio (needs virtual-audio-capturer)")
        self._audio_cb.setStyleSheet(check_css)
        self._audio_cb.toggled.connect(lambda on: self._recorder.set_audio(on))
        layout.addWidget(self._audio_cb)

        # Status
        self._status = QLabel("Ready — choose a recording mode below")
        self._status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status)

        # Buttons
        btn_style = (
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 8px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #B4BEFE; }"
        )
        stop_style = (
            "QPushButton { background: #F38BA8; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 8px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #EBA0AC; }"
        )
        green_style = (
            "QPushButton { background: #A6E3A1; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 8px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #94E2D5; }"
        )

        self._btn_full = QPushButton("🖥️ Record Fullscreen")
        self._btn_full.setStyleSheet(btn_style)
        self._btn_full.clicked.connect(self._start_full)
        layout.addWidget(self._btn_full)

        self._btn_region = QPushButton("✂️ Record Region")
        self._btn_region.setStyleSheet(btn_style)
        self._btn_region.clicked.connect(self._start_region)
        layout.addWidget(self._btn_region)

        btn_row = QHBoxLayout()
        self._btn_pause = QPushButton("⏸ Pause")
        self._btn_pause.setStyleSheet(btn_style)
        self._btn_pause.clicked.connect(self._toggle_pause)
        self._btn_pause.setVisible(False)
        btn_row.addWidget(self._btn_pause)

        self._btn_stop = QPushButton("⏹ Stop Recording")
        self._btn_stop.setStyleSheet(stop_style)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_stop.setVisible(False)
        btn_row.addWidget(self._btn_stop)
        layout.addLayout(btn_row)

        # Open folder (shown after recording)
        self._btn_open = QPushButton("📂 Open Recordings Folder")
        self._btn_open.setStyleSheet(green_style)
        self._btn_open.clicked.connect(lambda: os.startfile(_OUTPUT_DIR))
        self._btn_open.setVisible(False)
        layout.addWidget(self._btn_open)

        # Timer for updating elapsed
        self._tick = QTimer(self)
        self._tick.timeout.connect(self._update_status)

        self._recorder.recording_started.connect(self._on_started)
        self._recorder.recording_stopped.connect(self._on_stopped)
        self._recorder.recording_paused.connect(self._on_paused)

    def _get_crf(self) -> int:
        return [28, 23, 18][self._quality.currentIndex()]

    def _start_full(self):
        self.hide()
        QTimer.singleShot(200, lambda: self._recorder.start_fullscreen(self._fps.value()))

    def _start_region(self):
        self.hide()
        QTimer.singleShot(200, lambda: self._recorder.start_region_select(self._fps.value()))

    def _toggle_pause(self):
        self._recorder.toggle_pause()

    def _stop(self):
        self._recorder.stop()

    def _on_started(self):
        self._btn_full.setVisible(False)
        self._btn_region.setVisible(False)
        self._btn_pause.setVisible(True)
        self._btn_stop.setVisible(True)
        self._btn_open.setVisible(False)
        self._tick.start(1000)
        self.show()

    def _on_paused(self, paused: bool):
        self._btn_pause.setText("▶ Resume" if paused else "⏸ Pause")

    def _on_stopped(self, path: str):
        self._btn_full.setVisible(True)
        self._btn_region.setVisible(True)
        self._btn_pause.setVisible(False)
        self._btn_stop.setVisible(False)
        self._tick.stop()
        size_mb = os.path.getsize(path) / (1024 * 1024)
        name = os.path.basename(path)
        self._status.setText(f"✅ Saved: {name} ({size_mb:.1f} MB)")
        self._status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._btn_open.setVisible(True)

    def _update_status(self):
        secs = self._recorder.elapsed_sec
        m, s = divmod(secs, 60)
        prefix = "⏸ Paused" if self._recorder.is_paused else "🔴 Recording"
        self._status.setText(f"{prefix}  {m:02d}:{s:02d}")
        clr = "#F9E2AF" if self._recorder.is_paused else "#F38BA8"
        self._status.setStyleSheet(f"color: {clr}; font-size: 12px; font-weight: bold;")
