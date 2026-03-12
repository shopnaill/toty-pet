"""System Cleaner — Scan & remove temp files, caches, and junk to free disk space."""
import os
import sys
import shutil
import logging
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    QProgressBar, QCheckBox, QApplication,
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QColor

log = logging.getLogger("toty.system_cleaner")

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"
_YELLOW = "#F9E2AF"

_SS = f"""
QDialog {{ background: {_BG}; }}
QTreeWidget {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; font-size: 13px;
}}
QTreeWidget::item {{ padding: 3px 0; }}
QTreeWidget::item:selected {{ background: #45475A; }}
QHeaderView::section {{
    background: {_SURFACE}; color: {_BLUE}; border: none;
    font-weight: bold; padding: 6px;
}}
QPushButton {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background: #45475A; border-color: {_BLUE}; }}
QPushButton:pressed {{ background: {_BLUE}; color: {_BG}; }}
QLabel {{ color: {_TEXT}; }}
QCheckBox {{ color: {_TEXT}; font-size: 13px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QProgressBar {{
    background: {_SURFACE}; border: 1px solid #45475A; border-radius: 4px;
    text-align: center; color: {_TEXT}; font-size: 11px;
}}
QProgressBar::chunk {{ background: {_GREEN}; border-radius: 3px; }}
"""


def _fmt_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _dir_size(path: str) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += _dir_size(entry.path)
            except (OSError, PermissionError):
                pass
    except (OSError, PermissionError):
        pass
    return total


# ── Scan targets ──────────────────────────────────────────────────
def _get_scan_categories() -> list[dict]:
    """Return list of cleanable categories with paths."""
    temp = os.environ.get("TEMP", os.environ.get("TMP", ""))
    localappdata = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    userprofile = os.environ.get("USERPROFILE", "")

    cats = []

    # Windows Temp
    if temp and os.path.isdir(temp):
        cats.append({
            "name": "🗑️ Windows Temp Files",
            "paths": [temp],
            "desc": "Temporary files created by Windows and apps",
            "safe": True,
        })

    # Windows Prefetch
    prefetch = r"C:\Windows\Prefetch"
    if os.path.isdir(prefetch):
        cats.append({
            "name": "⚡ Windows Prefetch",
            "paths": [prefetch],
            "desc": "Boot prefetch cache (regenerates automatically)",
            "safe": True,
        })

    # Thumbnail cache
    thumb = os.path.join(localappdata, "Microsoft", "Windows", "Explorer")
    if os.path.isdir(thumb):
        cats.append({
            "name": "🖼️ Thumbnail Cache",
            "paths": [thumb],
            "desc": "Cached thumbnails (regenerate on demand)",
            "safe": True,
            "pattern": "thumbcache_*.db",
        })

    # Recent files list
    recent = os.path.join(appdata, "Microsoft", "Windows", "Recent")
    if os.path.isdir(recent):
        cats.append({
            "name": "📄 Recent Files List",
            "paths": [recent],
            "desc": "Shortcuts to recently opened files",
            "safe": True,
        })

    # Browser caches
    chrome_cache = os.path.join(
        localappdata, "Google", "Chrome", "User Data", "Default", "Cache")
    if os.path.isdir(chrome_cache):
        cats.append({
            "name": "🌐 Chrome Cache",
            "paths": [chrome_cache],
            "desc": "Google Chrome browser cache",
            "safe": True,
        })

    edge_cache = os.path.join(
        localappdata, "Microsoft", "Edge", "User Data", "Default", "Cache")
    if os.path.isdir(edge_cache):
        cats.append({
            "name": "🌐 Edge Cache",
            "paths": [edge_cache],
            "desc": "Microsoft Edge browser cache",
            "safe": True,
        })

    firefox_dir = os.path.join(localappdata, "Mozilla", "Firefox", "Profiles")
    if os.path.isdir(firefox_dir):
        ff_caches = []
        for d in os.listdir(firefox_dir):
            c = os.path.join(firefox_dir, d, "cache2")
            if os.path.isdir(c):
                ff_caches.append(c)
        if ff_caches:
            cats.append({
                "name": "🦊 Firefox Cache",
                "paths": ff_caches,
                "desc": "Mozilla Firefox browser cache",
                "safe": True,
            })

    # Downloads folder (just show size, don't auto-clean)
    downloads = os.path.join(userprofile, "Downloads")
    if os.path.isdir(downloads):
        cats.append({
            "name": "📥 Downloads Folder",
            "paths": [downloads],
            "desc": "Your Downloads folder (review before cleaning!)",
            "safe": False,
        })

    # Recycle Bin (info only)
    cats.append({
        "name": "♻️ Recycle Bin",
        "paths": [],
        "desc": "Empty via Windows (right-click Recycle Bin → Empty)",
        "safe": False,
        "recycle_bin": True,
    })

    # pip cache
    pip_cache = os.path.join(localappdata, "pip", "cache")
    if os.path.isdir(pip_cache):
        cats.append({
            "name": "🐍 Pip Cache",
            "paths": [pip_cache],
            "desc": "Python pip download cache",
            "safe": True,
        })

    # npm cache
    npm_cache = os.path.join(appdata, "npm-cache")
    if os.path.isdir(npm_cache):
        cats.append({
            "name": "📦 npm Cache",
            "paths": [npm_cache],
            "desc": "Node.js npm package cache",
            "safe": True,
        })

    return cats


class _ScanWorker(QThread):
    progress = pyqtSignal(str, int)  # category_name, size_bytes
    finished = pyqtSignal(list)      # list of (cat_dict, size)

    def __init__(self, categories):
        super().__init__()
        self._cats = categories

    def run(self):
        results = []
        for cat in self._cats:
            total = 0
            if cat.get("recycle_bin"):
                # Cannot easily measure recycle bin size without COM
                results.append((cat, -1))
                self.progress.emit(cat["name"], -1)
                continue
            pattern = cat.get("pattern")
            for p in cat["paths"]:
                if pattern:
                    import glob
                    for f in glob.glob(os.path.join(p, pattern)):
                        try:
                            total += os.path.getsize(f)
                        except OSError:
                            pass
                else:
                    total += _dir_size(p)
            results.append((cat, total))
            self.progress.emit(cat["name"], total)
        self.finished.emit(results)


class SystemCleanerDialog(QDialog):
    """Scan and clean temp files, caches, and junk."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧹 System Cleaner")
        self.setMinimumSize(600, 500)
        self.resize(650, 540)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)
        self._results: list[tuple[dict, int]] = []
        self._checks: dict[str, QCheckBox] = {}
        self._worker: _ScanWorker | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title = QLabel("🧹 System Cleaner")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE}; margin-bottom: 4px;")
        lay.addWidget(title)

        info = QLabel("Scan for junk files, caches, and temp data to reclaim disk space.")
        info.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["", "Category", "Size", "Description"])
        self._tree.setColumnCount(4)
        hdr = self._tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tree.setColumnWidth(1, 200)
        self._tree.setRootIsDecorated(False)
        lay.addWidget(self._tree)

        self._prog = QProgressBar()
        self._prog.setVisible(False)
        self._prog.setFixedHeight(22)
        lay.addWidget(self._prog)

        self._status = QLabel("Press Scan to analyze your system.")
        self._status.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        lay.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_scan = QPushButton("🔍 Scan")
        self._btn_scan.clicked.connect(self._start_scan)
        btn_row.addWidget(self._btn_scan)

        self._btn_clean = QPushButton("🧹 Clean Selected")
        self._btn_clean.clicked.connect(self._clean)
        self._btn_clean.setEnabled(False)
        self._btn_clean.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_BG}; "
            f"border: none; border-radius: 6px; padding: 8px 16px; "
            f"font-weight: bold; font-size: 13px; }}"
            f"QPushButton:hover {{ background: #94D89A; }}"
            f"QPushButton:disabled {{ background: {_SURFACE}; color: #585B70; }}")
        btn_row.addWidget(self._btn_clean)

        btn_row.addStretch()

        self._btn_sel_all = QPushButton("☑ Select Safe")
        self._btn_sel_all.clicked.connect(self._select_safe)
        btn_row.addWidget(self._btn_sel_all)

        lay.addLayout(btn_row)

    def _start_scan(self):
        self._tree.clear()
        self._checks.clear()
        self._results.clear()
        self._btn_scan.setEnabled(False)
        self._btn_clean.setEnabled(False)
        self._prog.setVisible(True)
        self._prog.setMaximum(0)  # indeterminate
        self._status.setText("Scanning…")
        self._status.setStyleSheet(f"color: {_BLUE}; font-size: 12px;")

        cats = _get_scan_categories()
        self._worker = _ScanWorker(cats)
        self._worker.progress.connect(self._on_scan_progress)
        self._worker.finished.connect(self._on_scan_done)
        self._worker.start()

    def _on_scan_progress(self, name: str, size: int):
        self._status.setText(f"Scanning: {name}…")

    def _on_scan_done(self, results: list):
        self._prog.setVisible(False)
        self._results = results
        total = 0

        for cat, size in results:
            row = QTreeWidgetItem()
            cb = QCheckBox()
            self._tree.addTopLevelItem(row)
            self._tree.setItemWidget(row, 0, cb)
            row.setText(1, cat["name"])
            if size < 0:
                row.setText(2, "—")
                cb.setEnabled(False)
            else:
                row.setText(2, _fmt_size(size))
                total += size
            row.setText(3, cat["desc"])
            row.setData(0, Qt.ItemDataRole.UserRole, cat)
            row.setData(0, Qt.ItemDataRole.UserRole + 1, size)
            self._checks[cat["name"]] = cb

            if not cat.get("safe", False):
                row.setForeground(2, QColor(_YELLOW))
                cb.setChecked(False)
            else:
                if size > 0:
                    cb.setChecked(True)

        self._status.setText(
            f"Scan complete — {_fmt_size(total)} of cleanable data found")
        self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
        self._btn_scan.setEnabled(True)
        self._btn_clean.setEnabled(True)

    def _select_safe(self):
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            cat = item.data(0, Qt.ItemDataRole.UserRole)
            size = item.data(0, Qt.ItemDataRole.UserRole + 1)
            cb = self._checks.get(cat["name"])
            if cb and cb.isEnabled():
                cb.setChecked(cat.get("safe", False) and (size or 0) > 0)

    def _clean(self):
        selected = []
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            cat = item.data(0, Qt.ItemDataRole.UserRole)
            cb = self._checks.get(cat["name"])
            if cb and cb.isChecked():
                selected.append(cat)

        if not selected:
            QMessageBox.information(self, "Nothing Selected",
                                    "Check the categories you want to clean.")
            return

        names = "\n".join(f"  • {c['name']}" for c in selected)
        ans = QMessageBox.question(
            self, "Confirm Cleanup",
            f"Clean the following?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return

        freed = 0
        errors = 0
        for cat in selected:
            pattern = cat.get("pattern")
            for p in cat["paths"]:
                if pattern:
                    import glob
                    for f in glob.glob(os.path.join(p, pattern)):
                        try:
                            sz = os.path.getsize(f)
                            os.remove(f)
                            freed += sz
                        except OSError:
                            errors += 1
                else:
                    try:
                        for entry in os.scandir(p):
                            try:
                                if entry.is_file(follow_symlinks=False):
                                    sz = entry.stat().st_size
                                    os.remove(entry.path)
                                    freed += sz
                                elif entry.is_dir(follow_symlinks=False):
                                    sz = _dir_size(entry.path)
                                    shutil.rmtree(entry.path,
                                                  ignore_errors=True)
                                    freed += sz
                            except (OSError, PermissionError):
                                errors += 1
                    except (OSError, PermissionError):
                        errors += 1

        msg = f"✅ Freed {_fmt_size(freed)}"
        if errors:
            msg += f" ({errors} files skipped — in use)"
        self._status.setText(msg)
        self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
        log.info("System cleaner freed %s (%d errors)", _fmt_size(freed), errors)

        # Rescan to show updated sizes
        self._start_scan()
