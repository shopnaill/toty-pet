"""File Compressor Pro — WinRAR-like archive manager with Windows shell integration."""
import os
import sys

# When run standalone (e.g. from context menu), add project root to sys.path
# so that `from features.…` imports work.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

import re
import logging
import subprocess
import shutil
import zipfile
import tarfile
import tempfile
import winreg
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QProgressBar, QComboBox, QLineEdit, QMessageBox,
    QFrame, QTabWidget, QWidget, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QSpinBox, QApplication, QFileIconProvider,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QFileInfo
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent, QIcon
from features.auto_deps import find_7z, ensure_7z

log = logging.getLogger("toty.file_compressor")

# Assets
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
_ICON_PATH = os.path.join(_ASSETS_DIR, "toty_archive.ico")

# File icon provider (for real system icons)
_icon_provider = QFileIconProvider()

# 7z finder delegated to auto_deps
_7Z = find_7z()

def _refresh_7z():
    global _7Z
    _7Z = find_7z()
    return _7Z

# ── Constants ────────────────────────────────────────────────────────
_ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"}
_FORMATS = ["ZIP", "7Z", "TAR.GZ", "TAR.BZ2", "TAR.XZ"]
_LEVELS = ["Store", "Fast", "Normal", "Maximum", "Ultra"]
_EXT_MAP = {"ZIP": ".zip", "7Z": ".7z", "TAR.GZ": ".tar.gz",
            "TAR.BZ2": ".tar.bz2", "TAR.XZ": ".tar.xz"}
_ZIP_METHOD = {
    "Store": zipfile.ZIP_STORED, "Fast": zipfile.ZIP_DEFLATED,
    "Normal": zipfile.ZIP_DEFLATED, "Maximum": zipfile.ZIP_BZIP2,
    "Ultra": zipfile.ZIP_LZMA,
}
_7Z_MX = {"Store": 0, "Fast": 1, "Normal": 5, "Maximum": 7, "Ultra": 9}
_SPLIT_CHOICES = [
    ("No split", 0), ("10 MB", 10), ("50 MB", 50), ("100 MB", 100),
    ("250 MB", 250), ("500 MB", 500), ("1 GB", 1024),
]

# ── Helpers ──────────────────────────────────────────────────────────
def _human(b) -> str:
    b = float(b)
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"

def _total_size(paths: list[str]) -> int:
    total = 0
    for p in paths:
        if os.path.isdir(p):
            for root, _, files in os.walk(p):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
        elif os.path.isfile(p):
            total += os.path.getsize(p)
    return total

def _get_file_icon(filename: str) -> QIcon:
    """Get the system icon for a file based on its extension."""
    info = QFileInfo(filename)
    return _icon_provider.icon(info)

def _get_folder_icon() -> QIcon:
    """Get the system folder icon."""
    return _icon_provider.icon(QFileIconProvider.IconType.Folder)

def _is_archive(path: str) -> bool:
    name = path.lower()
    if name.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
        return True
    return os.path.splitext(name)[1] in _ARCHIVE_EXTS

# ── Archive entry ────────────────────────────────────────────────────
@dataclass
class _Entry:
    name: str
    size: int = 0
    packed: int = 0
    modified: str = ""
    is_dir: bool = False
    method: str = ""

# ── Archive listing ─────────────────────────────────────────────────
def _list_zip(path: str, pw: str = "") -> list[_Entry]:
    entries = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            for info in zf.infolist():
                dt = ""
                if info.date_time and info.date_time[0] >= 1980:
                    dt = datetime(*info.date_time).strftime("%Y-%m-%d %H:%M")
                entries.append(_Entry(
                    name=info.filename, size=info.file_size,
                    packed=info.compress_size, modified=dt,
                    is_dir=info.is_dir(),
                    method={0: "Store", 8: "Deflate", 12: "BZip2",
                            14: "LZMA"}.get(info.compress_type,
                                            str(info.compress_type)),
                ))
    except Exception as e:
        log.error("list_zip: %s", e)
    return entries

def _list_tar(path: str) -> list[_Entry]:
    entries = []
    try:
        with tarfile.open(path, "r:*") as tf:
            for m in tf.getmembers():
                dt = datetime.fromtimestamp(m.mtime).strftime(
                    "%Y-%m-%d %H:%M") if m.mtime else ""
                entries.append(_Entry(
                    name=m.name, size=m.size, packed=m.size,
                    modified=dt, is_dir=m.isdir(),
                ))
    except Exception as e:
        log.error("list_tar: %s", e)
    return entries

def _list_7z(path: str, pw: str = "") -> list[_Entry]:
    if not _7Z:
        return []
    cmd = [_7Z, "l", "-slt", path]
    if pw:
        cmd.append(f"-p{pw}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW,
                           timeout=30)
        if r.returncode != 0:
            return []
    except Exception:
        return []
    entries, cur = [], {}
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("----------"):
            if cur.get("Path"):
                entries.append(_Entry(
                    name=cur["Path"],
                    size=int(cur.get("Size", 0) or 0),
                    packed=int(cur.get("Packed Size", 0) or 0),
                    modified=cur.get("Modified", "")[:16],
                    is_dir=cur.get("Folder", "-") == "+",
                    method=cur.get("Method", ""),
                ))
            cur = {}
        elif "=" in line:
            k, _, v = line.partition("=")
            cur[k.strip()] = v.strip()
    if cur.get("Path"):
        entries.append(_Entry(
            name=cur["Path"],
            size=int(cur.get("Size", 0) or 0),
            packed=int(cur.get("Packed Size", 0) or 0),
            modified=cur.get("Modified", "")[:16],
            is_dir=cur.get("Folder", "-") == "+",
            method=cur.get("Method", ""),
        ))
    return entries

def _list_archive(path: str, pw: str = "") -> list[_Entry]:
    ext = path.lower()
    if ext.endswith(".zip"):
        return _list_zip(path, pw)
    if any(ext.endswith(e) for e in (".tar", ".tar.gz", ".tgz",
                                     ".tar.bz2", ".tar.xz")):
        entries = _list_tar(path)
        if not entries:
            entries = _list_7z(path, pw)
        return entries
    return _list_7z(path, pw)

# ── Test archive ─────────────────────────────────────────────────────
def _test_archive(path: str, pw: str = "") -> tuple[bool, str]:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".zip" and not pw:
        try:
            with zipfile.ZipFile(path, "r") as zf:
                bad = zf.testzip()
                if bad:
                    return False, f"Corrupt: {bad}"
            return True, "All files OK ✅"
        except Exception as e:
            return False, str(e)
    if not _7Z:
        return False, "7-Zip required to test this format"
    cmd = [_7Z, "t", path]
    if pw:
        cmd.append(f"-p{pw}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW,
                           timeout=120)
        if r.returncode == 0:
            return True, "All files OK ✅"
        return False, r.stderr[:300] or "Test failed"
    except Exception as e:
        return False, str(e)

# ── Workers ──────────────────────────────────────────────────────────
class _CompressWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, files, output, fmt="ZIP", level="Normal",
                 password="", split_mb=0):
        super().__init__()
        self._files = files
        self._output = output
        self._fmt = fmt.upper()
        self._level = level
        self._pw = password
        self._split = split_mb

    def run(self):
        try:
            if self._fmt == "ZIP" and not self._pw and self._split <= 0:
                self._zip_native()
            elif self._fmt.startswith("TAR"):
                self._tar_native()
            else:
                self._compress_7z()
        except Exception as e:
            self.error.emit(str(e))

    def _zip_native(self):
        method = _ZIP_METHOD.get(self._level, zipfile.ZIP_DEFLATED)
        all_files = self._gather_files()
        total = len(all_files)
        with zipfile.ZipFile(self._output, "w", method) as zf:
            for i, (full, arc) in enumerate(all_files):
                zf.write(full, arc)
                self.progress.emit(int((i + 1) / max(total, 1) * 100))
        self.finished.emit(self._output)

    def _tar_native(self):
        mode_map = {"TAR.GZ": "w:gz", "TAR.BZ2": "w:bz2", "TAR.XZ": "w:xz"}
        mode = mode_map.get(self._fmt, "w:gz")
        all_files = self._gather_files()
        total = len(all_files)
        with tarfile.open(self._output, mode) as tf:
            for i, (full, arc) in enumerate(all_files):
                tf.add(full, arcname=arc)
                self.progress.emit(int((i + 1) / max(total, 1) * 100))
        self.finished.emit(self._output)

    def _compress_7z(self):
        if not _7Z:
            self.error.emit(
                "7-Zip required for this format/option.\n"
                "Install 7-Zip to enable.")
            return
        type_map = {"ZIP": "zip", "7Z": "7z"}
        t = type_map.get(self._fmt, "zip")
        mx = _7Z_MX.get(self._level, 5)
        cmd = [_7Z, "a", f"-t{t}", f"-mx={mx}", "-y"]
        if self._pw:
            cmd += [f"-p{self._pw}", "-mem=AES256"]
        if self._split > 0:
            cmd.append(f"-v{self._split}m")
        cmd.append(self._output)
        cmd.extend(self._files)
        r = subprocess.run(cmd, capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode == 0:
            self.progress.emit(100)
            self.finished.emit(self._output)
        else:
            self.error.emit(r.stderr[:300] or "Compression failed")

    def _gather_files(self):
        """Return list of (full_path, arcname) pairs."""
        result = []
        for fpath in self._files:
            if os.path.isdir(fpath):
                base = os.path.dirname(fpath)
                for root, _, fnames in os.walk(fpath):
                    for fname in fnames:
                        full = os.path.join(root, fname)
                        result.append((full, os.path.relpath(full, base)))
            else:
                result.append((fpath, os.path.basename(fpath)))
        return result


class _ExtractWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, archive, output_dir, password="", files=None):
        super().__init__()
        self._archive = archive
        self._output = output_dir
        self._pw = password
        self._files = files  # None = all, list = selected names

    def run(self):
        ext = self._archive.lower()
        try:
            if ext.endswith(".zip") and not self._pw and not self._files:
                self._extract_zip()
            elif (any(ext.endswith(e) for e in (".tar", ".tar.gz", ".tgz",
                      ".tar.bz2", ".tar.xz"))
                  and not self._pw and not self._files):
                self._extract_tar()
            else:
                self._extract_7z()
        except Exception as e:
            self.error.emit(str(e))

    def _extract_zip(self):
        with zipfile.ZipFile(self._archive, "r") as zf:
            members = zf.namelist()
            total = len(members)
            for i, member in enumerate(members):
                safe = os.path.normpath(member)
                if safe.startswith("..") or os.path.isabs(safe):
                    continue
                zf.extract(member, self._output)
                self.progress.emit(int((i + 1) / max(total, 1) * 100))
        self.finished.emit(self._output)

    def _extract_tar(self):
        with tarfile.open(self._archive, "r:*") as tf:
            members = tf.getmembers()
            safe = [m for m in members
                    if not os.path.isabs(m.name)
                    and ".." not in m.name.split("/")]
            total = len(safe)
            for i, m in enumerate(safe):
                tf.extract(m, self._output, set_attrs=False)
                self.progress.emit(int((i + 1) / max(total, 1) * 100))
        self.finished.emit(self._output)

    def _extract_7z(self):
        if not _7Z:
            self.error.emit("7-Zip required to extract this format.")
            return
        cmd = [_7Z, "x", self._archive, f"-o{self._output}", "-y"]
        if self._pw:
            cmd.append(f"-p{self._pw}")
        if self._files:
            cmd.extend(self._files)
        r = subprocess.run(cmd, capture_output=True, text=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        if r.returncode == 0:
            self.progress.emit(100)
            self.finished.emit(self._output)
        else:
            msg = r.stderr[:300] or "Extraction failed"
            if "password" in msg.lower():
                msg = "Wrong password or encrypted archive."
            self.error.emit(msg)


class _TestWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, path, pw=""):
        super().__init__()
        self._path = path
        self._pw = pw

    def run(self):
        ok, msg = _test_archive(self._path, self._pw)
        self.finished.emit(ok, msg)


# ── Styles ───────────────────────────────────────────────────────────
_S = {
    "lbl":   "color: #CDD6F4; font-size: 12px;",
    "head":  "color: #F9E2AF; font-weight: bold; font-size: 12px;",
    "input": ("QLineEdit { background: #313244; color: #CDD6F4;"
              " border: 1px solid #45475A; border-radius: 6px; padding: 6px;"
              " font-size: 12px; }"
              "QLineEdit:focus { border-color: #89B4FA; }"),
    "combo": ("QComboBox { background: #313244; color: #CDD6F4;"
              " border: 1px solid #45475A; border-radius: 6px; padding: 6px; }"
              "QComboBox QAbstractItemView { background: #313244;"
              " color: #CDD6F4; }"),
    "spin":  ("QSpinBox { background: #313244; color: #CDD6F4;"
              " border: 1px solid #45475A; border-radius: 6px; padding: 6px; }"),
    "btn":   ("QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
              " border-radius: 8px; padding: 10px 16px; font-weight: bold;"
              " font-size: 12px; }"
              "QPushButton:hover { background: #B4BEFE; }"
              "QPushButton:disabled { background: #45475A; color: #6C7086; }"),
    "green": ("QPushButton { background: #A6E3A1; color: #1E1E2E; border: none;"
              " border-radius: 8px; padding: 10px 16px; font-weight: bold;"
              " font-size: 12px; }"
              "QPushButton:hover { background: #94E2D5; }"
              "QPushButton:disabled { background: #45475A; color: #6C7086; }"),
    "red":   ("QPushButton { background: #F38BA8; color: #1E1E2E; border: none;"
              " border-radius: 8px; padding: 10px 16px; font-weight: bold;"
              " font-size: 12px; }"
              "QPushButton:hover { background: #EBA0AC; }"),
    "tab":   ("QTabWidget::pane { border: 1px solid #45475A;"
              " background: #1E1E2E; border-radius: 6px; }"
              "QTabBar::tab { background: #313244; color: #CDD6F4;"
              " padding: 8px 16px; border-top-left-radius: 8px;"
              " border-top-right-radius: 8px; margin-right: 2px; }"
              "QTabBar::tab:selected { background: #45475A; color: #89B4FA; }"
              "QTabBar::tab:hover { background: #3B3C52; }"),
    "tree":  ("QTreeWidget { background: #313244; color: #CDD6F4;"
              " border: 1px solid #45475A; border-radius: 6px;"
              " font-size: 12px; }"
              "QTreeWidget::item { padding: 3px; }"
              "QTreeWidget::item:selected { background: #45475A; }"
              "QTreeWidget::item:hover { background: #3B3C52; }"
              "QHeaderView::section { background: #1E1E2E; color: #89B4FA;"
              " border: 1px solid #45475A; padding: 5px;"
              " font-weight: bold; font-size: 11px; }"),
    "prog":  ("QProgressBar { background: #313244; border: 1px solid #45475A;"
              " border-radius: 6px; height: 18px; text-align: center;"
              " color: #CDD6F4; }"
              "QProgressBar::chunk { background: #89B4FA;"
              " border-radius: 5px; }"),
}


# ── Drop zone ────────────────────────────────────────────────────────
class _DropZone(QFrame):
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(60)
        self.setStyleSheet(
            "QFrame { background: #313244; border: 2px dashed #45475A;"
            " border-radius: 10px; }")
        lay = QVBoxLayout(self)
        self._lbl = QLabel("📥 Drop files or folders here")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet("color: #6C7086; font-size: 12px; border: none;")
        lay.addWidget(self._lbl)

    def set_text(self, text: str):
        self._lbl.setText(text)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(
                "QFrame { background: #313244; border: 2px dashed #89B4FA;"
                " border-radius: 10px; }")

    def dragLeaveEvent(self, event):
        self.setStyleSheet(
            "QFrame { background: #313244; border: 2px dashed #45475A;"
            " border-radius: 10px; }")

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(
            "QFrame { background: #313244; border: 2px dashed #45475A;"
            " border-radius: 10px; }")
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.exists(p):
                paths.append(p)
        if paths:
            self.files_dropped.emit(paths)


# ═════════════════════════════════════════════════════════════════════
#  Main Dialog
# ═════════════════════════════════════════════════════════════════════
class FileCompressorDialog(QDialog):
    """Pro WinRAR-like compress & extract dialog with 3 tabs."""

    def __init__(self, parent=None, *, compress_paths=None,
                 open_archive=None, extract_here=None):
        super().__init__(parent)
        self.setWindowTitle("📦 Toty Archive Manager")
        self.setMinimumSize(540, 620)
        self.resize(560, 660)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")
        if os.path.isfile(_ICON_PATH):
            self.setWindowIcon(QIcon(_ICON_PATH))
        self._worker = None
        self._selected_files: list[str] = []
        self._original_size = 0
        self._archive_path = ""
        self._archive_entries: list[_Entry] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)

        # Title
        title = QLabel("📦 Toty Archive Manager")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #89B4FA; margin-bottom: 8px;")
        layout.addWidget(title)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_S["tab"])
        layout.addWidget(self._tabs)

        self._build_compress_tab()
        self._build_browse_tab()
        self._build_tools_tab()

        # Handle pre-loaded args
        if compress_paths:
            self._tabs.setCurrentIndex(0)
            self._update_selection(compress_paths)
        elif open_archive:
            self._tabs.setCurrentIndex(1)
            QTimer.singleShot(100, lambda: self._open_archive(open_archive))
        elif extract_here:
            self._tabs.setCurrentIndex(1)
            QTimer.singleShot(100,
                              lambda: self._quick_extract_here(extract_here))

    # ── Compress Tab ─────────────────────────────────────────────────
    def _build_compress_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lbl = QLabel("🗜️ Compress Files & Folders")
        lbl.setStyleSheet(_S["head"])
        lay.addWidget(lbl)

        # Drop zone
        self._drop = _DropZone()
        self._drop.files_dropped.connect(self._on_drop)
        lay.addWidget(self._drop)

        # Pick buttons
        row = QHBoxLayout()
        btn_f = QPushButton("📄 Select Files")
        btn_f.setStyleSheet(_S["btn"])
        btn_f.clicked.connect(self._pick_files)
        row.addWidget(btn_f)
        btn_d = QPushButton("📁 Select Folder")
        btn_d.setStyleSheet(_S["btn"])
        btn_d.clicked.connect(self._pick_folder)
        row.addWidget(btn_d)
        lay.addLayout(row)

        # Format + Level
        row2 = QHBoxLayout()
        row2.addWidget(self._styled_lbl("Format:"))
        self._fmt_combo = QComboBox()
        self._fmt_combo.addItems(_FORMATS)
        self._fmt_combo.setStyleSheet(_S["combo"])
        self._fmt_combo.currentIndexChanged.connect(self._on_format_changed)
        row2.addWidget(self._fmt_combo)
        row2.addWidget(self._styled_lbl("Level:"))
        self._lvl_combo = QComboBox()
        self._lvl_combo.addItems(_LEVELS)
        self._lvl_combo.setCurrentIndex(2)  # Normal
        self._lvl_combo.setStyleSheet(_S["combo"])
        row2.addWidget(self._lvl_combo)
        lay.addLayout(row2)

        # Password
        row3 = QHBoxLayout()
        row3.addWidget(self._styled_lbl("🔒 Password:"))
        self._c_pw = QLineEdit()
        self._c_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._c_pw.setPlaceholderText("Optional — requires 7-Zip")
        self._c_pw.setStyleSheet(_S["input"])
        row3.addWidget(self._c_pw)
        lay.addLayout(row3)

        # Split
        row4 = QHBoxLayout()
        row4.addWidget(self._styled_lbl("Split:"))
        self._split_combo = QComboBox()
        for label, _ in _SPLIT_CHOICES:
            self._split_combo.addItem(label)
        self._split_combo.setStyleSheet(_S["combo"])
        row4.addWidget(self._split_combo)
        row4.addStretch()
        lay.addLayout(row4)

        # Compress button
        self._btn_compress = QPushButton("🗜️ Compress")
        self._btn_compress.setStyleSheet(_S["btn"])
        self._btn_compress.setEnabled(False)
        self._btn_compress.clicked.connect(self._compress)
        lay.addWidget(self._btn_compress)

        # Progress + status
        self._c_prog = QProgressBar()
        self._c_prog.setVisible(False)
        self._c_prog.setStyleSheet(_S["prog"])
        lay.addWidget(self._c_prog)

        self._c_status = QLabel("")
        self._c_status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._c_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._c_status.setWordWrap(True)
        lay.addWidget(self._c_status)

        self._c_open_btn = QPushButton("📂 Open Output Folder")
        self._c_open_btn.setStyleSheet(_S["green"])
        self._c_open_btn.setVisible(False)
        lay.addWidget(self._c_open_btn)

        lay.addStretch()
        self._tabs.addTab(tab, "🗜️ Compress")
        self._on_format_changed()

    # ── Browse / Extract Tab ─────────────────────────────────────────
    def _build_browse_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        lbl = QLabel("📂 Open & Extract Archives")
        lbl.setStyleSheet(_S["head"])
        lay.addWidget(lbl)

        # Open + password
        row = QHBoxLayout()
        btn_open = QPushButton("📂 Open Archive")
        btn_open.setStyleSheet(_S["btn"])
        btn_open.clicked.connect(self._pick_archive)
        row.addWidget(btn_open)
        row.addWidget(self._styled_lbl("🔒"))
        self._b_pw = QLineEdit()
        self._b_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._b_pw.setPlaceholderText("Password (if encrypted)")
        self._b_pw.setStyleSheet(_S["input"])
        self._b_pw.setMaximumWidth(180)
        row.addWidget(self._b_pw)
        lay.addLayout(row)

        # Archive info bar
        self._b_info = QLabel("")
        self._b_info.setStyleSheet(
            "color: #89B4FA; font-size: 11px; background: #313244;"
            " border-radius: 6px; padding: 6px;")
        self._b_info.setVisible(False)
        lay.addWidget(self._b_info)

        # File table
        self._table = QTreeWidget()
        self._table.setHeaderLabels(
            ["Name", "Size", "Packed", "Ratio", "Modified"])
        self._table.setColumnCount(5)
        self._table.setRootIsDecorated(False)
        self._table.setSortingEnabled(True)
        self._table.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection)
        self._table.setStyleSheet(_S["tree"])
        self._table.setIconSize(self._table.iconSize())  # ensure icon col
        self._table.itemDoubleClicked.connect(self._open_file_from_archive)
        header = self._table.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 5):
            header.setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._table, 1)

        # Action buttons
        btn_row = QHBoxLayout()

        self._btn_open_file = QPushButton("▶️ Open File")
        self._btn_open_file.setStyleSheet(_S["btn"])
        self._btn_open_file.setEnabled(False)
        self._btn_open_file.setToolTip("Extract & open selected file")
        self._btn_open_file.clicked.connect(
            lambda: self._open_file_from_archive(
                self._table.currentItem(), 0))
        btn_row.addWidget(self._btn_open_file)

        self._btn_ext_all = QPushButton("📂 Extract All")
        self._btn_ext_all.setStyleSheet(_S["green"])
        self._btn_ext_all.setEnabled(False)
        self._btn_ext_all.clicked.connect(self._extract_all)
        btn_row.addWidget(self._btn_ext_all)

        self._btn_ext_sel = QPushButton("📋 Extract Selected")
        self._btn_ext_sel.setStyleSheet(_S["btn"])
        self._btn_ext_sel.setEnabled(False)
        self._btn_ext_sel.clicked.connect(self._extract_selected)
        btn_row.addWidget(self._btn_ext_sel)

        self._btn_test = QPushButton("🔍 Test")
        self._btn_test.setStyleSheet(_S["btn"])
        self._btn_test.setEnabled(False)
        self._btn_test.clicked.connect(self._test_archive)
        btn_row.addWidget(self._btn_test)

        self._btn_ext_here = QPushButton("📥 Here")
        self._btn_ext_here.setStyleSheet(_S["btn"])
        self._btn_ext_here.setEnabled(False)
        self._btn_ext_here.clicked.connect(self._extract_here)
        btn_row.addWidget(self._btn_ext_here)
        lay.addLayout(btn_row)

        # Progress + status
        self._b_prog = QProgressBar()
        self._b_prog.setVisible(False)
        self._b_prog.setStyleSheet(_S["prog"])
        lay.addWidget(self._b_prog)

        self._b_status = QLabel("")
        self._b_status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._b_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._b_status.setWordWrap(True)
        lay.addWidget(self._b_status)

        self._b_open_btn = QPushButton("📂 Open Output Folder")
        self._b_open_btn.setStyleSheet(_S["green"])
        self._b_open_btn.setVisible(False)
        lay.addWidget(self._b_open_btn)

        self._tabs.addTab(tab, "📂 Browse")

    # ── Tools Tab ────────────────────────────────────────────────────
    def _build_tools_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        # Context menu section
        ctx_lbl = QLabel("📋 Windows Context Menu")
        ctx_lbl.setStyleSheet(_S["head"])
        lay.addWidget(ctx_lbl)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("color: #45475A;")
        lay.addWidget(sep1)

        info = QLabel(
            "Add right-click options to Windows Explorer:\n"
            '  • "📦 Compress with Toty" on files & folders\n'
            '  • "📦 Open with Toty" on archives\n'
            '  • "📂 Extract Here" on archives\n'
            '  • "📂 Extract to..." on archives\n\n'
            "Uses HKCU registry — no admin required.")
        info.setStyleSheet("color: #BAC2DE; font-size: 11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._ctx_status = QLabel("")
        self._ctx_status.setStyleSheet("color: #CDD6F4; font-size: 12px;")
        lay.addWidget(self._ctx_status)

        btn_row = QHBoxLayout()
        self._btn_install_ctx = QPushButton("📥 Install Context Menu")
        self._btn_install_ctx.setStyleSheet(_S["green"])
        self._btn_install_ctx.clicked.connect(self._install_ctx)
        btn_row.addWidget(self._btn_install_ctx)

        self._btn_remove_ctx = QPushButton("🗑️ Remove Context Menu")
        self._btn_remove_ctx.setStyleSheet(_S["red"])
        self._btn_remove_ctx.clicked.connect(self._remove_ctx)
        btn_row.addWidget(self._btn_remove_ctx)
        lay.addLayout(btn_row)

        # 7-Zip status section
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #45475A;")
        lay.addWidget(sep2)

        sz_lbl = QLabel("🔧 7-Zip Status")
        sz_lbl.setStyleSheet(_S["head"])
        lay.addWidget(sz_lbl)

        self._sz_info = QLabel("")
        self._sz_info.setWordWrap(True)
        lay.addWidget(self._sz_info)

        self._btn_install_7z = QPushButton("📥 Install 7-Zip Now")
        self._btn_install_7z.setStyleSheet(_S["green"])
        self._btn_install_7z.clicked.connect(self._auto_install_7z)
        lay.addWidget(self._btn_install_7z)

        self._update_7z_status()

        feat_lbl = QLabel(
            "7-Zip enables:\n"
            "  • 7Z compression format\n"
            "  • AES-256 password protection\n"
            "  • RAR, CAB, ISO extraction\n"
            "  • Split/volume archives\n"
            "  • Archive integrity testing")
        feat_lbl.setStyleSheet("color: #BAC2DE; font-size: 11px;")
        feat_lbl.setWordWrap(True)
        lay.addWidget(feat_lbl)

        lay.addStretch()

        # Supported formats
        fmt_lbl = QLabel(
            "📋 Supported Formats\n"
            "  Compress: ZIP, 7Z*, TAR.GZ, TAR.BZ2, TAR.XZ\n"
            "  Extract:  ZIP, 7Z*, RAR*, TAR, GZ, BZ2, XZ\n"
            "  * Requires 7-Zip")
        fmt_lbl.setStyleSheet(
            "color: #6C7086; font-size: 10px; background: #313244;"
            " border-radius: 6px; padding: 8px;")
        lay.addWidget(fmt_lbl)

        self._tabs.addTab(tab, "⚙️ Tools")
        self._check_ctx_status()

    # ── Helpers ──────────────────────────────────────────────────────
    def _styled_lbl(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_S["lbl"])
        return lbl

    # ── Compress Tab Actions ─────────────────────────────────────────
    def _on_drop(self, paths: list[str]):
        if len(paths) == 1 and _is_archive(paths[0]):
            self._tabs.setCurrentIndex(1)
            self._open_archive(paths[0])
        else:
            self._update_selection(paths)

    def _update_selection(self, files: list[str]):
        self._selected_files = files
        self._original_size = _total_size(files)
        names = ", ".join(os.path.basename(f) for f in files[:4])
        if len(files) > 4:
            names += f" (+{len(files) - 4} more)"
        icon = "📁" if (len(files) == 1 and os.path.isdir(files[0])) else "📄"
        self._drop.set_text(
            f"{icon} {names}\n📐 {_human(self._original_size)}")
        self._btn_compress.setEnabled(True)

    def _pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select files to compress")
        if files:
            self._update_selection(files)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to compress")
        if folder:
            self._update_selection([folder])

    def _on_format_changed(self):
        fmt = self._fmt_combo.currentText().upper()
        is_tar = fmt.startswith("TAR")
        has_7z = _7Z is not None
        self._c_pw.setEnabled(not is_tar and has_7z)
        self._split_combo.setEnabled(not is_tar and has_7z)
        if is_tar:
            self._c_pw.setPlaceholderText("N/A for TAR formats")
            self._split_combo.setCurrentIndex(0)
        elif not has_7z:
            self._c_pw.setPlaceholderText("Requires 7-Zip")
        else:
            self._c_pw.setPlaceholderText("Optional — AES-256 encryption")
        if fmt == "7Z" and not has_7z:
            self._c_status.setText("⚠️ 7-Zip required for 7Z format")
            self._c_status.setStyleSheet("color: #F38BA8; font-size: 12px;")

    def _compress(self):
        if not self._selected_files:
            return
        fmt = self._fmt_combo.currentText().upper()
        if fmt == "7Z" and not _7Z:
            QMessageBox.warning(self, "7-Zip Required",
                                "Install 7-Zip to use 7Z format.")
            return
        ext = _EXT_MAP.get(fmt, ".zip")
        base_name = os.path.basename(self._selected_files[0])
        if len(self._selected_files) > 1:
            base_name = "archive"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = os.path.join(
            os.path.dirname(self._selected_files[0]),
            f"{base_name}_{ts}{ext}")
        filt = f"Archive (*{ext})"
        output, _ = QFileDialog.getSaveFileName(
            self, "Save Archive As", default_path, filt)
        if not output:
            return

        self._c_prog.setVisible(True)
        self._c_prog.setValue(0)
        self._c_status.setText("Compressing...")
        self._c_status.setStyleSheet("color: #89B4FA; font-size: 12px;")
        self._btn_compress.setEnabled(False)
        self._c_open_btn.setVisible(False)

        level = self._lvl_combo.currentText()
        pw = self._c_pw.text().strip()
        split_idx = self._split_combo.currentIndex()
        split_mb = _SPLIT_CHOICES[split_idx][1] if split_idx < len(
            _SPLIT_CHOICES) else 0

        self._worker = _CompressWorker(
            self._selected_files, output, fmt, level, pw, split_mb)
        self._worker.progress.connect(self._c_prog.setValue)
        self._worker.finished.connect(self._on_compress_done)
        self._worker.error.connect(self._on_compress_err)
        self._worker.start()

    def _on_compress_done(self, path: str):
        try:
            compressed_size = os.path.getsize(path)
        except OSError:
            compressed_size = 0
        ratio = ((1 - compressed_size / self._original_size) * 100
                 ) if self._original_size else 0
        self._c_status.setText(
            f"✅ {os.path.basename(path)}\n"
            f"📐 {_human(self._original_size)} → "
            f"{_human(compressed_size)}  ({ratio:.0f}% smaller)")
        self._c_status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._btn_compress.setEnabled(True)
        self._c_open_btn.setVisible(True)
        out_dir = os.path.dirname(path)
        try:
            self._c_open_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._c_open_btn.clicked.connect(lambda: os.startfile(out_dir))
        self._worker = None

    def _on_compress_err(self, msg: str):
        self._c_status.setText(f"❌ {msg}")
        self._c_status.setStyleSheet("color: #F38BA8; font-size: 12px;")
        self._btn_compress.setEnabled(True)
        self._c_prog.setVisible(False)
        self._c_open_btn.setVisible(False)
        self._worker = None

    # ── Browse Tab Actions ───────────────────────────────────────────
    def _pick_archive(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open archive",
            "", "Archives (*.zip *.rar *.7z *.tar *.gz *.bz2 *.xz *.tgz"
                " *.tar.gz *.tar.bz2 *.tar.xz *.cab *.iso)")
        if path:
            self._open_archive(path)

    def _open_archive(self, path: str):
        if not os.path.isfile(path):
            return
        self._archive_path = path
        pw = self._b_pw.text().strip()
        self._b_status.setText("Loading archive...")
        self._b_status.setStyleSheet("color: #89B4FA; font-size: 12px;")

        entries = _list_archive(path, pw)
        self._archive_entries = entries
        self._table.clear()

        total_size = 0
        total_packed = 0
        file_count = 0
        folder_icon = _get_folder_icon()

        for e in entries:
            if e.is_dir:
                continue
            file_count += 1
            total_size += e.size
            total_packed += e.packed
            ratio = f"{(1 - e.packed / e.size) * 100:.0f}%" if e.size else "-"
            item = QTreeWidgetItem([
                e.name,
                _human(e.size),
                _human(e.packed),
                ratio,
                e.modified,
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, e.name)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, False)  # is_dir
            # Set real file type icon
            item.setIcon(0, _get_file_icon(e.name))
            self._table.addTopLevelItem(item)

        # Folders
        for e in entries:
            if not e.is_dir:
                continue
            item = QTreeWidgetItem([e.name, "-", "-", "-", e.modified])
            item.setData(0, Qt.ItemDataRole.UserRole, e.name)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, True)  # is_dir
            item.setIcon(0, folder_icon)
            self._table.addTopLevelItem(item)

        overall_ratio = ((1 - total_packed / total_size) * 100
                         ) if total_size else 0
        self._b_info.setText(
            f"📦 {os.path.basename(path)}  |  "
            f"{file_count} files  |  "
            f"{_human(total_size)} → {_human(total_packed)}  "
            f"({overall_ratio:.0f}% ratio)")
        self._b_info.setVisible(True)

        has_entries = len(entries) > 0
        self._btn_ext_all.setEnabled(has_entries)
        self._btn_ext_sel.setEnabled(has_entries)
        self._btn_test.setEnabled(True)
        self._btn_ext_here.setEnabled(has_entries)
        self._btn_open_file.setEnabled(has_entries)

        self._b_status.setText(
            f"✅ Loaded {file_count} files" if has_entries
            else "⚠️ No entries found (wrong password?)")
        self._b_status.setStyleSheet(
            f"color: {'#A6E3A1' if has_entries else '#F38BA8'};"
            " font-size: 12px;")

    def _extract_all(self):
        if not self._archive_path:
            return
        output_dir = QFileDialog.getExistingDirectory(
            self, "Extract to folder",
            os.path.dirname(self._archive_path))
        if not output_dir:
            return
        self._run_extract(self._archive_path, output_dir)

    def _extract_selected(self):
        if not self._archive_path:
            return
        items = self._table.selectedItems()
        if not items:
            QMessageBox.information(self, "No Selection",
                                   "Select files to extract first.")
            return
        names = [item.data(0, Qt.ItemDataRole.UserRole) for item in items]
        output_dir = QFileDialog.getExistingDirectory(
            self, "Extract selected to",
            os.path.dirname(self._archive_path))
        if not output_dir:
            return
        self._run_extract(self._archive_path, output_dir, files=names)

    def _extract_here(self):
        if not self._archive_path:
            return
        output_dir = os.path.dirname(self._archive_path)
        self._run_extract(self._archive_path, output_dir)

    def _open_file_from_archive(self, item, column):
        """Extract a file to temp and open it with the default app."""
        if item is None:
            return
        is_dir = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if is_dir:
            return
        entry_name = item.data(0, Qt.ItemDataRole.UserRole)
        if not entry_name or not self._archive_path:
            return
        pw = self._b_pw.text().strip()
        arc = self._archive_path

        # Extract to a temp dir preserving the subfolder structure
        tmp_dir = tempfile.mkdtemp(prefix="toty_view_")
        try:
            name_lower = arc.lower()
            if name_lower.endswith(".zip"):
                with zipfile.ZipFile(arc, "r") as zf:
                    if pw:
                        zf.extractall(tmp_dir, [entry_name],
                                      pwd=pw.encode())
                    else:
                        zf.extractall(tmp_dir, [entry_name])
            elif name_lower.endswith(
                    (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz",
                     ".gz", ".bz2", ".xz")):
                with tarfile.open(arc, "r:*") as tf:
                    # Only extract the specific member
                    members = [m for m in tf.getmembers()
                               if m.name == entry_name]
                    if members:
                        tf.extractall(tmp_dir, members=members,
                                      filter="data")
            elif _7Z:
                cmd = [_7Z, "e", "-y", f"-o{tmp_dir}", arc, entry_name]
                if pw:
                    cmd.insert(3, f"-p{pw}")
                subprocess.run(
                    cmd, capture_output=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            else:
                QMessageBox.warning(
                    self, "Cannot Open",
                    "7-Zip required to open files from this archive type.")
                return

            # Find the extracted file
            extracted = os.path.join(tmp_dir, entry_name)
            if not os.path.isfile(extracted):
                # 7z "e" flattens — check base name
                base = os.path.basename(entry_name)
                extracted = os.path.join(tmp_dir, base)
            if os.path.isfile(extracted):
                os.startfile(extracted)
                self._b_status.setText(f"▶️ Opened: {os.path.basename(entry_name)}")
                self._b_status.setStyleSheet(
                    "color: #A6E3A1; font-size: 12px;")
            else:
                QMessageBox.warning(
                    self, "Open Failed",
                    f"Could not extract:\n{entry_name}")
        except Exception as exc:
            QMessageBox.warning(
                self, "Open Failed", f"Error:\n{exc}")

    def _run_extract(self, archive, output_dir, files=None):
        self._b_prog.setVisible(True)
        self._b_prog.setValue(0)
        self._b_status.setText("Extracting...")
        self._b_status.setStyleSheet("color: #89B4FA; font-size: 12px;")
        self._b_open_btn.setVisible(False)
        self._btn_ext_all.setEnabled(False)
        self._btn_ext_sel.setEnabled(False)
        self._btn_ext_here.setEnabled(False)

        pw = self._b_pw.text().strip()
        self._worker = _ExtractWorker(archive, output_dir, pw, files)
        self._worker.progress.connect(self._b_prog.setValue)
        self._worker.finished.connect(self._on_extract_done)
        self._worker.error.connect(self._on_extract_err)
        self._worker.start()

    def _on_extract_done(self, dir_path: str):
        self._b_status.setText(f"✅ Extracted to {dir_path}")
        self._b_status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._btn_ext_all.setEnabled(True)
        self._btn_ext_sel.setEnabled(True)
        self._btn_ext_here.setEnabled(True)
        self._b_open_btn.setVisible(True)
        try:
            self._b_open_btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._b_open_btn.clicked.connect(lambda: os.startfile(dir_path))
        self._worker = None

    def _on_extract_err(self, msg: str):
        self._b_status.setText(f"❌ {msg}")
        self._b_status.setStyleSheet("color: #F38BA8; font-size: 12px;")
        self._b_prog.setVisible(False)
        self._b_open_btn.setVisible(False)
        self._btn_ext_all.setEnabled(True)
        self._btn_ext_sel.setEnabled(True)
        self._btn_ext_here.setEnabled(True)
        self._worker = None

    def _test_archive(self):
        if not self._archive_path:
            return
        self._b_status.setText("🔍 Testing archive integrity...")
        self._b_status.setStyleSheet("color: #89B4FA; font-size: 12px;")
        self._btn_test.setEnabled(False)
        pw = self._b_pw.text().strip()
        self._worker = _TestWorker(self._archive_path, pw)
        self._worker.finished.connect(self._on_test_done)
        self._worker.start()

    def _on_test_done(self, ok: bool, msg: str):
        self._b_status.setText(msg)
        self._b_status.setStyleSheet(
            f"color: {'#A6E3A1' if ok else '#F38BA8'}; font-size: 12px;")
        self._btn_test.setEnabled(True)
        self._worker = None

    def _quick_extract_here(self, archive: str):
        """Auto extract to same dir (context menu --extract-here)."""
        self._archive_path = archive
        self._open_archive(archive)
        output_dir = os.path.dirname(archive)
        self._run_extract(archive, output_dir)

    # ── Tools Tab Actions ────────────────────────────────────────────
    def _check_ctx_status(self):
        try:
            winreg.OpenKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\Classes\*\shell\TotyCompress",
                0, winreg.KEY_READ)
            self._ctx_status.setText("✅ Context menu is installed")
            self._ctx_status.setStyleSheet(
                "color: #A6E3A1; font-size: 12px;")
        except OSError:
            self._ctx_status.setText("❌ Context menu is not installed")
            self._ctx_status.setStyleSheet(
                "color: #F38BA8; font-size: 12px;")

    def _install_ctx(self):
        reply = QMessageBox.question(
            self, "Install Context Menu",
            "This will add right-click options to Windows Explorer:\n\n"
            '• "📦 Compress with Toty" on files & folders\n'
            '• "📦 Open with Toty" on archives\n'
            '• "📂 Extract Here" on archives\n'
            '• "📂 Extract to..." on archives\n\n'
            "Registry entries will be added under HKCU.\n"
            "No admin rights required.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            install_context_menu()
            self._check_ctx_status()
            QMessageBox.information(
                self, "Done",
                "✅ Context menu installed!\n"
                "Right-click any file or archive in Explorer.")
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to install:\n{e}")

    def _remove_ctx(self):
        reply = QMessageBox.question(
            self, "Remove Context Menu",
            "Remove all Toty context menu entries from Explorer?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            uninstall_context_menu()
            self._check_ctx_status()
            QMessageBox.information(self, "Done",
                                   "✅ Context menu removed.")
        except Exception as e:
            QMessageBox.critical(
                self, "Error", f"Failed to remove:\n{e}")

    def _update_7z_status(self):
        if _7Z:
            self._sz_info.setText(f"✅ Found: {_7Z}")
            self._sz_info.setStyleSheet("color: #A6E3A1; font-size: 11px;")
            self._btn_install_7z.setVisible(False)
        else:
            self._sz_info.setText(
                "❌ Not found\n"
                "Install 7-Zip to enable: 7Z format, passwords,\n"
                "RAR extraction, split archives")
            self._sz_info.setStyleSheet("color: #F38BA8; font-size: 11px;")
            self._btn_install_7z.setVisible(True)

    def _auto_install_7z(self):
        self._btn_install_7z.setEnabled(False)
        self._btn_install_7z.setText("⏳ Installing 7-Zip...")
        self._sz_info.setText("Downloading via winget — this may take a minute...")
        self._sz_info.setStyleSheet("color: #89B4FA; font-size: 11px;")

        def _on_done(path):
            _refresh_7z()
            self._update_7z_status()
            if _7Z:
                self._btn_install_7z.setText("✅ Installed!")
            else:
                self._btn_install_7z.setText("🔄 Retry Install")
                self._btn_install_7z.setEnabled(True)

        ensure_7z(callback=lambda p: QTimer.singleShot(0, lambda: _on_done(p)))


# ═════════════════════════════════════════════════════════════════════
#   Windows Context Menu Registration
# ═════════════════════════════════════════════════════════════════════
_CTX_ARCHIVE_EXTS = [
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"]

def _set_reg(subpath: str, value: str):
    """Set a default value under HKCU\\Software\\Classes\\<subpath>."""
    key_path = f"Software\\Classes\\{subpath}"
    with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, key_path,
            0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)

def _set_reg_named(subpath: str, name: str, value: str):
    """Set a named value under HKCU\\Software\\Classes\\<subpath>."""
    key_path = f"Software\\Classes\\{subpath}"
    with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, key_path,
            0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

def _del_reg_tree(subpath: str):
    """Delete a registry key tree under HKCU\\Software\\Classes."""
    key_path = f"Software\\Classes\\{subpath}"
    _recursive_del(winreg.HKEY_CURRENT_USER, key_path)

def _recursive_del(root, path: str):
    try:
        key = winreg.OpenKeyEx(root, path, 0, winreg.KEY_ALL_ACCESS)
    except OSError:
        return
    try:
        while True:
            sub = winreg.EnumKey(key, 0)
            _recursive_del(root, f"{path}\\{sub}")
    except OSError:
        pass
    winreg.CloseKey(key)
    try:
        winreg.DeleteKey(root, path)
    except OSError:
        pass

def install_context_menu():
    """Register right-click context menu entries in HKCU."""
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = sys.executable
    script = os.path.abspath(__file__)
    icon = _ICON_PATH if os.path.isfile(_ICON_PATH) else ""

    # "Compress with Toty" on any file
    _set_reg(r"*\shell\TotyCompress", "\U0001f4e6 Compress with Toty")
    _set_reg(r"*\shell\TotyCompress\command",
             f'"{pythonw}" "{script}" --compress "%1"')
    if icon:
        _set_reg_named(r"*\shell\TotyCompress", "Icon", icon)

    # "Compress with Toty" on directories
    _set_reg(r"Directory\shell\TotyCompress",
             "\U0001f4e6 Compress with Toty")
    _set_reg(r"Directory\shell\TotyCompress\command",
             f'"{pythonw}" "{script}" --compress "%V"')
    if icon:
        _set_reg_named(r"Directory\shell\TotyCompress", "Icon", icon)

    # Archive-specific entries per extension
    for ext in _CTX_ARCHIVE_EXTS:
        base = f"SystemFileAssociations\\{ext}\\shell"

        _set_reg(f"{base}\\TotyOpen", "\U0001f4e6 Open with Toty")
        _set_reg(f"{base}\\TotyOpen\\command",
                 f'"{pythonw}" "{script}" --open "%1"')
        if icon:
            _set_reg_named(f"{base}\\TotyOpen", "Icon", icon)

        _set_reg(f"{base}\\TotyExtractHere",
                 "\U0001f4c2 Extract Here (Toty)")
        _set_reg(f"{base}\\TotyExtractHere\\command",
                 f'"{pythonw}" "{script}" --extract-here "%1"')
        if icon:
            _set_reg_named(f"{base}\\TotyExtractHere", "Icon", icon)

        _set_reg(f"{base}\\TotyExtract",
                 "\U0001f4c2 Extract to... (Toty)")
        _set_reg(f"{base}\\TotyExtract\\command",
                 f'"{pythonw}" "{script}" --extract-to "%1"')
        if icon:
            _set_reg_named(f"{base}\\TotyExtract", "Icon", icon)

    # ── Register "Toty" as a Windows Application ───────────────
    # This makes "Toty" (with icon) appear in the "Open with" dialog
    # instead of showing "Python".
    app_key = r"Applications\Toty.exe"
    _set_reg(app_key, "Toty Archive Manager")
    _set_reg_named(app_key, "FriendlyAppName", "Toty")
    if icon:
        _set_reg(f"{app_key}\\DefaultIcon", f"{icon},0")
    _set_reg(f"{app_key}\\shell\\open\\command",
             f'"{ pythonw}" "{script}" --open "%1"')
    # Declare supported types
    for ext in _CTX_ARCHIVE_EXTS:
        _set_reg(f"{app_key}\\SupportedTypes", "")
        _set_reg_named(f"{app_key}\\SupportedTypes", ext, "")

    # ── Register Toty icon as default icon for archive types ──────
    if icon:
        for ext in _CTX_ARCHIVE_EXTS:
            prog_id = f"Toty.Archive{ext.replace('.', '_')}"
            # Create ProgID with friendly name + icon
            _set_reg(prog_id, f"Toty Archive ({ext})")
            _set_reg_named(prog_id, "FriendlyTypeName",
                           f"Toty Archive ({ext})")
            _set_reg(f"{prog_id}\\DefaultIcon", f"{icon},0")
            # Add open command to the ProgID with FriendlyAppName
            _set_reg(f"{prog_id}\\shell\\open", "\U0001f4e6 Open with Toty")
            _set_reg_named(f"{prog_id}\\shell\\open",
                           "FriendlyAppName", "Toty")
            _set_reg(f"{prog_id}\\shell\\open\\command",
                     f'"{ pythonw}" "{script}" --open "%1"')
            if icon:
                _set_reg_named(f"{prog_id}\\shell\\open", "Icon", icon)
            # Point the extension to our ProgID
            _set_reg(ext, prog_id)
            # Also register in OpenWithProgids for modern Windows
            key_path = f"Software\\Classes\\{ext}\\OpenWithProgids"
            with winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER, key_path,
                    0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, prog_id, 0, winreg.REG_NONE, b"")
            # Also add Toty.exe to OpenWithList
            owl_path = f"Software\\Classes\\{ext}\\OpenWithList\\Toty.exe"
            with winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER, owl_path,
                    0, winreg.KEY_SET_VALUE) as key:
                pass  # just create the key

    # Tell Explorer to refresh icons
    try:
        import ctypes
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(
            SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass

    log.info("Context menu installed")

def uninstall_context_menu():
    """Remove all Toty context menu entries from HKCU."""
    _del_reg_tree(r"*\shell\TotyCompress")
    _del_reg_tree(r"Directory\shell\TotyCompress")
    # Remove Toty application registration
    _del_reg_tree(r"Applications\Toty.exe")
    for ext in _CTX_ARCHIVE_EXTS:
        base = f"SystemFileAssociations\\{ext}\\shell"
        _del_reg_tree(f"{base}\\TotyOpen")
        _del_reg_tree(f"{base}\\TotyExtractHere")
        _del_reg_tree(f"{base}\\TotyExtract")
        # Clean up icon association
        prog_id = f"Toty.Archive{ext.replace('.', '_')}"
        _del_reg_tree(prog_id)
        # Remove old-style ProgID too (from previous install)
        _del_reg_tree(f"TotyArchive{ext}")
        # Remove extension override & OpenWithProgids entry
        _del_reg_tree(ext)
        try:
            key_path = f"Software\\Classes\\{ext}\\OpenWithProgids"
            with winreg.OpenKeyEx(
                    winreg.HKEY_CURRENT_USER, key_path,
                    0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, prog_id)
        except OSError:
            pass
        # Remove OpenWithList entry
        try:
            owl_path = f"Software\\Classes\\{ext}\\OpenWithList\\Toty.exe"
            _del_reg_tree(owl_path[len('Software\\Classes\\'):])
        except Exception:
            pass
    # Tell Explorer to refresh icons
    try:
        import ctypes
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass
    log.info("Context menu uninstalled")


# ═════════════════════════════════════════════════════════════════════
#   Standalone CLI entry point (called from context menu)
# ═════════════════════════════════════════════════════════════════════
def _run_standalone():
    """Handle command-line invocation from Windows context menu."""
    import argparse
    parser = argparse.ArgumentParser(description="Toty Archive Manager")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--compress", metavar="PATH",
                       help="Compress a file or folder")
    group.add_argument("--open", metavar="PATH",
                       help="Open and browse an archive")
    group.add_argument("--extract-here", metavar="PATH",
                       help="Extract archive to same directory")
    group.add_argument("--extract-to", metavar="PATH",
                       help="Extract archive with folder picker")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")

    if args.compress:
        path = os.path.abspath(args.compress)
        if not os.path.exists(path):
            QMessageBox.critical(None, "Error", f"Path not found:\n{path}")
            return
        dlg = FileCompressorDialog(compress_paths=[path])
        dlg.exec()

    elif args.open:
        path = os.path.abspath(args.open)
        if not os.path.isfile(path):
            QMessageBox.critical(None, "Error", f"File not found:\n{path}")
            return
        dlg = FileCompressorDialog(open_archive=path)
        dlg.exec()

    elif args.extract_here:
        path = os.path.abspath(args.extract_here)
        if not os.path.isfile(path):
            QMessageBox.critical(None, "Error", f"File not found:\n{path}")
            return
        dlg = FileCompressorDialog(extract_here=path)
        dlg.exec()

    elif args.extract_to:
        path = os.path.abspath(args.extract_to)
        if not os.path.isfile(path):
            QMessageBox.critical(None, "Error", f"File not found:\n{path}")
            return
        dest = QFileDialog.getExistingDirectory(
            None, "Extract to folder", os.path.dirname(path))
        if not dest:
            return
        dlg = FileCompressorDialog(open_archive=path)
        dlg.show()
        dlg._run_extract(path, dest)
        dlg.exec()


if __name__ == "__main__":
    try:
        _run_standalone()
    except Exception as e:
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(None, "Toty Archive Manager Error", str(e))
        except Exception:
            pass
