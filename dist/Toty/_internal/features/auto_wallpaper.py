"""Auto Wallpaper — Change desktop wallpaper by time of day, with folder-based rotation."""
import ctypes
import json
import os
import random
import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QListWidget, QListWidgetItem, QComboBox,
    QCheckBox, QApplication, QMessageBox, QSpinBox,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QPixmap, QIcon

log = logging.getLogger("toty.auto_wallpaper")

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"
_YELLOW = "#F9E2AF"

_SS = f"""
QDialog {{ background: {_BG}; }}
QListWidget {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; font-size: 13px; padding: 4px;
}}
QListWidget::item {{ padding: 4px 8px; border-radius: 4px; }}
QListWidget::item:selected {{ background: #45475A; color: {_BLUE}; }}
QPushButton {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background: #45475A; border-color: {_BLUE}; }}
QPushButton:pressed {{ background: {_BLUE}; color: {_BG}; }}
QLabel {{ color: {_TEXT}; }}
QComboBox {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 6px 10px; font-size: 13px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {_SURFACE}; color: {_TEXT}; selection-background-color: #45475A;
}}
QCheckBox {{ color: {_TEXT}; font-size: 13px; }}
QSpinBox {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 4px 8px; font-size: 13px;
}}
"""

_DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "wallpaper_config.json")

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

# Windows API for setting wallpaper
SPI_SETDESKWALLPAPER = 0x0014
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDWININICHANGE = 0x02

# Time periods
_PERIODS = [
    ("🌅 Morning", "morning", 6, 12),
    ("☀️ Afternoon", "afternoon", 12, 17),
    ("🌇 Evening", "evening", 17, 21),
    ("🌙 Night", "night", 21, 6),
]


def set_wallpaper(path: str) -> bool:
    """Set the Windows desktop wallpaper."""
    if not os.path.isfile(path):
        return False
    try:
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, path,
            SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE)
        return bool(result)
    except Exception as e:
        log.warning("Failed to set wallpaper: %s", e)
        return False


def _get_images_in_folder(folder: str) -> list[str]:
    """Get all image files in a folder."""
    images = []
    if not os.path.isdir(folder):
        return images
    for f in os.listdir(folder):
        if os.path.splitext(f)[1].lower() in _IMAGE_EXTS:
            images.append(os.path.join(folder, f))
    return sorted(images)


class AutoWallpaper:
    """Background wallpaper rotation engine."""

    def __init__(self, settings=None):
        self._config = self._load()
        self._last_period = ""
        self._timer = QTimer()
        self._timer.timeout.connect(self._check)
        if self._config.get("enabled"):
            self._timer.start(60000)  # check every minute

    def _load(self) -> dict:
        if os.path.isfile(_DATA_FILE):
            try:
                with open(_DATA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "enabled": False,
            "mode": "time",  # "time" or "interval"
            "interval_min": 30,
            "folders": {},  # period -> folder path
            "single_folder": "",
            "shuffle": True,
            "_index": 0,
        }

    def _save(self):
        try:
            with open(_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            log.warning("Cannot save wallpaper config: %s", e)

    def start(self):
        self._config["enabled"] = True
        self._save()
        if not self._timer.isActive():
            self._timer.start(60000)
        self._check()

    def stop(self):
        self._config["enabled"] = False
        self._save()
        self._timer.stop()

    def is_enabled(self) -> bool:
        return self._config.get("enabled", False)

    def _current_period(self) -> str:
        hour = datetime.now().hour
        for _, key, start, end in _PERIODS:
            if start < end:
                if start <= hour < end:
                    return key
            else:  # wraps midnight
                if hour >= start or hour < end:
                    return key
        return "morning"

    def _check(self):
        if not self._config.get("enabled"):
            return
        mode = self._config.get("mode", "time")

        if mode == "time":
            period = self._current_period()
            if period != self._last_period:
                self._last_period = period
                folder = self._config.get("folders", {}).get(period, "")
                if folder:
                    self._set_random(folder)
        elif mode == "interval":
            folder = self._config.get("single_folder", "")
            if folder:
                self._set_random(folder)

    def _set_random(self, folder: str):
        images = _get_images_in_folder(folder)
        if not images:
            return
        if self._config.get("shuffle", True):
            img = random.choice(images)
        else:
            idx = self._config.get("_index", 0) % len(images)
            img = images[idx]
            self._config["_index"] = idx + 1
            self._save()
        set_wallpaper(img)
        log.info("Wallpaper set to: %s", img)

    def set_now(self, path: str):
        """Set a specific wallpaper immediately."""
        set_wallpaper(path)


class AutoWallpaperDialog(QDialog):
    """Configure automatic wallpaper rotation."""

    def __init__(self, wallpaper_engine: AutoWallpaper, parent=None):
        super().__init__(parent)
        self._engine = wallpaper_engine
        self.setWindowTitle("🖼️ Auto Wallpaper")
        self.setMinimumSize(520, 480)
        self.resize(540, 500)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title = QLabel("🖼️ Auto Wallpaper")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE};")
        lay.addWidget(title)

        # Enable toggle
        self._chk_enable = QCheckBox("Enable auto wallpaper rotation")
        self._chk_enable.setChecked(self._engine._config.get("enabled", False))
        self._chk_enable.toggled.connect(self._toggle_enable)
        lay.addWidget(self._chk_enable)

        # Mode
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_row.addWidget(QLabel("Mode:"))
        self._mode = QComboBox()
        self._mode.addItems(["🕐 By Time of Day", "⏱️ Timed Interval"])
        if self._engine._config.get("mode") == "interval":
            self._mode.setCurrentIndex(1)
        self._mode.currentIndexChanged.connect(self._on_mode_change)
        mode_row.addWidget(self._mode)

        mode_row.addWidget(QLabel("Interval:"))
        self._interval = QSpinBox()
        self._interval.setRange(1, 1440)
        self._interval.setSuffix(" min")
        self._interval.setValue(
            self._engine._config.get("interval_min", 30))
        self._interval.setEnabled(self._mode.currentIndex() == 1)
        mode_row.addWidget(self._interval)

        lay.addLayout(mode_row)

        # Shuffle
        self._chk_shuffle = QCheckBox("🔀 Shuffle (random order)")
        self._chk_shuffle.setChecked(
            self._engine._config.get("shuffle", True))
        lay.addWidget(self._chk_shuffle)

        # Time-of-day folders
        lay.addWidget(QLabel("📁 Wallpaper Folders by Time of Day:"))
        self._folder_widgets: dict[str, QLabel] = {}
        folders = self._engine._config.get("folders", {})

        for display, key, _, _ in _PERIODS:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(QLabel(f"{display}:"))
            lbl = QLabel(folders.get(key, "Not set"))
            lbl.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
            lbl.setMinimumWidth(200)
            self._folder_widgets[key] = lbl
            row.addWidget(lbl, 1)
            btn = QPushButton("📂")
            btn.setFixedWidth(40)
            btn.clicked.connect(lambda _, k=key: self._pick_folder(k))
            row.addWidget(btn)
            lay.addLayout(row)

        # Single folder (for interval mode)
        sf_row = QHBoxLayout()
        sf_row.setSpacing(6)
        sf_row.addWidget(QLabel("📂 Single Folder:"))
        self._lbl_single = QLabel(
            self._engine._config.get("single_folder", "Not set"))
        self._lbl_single.setStyleSheet(f"color: {_TEXT}; font-size: 12px;")
        sf_row.addWidget(self._lbl_single, 1)
        btn_sf = QPushButton("📂")
        btn_sf.setFixedWidth(40)
        btn_sf.clicked.connect(self._pick_single_folder)
        sf_row.addWidget(btn_sf)
        lay.addLayout(sf_row)

        # Preview
        self._preview = QLabel()
        self._preview.setFixedHeight(120)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet(
            f"background: {_SURFACE}; border: 2px solid #45475A; "
            f"border-radius: 8px;")
        lay.addWidget(self._preview)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_apply = QPushButton("✅ Apply & Save")
        btn_apply.clicked.connect(self._apply)
        btn_apply.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 8px 16px; font-weight: bold; }}")
        btn_row.addWidget(btn_apply)

        btn_now = QPushButton("🎲 Random Now")
        btn_now.clicked.connect(self._random_now)
        btn_row.addWidget(btn_now)

        btn_pick = QPushButton("🖼️ Set Image…")
        btn_pick.clicked.connect(self._pick_image)
        btn_row.addWidget(btn_pick)

        lay.addLayout(btn_row)

        self._status = QLabel("")
        self._status.setStyleSheet(f"font-size: 12px;")
        lay.addWidget(self._status)

    def _toggle_enable(self, checked: bool):
        if checked:
            self._engine.start()
        else:
            self._engine.stop()

    def _on_mode_change(self, idx: int):
        self._interval.setEnabled(idx == 1)

    def _pick_folder(self, period: str):
        path = QFileDialog.getExistingDirectory(
            self, f"Select wallpaper folder for {period}")
        if path:
            if "folders" not in self._engine._config:
                self._engine._config["folders"] = {}
            self._engine._config["folders"][period] = path
            self._folder_widgets[period].setText(path)
            # Preview first image
            images = _get_images_in_folder(path)
            if images:
                pix = QPixmap(images[0]).scaled(
                    self._preview.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                self._preview.setPixmap(pix)

    def _pick_single_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select wallpaper folder")
        if path:
            self._engine._config["single_folder"] = path
            self._lbl_single.setText(path)

    def _apply(self):
        cfg = self._engine._config
        cfg["mode"] = "interval" if self._mode.currentIndex() == 1 else "time"
        cfg["interval_min"] = self._interval.value()
        cfg["shuffle"] = self._chk_shuffle.isChecked()
        cfg["enabled"] = self._chk_enable.isChecked()
        self._engine._save()

        if cfg["enabled"]:
            self._engine.start()
            # For interval mode, restart timer with new interval
            if cfg["mode"] == "interval":
                self._engine._timer.setInterval(
                    cfg["interval_min"] * 60000)

        self._status.setText("✅ Settings saved")
        self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")

    def _random_now(self):
        period = self._engine._current_period()
        folder = self._engine._config.get("folders", {}).get(
            period, self._engine._config.get("single_folder", ""))
        if folder:
            self._engine._set_random(folder)
            self._status.setText("✅ Wallpaper changed!")
            self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
        else:
            self._status.setText("❌ No folder set for current period")
            self._status.setStyleSheet(f"color: {_RED}; font-size: 12px;")

    def _pick_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Wallpaper",
            filter="Images (*.jpg *.jpeg *.png *.bmp *.gif *.webp)")
        if path:
            set_wallpaper(path)
            pix = QPixmap(path).scaled(
                self._preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self._preview.setPixmap(pix)
            self._status.setText(f"✅ Wallpaper set!")
            self._status.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
