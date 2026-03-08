"""
System Tray Integration — proper QSystemTrayIcon with status,
quick menu, DND, show/hide pet, and key stats.
"""
import logging
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import QObject, pyqtSignal, QSize

log = logging.getLogger("toty")


def _generate_tray_icon(mood_color: str = "#5599FF") -> QIcon:
    """Generate a small tray icon with mood-colored circle."""
    pm = QPixmap(32, 32)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(mood_color))
    p.setPen(QColor("#333"))
    p.drawEllipse(2, 2, 28, 28)
    # Eyes
    p.setBrush(QColor("#333"))
    p.drawEllipse(9, 10, 5, 5)
    p.drawEllipse(18, 10, 5, 5)
    # Smile
    p.setPen(QColor("#333"))
    p.drawArc(10, 14, 12, 10, 0, -180 * 16)
    p.end()
    return QIcon(pm)


class TrayManager(QObject):
    """Manages system tray icon and menu."""
    show_pet = pyqtSignal()
    hide_pet = pyqtSignal()
    toggle_dnd = pyqtSignal()
    toggle_focus = pyqtSignal()
    open_dashboard = pyqtSignal()
    open_launcher = pyqtSignal()
    open_settings = pyqtSignal()
    quit_app = pyqtSignal()

    def __init__(self, pet_name: str = "Toty"):
        super().__init__()
        self._pet_name = pet_name
        self._visible = True
        self._tray = QSystemTrayIcon()
        self._tray.setIcon(_generate_tray_icon())
        self._tray.setToolTip(f"🐾 {pet_name}")
        self._tray.activated.connect(self._on_activated)

        self._build_menu()

    def _build_menu(self):
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #2B2B2B; border: 1px solid #555; }"
            "QMenu::item { padding: 6px 20px; color: #EEE; }"
            "QMenu::item:selected { background: #5599FF; color: white; }"
        )

        title = QAction(f"🐾 {self._pet_name}", menu)
        title.setEnabled(False)
        menu.addAction(title)
        menu.addSeparator()

        show_act = QAction("👁️ Show / Hide Pet", menu)
        show_act.triggered.connect(self._toggle_visibility)
        menu.addAction(show_act)

        dash_act = QAction("📊 Dashboard", menu)
        dash_act.triggered.connect(self.open_dashboard.emit)
        menu.addAction(dash_act)

        launch_act = QAction("🎯 Quick Launcher", menu)
        launch_act.triggered.connect(self.open_launcher.emit)
        menu.addAction(launch_act)

        menu.addSeparator()

        self._dnd_act = QAction("🔕 Do Not Disturb", menu)
        self._dnd_act.setCheckable(True)
        self._dnd_act.triggered.connect(self.toggle_dnd.emit)
        menu.addAction(self._dnd_act)

        self._focus_act = QAction("🎯 Focus Mode", menu)
        self._focus_act.setCheckable(True)
        self._focus_act.triggered.connect(self.toggle_focus.emit)
        menu.addAction(self._focus_act)

        menu.addSeparator()

        quit_act = QAction("❌ Quit", menu)
        quit_act.triggered.connect(self.quit_app.emit)
        menu.addAction(quit_act)

        self._tray.setContextMenu(menu)

    def _toggle_visibility(self):
        self._visible = not self._visible
        if self._visible:
            self.show_pet.emit()
        else:
            self.hide_pet.emit()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def update_tooltip(self, text: str):
        self._tray.setToolTip(text)

    def update_mood_color(self, color: str):
        self._tray.setIcon(_generate_tray_icon(color))

    def set_dnd(self, on: bool):
        self._dnd_act.setChecked(on)

    def set_focus(self, on: bool):
        self._focus_act.setChecked(on)

    def show_message(self, title: str, msg: str, duration_ms: int = 3000):
        self._tray.showMessage(title, msg,
                               QSystemTrayIcon.MessageIcon.Information,
                               duration_ms)

    def stop(self):
        self._tray.hide()
