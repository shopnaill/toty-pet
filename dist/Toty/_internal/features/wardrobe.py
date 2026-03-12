"""
Pet Wardrobe — unlockable cosmetic accessories tied to achievements/level.
"""
import json
import os
import logging
from core.safe_json import safe_json_save
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPixmap, QPainter

log = logging.getLogger("toty.wardrobe")
_FILE = "wardrobe.json"

# (id, display_name, emoji, unlock_condition_description, unlock_check_fn_key)
WARDROBE_ITEMS = [
    ("crown",       "👑 Crown",       "Level 10 — royalty unlocked!",    "level_10"),
    ("party_hat",   "🎉 Party Hat",   "Reach 7-day streak",             "streak_7"),
    ("bow_tie",     "🎀 Bow Tie",     "Complete 10 pomodoros",           "pomodoro_10"),
    ("wizard_hat",  "🧙 Wizard Hat",  "Reach Level 20",                 "level_20"),
    ("cape",        "🦸 Cape",        "3-hour focus session",            "focus_3h"),
    ("flower",      "🌸 Flower",      "Use Toty for 30 days",           "days_30"),
    ("star_badge",  "⭐ Star Badge",  "Unlock 5 achievements",          "achievements_5"),
    ("sunglasses",  "😎 Sunglasses",  "Available from start!",          "free"),
    ("halo",        "😇 Halo",        "Log 50 habits",                  "habits_50"),
    ("pirate_hat",  "🏴‍☠️ Pirate Hat",  "Reach Level 15",                 "level_15"),
]


class Wardrobe:
    """Manages unlocked accessories and current equipped cosmetic."""

    def __init__(self):
        self._unlocked: set[str] = {"sunglasses"}  # free items
        self._equipped: str = ""
        self._load()

    def _load(self):
        if os.path.exists(_FILE):
            try:
                with open(_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._unlocked = set(data.get("unlocked", ["sunglasses"]))
                self._equipped = data.get("equipped", "")
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        safe_json_save({
            "unlocked": list(self._unlocked),
            "equipped": self._equipped,
        }, _FILE)

    def check_unlocks(self, stats, habits) -> list[str]:
        """Check unlock conditions and return newly unlocked item names."""
        newly = []
        level = stats.data.get("level", 1)
        streak = stats.data.get("current_streak", 0)
        pomodoros = stats.data.get("total_pomodoros", 0)
        days = stats.data.get("total_sessions", 0)
        unlocked_ach = stats.data.get("unlocked_achievements", 0)

        # Count total habit logs
        total_habits_logged = sum(
            sum(day_log.values())
            for day_log in habits.data.get("log", {}).values()
        )

        checks = {
            "free":            True,
            "level_10":        level >= 10,
            "level_15":        level >= 15,
            "level_20":        level >= 20,
            "streak_7":        streak >= 7,
            "pomodoro_10":     pomodoros >= 10,
            "focus_3h":        False,  # checked externally via milestone
            "days_30":         days >= 30,
            "achievements_5":  unlocked_ach >= 5,
            "habits_50":       total_habits_logged >= 50,
        }

        for item_id, _name, _desc, key in WARDROBE_ITEMS:
            if item_id not in self._unlocked and checks.get(key, False):
                self._unlocked.add(item_id)
                newly.append(item_id)

        if newly:
            self.save()
        return newly

    def unlock(self, item_id: str):
        """Manually unlock an item (e.g. from focus milestone)."""
        if item_id not in self._unlocked:
            self._unlocked.add(item_id)
            self.save()

    def equip(self, item_id: str) -> bool:
        if item_id in self._unlocked:
            self._equipped = item_id
            self.save()
            return True
        return False

    def unequip(self):
        self._equipped = ""
        self.save()

    def get_equipped(self) -> str:
        return self._equipped

    def is_unlocked(self, item_id: str) -> bool:
        return item_id in self._unlocked

    def get_unlocked(self) -> set[str]:
        return set(self._unlocked)


class WardrobeDialog(QDialog):
    """Visual wardrobe selection dialog."""
    accessory_changed = pyqtSignal(str)  # item_id or "" for unequip

    def __init__(self, wardrobe: Wardrobe, draw_fn, parent=None):
        super().__init__(parent)
        self._wardrobe = wardrobe
        self._draw_fn = draw_fn  # callable(name) -> QPixmap
        self.setWindowTitle("👗 Pet Wardrobe")
        self.setFixedSize(420, 480)
        self.setStyleSheet(
            "QDialog { background: #1e1e1e; }"
            "QLabel { color: #ddd; }"
            "QPushButton { background: #333; color: #ccc; border: 1px solid #555; "
            "  border-radius: 6px; padding: 4px; }"
            "QPushButton:hover { background: #444; border-color: #888; }"
            "QPushButton:checked { background: #3a6ea5; border-color: #5599ff; }"
        )
        layout = QVBoxLayout(self)

        title = QLabel("👗 Pet Wardrobe — Choose an Accessory")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #ff9966;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(8)

        self._buttons: list[QPushButton] = []
        equipped = wardrobe.get_equipped()

        for i, (item_id, display, desc, _key) in enumerate(WARDROBE_ITEMS):
            unlocked = wardrobe.is_unlocked(item_id)
            frame = QFrame()
            frame.setFixedSize(120, 130)
            frame_lay = QVBoxLayout(frame)
            frame_lay.setContentsMargins(4, 4, 4, 4)
            frame_lay.setSpacing(2)

            btn = QPushButton()
            btn.setCheckable(True)
            btn.setChecked(item_id == equipped)
            btn.setFixedSize(80, 80)

            if unlocked:
                pm = draw_fn(item_id)
                if not pm.isNull():
                    from PyQt6.QtGui import QIcon
                    scaled = pm.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                       Qt.TransformationMode.SmoothTransformation)
                    btn.setIcon(QIcon(scaled))
                    btn.setIconSize(scaled.size())
                else:
                    btn.setText(display.split(" ")[0])
                    btn.setStyleSheet(btn.styleSheet() + "font-size: 28px;")
                btn.clicked.connect(lambda checked, iid=item_id: self._on_select(iid))
            else:
                btn.setText("🔒")
                btn.setStyleSheet(btn.styleSheet() + "font-size: 28px; color: #666;")
                btn.setEnabled(False)
                btn.setToolTip(f"Unlock: {desc}")

            frame_lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)

            label = QLabel(display if unlocked else "???")
            label.setFont(QFont("Segoe UI", 8))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("color: #aaa;" if unlocked else "color: #555;")
            frame_lay.addWidget(label)

            if not unlocked:
                cond = QLabel(desc)
                cond.setFont(QFont("Segoe UI", 7))
                cond.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cond.setStyleSheet("color: #666;")
                cond.setWordWrap(True)
                frame_lay.addWidget(cond)

            grid.addWidget(frame, i // 3, i % 3)
            self._buttons.append(btn)

        layout.addLayout(grid)

        # Unequip button
        unequip_btn = QPushButton("❌ Remove Accessory")
        unequip_btn.clicked.connect(self._on_unequip)
        layout.addWidget(unequip_btn)

    def _on_select(self, item_id: str):
        if self._wardrobe.equip(item_id):
            self.accessory_changed.emit(item_id)
            # Uncheck all other buttons
            for i, (iid, *_) in enumerate(WARDROBE_ITEMS):
                if i < len(self._buttons):
                    self._buttons[i].setChecked(iid == item_id)

    def _on_unequip(self):
        self._wardrobe.unequip()
        self.accessory_changed.emit("")
        for btn in self._buttons:
            btn.setChecked(False)
