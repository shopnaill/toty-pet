"""Video Downloader — Download videos from YouTube, Facebook, Instagram & more via yt-dlp."""
import os
import sys
import re
import subprocess
import logging
import json
import shutil
import threading

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QProgressBar, QFileDialog, QMessageBox,
    QApplication, QFrame, QTextEdit, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPixmap, QImage

log = logging.getLogger("toty.video_downloader")

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"
_YELLOW = "#F9E2AF"

_SS = f"""
QDialog {{ background: {_BG}; }}
QLineEdit {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 12px; font-size: 13px;
}}
QLineEdit:focus {{ border-color: {_BLUE}; }}
QPushButton {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background: #45475A; border-color: {_BLUE}; }}
QPushButton:pressed {{ background: {_BLUE}; color: {_BG}; }}
QPushButton:disabled {{ background: #181825; color: #585B70; border-color: #313244; }}
QLabel {{ color: {_TEXT}; }}
QComboBox {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 6px 10px; font-size: 13px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {_SURFACE}; color: {_TEXT}; selection-background-color: #45475A;
}}
QProgressBar {{
    background: {_SURFACE}; border: 1px solid #45475A; border-radius: 6px;
    text-align: center; color: {_TEXT}; font-size: 12px; min-height: 22px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, x2:1, stop:0 {_BLUE}, stop:1 {_GREEN});
    border-radius: 5px;
}}
QTextEdit {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 6px; font-size: 12px; font-family: Consolas;
}}
QCheckBox {{ color: {_TEXT}; font-size: 13px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border: 1px solid #45475A;
    border-radius: 3px; background: {_SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {_BLUE}; border-color: {_BLUE};
}}
"""

# ── yt-dlp availability ──────────────────────────────────────────────

def _find_ytdlp() -> str | None:
    """Find yt-dlp executable."""
    found = shutil.which("yt-dlp")
    if found:
        return found
    # Check common pip install locations (system + user)
    candidates = [
        os.path.join(os.path.dirname(sys.executable), "Scripts", "yt-dlp.exe"),
        os.path.join(os.environ.get("APPDATA", ""), "Python",
                     f"Python{sys.version_info.major}{sys.version_info.minor}",
                     "Scripts", "yt-dlp.exe"),
        os.path.expanduser(r"~\AppData\Local\Programs\Python\Python%d%d\Scripts\yt-dlp.exe"
                           % (sys.version_info.major, sys.version_info.minor)),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return None


def _ensure_ytdlp() -> bool:
    """Install yt-dlp via pip if missing. Returns True if available."""
    if _find_ytdlp():
        return True
    try:
        log.info("yt-dlp not found, installing via pip...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "yt-dlp"],
            capture_output=True, text=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return r.returncode == 0 and _find_ytdlp() is not None
    except Exception as e:
        log.warning("Failed to install yt-dlp: %s", e)
        return False


# ── Probe worker ─────────────────────────────────────────────────────

class _ProbeWorker(QThread):
    """Fetch video info (title, formats, thumbnail) in background."""
    finished = pyqtSignal(dict)   # {"ok": True, "info": {...}} or {"ok": False, "error": "..."}

    def __init__(self, url: str, ytdlp_path: str):
        super().__init__()
        self._url = url
        self._ytdlp = ytdlp_path

    def run(self):
        try:
            r = subprocess.run(
                [self._ytdlp, "--no-download", "--dump-json",
                 "--no-playlist", "--no-warnings", self._url],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode != 0:
                self.finished.emit({"ok": False, "error": r.stderr.strip()[:300] or "Unknown error"})
                return
            info = json.loads(r.stdout)
            self.finished.emit({"ok": True, "info": info})
        except json.JSONDecodeError:
            self.finished.emit({"ok": False, "error": "Could not parse video info"})
        except subprocess.TimeoutExpired:
            self.finished.emit({"ok": False, "error": "Timed out fetching video info"})
        except Exception as e:
            self.finished.emit({"ok": False, "error": str(e)[:300]})


# ── Download worker ──────────────────────────────────────────────────

class _DownloadWorker(QThread):
    """Download a video with progress reporting."""
    progress = pyqtSignal(float, str)       # percent (0-100), status text
    finished = pyqtSignal(bool, str)         # success, message/filepath

    def __init__(self, url: str, ytdlp_path: str, output_dir: str,
                 format_id: str = "", audio_only: bool = False):
        super().__init__()
        self._url = url
        self._ytdlp = ytdlp_path
        self._output_dir = output_dir
        self._format_id = format_id
        self._audio_only = audio_only
        self._process: subprocess.Popen | None = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass

    def run(self):
        try:
            tmpl = os.path.join(self._output_dir, "%(title).80s.%(ext)s")
            cmd = [
                self._ytdlp,
                "--newline",              # one progress line per update
                "--no-playlist",
                "--no-warnings",
                "-o", tmpl,
            ]
            if self._audio_only:
                cmd += ["-x", "--audio-format", "mp3"]
            elif self._format_id:
                cmd += ["-f", self._format_id]
            else:
                # Best video+audio merged
                cmd += ["-f", "bv*+ba/b"]

            # Prefer ffmpeg for merging if available
            ffmpeg = shutil.which("ffmpeg")
            if ffmpeg:
                cmd += ["--ffmpeg-location", os.path.dirname(ffmpeg)]

            cmd.append(self._url)

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            filepath = ""
            for line in iter(self._process.stdout.readline, ""):
                if self._cancelled:
                    break
                line = line.strip()
                if not line:
                    continue

                # Parse progress: [download]  45.2% of  120.50MiB at  5.20MiB/s ETA 00:12
                m = re.search(r'\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+\S+)', line)
                if m:
                    pct = float(m.group(1))
                    size = m.group(2)
                    # Extract speed and ETA if present
                    speed_m = re.search(r'at\s+([\d.]+\S+/s)', line)
                    eta_m = re.search(r'ETA\s+(\S+)', line)
                    status = f"{pct:.1f}% of {size}"
                    if speed_m:
                        status += f" • {speed_m.group(1)}"
                    if eta_m:
                        status += f" • ETA {eta_m.group(1)}"
                    self.progress.emit(pct, status)
                    continue

                # Destination or merge line
                if "[download] Destination:" in line:
                    filepath = line.split("Destination:", 1)[1].strip()
                elif "[Merger] Merging formats into" in line:
                    filepath = line.split("into ", 1)[1].strip().strip('"')
                elif line.startswith("[download] ") and "has already been downloaded" in line:
                    filepath = line.replace("[download] ", "").split(" has already")[0].strip()
                    self.progress.emit(100, "Already downloaded")

            self._process.wait()

            if self._cancelled:
                self.finished.emit(False, "Download cancelled")
                return

            if self._process.returncode == 0:
                self.progress.emit(100, "Complete!")
                self.finished.emit(True, filepath or self._output_dir)
            else:
                self.finished.emit(False, "Download failed (exit code %d)" % self._process.returncode)

        except Exception as e:
            self.finished.emit(False, str(e)[:300])


# ── Thumbnail loader ─────────────────────────────────────────────────

class _ThumbLoader(QThread):
    """Download a thumbnail image in background."""
    loaded = pyqtSignal(QPixmap)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            import urllib.request
            req = urllib.request.Request(self._url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
            pix = QPixmap()
            pix.loadFromData(data)
            if not pix.isNull():
                self.loaded.emit(pix)
        except Exception:
            pass


# ── Main dialog ──────────────────────────────────────────────────────

class VideoDownloaderDialog(QDialog):
    """Download videos from YouTube, Facebook, Instagram & more."""

    def __init__(self, parent=None, prefill_url: str = ""):
        super().__init__(parent)
        self.setWindowTitle("⬇️ Video Downloader")
        self.setFixedSize(520, 600)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)

        self._prefill_url = prefill_url
        self._ytdlp_path: str | None = None
        self._video_info: dict | None = None
        self._probe_worker: _ProbeWorker | None = None
        self._dl_worker: _DownloadWorker | None = None
        self._thumb_loader: _ThumbLoader | None = None
        self._output_dir = os.path.join(os.path.expanduser("~"), "Downloads")

        self._build_ui()
        self._check_ytdlp()

        # Auto-fill and fetch if URL was provided
        if self._prefill_url:
            self._url_input.setText(self._prefill_url)
            QTimer.singleShot(500, self._auto_fetch_when_ready)

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # Title
        title = QLabel("⬇️ Video Downloader")
        title.setFont(QFont("Arial", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE};")
        lay.addWidget(title)

        sub = QLabel("YouTube • Facebook • Instagram • Twitter/X • TikTok & more")
        sub.setStyleSheet(f"color: #A6ADC8; font-size: 12px;")
        lay.addWidget(sub)

        # Status bar for yt-dlp
        self._status_label = QLabel("Checking yt-dlp...")
        self._status_label.setStyleSheet(f"color: {_YELLOW}; font-size: 12px;")
        lay.addWidget(self._status_label)

        # URL input row
        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("Paste video URL here…")
        self._url_input.returnPressed.connect(self._fetch_info)
        url_row.addWidget(self._url_input, 1)

        self._btn_fetch = QPushButton("🔍 Fetch")
        self._btn_fetch.setStyleSheet(
            f"QPushButton {{ background: {_BLUE}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 8px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #B4D0FB; }}"
            f"QPushButton:disabled {{ background: #181825; color: #585B70; }}")
        self._btn_fetch.clicked.connect(self._fetch_info)
        url_row.addWidget(self._btn_fetch)
        lay.addLayout(url_row)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: #45475A;")
        sep.setFixedHeight(1)
        lay.addWidget(sep)

        # Video info area
        info_row = QHBoxLayout()
        info_row.setSpacing(10)

        self._thumb_label = QLabel()
        self._thumb_label.setFixedSize(160, 90)
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setStyleSheet(
            f"background: {_SURFACE}; border: 1px solid #45475A; border-radius: 6px;")
        self._thumb_label.setText("🎬")
        info_row.addWidget(self._thumb_label)

        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        self._title_label = QLabel("No video loaded")
        self._title_label.setWordWrap(True)
        self._title_label.setStyleSheet(f"color: {_TEXT}; font-size: 13px; font-weight: bold;")
        self._title_label.setMaximumHeight(50)
        info_col.addWidget(self._title_label)

        self._meta_label = QLabel("")
        self._meta_label.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        info_col.addWidget(self._meta_label)
        info_col.addStretch()
        info_row.addLayout(info_col, 1)
        lay.addLayout(info_row)

        # Format / quality selector
        fmt_row = QHBoxLayout()
        fmt_row.setSpacing(8)
        fmt_row.addWidget(QLabel("Quality:"))

        self._quality_combo = QComboBox()
        self._quality_combo.setMinimumWidth(260)
        self._quality_combo.addItem("Best available", "best")
        fmt_row.addWidget(self._quality_combo, 1)
        lay.addLayout(fmt_row)

        # Audio-only checkbox
        self._audio_only = QCheckBox("🎵 Audio only (MP3)")
        lay.addWidget(self._audio_only)

        # Output directory
        dir_row = QHBoxLayout()
        dir_row.setSpacing(6)
        dir_row.addWidget(QLabel("Save to:"))
        self._dir_label = QLineEdit(self._output_dir)
        self._dir_label.setReadOnly(True)
        dir_row.addWidget(self._dir_label, 1)
        btn_browse = QPushButton("📁")
        btn_browse.setFixedWidth(40)
        btn_browse.clicked.connect(self._pick_dir)
        dir_row.addWidget(btn_browse)
        lay.addLayout(dir_row)

        # Download button
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_download = QPushButton("⬇️ Download")
        self._btn_download.setEnabled(False)
        self._btn_download.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 10px 24px; font-weight: bold; font-size: 14px; }}"
            f"QPushButton:hover {{ background: #C6F3C1; }}"
            f"QPushButton:disabled {{ background: #181825; color: #585B70; }}")
        self._btn_download.clicked.connect(self._start_download)
        btn_row.addWidget(self._btn_download, 1)

        self._btn_cancel = QPushButton("✖ Cancel")
        self._btn_cancel.setVisible(False)
        self._btn_cancel.setStyleSheet(
            f"QPushButton {{ background: {_RED}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 10px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #F5A0B8; }}")
        self._btn_cancel.clicked.connect(self._cancel_download)
        btn_row.addWidget(self._btn_cancel)
        lay.addLayout(btn_row)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        lay.addWidget(self._progress)

        # Progress detail text
        self._progress_text = QLabel("")
        self._progress_text.setStyleSheet("color: #A6ADC8; font-size: 12px;")
        self._progress_text.setVisible(False)
        lay.addWidget(self._progress_text)

        # Open folder button (shown after download)
        self._btn_open_folder = QPushButton("📂 Open Download Folder")
        self._btn_open_folder.setVisible(False)
        self._btn_open_folder.clicked.connect(self._open_folder)
        lay.addWidget(self._btn_open_folder)

        lay.addStretch()

    # ── yt-dlp check ──────────────────────────────────────────────────

    def _check_ytdlp(self):
        """Check if yt-dlp is available, install if not."""
        self._ytdlp_path = _find_ytdlp()
        if self._ytdlp_path:
            self._status_label.setText(f"✅ yt-dlp ready")
            self._status_label.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            return

        self._status_label.setText("⏳ Installing yt-dlp (first time only)...")
        self._status_label.setStyleSheet(f"color: {_YELLOW}; font-size: 12px;")
        self._btn_fetch.setEnabled(False)

        def _install():
            ok = _ensure_ytdlp()
            QTimer.singleShot(0, lambda: self._on_ytdlp_installed(ok))

        threading.Thread(target=_install, daemon=True).start()

    def _on_ytdlp_installed(self, ok: bool):
        if ok:
            self._ytdlp_path = _find_ytdlp()
            self._status_label.setText("✅ yt-dlp installed & ready")
            self._status_label.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            self._btn_fetch.setEnabled(True)
        else:
            self._status_label.setText("❌ Failed to install yt-dlp. Install manually: pip install yt-dlp")
            self._status_label.setStyleSheet(f"color: {_RED}; font-size: 12px;")

    # ── Fetch info ────────────────────────────────────────────────────

    def _fetch_info(self):
        url = self._url_input.text().strip()
        if not url:
            return

        if not self._ytdlp_path:
            QMessageBox.warning(self, "Error", "yt-dlp is not available.")
            return

        self._btn_fetch.setEnabled(False)
        self._btn_download.setEnabled(False)
        self._status_label.setText("⏳ Fetching video info...")
        self._status_label.setStyleSheet(f"color: {_YELLOW}; font-size: 12px;")
        self._title_label.setText("Loading...")
        self._meta_label.setText("")
        self._thumb_label.setText("⏳")
        self._video_info = None

        self._probe_worker = _ProbeWorker(url, self._ytdlp_path)
        self._probe_worker.finished.connect(self._on_info_fetched)
        self._probe_worker.start()

    def _on_info_fetched(self, result: dict):
        self._btn_fetch.setEnabled(True)

        if not result["ok"]:
            self._status_label.setText(f"❌ {result['error'][:120]}")
            self._status_label.setStyleSheet(f"color: {_RED}; font-size: 12px;")
            self._title_label.setText("Failed to load video")
            return

        info = result["info"]
        self._video_info = info

        # Title
        self._title_label.setText(info.get("title", "Unknown")[:120])

        # Meta
        duration = info.get("duration")
        uploader = info.get("uploader", "")
        ext = info.get("ext", "?")
        meta_parts = []
        if uploader:
            meta_parts.append(uploader)
        if duration:
            m, s = divmod(int(duration), 60)
            h, m = divmod(m, 60)
            meta_parts.append(f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")
        meta_parts.append(info.get("extractor", "").title())
        self._meta_label.setText(" • ".join(meta_parts))

        # Thumbnail
        thumb = info.get("thumbnail")
        if thumb:
            self._thumb_loader = _ThumbLoader(thumb)
            self._thumb_loader.loaded.connect(self._on_thumb_loaded)
            self._thumb_loader.start()
        else:
            self._thumb_label.setText("🎬")

        # Populate quality options
        self._quality_combo.clear()
        self._quality_combo.addItem("🏆 Best video+audio", "bv*+ba/b")

        formats = info.get("formats", [])
        # Collect unique resolutions with video
        seen = set()
        for f in reversed(formats):
            h = f.get("height")
            vcodec = f.get("vcodec", "none")
            if not h or vcodec == "none":
                continue
            label = f"{h}p"
            if label in seen:
                continue
            seen.add(label)
            # Build format selector for this height
            fid = f"bv*[height<={h}]+ba/b[height<={h}]`"
            self._quality_combo.addItem(f"📺 {label}", f"bv*[height<={h}]+ba/b[height<={h}]")

        self._quality_combo.addItem("🔊 Audio only (best)", "ba/b")

        self._status_label.setText(f"✅ Ready to download")
        self._status_label.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
        self._btn_download.setEnabled(True)

    def _on_thumb_loaded(self, pix: QPixmap):
        scaled = pix.scaled(
            self._thumb_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self._thumb_label.setPixmap(scaled)

    # ── Download ──────────────────────────────────────────────────────

    def _start_download(self):
        url = self._url_input.text().strip()
        if not url or not self._ytdlp_path:
            return

        fmt = self._quality_combo.currentData() or "bv*+ba/b"
        audio_only = self._audio_only.isChecked()

        self._btn_download.setEnabled(False)
        self._btn_fetch.setEnabled(False)
        self._btn_cancel.setVisible(True)
        self._btn_open_folder.setVisible(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._progress_text.setVisible(True)
        self._progress_text.setText("Starting download...")
        self._status_label.setText("⬇️ Downloading...")
        self._status_label.setStyleSheet(f"color: {_BLUE}; font-size: 12px;")

        self._dl_worker = _DownloadWorker(
            url, self._ytdlp_path, self._output_dir,
            format_id=fmt, audio_only=audio_only)
        self._dl_worker.progress.connect(self._on_dl_progress)
        self._dl_worker.finished.connect(self._on_dl_finished)
        self._dl_worker.start()

    def _on_dl_progress(self, pct: float, status: str):
        self._progress.setValue(int(pct))
        self._progress_text.setText(status)

    def _on_dl_finished(self, ok: bool, msg: str):
        self._btn_cancel.setVisible(False)
        self._btn_fetch.setEnabled(True)

        if ok:
            self._progress.setValue(100)
            self._status_label.setText("✅ Download complete!")
            self._status_label.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            self._progress_text.setText(os.path.basename(msg) if os.path.isfile(msg) else "Done")
            self._btn_open_folder.setVisible(True)
            self._btn_download.setEnabled(True)
        else:
            self._status_label.setText(f"❌ {msg[:120]}")
            self._status_label.setStyleSheet(f"color: {_RED}; font-size: 12px;")
            self._progress_text.setText("Failed")
            self._btn_download.setEnabled(True)

    def _cancel_download(self):
        if self._dl_worker:
            self._dl_worker.cancel()
        self._btn_cancel.setVisible(False)
        self._status_label.setText("⚠️ Cancelled")
        self._status_label.setStyleSheet(f"color: {_YELLOW}; font-size: 12px;")

    # ── Helpers ───────────────────────────────────────────────────────

    def _auto_fetch_when_ready(self):
        """Auto-fetch info once yt-dlp is ready (for prefilled URLs)."""
        if self._ytdlp_path:
            self._fetch_info()
        else:
            # Retry in 1s if still installing
            QTimer.singleShot(1000, self._auto_fetch_when_ready)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Select Download Folder", self._output_dir)
        if d:
            self._output_dir = d
            self._dir_label.setText(d)

    def _open_folder(self):
        os.startfile(self._output_dir)

    def closeEvent(self, ev):
        if self._dl_worker and self._dl_worker.isRunning():
            reply = QMessageBox.question(
                self, "Download in progress",
                "A download is still running. Cancel it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                ev.ignore()
                return
            self._dl_worker.cancel()
            self._dl_worker.wait(3000)
        super().closeEvent(ev)
