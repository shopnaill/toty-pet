"""Package & App Manager — pip packages + Windows apps install/uninstall."""
import os
import sys
import logging
import subprocess
import threading
import winreg
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTabWidget, QWidget, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QMessageBox, QProgressBar, QComboBox, QFrame,
    QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont

log = logging.getLogger("toty.package_manager")


# ═════════════════════════════════════════════════════════════════════
#  Workers
# ═════════════════════════════════════════════════════════════════════
_NO_WIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class _PipListWorker(QThread):
    """List installed pip packages."""
    finished = pyqtSignal(list)  # list[dict]
    error = pyqtSignal(str)

    def run(self):
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pip", "list",
                 "--format=columns", "--no-color"],
                capture_output=True, text=True, timeout=30,
                creationflags=_NO_WIN,
            )
            if r.returncode != 0:
                self.error.emit(r.stderr[:300])
                return
            lines = r.stdout.strip().splitlines()
            pkgs = []
            for line in lines[2:]:  # skip header + separator
                parts = line.split()
                if len(parts) >= 2:
                    pkgs.append({"name": parts[0], "version": parts[1]})
            self.finished.emit(pkgs)
        except Exception as e:
            self.error.emit(str(e))


class _PipActionWorker(QThread):
    """Install or uninstall a pip package."""
    progress = pyqtSignal(str)  # status text
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, action: str, package: str):
        super().__init__()
        self._action = action  # "install" or "uninstall"
        self._package = package

    def run(self):
        try:
            if self._action == "install":
                cmd = [sys.executable, "-m", "pip", "install", self._package]
            else:
                cmd = [sys.executable, "-m", "pip", "uninstall",
                       "-y", self._package]

            self.progress.emit(f"Running: pip {self._action} {self._package}...")
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                creationflags=_NO_WIN,
            )
            if r.returncode == 0:
                self.finished.emit(True, r.stdout[-500:] if r.stdout else "Done")
            else:
                self.finished.emit(False, r.stderr[:500] or "Failed")
        except Exception as e:
            self.finished.emit(False, str(e))


class _WinAppListWorker(QThread):
    """List installed Windows apps via winreg (no PowerShell needed)."""
    finished = pyqtSignal(list)  # list[dict]
    error = pyqtSignal(str)

    _REG_PATHS = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    def run(self):
        try:
            apps = []
            seen = set()
            for hive, path in self._REG_PATHS:
                try:
                    key = winreg.OpenKey(hive, path)
                except OSError:
                    continue
                try:
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            sk = winreg.OpenKey(key, subkey_name)
                        except OSError:
                            continue
                        try:
                            name = self._val(sk, "DisplayName")
                            if not name or name in seen:
                                continue
                            seen.add(name)
                            quiet = self._val(sk, "QuietUninstallString")
                            uninst = quiet or self._val(sk, "UninstallString")
                            size_kb = 0
                            try:
                                size_kb = int(
                                    self._val(sk, "EstimatedSize") or 0)
                            except (ValueError, TypeError):
                                pass
                            apps.append({
                                "name": name,
                                "version": self._val(sk, "DisplayVersion"),
                                "publisher": self._val(sk, "Publisher"),
                                "date": self._val(sk, "InstallDate"),
                                "size_kb": size_kb,
                                "uninstall": uninst or "",
                            })
                        finally:
                            winreg.CloseKey(sk)
                finally:
                    winreg.CloseKey(key)
            apps.sort(key=lambda a: a["name"].lower())
            self.finished.emit(apps)
        except Exception as e:
            self.error.emit(str(e))

    @staticmethod
    def _val(key, name):
        try:
            return str(winreg.QueryValueEx(key, name)[0])
        except OSError:
            return ""


class _WinAppUninstallWorker(QThread):
    """Uninstall a Windows app."""
    finished = pyqtSignal(bool, str)

    def __init__(self, uninstall_cmd: str, app_name: str):
        super().__init__()
        self._cmd = uninstall_cmd
        self._name = app_name

    def run(self):
        try:
            if not self._cmd:
                self.finished.emit(False, "No uninstall command found.")
                return
            # Use cmd /c to handle the uninstall string properly
            r = subprocess.run(
                self._cmd, shell=False,
                capture_output=True, text=True, timeout=300,
                creationflags=_NO_WIN,
            )
            if r.returncode == 0:
                self.finished.emit(True, f"✅ {self._name} uninstalled")
            else:
                # Many uninstallers return non-zero but still work,
                # or they launch a GUI
                self.finished.emit(
                    True,
                    f"Uninstaller launched for {self._name}.\n"
                    "If a window appeared, follow the prompts.")
        except FileNotFoundError:
            # Try via cmd /c for complex uninstall strings
            try:
                r = subprocess.run(
                    ["cmd", "/c", self._cmd],
                    capture_output=True, text=True, timeout=300,
                    creationflags=_NO_WIN,
                )
                self.finished.emit(True, f"Uninstaller launched for {self._name}")
            except Exception as e:
                self.finished.emit(False, str(e))
        except Exception as e:
            self.finished.emit(False, str(e))


class _WinGetListWorker(QThread):
    """List winget-installed packages."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def run(self):
        try:
            r = subprocess.run(
                ["winget", "list", "--disable-interactivity"],
                capture_output=True, text=True, timeout=30,
                creationflags=_NO_WIN,
            )
            if r.returncode != 0:
                self.error.emit("winget not available")
                return
            lines = r.stdout.strip().splitlines()
            # Find the header separator line (contains dashes)
            header_idx = -1
            for i, line in enumerate(lines):
                if set(line.strip()) <= {'-', ' '}  and len(line.strip()) > 10:
                    header_idx = i
                    break
            if header_idx < 1:
                self.finished.emit([])
                return

            # Parse column positions from header
            header = lines[header_idx - 1]
            pkgs = []
            for line in lines[header_idx + 1:]:
                if len(line.strip()) < 5:
                    continue
                # Simple split — winget output is columnar
                name = line[:40].strip()
                rest = line[40:].strip()
                parts = rest.split()
                version = parts[0] if parts else ""
                pkg_id = parts[-1] if len(parts) >= 2 else ""
                if name:
                    pkgs.append({
                        "name": name,
                        "version": version,
                        "id": pkg_id,
                    })
            self.finished.emit(pkgs)
        except Exception as e:
            self.error.emit(str(e))


class _WinGetActionWorker(QThread):
    """Install or uninstall via winget."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, action: str, package_id: str):
        super().__init__()
        self._action = action
        self._id = package_id

    def run(self):
        try:
            if self._action == "install":
                cmd = ["winget", "install", "--id", self._id,
                       "--accept-source-agreements",
                       "--accept-package-agreements", "--silent"]
            else:
                cmd = ["winget", "uninstall", "--id", self._id, "--silent"]

            self.progress.emit(
                f"Running: winget {self._action} {self._id}...")
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                creationflags=_NO_WIN,
            )
            out = r.stdout[-500:] if r.stdout else ""
            if r.returncode == 0 or "successfully" in out.lower():
                self.finished.emit(True, out or "Done")
            else:
                self.finished.emit(False, r.stderr[:500] or out or "Failed")
        except Exception as e:
            self.finished.emit(False, str(e))


# ═════════════════════════════════════════════════════════════════════
#  Styles
# ═════════════════════════════════════════════════════════════════════
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
    "btn":   ("QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
              " border-radius: 8px; padding: 8px 14px; font-weight: bold;"
              " font-size: 12px; }"
              "QPushButton:hover { background: #B4BEFE; }"
              "QPushButton:disabled { background: #45475A; color: #6C7086; }"),
    "green": ("QPushButton { background: #A6E3A1; color: #1E1E2E; border: none;"
              " border-radius: 8px; padding: 8px 14px; font-weight: bold;"
              " font-size: 12px; }"
              "QPushButton:hover { background: #94E2D5; }"
              "QPushButton:disabled { background: #45475A; color: #6C7086; }"),
    "red":   ("QPushButton { background: #F38BA8; color: #1E1E2E; border: none;"
              " border-radius: 8px; padding: 8px 14px; font-weight: bold;"
              " font-size: 12px; }"
              "QPushButton:hover { background: #EBA0AC; }"
              "QPushButton:disabled { background: #45475A; color: #6C7086; }"),
    "sm_btn": ("QPushButton { background: #45475A; color: #CDD6F4; border: none;"
               " border-radius: 6px; padding: 5px 10px; font-size: 11px; }"
               "QPushButton:hover { background: #585B70; }"
               "QPushButton:disabled { color: #6C7086; }"),
    "tab":   ("QTabWidget::pane { border: 1px solid #45475A;"
              " background: #1E1E2E; border-radius: 6px; }"
              "QTabBar::tab { background: #313244; color: #CDD6F4;"
              " padding: 8px 14px; border-top-left-radius: 8px;"
              " border-top-right-radius: 8px; margin-right: 2px; }"
              "QTabBar::tab:selected { background: #45475A; color: #89B4FA; }"
              "QTabBar::tab:hover { background: #3B3C52; }"),
    "tree":  ("QTreeWidget { background: #313244; color: #CDD6F4;"
              " border: 1px solid #45475A; border-radius: 6px;"
              " font-size: 12px; }"
              "QTreeWidget::item { padding: 2px; }"
              "QTreeWidget::item:selected { background: #45475A; }"
              "QTreeWidget::item:hover { background: #3B3C52; }"
              "QHeaderView::section { background: #1E1E2E; color: #89B4FA;"
              " border: 1px solid #45475A; padding: 4px;"
              " font-weight: bold; font-size: 11px; }"),
    "prog":  ("QProgressBar { background: #313244; border: 1px solid #45475A;"
              " border-radius: 6px; height: 18px; text-align: center;"
              " color: #CDD6F4; }"
              "QProgressBar::chunk { background: #89B4FA;"
              " border-radius: 5px; }"),
}


def _human(kb: int) -> str:
    """Human-readable size from KB."""
    if kb <= 0:
        return "-"
    b = kb * 1024.0
    for u in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} TB"


# ═════════════════════════════════════════════════════════════════════
#  Main Dialog
# ═════════════════════════════════════════════════════════════════════
class PackageManagerDialog(QDialog):
    """Package & App Manager with 3 tabs: pip, Windows apps, winget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📦 Package & App Manager")
        self.setMinimumSize(620, 560)
        self.resize(660, 600)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")
        self._worker = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)

        title = QLabel("📦 Package & App Manager")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: #89B4FA; margin-bottom: 8px;")
        layout.addWidget(title)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_S["tab"])
        layout.addWidget(self._tabs)

        self._build_pip_tab()
        self._build_apps_tab()
        self._build_winget_tab()

    # ── Pip Tab ──────────────────────────────────────────────────────
    def _build_pip_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        lbl = QLabel("🐍 Python Packages (pip)")
        lbl.setStyleSheet(_S["head"])
        lay.addWidget(lbl)

        # Search / filter row
        row = QHBoxLayout()
        self._pip_search = QLineEdit()
        self._pip_search.setPlaceholderText("🔍 Filter or type package name to install...")
        self._pip_search.setStyleSheet(_S["input"])
        self._pip_search.textChanged.connect(self._pip_filter)
        row.addWidget(self._pip_search)

        self._pip_refresh_btn = QPushButton("🔄")
        self._pip_refresh_btn.setStyleSheet(_S["sm_btn"])
        self._pip_refresh_btn.setFixedWidth(36)
        self._pip_refresh_btn.setToolTip("Refresh list")
        self._pip_refresh_btn.clicked.connect(self._pip_load)
        row.addWidget(self._pip_refresh_btn)
        lay.addLayout(row)

        # Table
        self._pip_tree = QTreeWidget()
        self._pip_tree.setHeaderLabels(["Package", "Version"])
        self._pip_tree.setColumnCount(2)
        self._pip_tree.setRootIsDecorated(False)
        self._pip_tree.setSortingEnabled(True)
        self._pip_tree.setSelectionMode(
            QTreeWidget.SelectionMode.ExtendedSelection)
        self._pip_tree.setStyleSheet(_S["tree"])
        h = self._pip_tree.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._pip_tree, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        self._pip_install_btn = QPushButton("📥 Install Package")
        self._pip_install_btn.setStyleSheet(_S["green"])
        self._pip_install_btn.clicked.connect(self._pip_install)
        btn_row.addWidget(self._pip_install_btn)

        self._pip_uninstall_btn = QPushButton("🗑️ Uninstall Selected")
        self._pip_uninstall_btn.setStyleSheet(_S["red"])
        self._pip_uninstall_btn.clicked.connect(self._pip_uninstall)
        btn_row.addWidget(self._pip_uninstall_btn)

        self._pip_count = QLabel("")
        self._pip_count.setStyleSheet("color: #6C7086; font-size: 11px;")
        btn_row.addWidget(self._pip_count)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Status
        self._pip_status = QLabel("")
        self._pip_status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._pip_status.setWordWrap(True)
        lay.addWidget(self._pip_status)

        self._tabs.addTab(tab, "🐍 Pip")
        QTimer.singleShot(100, self._pip_load)

    # ── Windows Apps Tab ─────────────────────────────────────────────
    def _build_apps_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        lbl = QLabel("🪟 Installed Windows Applications")
        lbl.setStyleSheet(_S["head"])
        lay.addWidget(lbl)

        # Search
        row = QHBoxLayout()
        self._app_search = QLineEdit()
        self._app_search.setPlaceholderText("🔍 Search apps...")
        self._app_search.setStyleSheet(_S["input"])
        self._app_search.textChanged.connect(self._app_filter)
        row.addWidget(self._app_search)

        self._app_refresh_btn = QPushButton("🔄")
        self._app_refresh_btn.setStyleSheet(_S["sm_btn"])
        self._app_refresh_btn.setFixedWidth(36)
        self._app_refresh_btn.setToolTip("Refresh list")
        self._app_refresh_btn.clicked.connect(self._app_load)
        row.addWidget(self._app_refresh_btn)
        lay.addLayout(row)

        # Table
        self._app_tree = QTreeWidget()
        self._app_tree.setHeaderLabels(
            ["Name", "Version", "Publisher", "Size"])
        self._app_tree.setColumnCount(4)
        self._app_tree.setRootIsDecorated(False)
        self._app_tree.setSortingEnabled(True)
        self._app_tree.setSelectionMode(
            QTreeWidget.SelectionMode.SingleSelection)
        self._app_tree.setStyleSheet(_S["tree"])
        h = self._app_tree.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i in range(1, 4):
            h.setSectionResizeMode(
                i, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._app_tree, 1)

        # Action row
        btn_row = QHBoxLayout()
        self._app_uninstall_btn = QPushButton("🗑️ Uninstall Selected")
        self._app_uninstall_btn.setStyleSheet(_S["red"])
        self._app_uninstall_btn.clicked.connect(self._app_uninstall)
        btn_row.addWidget(self._app_uninstall_btn)

        self._app_count = QLabel("")
        self._app_count.setStyleSheet("color: #6C7086; font-size: 11px;")
        btn_row.addWidget(self._app_count)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._app_status = QLabel("")
        self._app_status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._app_status.setWordWrap(True)
        lay.addWidget(self._app_status)

        self._tabs.addTab(tab, "🪟 Apps")
        QTimer.singleShot(200, self._app_load)

    # ── Winget Tab ───────────────────────────────────────────────────
    def _build_winget_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        lbl = QLabel("📦 Winget Package Manager")
        lbl.setStyleSheet(_S["head"])
        lay.addWidget(lbl)

        # Install row
        inst_row = QHBoxLayout()
        self._wg_input = QLineEdit()
        self._wg_input.setPlaceholderText(
            "Enter winget package ID (e.g. 7zip.7zip, Gyan.FFmpeg)...")
        self._wg_input.setStyleSheet(_S["input"])
        inst_row.addWidget(self._wg_input)

        self._wg_install_btn = QPushButton("📥 Install")
        self._wg_install_btn.setStyleSheet(_S["green"])
        self._wg_install_btn.clicked.connect(self._wg_install)
        inst_row.addWidget(self._wg_install_btn)
        lay.addLayout(inst_row)

        # Search / filter
        row = QHBoxLayout()
        self._wg_search = QLineEdit()
        self._wg_search.setPlaceholderText("🔍 Filter installed winget packages...")
        self._wg_search.setStyleSheet(_S["input"])
        self._wg_search.textChanged.connect(self._wg_filter)
        row.addWidget(self._wg_search)

        self._wg_refresh_btn = QPushButton("🔄")
        self._wg_refresh_btn.setStyleSheet(_S["sm_btn"])
        self._wg_refresh_btn.setFixedWidth(36)
        self._wg_refresh_btn.setToolTip("Refresh list")
        self._wg_refresh_btn.clicked.connect(self._wg_load)
        row.addWidget(self._wg_refresh_btn)
        lay.addLayout(row)

        # Table
        self._wg_tree = QTreeWidget()
        self._wg_tree.setHeaderLabels(["Name", "Version", "ID"])
        self._wg_tree.setColumnCount(3)
        self._wg_tree.setRootIsDecorated(False)
        self._wg_tree.setSortingEnabled(True)
        self._wg_tree.setSelectionMode(
            QTreeWidget.SelectionMode.SingleSelection)
        self._wg_tree.setStyleSheet(_S["tree"])
        h = self._wg_tree.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._wg_tree, 1)

        # Action row
        btn_row = QHBoxLayout()
        self._wg_uninstall_btn = QPushButton("🗑️ Uninstall Selected")
        self._wg_uninstall_btn.setStyleSheet(_S["red"])
        self._wg_uninstall_btn.clicked.connect(self._wg_uninstall)
        btn_row.addWidget(self._wg_uninstall_btn)

        self._wg_count = QLabel("")
        self._wg_count.setStyleSheet("color: #6C7086; font-size: 11px;")
        btn_row.addWidget(self._wg_count)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        self._wg_status = QLabel("")
        self._wg_status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._wg_status.setWordWrap(True)
        lay.addWidget(self._wg_status)

        self._tabs.addTab(tab, "📦 Winget")
        QTimer.singleShot(300, self._wg_load)

    # ═════════════════════════════════════════════════════════════════
    #  Pip Actions
    # ═════════════════════════════════════════════════════════════════
    def _pip_load(self):
        self._pip_status.setText("Loading packages...")
        self._pip_status.setStyleSheet("color: #89B4FA; font-size: 12px;")
        self._pip_refresh_btn.setEnabled(False)
        self._worker = _PipListWorker()
        self._worker.finished.connect(self._pip_loaded)
        self._worker.error.connect(self._pip_error)
        self._worker.start()

    def _pip_loaded(self, pkgs: list):
        self._pip_tree.clear()
        self._pip_all_items = []
        for p in pkgs:
            item = QTreeWidgetItem([p["name"], p["version"]])
            item.setData(0, Qt.ItemDataRole.UserRole, p["name"])
            self._pip_tree.addTopLevelItem(item)
            self._pip_all_items.append(item)
        self._pip_count.setText(f"{len(pkgs)} packages")
        self._pip_status.setText("")
        self._pip_refresh_btn.setEnabled(True)
        self._pip_filter(self._pip_search.text())
        self._worker = None

    def _pip_error(self, msg):
        self._pip_status.setText(f"❌ {msg}")
        self._pip_status.setStyleSheet("color: #F38BA8; font-size: 12px;")
        self._pip_refresh_btn.setEnabled(True)
        self._worker = None

    def _pip_filter(self, text: str):
        text = text.lower()
        for i in range(self._pip_tree.topLevelItemCount()):
            item = self._pip_tree.topLevelItem(i)
            name = item.text(0).lower()
            item.setHidden(text not in name)

    def _pip_install(self):
        pkg = self._pip_search.text().strip()
        if not pkg:
            QMessageBox.information(
                self, "Install Package",
                "Type a package name in the search box first.\n"
                "Example: requests, flask, pandas")
            return
        # Validate package name
        if not all(c.isalnum() or c in "-_.[],><=! " for c in pkg):
            QMessageBox.warning(self, "Invalid", "Invalid package name.")
            return
        reply = QMessageBox.question(
            self, "Install Package",
            f"Install Python package:\n\n  pip install {pkg}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._pip_set_busy(True, f"Installing {pkg}...")
        self._worker = _PipActionWorker("install", pkg)
        self._worker.progress.connect(
            lambda s: self._pip_status.setText(s))
        self._worker.finished.connect(self._pip_action_done)
        self._worker.start()

    def _pip_uninstall(self):
        items = self._pip_tree.selectedItems()
        if not items:
            QMessageBox.information(
                self, "Uninstall",
                "Select a package from the list first.")
            return
        names = [item.data(0, Qt.ItemDataRole.UserRole) for item in items]
        # Protect critical packages
        protected = {"pip", "setuptools", "wheel", "PyQt6", "PyQt6-Qt6",
                     "PyQt6-sip"}
        blocked = [n for n in names if n in protected]
        if blocked:
            QMessageBox.warning(
                self, "Protected",
                f"Cannot uninstall protected packages:\n{', '.join(blocked)}")
            return
        reply = QMessageBox.question(
            self, "Uninstall Package",
            f"Uninstall {len(names)} package(s)?\n\n"
            + "\n".join(f"  • {n}" for n in names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._pip_set_busy(True, f"Uninstalling {names[0]}...")
        self._worker = _PipActionWorker("uninstall", " ".join(names))
        self._worker.progress.connect(
            lambda s: self._pip_status.setText(s))
        self._worker.finished.connect(self._pip_action_done)
        self._worker.start()

    def _pip_action_done(self, ok, msg):
        color = "#A6E3A1" if ok else "#F38BA8"
        icon = "✅" if ok else "❌"
        self._pip_status.setText(f"{icon} {msg[-200:]}")
        self._pip_status.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._pip_set_busy(False)
        self._worker = None
        if ok:
            QTimer.singleShot(500, self._pip_load)

    def _pip_set_busy(self, busy, msg=""):
        self._pip_install_btn.setEnabled(not busy)
        self._pip_uninstall_btn.setEnabled(not busy)
        self._pip_refresh_btn.setEnabled(not busy)
        if msg:
            self._pip_status.setText(msg)
            self._pip_status.setStyleSheet(
                "color: #89B4FA; font-size: 12px;")

    # ═════════════════════════════════════════════════════════════════
    #  Windows Apps Actions
    # ═════════════════════════════════════════════════════════════════
    def _app_load(self):
        self._app_status.setText("Loading installed apps...")
        self._app_status.setStyleSheet("color: #89B4FA; font-size: 12px;")
        self._app_refresh_btn.setEnabled(False)
        self._worker = _WinAppListWorker()
        self._worker.finished.connect(self._app_loaded)
        self._worker.error.connect(self._app_error)
        self._worker.start()

    def _app_loaded(self, apps: list):
        self._app_tree.clear()
        self._app_all_data = apps
        for a in apps:
            item = QTreeWidgetItem([
                a["name"],
                a["version"],
                a["publisher"],
                _human(a["size_kb"]),
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, a)
            self._app_tree.addTopLevelItem(item)
        self._app_count.setText(f"{len(apps)} apps")
        self._app_status.setText("")
        self._app_refresh_btn.setEnabled(True)
        self._app_filter(self._app_search.text())
        self._worker = None

    def _app_error(self, msg):
        self._app_status.setText(f"❌ {msg}")
        self._app_status.setStyleSheet("color: #F38BA8; font-size: 12px;")
        self._app_refresh_btn.setEnabled(True)
        self._worker = None

    def _app_filter(self, text: str):
        text = text.lower()
        for i in range(self._app_tree.topLevelItemCount()):
            item = self._app_tree.topLevelItem(i)
            name = item.text(0).lower()
            pub = item.text(2).lower()
            item.setHidden(text not in name and text not in pub)

    def _app_uninstall(self):
        items = self._app_tree.selectedItems()
        if not items:
            QMessageBox.information(
                self, "Uninstall",
                "Select an app from the list first.")
            return
        data = items[0].data(0, Qt.ItemDataRole.UserRole)
        name = data["name"]
        ucmd = data.get("uninstall", "")
        if not ucmd:
            QMessageBox.warning(
                self, "Cannot Uninstall",
                f"No uninstall command found for:\n{name}")
            return
        reply = QMessageBox.question(
            self, "Uninstall Application",
            f"Uninstall {name}?\n\n"
            "This will run the application's uninstaller.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._app_set_busy(True, f"Uninstalling {name}...")
        self._worker = _WinAppUninstallWorker(ucmd, name)
        self._worker.finished.connect(self._app_action_done)
        self._worker.start()

    def _app_action_done(self, ok, msg):
        color = "#A6E3A1" if ok else "#F38BA8"
        icon = "✅" if ok else "❌"
        self._app_status.setText(f"{icon} {msg}")
        self._app_status.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._app_set_busy(False)
        self._worker = None
        if ok:
            QTimer.singleShot(2000, self._app_load)

    def _app_set_busy(self, busy, msg=""):
        self._app_uninstall_btn.setEnabled(not busy)
        self._app_refresh_btn.setEnabled(not busy)
        if msg:
            self._app_status.setText(msg)
            self._app_status.setStyleSheet(
                "color: #89B4FA; font-size: 12px;")

    # ═════════════════════════════════════════════════════════════════
    #  Winget Actions
    # ═════════════════════════════════════════════════════════════════
    def _wg_load(self):
        self._wg_status.setText("Loading winget packages...")
        self._wg_status.setStyleSheet("color: #89B4FA; font-size: 12px;")
        self._wg_refresh_btn.setEnabled(False)
        self._worker = _WinGetListWorker()
        self._worker.finished.connect(self._wg_loaded)
        self._worker.error.connect(self._wg_error)
        self._worker.start()

    def _wg_loaded(self, pkgs: list):
        self._wg_tree.clear()
        for p in pkgs:
            item = QTreeWidgetItem([
                p["name"], p["version"], p.get("id", "")])
            item.setData(0, Qt.ItemDataRole.UserRole, p.get("id", ""))
            self._wg_tree.addTopLevelItem(item)
        self._wg_count.setText(f"{len(pkgs)} packages")
        self._wg_status.setText("")
        self._wg_refresh_btn.setEnabled(True)
        self._wg_filter(self._wg_search.text())
        self._worker = None

    def _wg_error(self, msg):
        self._wg_status.setText(f"❌ {msg}")
        self._wg_status.setStyleSheet("color: #F38BA8; font-size: 12px;")
        self._wg_refresh_btn.setEnabled(True)
        self._worker = None

    def _wg_filter(self, text: str):
        text = text.lower()
        for i in range(self._wg_tree.topLevelItemCount()):
            item = self._wg_tree.topLevelItem(i)
            name = item.text(0).lower()
            pkg_id = item.text(2).lower()
            item.setHidden(text not in name and text not in pkg_id)

    def _wg_install(self):
        pkg_id = self._wg_input.text().strip()
        if not pkg_id:
            QMessageBox.information(
                self, "Install Package",
                "Enter a winget package ID.\n\n"
                "Examples:\n"
                "  7zip.7zip\n"
                "  Gyan.FFmpeg\n"
                "  Git.Git\n"
                "  Notepad++.Notepad++")
            return
        reply = QMessageBox.question(
            self, "Install via Winget",
            f"Install:\n  winget install --id {pkg_id}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._wg_set_busy(True, f"Installing {pkg_id}...")
        self._worker = _WinGetActionWorker("install", pkg_id)
        self._worker.progress.connect(
            lambda s: self._wg_status.setText(s))
        self._worker.finished.connect(self._wg_action_done)
        self._worker.start()

    def _wg_uninstall(self):
        items = self._wg_tree.selectedItems()
        if not items:
            QMessageBox.information(
                self, "Uninstall",
                "Select a package from the list first.")
            return
        pkg_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        name = items[0].text(0)
        if not pkg_id:
            QMessageBox.warning(
                self, "Cannot Uninstall",
                f"No package ID found for: {name}")
            return
        reply = QMessageBox.question(
            self, "Uninstall via Winget",
            f"Uninstall {name} ({pkg_id})?\n\n"
            f"  winget uninstall --id {pkg_id}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._wg_set_busy(True, f"Uninstalling {name}...")
        self._worker = _WinGetActionWorker("uninstall", pkg_id)
        self._worker.progress.connect(
            lambda s: self._wg_status.setText(s))
        self._worker.finished.connect(self._wg_action_done)
        self._worker.start()

    def _wg_action_done(self, ok, msg):
        color = "#A6E3A1" if ok else "#F38BA8"
        icon = "✅" if ok else "❌"
        self._wg_status.setText(f"{icon} {msg[-200:]}")
        self._wg_status.setStyleSheet(f"color: {color}; font-size: 12px;")
        self._wg_set_busy(False)
        self._worker = None
        if ok:
            QTimer.singleShot(1000, self._wg_load)

    def _wg_set_busy(self, busy, msg=""):
        self._wg_install_btn.setEnabled(not busy)
        self._wg_uninstall_btn.setEnabled(not busy)
        self._wg_refresh_btn.setEnabled(not busy)
        if msg:
            self._wg_status.setText(msg)
            self._wg_status.setStyleSheet(
                "color: #89B4FA; font-size: 12px;")
