"""
Vocal Remover — AI-powered vocal / music separation using demucs.
Splits any audio (or audio from video) into stems:
  • Vocals only  (remove the music)
  • Music only   (remove the vocals — karaoke)
  • All 4 stems  (vocals, drums, bass, other)
Similar to vocalremover.org / vocalremover.com but runs 100 % locally.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QProgressBar, QComboBox, QMessageBox, QFrame,
    QWidget, QApplication,
)

log = logging.getLogger(__name__)

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_AUDIO_EXTS = "*.mp3 *.wav *.flac *.ogg *.aac *.m4a *.wma *.opus"
_VIDEO_EXTS = "*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v"
_ALL_FILTER = (
    f"Audio Files ({_AUDIO_EXTS});;"
    f"Video Files ({_VIDEO_EXTS});;"
    "All Files (*)"
)


# ── FFmpeg discovery (needed for pre-processing video → wav) ──────
def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    candidates = [
        os.path.join(os.path.dirname(sys.executable), "Scripts", "ffmpeg.exe"),
        os.path.join(os.path.dirname(sys.executable), "ffmpeg.exe"),
        r"C:\ffmpeg\bin\ffmpeg.exe",
        os.path.expanduser(r"~\ffmpeg\bin\ffmpeg.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _find_ffprobe() -> str | None:
    found = shutil.which("ffprobe")
    if found:
        return found
    ff = _find_ffmpeg()
    if ff:
        probe = os.path.join(os.path.dirname(ff),
                             "ffprobe" + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(probe):
            return probe
    return None


def _get_duration(path: str) -> float:
    """Get media duration in seconds via ffprobe."""
    probe = _find_ffprobe()
    if not probe:
        return 0.0
    try:
        r = subprocess.run(
            [probe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, encoding="utf-8", errors="replace", timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        )
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def _check_demucs() -> tuple[bool, str]:
    """Return (ok, error_detail). Tests torch + demucs imports."""
    try:
        r = subprocess.run(
            [sys.executable, "-c",
             "import torch; import torchaudio; import demucs; print('ok')"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
            creationflags=_CREATE_NO_WINDOW,
        )
        if r.returncode == 0 and "ok" in r.stdout:
            return True, ""
        # Capture the real error
        err = (r.stderr or r.stdout or "").strip()
        # Shorten to last meaningful lines
        lines = [l for l in err.splitlines() if l.strip()]
        short = "\n".join(lines[-6:])
        return False, short
    except Exception as e:
        return False, str(e)


def _install_demucs() -> tuple[bool, str]:
    """Attempt to pip-install demucs + torch. Returns (ok, detail)."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "demucs"],
            capture_output=True, encoding="utf-8", errors="replace", timeout=300,
            creationflags=_CREATE_NO_WINDOW,
        )
        if r.returncode == 0:
            return True, ""
        return False, (r.stderr or r.stdout or "")[:500]
    except Exception as e:
        return False, str(e)


# ── Separation modes ──────────────────────────────────────────────
_MODES = [
    ("Vocals Only (remove music)",     "vocals",    "Extract just the singing voice"),
    ("Music Only (remove vocals)",      "no_vocals", "Get the instrumental / karaoke version"),
    ("All 4 Stems (vocals+drums+bass+other)", "all", "Full separation into 4 tracks"),
]


# ── Worker thread ─────────────────────────────────────────────────
class _SeparationWorker(QThread):
    """
    Runs demucs in a subprocess to separate audio stems.
    If the input is a video, ffmpeg first extracts the audio to WAV.
    """
    progress = pyqtSignal(int, str)     # percent (-1 = indeterminate), status text
    finished = pyqtSignal(bool, str)    # success?, result_path_or_error

    _VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm",
                         ".flv", ".wmv", ".m4v", ".ts", ".mpg", ".mpeg"}

    def __init__(self, input_path: str, output_dir: str, mode: str,
                 model: str = "htdemucs"):
        super().__init__()
        self._input = input_path
        self._output_dir = output_dir
        self._mode = mode           # "vocals" | "no_vocals" | "all"
        self._model = model
        self._process: subprocess.Popen | None = None
        self._cancelled = False
        self._temp_wav: str | None = None

    def run(self):
        try:
            audio_path = self._input

            # Step 1 — If video, extract audio to a temp WAV first
            ext = os.path.splitext(self._input)[1].lower()
            if ext in self._VIDEO_EXTENSIONS:
                self.progress.emit(-1, "Extracting audio from video…")
                audio_path = self._extract_audio()
                if audio_path is None:
                    return  # error already emitted

            # Step 2 — Run demucs
            self._run_demucs(audio_path)

        except Exception as e:
            self.finished.emit(False, str(e))
        finally:
            # Clean up temp file
            if self._temp_wav and os.path.isfile(self._temp_wav):
                try:
                    os.remove(self._temp_wav)
                except OSError:
                    pass

    # ── Internal helpers ──────────────────────────────────────
    def _extract_audio(self) -> str | None:
        """Convert video → temporary WAV using ffmpeg."""
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            self.finished.emit(False,
                "ffmpeg is required to extract audio from video files.\n"
                "Install from https://ffmpeg.org and add to PATH.")
            return None

        base = os.path.splitext(os.path.basename(self._input))[0]
        self._temp_wav = os.path.join(self._output_dir, f"_temp_{base}.wav")

        cmd = [ffmpeg, "-y", "-i", self._input,
               "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
               self._temp_wav]

        proc = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=600,
            creationflags=_CREATE_NO_WINDOW,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            self.finished.emit(False,
                f"Failed to extract audio from video.\n{detail[:500]}" if detail
                else "Failed to extract audio from video.")
            return None

        return self._temp_wav

    def _run_demucs(self, audio_path: str):
        """Run the demucs model."""
        cmd = [sys.executable, "-m", "demucs"]

        if self._mode in ("vocals", "no_vocals"):
            cmd += ["--two-stems", "vocals"]

        # Use smaller segments on CPU to avoid OOM with large files
        # htdemucs max segment is 7.8s; use conservative values
        duration = _get_duration(audio_path)
        if duration > 300:          # > 5 min
            cmd += ["--segment", "5"]
        elif duration > 60:         # > 1 min
            cmd += ["--segment", "7"]

        cmd += ["-n", self._model, "-o", self._output_dir, audio_path]

        self.progress.emit(0, "AI model loading\u2026 (first run downloads ~80 MB)")
        from collections import deque
        self._output_tail = deque(maxlen=30)  # keep last 30 lines for error reporting

        # Ensure torchaudio uses soundfile backend (avoids torchcodec DLL issues)
        # Force UTF-8 IO so demucs print() doesn't crash on cp1252
        env = {**os.environ, "TORCHAUDIO_BACKEND": "soundfile",
               "PYTHONIOENCODING": "utf-8"}

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            env=env,
            creationflags=_CREATE_NO_WINDOW,
        )

        for line in iter(self._process.stdout.readline, ""):
            if self._cancelled:
                break
            line = line.strip()
            if not line:
                continue
            self._output_tail.append(line)
            # Demucs tqdm output: " 45%|\u2588\u2588\u2588     | 900/2000 [00:12<..."
            m = re.search(r"(\d+)%\|", line)
            if m:
                pct = int(m.group(1))
                self.progress.emit(min(pct, 99), f"Separating\u2026 {pct}%")
            else:
                # Show any other meaningful output
                self.progress.emit(-1, line[:90])

        self._process.wait()

        if self._cancelled:
            self.finished.emit(False, "Cancelled")
            return

        if self._process.returncode != 0:
            tail = "\n".join(self._output_tail) if self._output_tail else "(none)"
            self.finished.emit(False,
                f"Separation failed (exit code {self._process.returncode}).\n\n"
                f"Last output:\n{tail[-1500:]}")
            return

        # Locate results
        base = os.path.splitext(os.path.basename(audio_path))[0]
        result_dir = os.path.join(self._output_dir, self._model, base)

        if not os.path.isdir(result_dir):
            self.finished.emit(False, f"Output folder not found: {result_dir}")
            return

        if self._mode == "vocals":
            target = os.path.join(result_dir, "vocals.wav")
        elif self._mode == "no_vocals":
            target = os.path.join(result_dir, "no_vocals.wav")
        else:  # all
            target = result_dir  # whole folder

        if self._mode == "all":
            files = [f for f in os.listdir(result_dir) if f.endswith(".wav")]
            if files:
                self.progress.emit(100, f"Done! {len(files)} stems saved")
                self.finished.emit(True, result_dir)
            else:
                self.finished.emit(False, "No output files found.")
        elif os.path.isfile(target):
            self.progress.emit(100, "Done!")
            self.finished.emit(True, target)
        else:
            self.finished.emit(False, f"Expected output not found: {target}")

    def cancel(self):
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass


# ── Export worker (convert format / re-mux into video) ────────────
class _ExportWorker(QThread):
    """Converts a WAV stem to another format, or muxes it into the original video."""
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def __init__(self, stem_path: str, output_path: str,
                 original_video: str | None = None):
        super().__init__()
        self._stem = stem_path
        self._output = output_path
        self._video = original_video   # if set → mux audio into video
        self._process: subprocess.Popen | None = None
        self._cancelled = False

    def run(self):
        ffmpeg = _find_ffmpeg()
        if not ffmpeg:
            self.finished.emit(False, "ffmpeg is required for export.")
            return

        try:
            dur = _get_duration(self._video or self._stem)

            if self._video:
                # Re-mux: take video from original + audio from stem
                cmd = [
                    ffmpeg, "-y",
                    "-i", self._video,
                    "-i", self._stem,
                    "-map", "0:v:0",    # video from original
                    "-map", "1:a:0",    # audio from stem
                    "-c:v", "copy",     # don't re-encode video
                    "-c:a", "aac", "-b:a", "192k",
                    "-shortest",
                    self._output,
                ]
            else:
                # Audio format conversion
                ext = os.path.splitext(self._output)[1].lower()
                cmd = [ffmpeg, "-y", "-i", self._stem]
                if ext == ".mp3":
                    cmd += ["-codec:a", "libmp3lame", "-q:a", "2"]
                elif ext == ".flac":
                    cmd += ["-codec:a", "flac"]
                elif ext == ".ogg":
                    cmd += ["-codec:a", "libvorbis", "-q:a", "6"]
                elif ext == ".aac" or ext == ".m4a":
                    cmd += ["-codec:a", "aac", "-b:a", "192k"]
                else:  # wav or other
                    cmd += ["-codec:a", "pcm_s16le"]
                cmd.append(self._output)

            self.progress.emit(0, "Exporting…")

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                creationflags=_CREATE_NO_WINDOW,
            )
            for line in iter(self._process.stdout.readline, ""):
                if self._cancelled:
                    break
                m = re.search(r"time=(\d+):(\d+):([\d.]+)", line)
                if m and dur > 0:
                    secs = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                    pct = min(int(secs / dur * 100), 99)
                    self.progress.emit(pct, f"Exporting… {pct}%")

            self._process.wait()

            if self._cancelled:
                self.finished.emit(False, "Cancelled")
            elif self._process.returncode == 0:
                self.progress.emit(100, "Export done!")
                self.finished.emit(True, self._output)
            else:
                self.finished.emit(False, f"ffmpeg exited with code {self._process.returncode}")
        except Exception as e:
            self.finished.emit(False, str(e))

    def cancel(self):
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass


# ── Waveform preview widget ──────────────────────────────────────
class _WaveformPreview(QWidget):
    """Tiny animated placeholder waveform shown while processing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._bars = [0.3] * 40
        self._animating = False
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)

    def start(self):
        self._animating = True
        self._timer.start(60)

    def stop(self):
        self._animating = False
        self._timer.stop()
        self._bars = [0.3] * 40
        self.update()

    def _animate(self):
        import math
        self._tick += 1
        for i in range(len(self._bars)):
            self._bars[i] = 0.2 + 0.8 * abs(math.sin((self._tick + i * 5) * 0.08))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        bar_w = max(w / len(self._bars) - 1, 2)
        color_top = QColor("#89b4fa")
        color_bot = QColor("#cba6f7")
        for i, v in enumerate(self._bars):
            x = i * (bar_w + 1)
            bar_h = v * h * 0.9
            t = i / len(self._bars)
            c = QColor(
                int(color_top.red() * (1 - t) + color_bot.red() * t),
                int(color_top.green() * (1 - t) + color_bot.green() * t),
                int(color_top.blue() * (1 - t) + color_bot.blue() * t),
            )
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            path = QPainterPath()
            path.addRoundedRect(x, (h - bar_h) / 2, bar_w, bar_h, 2, 2)
            p.drawPath(path)
        p.end()


# ── Main Dialog ───────────────────────────────────────────────────
class VocalRemoverDialog(QDialog):
    """
    AI-powered vocal / music separator — runs locally via demucs.
    Modes:
      • Vocals only   → for extracting singing voice (remove background music)
      • Music only    → for karaoke / instrumental (remove vocals)
      • All 4 stems   → vocals, drums, bass, other
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎤 Vocal Remover")
        self.setFixedSize(530, 480)
        self.setStyleSheet(
            "QDialog { background: #1e1e2e; }"
            "QLabel { color: #cdd6f4; }"
            "QComboBox { background: #313244; color: #cdd6f4; border: 1px solid #585b70;"
            " border-radius: 6px; padding: 8px; font-size: 13px; }"
            "QComboBox QAbstractItemView { background: #313244; color: #cdd6f4;"
            " selection-background-color: #89b4fa; }"
            "QComboBox::drop-down { border: none; }"
        )
        self._worker: _SeparationWorker | _ExportWorker | None = None
        self._input_path: str | None = None
        self._is_video_input = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)

        # ── Header ──
        title = QLabel("🎤 Vocal Remover")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #cdd6f4;")
        lay.addWidget(title)

        subtitle = QLabel("Remove vocals or music from any audio — powered by AI, 100% local")
        subtitle.setStyleSheet("color: #a6adc8; font-size: 12px;")
        subtitle.setWordWrap(True)
        lay.addWidget(subtitle)

        lay.addSpacing(4)

        # ── Mode selector ──
        mode_label = QLabel("Separation mode:")
        mode_label.setStyleSheet("color: #bac2de; font-size: 12px; font-weight: bold;")
        lay.addWidget(mode_label)

        self._mode_combo = QComboBox()
        self._mode_combo.setFont(QFont("Segoe UI", 12))
        for label, _, desc in _MODES:
            self._mode_combo.addItem(label)
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        lay.addWidget(self._mode_combo)

        self._mode_desc = QLabel(_MODES[0][2])
        self._mode_desc.setStyleSheet("color: #a6adc8; font-size: 11px; margin-left: 4px;")
        lay.addWidget(self._mode_desc)

        lay.addSpacing(4)

        # ── File picker ──
        file_label = QLabel("Input file:")
        file_label.setStyleSheet("color: #bac2de; font-size: 12px; font-weight: bold;")
        lay.addWidget(file_label)

        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self._file_label = QLabel("Drop a file or click Browse…")
        self._file_label.setStyleSheet(
            "color: #a6adc8; background: #313244; border: 1px dashed #585b70;"
            " border-radius: 8px; padding: 10px; font-size: 12px;")
        self._file_label.setWordWrap(True)
        self._file_label.setMinimumHeight(44)
        file_row.addWidget(self._file_label, 1)

        btn_style = (
            "QPushButton { background: #89b4fa; color: #1e1e2e; border: none;"
            " border-radius: 8px; padding: 10px 18px; font-weight: bold; font-size: 13px; }"
            "QPushButton:hover { background: #b4d0fb; }"
            "QPushButton:disabled { background: #585b70; color: #a6adc8; }"
        )
        browse_btn = QPushButton("Browse…")
        browse_btn.setStyleSheet(btn_style)
        browse_btn.clicked.connect(self._pick_file)
        file_row.addWidget(browse_btn)
        lay.addLayout(file_row)

        # ── Waveform ──
        self._waveform = _WaveformPreview()
        lay.addWidget(self._waveform)

        # ── Progress ──
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._progress.setStyleSheet(
            "QProgressBar { background: #313244; border-radius: 6px; height: 22px;"
            " text-align: center; color: #cdd6f4; }"
            "QProgressBar::chunk { background: qlineargradient("
            "x1:0, y1:0, x2:1, y2:0, stop:0 #89b4fa, stop:1 #cba6f7);"
            " border-radius: 6px; }")
        lay.addWidget(self._progress)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self._status_label.setWordWrap(True)
        lay.addWidget(self._status_label)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._start_btn = QPushButton("▶  Separate")
        self._start_btn.setStyleSheet(btn_style)
        self._start_btn.clicked.connect(self._start)
        btn_row.addWidget(self._start_btn)

        cancel_style = btn_style.replace("#89b4fa", "#f38ba8").replace("#b4d0fb", "#f5a0b8")
        self._cancel_btn = QPushButton("✖  Cancel")
        self._cancel_btn.setStyleSheet(cancel_style)
        self._cancel_btn.setEnabled(False)
        self._cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(self._cancel_btn)

        self._open_folder_btn = QPushButton("📂  Open Output")
        self._open_folder_btn.setStyleSheet(
            btn_style.replace("#89b4fa", "#a6e3a1").replace("#b4d0fb", "#c6f0c1"))
        self._open_folder_btn.setVisible(False)
        self._open_folder_btn.clicked.connect(self._open_output_folder)
        btn_row.addWidget(self._open_folder_btn)

        lay.addLayout(btn_row)

        # ── Export options (shown after successful separation) ──
        self._export_frame = QFrame()
        self._export_frame.setStyleSheet(
            "QFrame { background: rgba(49,50,68,180); border: 1px solid #585b70;"
            " border-radius: 10px; }")
        self._export_frame.setVisible(False)
        export_lay = QVBoxLayout(self._export_frame)
        export_lay.setContentsMargins(12, 10, 12, 10)
        export_lay.setSpacing(6)

        export_title = QLabel("Export options:")
        export_title.setStyleSheet("color: #bac2de; font-size: 12px; font-weight: bold; border: none;")
        export_lay.addWidget(export_title)

        # Audio format row
        audio_row = QHBoxLayout()
        audio_row.setSpacing(6)
        export_btn_style = (
            "QPushButton { background: #585b70; color: #cdd6f4; border: none;"
            " border-radius: 6px; padding: 7px 14px; font-size: 12px; }"
            "QPushButton:hover { background: #89b4fa; color: #1e1e2e; }"
        )
        for fmt in ["MP3", "WAV", "FLAC", "OGG", "AAC"]:
            b = QPushButton(fmt)
            b.setStyleSheet(export_btn_style)
            b.clicked.connect(lambda _, f=fmt: self._export_audio(f))
            audio_row.addWidget(b)
        export_lay.addLayout(audio_row)

        # Video export row (only for video inputs)
        self._video_export_row = QHBoxLayout()
        self._video_export_row.setSpacing(6)
        vid_label = QLabel("Re-mux into video:")
        vid_label.setStyleSheet("color: #a6adc8; font-size: 11px; border: none;")
        self._video_export_row.addWidget(vid_label)
        video_btn_style = export_btn_style.replace("#585b70", "#45475a")
        for vfmt in ["MP4", "MKV", "MOV"]:
            b = QPushButton(f"Video {vfmt}")
            b.setStyleSheet(video_btn_style)
            b.clicked.connect(lambda _, f=vfmt: self._export_video(f))
            self._video_export_row.addWidget(b)
        self._video_export_container = QWidget()
        self._video_export_container.setStyleSheet("border: none;")
        self._video_export_container.setLayout(self._video_export_row)
        self._video_export_container.setVisible(False)
        export_lay.addWidget(self._video_export_container)

        lay.addWidget(self._export_frame)

        # ── Demucs install hint ──
        self._install_hint = QLabel("")
        self._install_hint.setStyleSheet("color: #f9e2af; font-size: 11px;")
        self._install_hint.setWordWrap(True)
        lay.addWidget(self._install_hint)

        self._install_btn = QPushButton("⬇  Install demucs now")
        self._install_btn.setStyleSheet(
            btn_style.replace("#89b4fa", "#f9e2af").replace("#1e1e2e", "#1e1e2e"))
        self._install_btn.setVisible(False)
        self._install_btn.clicked.connect(self._do_install_demucs)
        lay.addWidget(self._install_btn)

        lay.addStretch()

        self._last_output_path: str | None = None

        # Enable drag-and-drop
        self.setAcceptDrops(True)

    # ── Drag & drop ───────────────────────────────────────────
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path and os.path.isfile(path):
                self._set_file(path)

    # ── Mode changed ──────────────────────────────────────────
    def _on_mode_changed(self, idx: int):
        if 0 <= idx < len(_MODES):
            self._mode_desc.setText(_MODES[idx][2])

    # ── File selection ────────────────────────────────────────
    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select audio or video file", "", _ALL_FILTER)
        if path:
            self._set_file(path)

    def _set_file(self, path: str):
        self._input_path = path
        self._is_video_input = os.path.splitext(path)[1].lower() in {
            ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv", ".m4v"}
        name = os.path.basename(path)
        dur = _get_duration(path)
        dur_str = ""
        if dur > 0:
            m, s = divmod(int(dur), 60)
            dur_str = f"  ({m}:{s:02d})"
        self._file_label.setText(f"🎵 {name}{dur_str}")
        self._file_label.setStyleSheet(
            "color: #cdd6f4; background: #313244; border: 1px solid #89b4fa;"
            " border-radius: 8px; padding: 10px; font-size: 12px;")
        self._progress.setValue(0)
        self._status_label.setText("")
        self._open_folder_btn.setVisible(False)
        self._export_frame.setVisible(False)

    # ── Start ─────────────────────────────────────────────────
    def _start(self):
        if not self._input_path or not os.path.isfile(self._input_path):
            QMessageBox.warning(self, "No File",
                                "Please select an audio or video file first.")
            return

        # Check demucs + torch
        ok, err_detail = _check_demucs()
        if not ok:
            if "shm.dll" in err_detail or "torch" in err_detail.lower():
                hint = (
                    "\u26a0\ufe0f  <b>PyTorch is broken or missing.</b><br><br>"
                    "Fix with:<br>"
                    "<code>pip install --force-reinstall torch torchaudio</code><br><br>"
                    "If that doesn't work, install the "
                    '<a href="https://aka.ms/vs/17/release/vc_redist.x64.exe">'
                    "VC++ Redistributable</a> first.<br><br>"
                    f"<small>{err_detail[:200]}</small>"
                )
            else:
                hint = (
                    "\u26a0\ufe0f  <b>demucs</b> is not working.<br>"
                    "Click below to install, or run:<br>"
                    "<code>pip install demucs</code><br><br>"
                    f"<small>{err_detail[:200]}</small>"
                )
            self._install_hint.setText(hint)
            self._install_btn.setVisible(True)
            return

        mode = _MODES[self._mode_combo.currentIndex()][1]
        out_dir = os.path.dirname(self._input_path)

        self._worker = _SeparationWorker(self._input_path, out_dir, mode)
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._open_folder_btn.setVisible(False)
        self._install_hint.setText("")
        self._install_btn.setVisible(False)
        self._progress.setValue(0)
        self._status_label.setText("Starting…")
        self._waveform.start()

        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    # ── Slots ─────────────────────────────────────────────────
    def _on_progress(self, pct: int, status: str):
        if pct >= 0:
            self._progress.setValue(pct)
        self._status_label.setText(status)

    def _on_finished(self, success: bool, message: str):
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._waveform.stop()
        self._worker = None

        if success:
            self._progress.setValue(100)
            self._last_output_path = message
            is_dir = os.path.isdir(message)
            display = os.path.basename(message) if not is_dir else message
            self._status_label.setText(f"✅ Saved: {display}")
            self._open_folder_btn.setVisible(True)

            # Show export options
            self._export_frame.setVisible(True)
            self._video_export_container.setVisible(self._is_video_input)
            # Resize dialog to accommodate export panel
            self.setFixedSize(530, 570 if self._is_video_input else 540)

            if is_dir:
                stems = [f for f in os.listdir(message) if f.endswith(".wav")]
                QMessageBox.information(
                    self, "Separation Complete!",
                    f"4 stems saved to:\n{message}\n\n"
                    + "\n".join(f"  • {s}" for s in stems))
            else:
                QMessageBox.information(
                    self, "Separation Complete!",
                    f"Output saved to:\n{message}\n\n"
                    "Use the export options below to convert to MP3, FLAC,\n"
                    "or re-mux back into video.")
        else:
            self._status_label.setText(f"❌ {message}")
            QMessageBox.warning(self, "Separation Failed", message)

    def _cancel(self):
        if self._worker:
            self._worker.cancel()
            self._status_label.setText("Cancelling…")

    def _open_output_folder(self):
        if self._last_output_path:
            folder = (self._last_output_path
                      if os.path.isdir(self._last_output_path)
                      else os.path.dirname(self._last_output_path))
            os.startfile(folder)

    # ── Export helpers ─────────────────────────────────────────
    def _export_audio(self, fmt: str):
        """Export the last separated stem to a different audio format."""
        src = self._last_output_path
        if not src or not os.path.isfile(src):
            if src and os.path.isdir(src):
                QMessageBox.information(self, "Multi-stem",
                    "For multi-stem output, use Open Output to access\n"
                    "individual WAV files, then export each one.")
                return
            QMessageBox.warning(self, "No Output", "No stem file to export.")
            return

        ext = f".{fmt.lower()}"
        base = os.path.splitext(src)[0]
        default_name = f"{base}{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export as {fmt}", default_name,
            f"{fmt} Files (*{ext})")
        if not path:
            return

        self._run_export(_ExportWorker(src, path))

    def _export_video(self, fmt: str):
        """Re-mux the separated stem back into the original video."""
        src = self._last_output_path
        if not src or not os.path.isfile(src):
            QMessageBox.warning(self, "No Output", "No stem file to export.")
            return
        if not self._input_path:
            return

        ext = f".{fmt.lower()}"
        base = os.path.splitext(self._input_path)[0]
        mode = _MODES[self._mode_combo.currentIndex()][1]
        suffix = "_vocals" if mode == "vocals" else "_instrumental"
        default_name = f"{base}{suffix}{ext}"
        path, _ = QFileDialog.getSaveFileName(
            self, f"Export video as {fmt}", default_name,
            f"{fmt} Video (*{ext})")
        if not path:
            return

        self._run_export(_ExportWorker(src, path, original_video=self._input_path))

    def _run_export(self, worker: _ExportWorker):
        self._worker = worker
        self._start_btn.setEnabled(False)
        self._cancel_btn.setEnabled(True)
        self._progress.setValue(0)
        self._status_label.setText("Exporting…")
        self._waveform.start()
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_export_finished)
        worker.start()

    def _on_export_finished(self, success: bool, message: str):
        self._start_btn.setEnabled(True)
        self._cancel_btn.setEnabled(False)
        self._waveform.stop()
        self._worker = None

        if success:
            self._progress.setValue(100)
            self._status_label.setText(f"✅ Exported: {os.path.basename(message)}")
            QMessageBox.information(self, "Export Complete!",
                                    f"Saved to:\n{message}")
        else:
            self._status_label.setText(f"❌ {message}")
            QMessageBox.warning(self, "Export Failed", message)

    # ── Auto-install demucs ───────────────────────────────────
    def _do_install_demucs(self):
        self._install_btn.setEnabled(False)
        self._install_hint.setText("⏳ Installing demucs… this may take a minute.")
        QApplication.processEvents()

        ok, detail = _install_demucs()
        if ok:
            # Re-check if it actually works now
            ok2, err2 = _check_demucs()
            if ok2:
                self._install_hint.setText("✅ demucs installed! Click Separate to begin.")
                self._install_btn.setVisible(False)
            else:
                self._install_hint.setText(
                    f"⚠️ Installed but still broken:<br><small>{err2[:200]}</small><br>"
                    "Try: <code>pip install --force-reinstall torch torchaudio demucs</code>")
        else:
            self._install_hint.setText(
                f"❌ Installation failed:<br><small>{detail[:200]}</small><br>"
                "Try manually: <code>pip install demucs</code>")
        self._install_btn.setEnabled(True)
