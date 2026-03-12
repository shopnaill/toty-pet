"""
Toty Auto-Updater — checks GitHub releases for new versions.

Uses the GitHub Releases API (no auth required for public repos).
Downloads the installer and optionally launches it.
"""

import json
import logging
import os
import re
import tempfile
import urllib.request
import urllib.error
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QMessageBox,
)

log = logging.getLogger("toty.updater")

# ── Config ────────────────────────────────────────────────────────
GITHUB_OWNER = "mfoud5391"
GITHUB_REPO = "toty"
RELEASES_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
USER_AGENT = "Toty-Desktop-Pet-Updater/1.0"


# ── Version comparison ────────────────────────────────────────────
def _parse_version(v: str) -> tuple[int, ...]:
    """Parse '15.0.0' → (15, 0, 0)."""
    nums = re.findall(r"\d+", v)
    return tuple(int(n) for n in nums)


def is_newer(remote: str, local: str) -> bool:
    return _parse_version(remote) > _parse_version(local)


# ── Check worker ──────────────────────────────────────────────────
class _CheckWorker(QThread):
    """Background check for latest GitHub release."""
    result = pyqtSignal(dict)   # {"tag": ..., "url": ..., "notes": ..., "size": ...}
    error = pyqtSignal(str)

    def run(self):
        try:
            req = urllib.request.Request(RELEASES_URL, headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            })
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            tag = data.get("tag_name", "").lstrip("vV")
            body = data.get("body", "") or ""
            assets = data.get("assets", [])

            # Find the .exe installer asset
            dl_url = ""
            dl_size = 0
            for asset in assets:
                name = asset.get("name", "").lower()
                if name.endswith(".exe") and "setup" in name or "install" in name:
                    dl_url = asset.get("browser_download_url", "")
                    dl_size = asset.get("size", 0)
                    break
            # Fallback: first .exe
            if not dl_url:
                for asset in assets:
                    if asset.get("name", "").lower().endswith(".exe"):
                        dl_url = asset.get("browser_download_url", "")
                        dl_size = asset.get("size", 0)
                        break

            self.result.emit({
                "tag": tag,
                "url": dl_url,
                "notes": body[:1000],
                "size": dl_size,
                "html_url": data.get("html_url", ""),
            })
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.error.emit("no_releases")
            else:
                self.error.emit(f"HTTP Error {e.code}: {e.reason}")
        except Exception as e:
            self.error.emit(str(e))


# ── Download worker ───────────────────────────────────────────────
class _DownloadWorker(QThread):
    """Download an installer file with progress."""
    progress = pyqtSignal(int)      # percent
    finished = pyqtSignal(str)      # path to downloaded file
    error = pyqtSignal(str)

    def __init__(self, url: str, dest: str):
        super().__init__()
        self._url = url
        self._dest = dest

    def run(self):
        try:
            req = urllib.request.Request(self._url, headers={
                "User-Agent": USER_AGENT,
            })
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(self._dest, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            self.progress.emit(int(downloaded / total * 100))
            self.finished.emit(self._dest)
        except Exception as e:
            self.error.emit(str(e))


# ── Update dialog ─────────────────────────────────────────────────
class UpdateDialog(QDialog):
    """Check for updates and optionally download + install."""

    def __init__(self, current_version: str, parent=None):
        super().__init__(parent)
        self._current = current_version
        self._dl_worker = None
        self._release = None

        try:
            from features.theme import C
            self._C = C
        except Exception:
            class _Fallback:
                ACCENT = "#4ADE80"; BG_DEEP = "#070B09"; TEXT = "#D1D5DB"
                TEXT_DIM = "#6B7280"; TEXT_BRIGHT = "#FFFFFF"; BG_CARD = "#131C17"
                SURFACE = "#1E2B23"; BORDER = "#1C3A2A"; ACCENT_DIM = "#1A4D32"
                RED = "#F87171"; AMBER = "#FBBF24"
            self._C = _Fallback

        self.setWindowTitle("Toty Updater")
        self.setMinimumSize(420, 280)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self._setup_ui()
        self._check_update()

    def _setup_ui(self):
        C = self._C
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # Header
        hdr = QLabel("🔄  Check for Updates")
        hdr.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACCENT}; background: transparent;")
        root.addWidget(hdr)

        ver_lbl = QLabel(f"Current version: v{self._current}")
        ver_lbl.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px;")
        root.addWidget(ver_lbl)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C.BORDER};")
        root.addWidget(line)

        # Status area
        self._status = QLabel("Checking for updates…")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(f"color: {C.TEXT}; font-size: 13px;")
        root.addWidget(self._status)

        # Release notes (hidden initially)
        self._notes_label = QLabel("")
        self._notes_label.setWordWrap(True)
        self._notes_label.setStyleSheet(
            f"color: {C.TEXT_DIM}; font-size: 12px; background: {C.SURFACE};"
            f"border-radius: 6px; padding: 10px;"
        )
        self._notes_label.setVisible(False)
        root.addWidget(self._notes_label)

        # Progress bar (hidden initially)
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        root.addWidget(self._progress)

        root.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._download_btn = QPushButton("⬇ Download & Install")
        self._download_btn.setObjectName("primary")
        self._download_btn.setVisible(False)
        self._download_btn.clicked.connect(self._download_update)
        btn_row.addWidget(self._download_btn)

        self._release_btn = QPushButton("🌐 View on GitHub")
        self._release_btn.setVisible(False)
        self._release_btn.clicked.connect(self._open_release_page)
        btn_row.addWidget(self._release_btn)

        btn_row.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

    def _check_update(self):
        self._worker = _CheckWorker()
        self._worker.result.connect(self._on_check_result)
        self._worker.error.connect(self._on_check_error)
        self._worker.start()

    def _on_check_result(self, release: dict):
        tag = release.get("tag", "")
        C = self._C
        if not tag:
            self._status.setText("Could not determine the latest version.")
            return

        self._release = release

        if is_newer(tag, self._current):
            self._status.setText(
                f"<b style='color:{C.ACCENT};'>New version available: v{tag}</b>"
            )
            if release.get("notes"):
                # Truncate and show release notes
                notes = release["notes"][:500]
                if len(release["notes"]) > 500:
                    notes += "…"
                self._notes_label.setText(notes)
                self._notes_label.setVisible(True)

            if release.get("url"):
                size = release.get("size", 0)
                size_str = f" ({size / 1024 / 1024:.1f} MB)" if size else ""
                self._download_btn.setText(f"⬇ Download & Install{size_str}")
                self._download_btn.setVisible(True)

            self._release_btn.setVisible(True)
        else:
            self._status.setText(
                f"<span style='color:{C.ACCENT};'>✅ You're up to date!</span><br>"
                f"<span style='color:{C.TEXT_DIM};'>v{self._current} is the latest version.</span>"
            )

    def _on_check_error(self, err: str):
        C = self._C
        if err == "no_releases":
            self._status.setText(
                f"<span style='color:{C.ACCENT};'>✅ You're up to date!</span><br>"
                f"<span style='color:{C.TEXT_DIM};'>No releases published yet. "
                f"v{self._current} is the latest version.</span>"
            )
        else:
            self._status.setText(
                f"<span style='color:{C.RED};'>❌ Failed to check for updates</span><br>"
                f"<span style='color:{C.TEXT_DIM};'>{err}</span>"
            )

    def _download_update(self):
        if not self._release or not self._release.get("url"):
            return

        url = self._release["url"]
        fname = url.rsplit("/", 1)[-1] if "/" in url else "TotypSetup.exe"
        dest = os.path.join(tempfile.gettempdir(), fname)

        self._download_btn.setEnabled(False)
        self._download_btn.setText("Downloading…")
        self._progress.setValue(0)
        self._progress.setVisible(True)

        self._dl_worker = _DownloadWorker(url, dest)
        self._dl_worker.progress.connect(self._progress.setValue)
        self._dl_worker.finished.connect(self._on_download_done)
        self._dl_worker.error.connect(self._on_download_error)
        self._dl_worker.start()

    def _on_download_done(self, path: str):
        self._progress.setValue(100)
        self._download_btn.setText("✅ Downloaded!")

        reply = QMessageBox.question(
            self, "Install Update",
            f"Update downloaded to:\n{path}\n\n"
            "Launch the installer now?\n"
            "(Toty will close)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            import subprocess
            subprocess.Popen([path], shell=True)
            # Quit the app so the installer can replace files
            from PyQt6.QtWidgets import QApplication
            QApplication.instance().quit()

    def _on_download_error(self, err: str):
        C = self._C
        self._download_btn.setEnabled(True)
        self._download_btn.setText("⬇ Retry Download")
        self._status.setText(
            f"<span style='color:{C.RED};'>Download failed: {err}</span>"
        )

    def _open_release_page(self):
        import webbrowser
        if self._release and self._release.get("html_url"):
            webbrowser.open(self._release["html_url"])


def check_update_silent(current_version: str, callback=None):
    """Run a background update check without UI. Calls callback(release_dict) if newer."""
    worker = _CheckWorker()

    def on_result(release):
        tag = release.get("tag", "")
        if tag and is_newer(tag, current_version):
            log.info("Update available: v%s → v%s", current_version, tag)
            if callback:
                callback(release)
        else:
            log.info("Up to date: v%s", current_version)

    def on_error(err):
        log.debug("Update check failed: %s", err)

    worker.result.connect(on_result)
    worker.error.connect(on_error)
    worker.start()
    # Keep a reference so the thread isn't garbage-collected
    return worker
