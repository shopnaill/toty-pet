"""
Quick Launcher — radial/pie menu for pinned apps and quick actions.
Shows a circular wheel around the pet with customizable slots.
"""
import math
import os
import subprocess
import json
from core.safe_json import safe_json_save
from PyQt6.QtWidgets import (
    QWidget, QLabel, QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QFileDialog,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QFont, QCursor, QPen, QBrush, QPainterPath


_LAUNCHER_PATH = "launcher_pins.json"

# Default quick-action slots
DEFAULT_SLOTS = [
    {"label": "📸", "name": "Screenshot", "action": "screenshot"},
    {"label": "🍅", "name": "Pomodoro", "action": "pomodoro"},
    {"label": "📝", "name": "Todo", "action": "todo"},
    {"label": "💬", "name": "Chat", "action": "chat"},
    {"label": "📿", "name": "Tasbeeh", "action": "tasbeeh"},
    {"label": "🗂️", "name": "Organize", "action": "organize"},
    {"label": "⏱️", "name": "Focus", "action": "focus"},
    {"label": "📊", "name": "Stats", "action": "stats"},
]


class QuickLauncherWheel(QWidget):
    """A radial menu that appears around the pet on middle-click or shortcut."""
    action_triggered = pyqtSignal(str)  # emits action name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._slots = list(DEFAULT_SLOTS)
        self._custom_apps: list[dict] = []
        self._load_custom()
        self._hovered_index = -1
        self._radius = 90
        self._center = QPoint(120, 120)
        self.setFixedSize(240, 240)
        self.setMouseTracking(True)
        self.hide()

    def _load_custom(self):
        if os.path.exists(_LAUNCHER_PATH):
            try:
                with open(_LAUNCHER_PATH, "r", encoding="utf-8") as f:
                    self._custom_apps = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

    def save_custom(self):
        try:
            safe_json_save(self._custom_apps, _LAUNCHER_PATH)
        except OSError:
            pass

    def add_custom_app(self, name: str, path: str, label: str = "🚀"):
        self._custom_apps.append({"label": label, "name": name, "action": f"app:{path}"})
        self.save_custom()

    def get_all_slots(self) -> list[dict]:
        return self._slots + [
            {"label": a["label"], "name": a["name"], "action": a["action"]}
            for a in self._custom_apps
        ]

    def show_at(self, center: QPoint):
        """Show the wheel centered on a screen position."""
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        self._hovered_index = -1
        self.show()
        self.raise_()
        self.setFocus()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        slots = self.get_all_slots()
        n = len(slots)
        if n == 0:
            p.end()
            return

        cx, cy = self._center.x(), self._center.y()

        # Draw semi-transparent background circle
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(30, 30, 30, 160))
        p.drawEllipse(cx - self._radius - 15, cy - self._radius - 15,
                       (self._radius + 15) * 2, (self._radius + 15) * 2)

        # Draw each slot
        angle_step = 360.0 / n
        font_icon = QFont("Segoe UI Emoji", 16)
        font_label = QFont("Arial", 7, QFont.Weight.Bold)

        for i, slot in enumerate(slots):
            angle_deg = -90 + i * angle_step  # start from top
            angle_rad = math.radians(angle_deg)
            sx = cx + self._radius * math.cos(angle_rad)
            sy = cy + self._radius * math.sin(angle_rad)

            # Slot circle
            is_hovered = (i == self._hovered_index)
            slot_r = 24 if is_hovered else 20
            bg = QColor(80, 160, 255, 200) if is_hovered else QColor(60, 60, 60, 200)
            p.setPen(QPen(QColor(200, 200, 200, 150), 2))
            p.setBrush(bg)
            p.drawEllipse(int(sx - slot_r), int(sy - slot_r), slot_r * 2, slot_r * 2)

            # Icon
            p.setFont(font_icon)
            p.setPen(QColor(255, 255, 255))
            p.drawText(int(sx - 12), int(sy - 4), 24, 20,
                       Qt.AlignmentFlag.AlignCenter, slot["label"])

            # Label below
            p.setFont(font_label)
            p.setPen(QColor(200, 200, 200, 200))
            p.drawText(int(sx - 30), int(sy + slot_r + 2), 60, 14,
                       Qt.AlignmentFlag.AlignCenter, slot["name"])

        # Center dot
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 80))
        p.drawEllipse(cx - 8, cy - 8, 16, 16)

        p.end()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        slots = self.get_all_slots()
        n = len(slots)
        if n == 0:
            return

        cx, cy = self._center.x(), self._center.y()
        best = -1
        best_dist = 999

        for i in range(n):
            angle_deg = -90 + i * (360.0 / n)
            angle_rad = math.radians(angle_deg)
            sx = cx + self._radius * math.cos(angle_rad)
            sy = cy + self._radius * math.sin(angle_rad)
            dist = math.hypot(pos.x() - sx, pos.y() - sy)
            if dist < 30 and dist < best_dist:
                best = i
                best_dist = dist

        if best != self._hovered_index:
            self._hovered_index = best
            self.update()

    def mousePressEvent(self, event):
        if self._hovered_index >= 0:
            slots = self.get_all_slots()
            if self._hovered_index < len(slots):
                action = slots[self._hovered_index]["action"]
                self.action_triggered.emit(action)
        self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()

    def focusOutEvent(self, event):
        self.hide()

    def leaveEvent(self, event):
        self._hovered_index = -1
        self.update()

    def remove_custom_app(self, index: int):
        if 0 <= index < len(self._custom_apps):
            self._custom_apps.pop(index)
            self.save_custom()


class LauncherEditDialog(QDialog):
    """Dialog for adding/removing custom launcher slots."""

    def __init__(self, launcher: QuickLauncherWheel, parent=None):
        super().__init__(parent)
        self._launcher = launcher
        self.setWindowTitle("Edit Quick Launcher")
        self.setFixedSize(400, 350)
        self.setStyleSheet(
            "QDialog { background: #1E1E2E; }"
            "QLabel { color: #CDD6F4; }"
            "QListWidget { background: #313244; color: #CDD6F4; border: 1px solid #585B70;"
            "  border-radius: 4px; padding: 4px; }"
            "QLineEdit { background: #313244; color: #CDD6F4; border: 1px solid #585B70;"
            "  border-radius: 4px; padding: 6px; }"
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "  border-radius: 4px; padding: 6px 14px; font-weight: bold; }"
            "QPushButton:hover { background: #74C7EC; }"
            "QPushButton#remove { background: #F38BA8; }"
            "QPushButton#remove:hover { background: #EBA0AC; }"
        )

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Custom Apps (click to remove):"))

        self._list = QListWidget()
        self._refresh_list()
        layout.addWidget(self._list)

        # Add new app
        add_row = QHBoxLayout()
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("App name")
        add_row.addWidget(self._name_input)

        self._path_input = QLineEdit()
        self._path_input.setPlaceholderText("Path or command")
        add_row.addWidget(self._path_input)

        browse_btn = QPushButton("📂")
        browse_btn.setFixedWidth(36)
        browse_btn.clicked.connect(self._browse)
        add_row.addWidget(browse_btn)
        layout.addLayout(add_row)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ Add App")
        add_btn.clicked.connect(self._add_app)
        btn_row.addWidget(add_btn)

        remove_btn = QPushButton("🗑️ Remove Selected")
        remove_btn.setObjectName("remove")
        remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(remove_btn)
        layout.addLayout(btn_row)

        close_btn = QPushButton("Done")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)

    def _refresh_list(self):
        self._list.clear()
        for i, app in enumerate(self._launcher._custom_apps):
            item = QListWidgetItem(f"{app.get('label', '🚀')} {app['name']} → {app['action']}")
            item.setData(256, i)
            self._list.addItem(item)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Application", "",
            "Executables (*.exe *.bat *.cmd);;All Files (*)"
        )
        if path:
            self._path_input.setText(path)
            if not self._name_input.text():
                self._name_input.setText(os.path.splitext(os.path.basename(path))[0])

    def _add_app(self):
        name = self._name_input.text().strip()
        path = self._path_input.text().strip()
        if not name or not path:
            return
        self._launcher.add_custom_app(name, path)
        self._name_input.clear()
        self._path_input.clear()
        self._refresh_list()

    def _remove_selected(self):
        item = self._list.currentItem()
        if item:
            idx = item.data(256)
            self._launcher.remove_custom_app(idx)
            self._refresh_list()
