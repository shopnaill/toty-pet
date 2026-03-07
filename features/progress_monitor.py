"""Real-time progress monitoring for downloads and Windows operations.

Monitors:
  1. Browser downloads (Chrome/Edge .crdownload, Firefox .part, etc.)
  2. Windows progress-bar dialogs (file copy, installers, updates)
Emits signals when progress updates or an item finishes.
"""

import ctypes
import ctypes.wintypes as wintypes
import logging
import os
import time
from pathlib import Path

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

log = logging.getLogger("toty.progress")

# ── Windows API constants & setup ──────────────────────────────
PBM_GETPOS = 0x0408
PBM_GETRANGE = 0x0407

user32 = ctypes.windll.user32
user32.FindWindowExW.argtypes = [
    wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
]
user32.FindWindowExW.restype = wintypes.HWND
user32.SendMessageW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
]
user32.SendMessageW.restype = ctypes.c_long
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL

PARTIAL_EXTENSIONS = {".crdownload", ".part", ".partial", ".download"}
DOWNLOADS_DIR = Path(os.environ.get("USERPROFILE", "")) / "Downloads"

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


# ── Helpers ────────────────────────────────────────────────────
def _get_window_text(hwnd):
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _find_child_progress_bars(hwnd):
    """Return list of percent values from msctls_progress32 children."""
    bars = []
    child = user32.FindWindowExW(hwnd, None, "msctls_progress32", None)
    while child:
        pos = user32.SendMessageW(child, PBM_GETPOS, 0, 0)
        range_hi = user32.SendMessageW(child, PBM_GETRANGE, 0, 0)
        if range_hi > 0:
            percent = round(pos / range_hi * 100, 1)
            bars.append(percent)
        child = user32.FindWindowExW(hwnd, child, "msctls_progress32", None)
    return bars


def _format_speed(bps):
    """Human-readable bytes/sec string."""
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    elif bps < 1024 * 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} MB/s"
    return f"{bps / (1024 * 1024 * 1024):.2f} GB/s"


def _format_size(size_bytes):
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# ── Background scanner ────────────────────────────────────────
class _ProgressScanner(QObject):
    """Runs on a background QThread. Scans for active progress items."""

    updated = pyqtSignal(list)           # list of item dicts
    item_started = pyqtSignal(str)       # display name
    item_finished = pyqtSignal(str, str) # display name, detail

    def __init__(self):
        super().__init__()
        self._tracked_downloads: dict[str, dict] = {}
        self._tracked_windows: dict[int, dict] = {}
        self._finished_paths: set[str] = set()

    # ── main scan entry point ──
    def scan(self):
        items = []
        try:
            items.extend(self._scan_downloads())
        except Exception as exc:
            log.debug("Download scan error: %s", exc)
        try:
            items.extend(self._scan_windows())
        except Exception as exc:
            log.debug("Window progress scan error: %s", exc)
        self.updated.emit(items)

    # ── downloads ──
    def _scan_downloads(self):
        items = []
        if not DOWNLOADS_DIR.exists():
            return items

        current = set()
        for f in DOWNLOADS_DIR.iterdir():
            if f.suffix.lower() not in PARTIAL_EXTENSIONS or not f.is_file():
                continue
            path_str = str(f)
            current.add(path_str)
            try:
                size = f.stat().st_size
            except OSError:
                continue

            now = time.monotonic()
            if path_str not in self._tracked_downloads:
                self._tracked_downloads[path_str] = {
                    "first_seen": now,
                    "last_size": size,
                    "last_time": now,
                    "prev_size": 0,
                    "prev_time": now,
                }
                display = f.stem[:45]
                log.info("Download started: %s", display)
                self.item_started.emit(display)

            info = self._tracked_downloads[path_str]
            dt = now - info["last_time"]
            speed = 0.0
            if dt > 0.5:
                speed = (size - info["last_size"]) / dt
                info["prev_size"] = info["last_size"]
                info["prev_time"] = info["last_time"]
                info["last_size"] = size
                info["last_time"] = now
            elif info["last_time"] != info["prev_time"]:
                dt2 = info["last_time"] - info["prev_time"]
                if dt2 > 0:
                    speed = (info["last_size"] - info["prev_size"]) / dt2

            display_name = f.stem
            if len(display_name) > 40:
                display_name = display_name[:37] + "..."
            items.append({
                "name": display_name,
                "percent": -1,
                "speed": max(0.0, speed),
                "size": size,
                "source": "download",
            })

        # Detect finished downloads
        for path_str in list(self._tracked_downloads):
            if path_str not in current:
                self._tracked_downloads.pop(path_str)
                if path_str not in self._finished_paths:
                    self._finished_paths.add(path_str)
                    p = Path(path_str)
                    final = p.stem  # e.g. "file.zip" from "file.zip.crdownload"
                    self.item_finished.emit(final, str(p.parent))
                    log.info("Download finished: %s", final)

        if len(self._finished_paths) > 200:
            self._finished_paths.clear()
        return items

    # ── windows progress bars ──
    def _scan_windows(self):
        items = []
        found: set[int] = set()

        def _enum_cb(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            bars = _find_child_progress_bars(hwnd)
            if not bars:
                return True
            title = _get_window_text(hwnd)
            if not title or title.startswith("Toty"):
                return True

            percent = max(bars)
            found.add(hwnd)
            prev = self._tracked_windows.get(hwnd)

            if percent > 0 or not prev:
                self._tracked_windows[hwnd] = {
                    "title": title,
                    "last_percent": percent,
                    "last_seen": time.monotonic(),
                }

            # Only show if truly progressing
            if percent > 0:
                display = title if len(title) <= 45 else title[:42] + "..."
                items.append({
                    "name": display,
                    "percent": percent,
                    "speed": None,
                    "size": None,
                    "source": "system",
                })

            # Was it just completed?
            if prev and prev["last_percent"] < 100 and percent >= 100:
                self.item_finished.emit(title, "")
                log.info("System progress complete: %s", title)
            return True

        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)

        # Prune stale entries
        now = time.monotonic()
        for hwnd in list(self._tracked_windows):
            if hwnd not in found and now - self._tracked_windows[hwnd]["last_seen"] > 6:
                self._tracked_windows.pop(hwnd)

        return items


# ── Public orchestrator ────────────────────────────────────────
class ProgressMonitor(QObject):
    """High-level API used by DesktopPet.  Polls every *interval_ms*."""

    updated = pyqtSignal(list)            # list of progress dicts
    item_started = pyqtSignal(str)        # display name
    item_finished = pyqtSignal(str, str)  # display name, detail

    def __init__(self, parent=None, interval_ms=2000):
        super().__init__(parent)
        self._thread = QThread()
        self._scanner = _ProgressScanner()
        self._scanner.moveToThread(self._thread)
        self._scanner.updated.connect(self.updated)
        self._scanner.item_started.connect(self.item_started)
        self._scanner.item_finished.connect(self.item_finished)
        self._thread.start()

        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self._request_scan)
        self._timer.start()

    def _request_scan(self):
        QTimer.singleShot(0, self._scanner.scan)

    def stop(self):
        self._timer.stop()
        self._thread.quit()
        self._thread.wait(2000)
