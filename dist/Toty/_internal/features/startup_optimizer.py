"""Startup Optimizer — Manage Windows startup apps to speed up boot."""
import os
import sys
import logging
import winreg
from dataclasses import dataclass
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QMessageBox,
    QFrame, QApplication,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QColor

log = logging.getLogger("toty.startup_optimizer")

# ── Catppuccin palette ────────────────────────────────────────────
_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"
_YELLOW = "#F9E2AF"
_MAUVE = "#CBA6F7"

_MENU_SS = f"""
QDialog {{ background: {_BG}; }}
QTreeWidget {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; font-size: 13px;
}}
QTreeWidget::item {{ padding: 4px 0; }}
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
"""

# Registry locations for startup items
_STARTUP_KEYS = [
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU\\Run"),
    (winreg.HKEY_CURRENT_USER,
     r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU\\RunOnce"),
    (winreg.HKEY_LOCAL_MACHINE,
     r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM\\Run"),
]

# Approved startup entries (windows critical – read-only)
_STARTUP_APPROVED = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer"
    r"\StartupApproved\Run"
)


@dataclass
class StartupItem:
    name: str
    command: str
    location: str  # e.g. "HKCU\\Run"
    root: int      # winreg root constant
    key_path: str
    enabled: bool = True


def _scan_startup() -> list[StartupItem]:
    """Read startup entries from registry."""
    items: list[StartupItem] = []
    for root, key_path, loc_name in _STARTUP_KEYS:
        try:
            key = winreg.OpenKeyEx(root, key_path, 0, winreg.KEY_READ)
        except OSError:
            continue
        try:
            i = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, i)
                    items.append(StartupItem(
                        name=name, command=str(value),
                        location=loc_name, root=root,
                        key_path=key_path, enabled=True))
                    i += 1
                except OSError:
                    break
        finally:
            winreg.CloseKey(key)

    # Check disabled entries via StartupApproved
    for root_key in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            approved = winreg.OpenKeyEx(root_key, _STARTUP_APPROVED,
                                        0, winreg.KEY_READ)
            i = 0
            while True:
                try:
                    name, data, _ = winreg.EnumValue(approved, i)
                    if isinstance(data, bytes) and len(data) >= 4:
                        # First byte: 02=disabled, 06=disabled, 03=enabled
                        is_disabled = data[0] in (0x02, 0x06, 0x00)
                        for item in items:
                            if item.name.lower() == name.lower():
                                item.enabled = not is_disabled
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(approved)
        except OSError:
            pass

    return items


def _get_startup_folder_items() -> list[StartupItem]:
    """Scan the Startup folder for .lnk shortcuts."""
    items: list[StartupItem] = []
    startup_dir = os.path.join(
        os.environ.get("APPDATA", ""),
        r"Microsoft\Windows\Start Menu\Programs\Startup")
    if os.path.isdir(startup_dir):
        for f in os.listdir(startup_dir):
            fp = os.path.join(startup_dir, f)
            if os.path.isfile(fp):
                items.append(StartupItem(
                    name=os.path.splitext(f)[0],
                    command=fp,
                    location="Startup Folder",
                    root=-1,  # special marker
                    key_path=startup_dir,
                    enabled=True))
    return items


class StartupOptimizerDialog(QDialog):
    """Manage Windows startup applications."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚀 Startup Optimizer")
        self.setMinimumSize(620, 480)
        self.resize(680, 520)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_MENU_SS)
        self._items: list[StartupItem] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title = QLabel("🚀 Startup Optimizer")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE}; margin-bottom: 4px;")
        lay.addWidget(title)

        info = QLabel("Manage apps that run when Windows starts. "
                       "Disable to speed up boot time.")
        info.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        # Tree
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Name", "Status", "Location", "Command"])
        self._tree.setColumnCount(4)
        hdr = self._tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tree.setColumnWidth(0, 180)
        self._tree.setRootIsDecorated(False)
        self._tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        lay.addWidget(self._tree)

        # Status
        self._status = QLabel("")
        self._status.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        lay.addWidget(self._status)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_toggle = QPushButton("⏸ Disable Selected")
        self._btn_toggle.clicked.connect(self._toggle_selected)
        btn_row.addWidget(self._btn_toggle)

        self._btn_delete = QPushButton("🗑️ Remove Selected")
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_delete.setStyleSheet(
            f"QPushButton {{ background: {_SURFACE}; color: {_RED}; "
            f"border: 1px solid {_RED}; border-radius: 6px; "
            f"padding: 8px 16px; }}"
            f"QPushButton:hover {{ background: {_RED}; color: {_BG}; }}")
        btn_row.addWidget(self._btn_delete)

        btn_row.addStretch()

        self._btn_refresh = QPushButton("🔄 Refresh")
        self._btn_refresh.clicked.connect(self._scan)
        btn_row.addWidget(self._btn_refresh)

        self._btn_folder = QPushButton("📂 Open Startup Folder")
        self._btn_folder.clicked.connect(self._open_startup_folder)
        btn_row.addWidget(self._btn_folder)

        lay.addLayout(btn_row)

        self._tree.currentItemChanged.connect(self._on_selection)
        self._scan()

    def _scan(self):
        self._tree.clear()
        self._items = _scan_startup() + _get_startup_folder_items()
        for item in self._items:
            row = QTreeWidgetItem()
            row.setText(0, item.name)
            if item.enabled:
                row.setText(1, "✅ Enabled")
                row.setForeground(1, QColor(_GREEN))
            else:
                row.setText(1, "⏸ Disabled")
                row.setForeground(1, QColor(_YELLOW))
            row.setText(2, item.location)
            row.setText(3, item.command)
            row.setData(0, Qt.ItemDataRole.UserRole, item)
            self._tree.addTopLevelItem(row)
        self._status.setText(f"Found {len(self._items)} startup items")
        self._btn_toggle.setEnabled(False)
        self._btn_delete.setEnabled(False)

    def _on_selection(self, current, _prev):
        if current is None:
            self._btn_toggle.setEnabled(False)
            self._btn_delete.setEnabled(False)
            return
        item: StartupItem = current.data(0, Qt.ItemDataRole.UserRole)
        self._btn_toggle.setEnabled(True)
        self._btn_delete.setEnabled(True)
        if item.enabled:
            self._btn_toggle.setText("⏸ Disable Selected")
        else:
            self._btn_toggle.setText("▶️ Enable Selected")

    def _get_selected(self) -> Optional[StartupItem]:
        cur = self._tree.currentItem()
        if cur is None:
            return None
        return cur.data(0, Qt.ItemDataRole.UserRole)

    def _toggle_selected(self):
        item = self._get_selected()
        if not item:
            return
        if item.location == "Startup Folder":
            QMessageBox.information(
                self, "Info",
                "Startup folder items can only be removed, not toggled.\n"
                "Use Remove to delete the shortcut.")
            return
        # Toggle via StartupApproved\Run
        root = item.root
        try:
            key = winreg.CreateKeyEx(
                root, _STARTUP_APPROVED, 0,
                winreg.KEY_READ | winreg.KEY_SET_VALUE)
            # Read current value or create default
            try:
                data, dtype = winreg.QueryValueEx(key, item.name)
                if not isinstance(data, bytes):
                    data = b"\x02" + b"\x00" * 11
            except OSError:
                data = b"\x02" + b"\x00" * 11

            new_data = bytearray(data)
            if len(new_data) < 1:
                new_data = bytearray(12)
            if item.enabled:
                new_data[0] = 0x03  # disable
            else:
                new_data[0] = 0x02  # enable (confusing but Windows uses 02=enabled, 03=disabled)
                # Actually: 02=enabled, 03=disabled in StartupApproved
                new_data[0] = 0x06 if item.enabled else 0x02

            winreg.SetValueEx(key, item.name, 0, winreg.REG_BINARY,
                              bytes(new_data))
            winreg.CloseKey(key)
            action = "Disabled" if item.enabled else "Enabled"
            self._status.setText(f"{action}: {item.name}")
            self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            self._scan()
        except OSError as e:
            QMessageBox.warning(self, "Error",
                                f"Cannot toggle: {e}\n\n"
                                "Try running as Administrator for HKLM items.")

    def _delete_selected(self):
        item = self._get_selected()
        if not item:
            return
        ans = QMessageBox.question(
            self, "Confirm",
            f"Remove startup entry?\n\n{item.name}\n{item.command}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if ans != QMessageBox.StandardButton.Yes:
            return

        if item.location == "Startup Folder":
            try:
                os.remove(item.command)
                self._status.setText(f"Removed: {item.name}")
                self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            except OSError as e:
                QMessageBox.warning(self, "Error", str(e))
        else:
            try:
                key = winreg.OpenKeyEx(
                    item.root, item.key_path, 0, winreg.KEY_SET_VALUE)
                winreg.DeleteValue(key, item.name)
                winreg.CloseKey(key)
                self._status.setText(f"Removed: {item.name}")
                self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
            except OSError as e:
                QMessageBox.warning(self, "Error",
                                    f"Cannot remove: {e}\n\n"
                                    "Try running as Administrator for HKLM items.")
        self._scan()

    @staticmethod
    def _open_startup_folder():
        path = os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup")
        os.startfile(path)
