"""
Notification Manager — centralised control over Windows notifications,
DND scheduling, per-app rules, and quick system toggles.
"""
import os
import json
import subprocess
import winreg
from datetime import datetime, time as dtime

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QIcon
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QCheckBox, QComboBox,
    QTimeEdit, QSpinBox, QMessageBox, QTabWidget, QGroupBox,
    QGridLayout, QSlider, QListWidget, QListWidgetItem,
)

_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "notification_manager.json",
)

# ── Default configuration ──────────────────────────────────────
_DEFAULTS = {
    "dnd_schedule_enabled": False,
    "dnd_start": "22:00",
    "dnd_end": "07:00",
    "digest_interval_min": 15,
    "badge_enabled": True,
    "sound_enabled": True,
    "pet_reaction_enabled": True,
    "blocked_apps": [],
    "priority_apps": [],      # always show even in DND
    "quiet_apps": [],          # batch-only, never toast
    "fullscreen_dnd": False,
    "gaming_dnd": False,
    "preset": "balanced",      # balanced | focus | gaming | sleep | silent
}

_PRESETS = {
    "balanced": {
        "dnd_schedule_enabled": False,
        "digest_interval_min": 15,
        "badge_enabled": True,
        "sound_enabled": True,
        "pet_reaction_enabled": True,
        "fullscreen_dnd": False,
    },
    "focus": {
        "dnd_schedule_enabled": False,
        "digest_interval_min": 30,
        "badge_enabled": True,
        "sound_enabled": False,
        "pet_reaction_enabled": False,
        "fullscreen_dnd": True,
    },
    "gaming": {
        "dnd_schedule_enabled": False,
        "digest_interval_min": 60,
        "badge_enabled": False,
        "sound_enabled": False,
        "pet_reaction_enabled": False,
        "fullscreen_dnd": True,
        "gaming_dnd": True,
    },
    "sleep": {
        "dnd_schedule_enabled": True,
        "dnd_start": "22:00",
        "dnd_end": "07:00",
        "digest_interval_min": 60,
        "badge_enabled": False,
        "sound_enabled": False,
        "pet_reaction_enabled": False,
    },
    "silent": {
        "dnd_schedule_enabled": False,
        "digest_interval_min": 0,
        "badge_enabled": False,
        "sound_enabled": False,
        "pet_reaction_enabled": False,
        "fullscreen_dnd": True,
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Configuration helper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class NotificationConfig:
    """Persist / load notification manager settings."""

    def __init__(self):
        self._data: dict = dict(_DEFAULTS)
        self._load()

    # ── persistence ─────────────────────────────────────────
    def _load(self):
        if os.path.exists(_CONFIG_PATH):
            try:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._data.update(stored)
            except Exception:
                pass

    def save(self):
        try:
            with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    # ── getters / setters ───────────────────────────────────
    def get(self, key: str):
        return self._data.get(key, _DEFAULTS.get(key))

    def set(self, key: str, value):
        self._data[key] = value

    def apply_preset(self, name: str):
        if name in _PRESETS:
            self._data.update(_PRESETS[name])
            self._data["preset"] = name

    def is_dnd_scheduled_now(self) -> bool:
        if not self._data.get("dnd_schedule_enabled"):
            return False
        try:
            now = datetime.now().time()
            start = dtime.fromisoformat(self._data["dnd_start"])
            end = dtime.fromisoformat(self._data["dnd_end"])
            if start <= end:
                return start <= now <= end
            else:  # overnight (e.g. 22:00 → 07:00)
                return now >= start or now <= end
        except Exception:
            return False

    def is_app_blocked(self, app_name: str) -> bool:
        return app_name.lower() in [a.lower() for a in self._data.get("blocked_apps", [])]

    def is_app_priority(self, app_name: str) -> bool:
        return app_name.lower() in [a.lower() for a in self._data.get("priority_apps", [])]

    def is_app_quiet(self, app_name: str) -> bool:
        return app_name.lower() in [a.lower() for a in self._data.get("quiet_apps", [])]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Windows system helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _get_focus_assist_state() -> str:
    """Read current Focus Assist / DND state from registry."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store"
            r"\DefaultAccount\Current\default$windows.data.notifications"
            r".quiethourssettings\windows.data.notifications.quiethourssettings",
        )
        val, _ = winreg.QueryValueEx(key, "Data")
        winreg.CloseKey(key)
        # Byte array; simplified detection
        if val and len(val) > 15:
            if val[15] == 1:
                return "priority_only"
            elif val[15] == 2:
                return "alarms_only"
        return "off"
    except Exception:
        return "unknown"


def _set_focus_assist_ps(mode: str) -> tuple[bool, str]:
    """Use PowerShell to toggle Focus Assist (best-effort)."""
    # Windows doesn't expose a simple API; we use ms-settings URI
    if mode == "off":
        # Open settings so user can toggle
        os.startfile("ms-settings:quiethours")
        return True, "Opened Windows Focus settings."
    else:
        os.startfile("ms-settings:quiethours")
        return True, "Opened Windows Focus settings."


def _get_notification_apps() -> list[dict]:
    """Get list of apps registered for notifications in Windows."""
    apps = []
    try:
        base = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings",
        )
        i = 0
        while True:
            try:
                sub_name = winreg.EnumKey(base, i)
                i += 1
                try:
                    sub = winreg.OpenKey(base, sub_name)
                    enabled = True
                    try:
                        val, _ = winreg.QueryValueEx(sub, "Enabled")
                        enabled = bool(val)
                    except FileNotFoundError:
                        pass
                    # Extract friendly name from the key
                    display = sub_name.split("!")[-1] if "!" in sub_name else sub_name
                    display = display.split("\\")[-1]
                    apps.append({
                        "id": sub_name,
                        "name": display,
                        "enabled": enabled,
                    })
                    winreg.CloseKey(sub)
                except Exception:
                    pass
            except OSError:
                break
        winreg.CloseKey(base)
    except Exception:
        pass
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def _toggle_app_notification(app_id: str, enabled: bool):
    """Toggle an app's notification permission in the registry."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Notifications\Settings"
            rf"\{app_id}",
            0,
            winreg.KEY_SET_VALUE,
        )
        winreg.SetValueEx(key, "Enabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        winreg.CloseKey(key)
    except Exception:
        pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Main dialog
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class NotificationManagerDialog(QDialog):
    """Full notification control center."""

    # Emitted when settings change so the pet can react
    settings_changed = pyqtSignal(dict)

    _BG = "#1e1e2e"
    _CARD = "#313244"
    _ACCENT = "#89b4fa"
    _TEXT = "#cdd6f4"
    _SUB = "#a6adc8"
    _BORDER = "#585b70"
    _HOVER = "#45475a"

    def __init__(self, config: NotificationConfig, notif_digest=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._digest = notif_digest
        self.setWindowTitle("🔔 Notification Manager")
        self.setFixedSize(560, 520)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(
            f"QDialog {{ background: {self._BG}; border: 2px solid {self._ACCENT};"
            f" border-radius: 14px; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(8)

        # Header
        hdr = QLabel("🔔 Notification Manager")
        hdr.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {self._ACCENT};")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(hdr)

        # Tabs
        tabs = QTabWidget()
        tabs.setStyleSheet(self._tab_style())
        tabs.addTab(self._build_presets_tab(), "Presets")
        tabs.addTab(self._build_schedule_tab(), "Schedule")
        tabs.addTab(self._build_apps_tab(), "Apps")
        tabs.addTab(self._build_pet_tab(), "Pet")
        tabs.addTab(self._build_system_tab(), "System")
        lay.addWidget(tabs)

        # Bottom buttons
        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 Save & Apply")
        save_btn.setStyleSheet(self._btn_style(self._ACCENT))
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(self._btn_style(self._BORDER))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

    # ── Tab builders ────────────────────────────────────────
    def _build_presets_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.setContentsMargins(8, 8, 8, 8)

        desc = QLabel("Quick presets to control all notification behaviour at once.")
        desc.setStyleSheet(f"color: {self._SUB}; font-size: 12px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        current = self._config.get("preset")
        self._preset_btns: dict[str, QPushButton] = {}

        presets_info = {
            "balanced":  ("⚖️ Balanced", "Normal notifications, 15-min digest, sounds on."),
            "focus":     ("🎯 Focus", "No sounds, no pet reactions, 30-min digest, fullscreen DND."),
            "gaming":    ("🎮 Gaming", "Total silence, 60-min digest, fullscreen+gaming DND."),
            "sleep":     ("🌙 Sleep", "Scheduled DND 22:00-07:00, no sounds, no badge."),
            "silent":    ("🔇 Silent", "Everything off. Zero interruptions."),
        }

        grid = QGridLayout()
        grid.setSpacing(8)
        for i, (key, (label, tip)) in enumerate(presets_info.items()):
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setChecked(key == current)
            active = self._ACCENT if key == current else self._CARD
            btn.setStyleSheet(self._preset_btn_style(active))
            btn.clicked.connect(lambda _, k=key: self._select_preset(k))
            self._preset_btns[key] = btn
            grid.addWidget(btn, i // 3, i % 3)

        lay.addLayout(grid)

        self._preset_desc = QLabel(presets_info.get(current, ("", ""))[1])
        self._preset_desc.setStyleSheet(f"color: {self._TEXT}; font-size: 11px;")
        self._preset_desc.setWordWrap(True)
        lay.addWidget(self._preset_desc)

        lay.addStretch()
        return w

    def _build_schedule_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.setContentsMargins(8, 8, 8, 8)

        self._sched_enabled = QCheckBox("Enable scheduled Do Not Disturb")
        self._sched_enabled.setStyleSheet(f"color: {self._TEXT}; font-size: 12px;")
        self._sched_enabled.setChecked(self._config.get("dnd_schedule_enabled"))
        lay.addWidget(self._sched_enabled)

        time_row = QHBoxLayout()
        time_row.setSpacing(8)

        start_lbl = QLabel("Start:")
        start_lbl.setStyleSheet(f"color: {self._SUB}; font-size: 12px;")
        time_row.addWidget(start_lbl)

        self._start_time = QTimeEdit()
        self._start_time.setDisplayFormat("HH:mm")
        start_str = self._config.get("dnd_start")
        self._start_time.setTime(dtime.fromisoformat(start_str) if start_str else dtime(22, 0))
        self._start_time.setStyleSheet(self._input_style())
        time_row.addWidget(self._start_time)

        end_lbl = QLabel("End:")
        end_lbl.setStyleSheet(f"color: {self._SUB}; font-size: 12px;")
        time_row.addWidget(end_lbl)

        self._end_time = QTimeEdit()
        self._end_time.setDisplayFormat("HH:mm")
        end_str = self._config.get("dnd_end")
        self._end_time.setTime(dtime.fromisoformat(end_str) if end_str else dtime(7, 0))
        self._end_time.setStyleSheet(self._input_style())
        time_row.addWidget(self._end_time)

        time_row.addStretch()
        lay.addLayout(time_row)

        # Digest interval
        digest_row = QHBoxLayout()
        digest_lbl = QLabel("Digest interval (minutes):")
        digest_lbl.setStyleSheet(f"color: {self._SUB}; font-size: 12px;")
        digest_row.addWidget(digest_lbl)

        self._digest_spin = QSpinBox()
        self._digest_spin.setRange(0, 120)
        self._digest_spin.setValue(self._config.get("digest_interval_min"))
        self._digest_spin.setStyleSheet(self._input_style())
        self._digest_spin.setToolTip("0 = disable digest (show all immediately)")
        digest_row.addWidget(self._digest_spin)
        digest_row.addStretch()
        lay.addLayout(digest_row)

        # Extra toggles
        self._fullscreen_dnd = QCheckBox("Auto-DND in fullscreen apps")
        self._fullscreen_dnd.setStyleSheet(f"color: {self._TEXT}; font-size: 12px;")
        self._fullscreen_dnd.setChecked(self._config.get("fullscreen_dnd"))
        lay.addWidget(self._fullscreen_dnd)

        self._gaming_dnd = QCheckBox("Auto-DND when games detected")
        self._gaming_dnd.setStyleSheet(f"color: {self._TEXT}; font-size: 12px;")
        self._gaming_dnd.setChecked(self._config.get("gaming_dnd"))
        lay.addWidget(self._gaming_dnd)

        lay.addStretch()
        return w

    def _build_apps_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(6)
        lay.setContentsMargins(8, 8, 8, 8)

        info = QLabel("Toggle notifications per app (from Windows registry):")
        info.setStyleSheet(f"color: {self._SUB}; font-size: 11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: 1px solid {self._BORDER}; border-radius: 6px;"
            f" background: {self._BG}; }}"
        )
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setSpacing(4)
        inner_lay.setContentsMargins(6, 6, 6, 6)

        self._app_checks: list[tuple[str, QCheckBox]] = []
        apps = _get_notification_apps()

        if not apps:
            empty = QLabel("Could not read Windows notification apps.")
            empty.setStyleSheet(f"color: {self._SUB};")
            inner_lay.addWidget(empty)
        else:
            for app in apps:
                cb = QCheckBox(app["name"])
                cb.setChecked(app["enabled"])
                cb.setStyleSheet(f"color: {self._TEXT}; font-size: 11px;")
                cb.setToolTip(app["id"])
                inner_lay.addWidget(cb)
                self._app_checks.append((app["id"], cb))

        inner_lay.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll)

        # Per-app Toty rules
        rule_lay = QHBoxLayout()
        rule_lay.setSpacing(6)

        blocked_btn = QPushButton("Manage Blocked Apps")
        blocked_btn.setStyleSheet(self._btn_style(self._BORDER))
        blocked_btn.setToolTip("Apps whose notifications Toty will silently ignore")
        blocked_btn.clicked.connect(lambda: self._edit_app_list("blocked_apps", "Blocked Apps"))
        rule_lay.addWidget(blocked_btn)

        priority_btn = QPushButton("Manage Priority Apps")
        priority_btn.setStyleSheet(self._btn_style(self._BORDER))
        priority_btn.setToolTip("Apps that bypass DND and always show notifications")
        priority_btn.clicked.connect(lambda: self._edit_app_list("priority_apps", "Priority Apps"))
        rule_lay.addWidget(priority_btn)

        lay.addLayout(rule_lay)

        return w

    def _build_pet_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.setContentsMargins(8, 8, 8, 8)

        desc = QLabel("How Toty reacts to notifications:")
        desc.setStyleSheet(f"color: {self._SUB}; font-size: 12px;")
        lay.addWidget(desc)

        self._badge_cb = QCheckBox("Show notification badge on pet")
        self._badge_cb.setStyleSheet(f"color: {self._TEXT}; font-size: 12px;")
        self._badge_cb.setChecked(self._config.get("badge_enabled"))
        lay.addWidget(self._badge_cb)

        self._sound_cb = QCheckBox("Play notification sound")
        self._sound_cb.setStyleSheet(f"color: {self._TEXT}; font-size: 12px;")
        self._sound_cb.setChecked(self._config.get("sound_enabled"))
        lay.addWidget(self._sound_cb)

        self._reaction_cb = QCheckBox("Pet reacts with animation + speech")
        self._reaction_cb.setStyleSheet(f"color: {self._TEXT}; font-size: 12px;")
        self._reaction_cb.setChecked(self._config.get("pet_reaction_enabled"))
        lay.addWidget(self._reaction_cb)

        lay.addSpacing(8)

        hint = QLabel(
            "When badge is enabled, a small counter appears on the pet\n"
            "showing unread notifications. Click the pet to dismiss.\n\n"
            "The pet will play its 'notification' animation and say\n"
            "the app name + title when a new notification arrives."
        )
        hint.setStyleSheet(f"color: {self._SUB}; font-size: 11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        lay.addStretch()
        return w

    def _build_system_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.setContentsMargins(8, 8, 8, 8)

        desc = QLabel("Windows system notification settings:")
        desc.setStyleSheet(f"color: {self._SUB}; font-size: 12px;")
        lay.addWidget(desc)

        # Focus Assist status
        fa_state = _get_focus_assist_state()
        fa_map = {"off": "Off", "priority_only": "Priority Only",
                  "alarms_only": "Alarms Only", "unknown": "Unknown"}
        fa_label = QLabel(f"Focus Assist: {fa_map.get(fa_state, fa_state)}")
        fa_label.setStyleSheet(f"color: {self._TEXT}; font-size: 12px;")
        lay.addWidget(fa_label)

        focus_btn = QPushButton("Open Windows Focus Settings")
        focus_btn.setStyleSheet(self._btn_style(self._BORDER))
        focus_btn.clicked.connect(lambda: os.startfile("ms-settings:quiethours"))
        lay.addWidget(focus_btn)

        lay.addSpacing(4)

        notif_btn = QPushButton("Open Windows Notification Settings")
        notif_btn.setStyleSheet(self._btn_style(self._BORDER))
        notif_btn.clicked.connect(lambda: os.startfile("ms-settings:notifications"))
        lay.addWidget(notif_btn)

        sound_btn = QPushButton("Open Windows Sound Settings")
        sound_btn.setStyleSheet(self._btn_style(self._BORDER))
        sound_btn.clicked.connect(lambda: os.startfile("ms-settings:sound"))
        lay.addWidget(sound_btn)

        lay.addSpacing(8)

        warn = QLabel(
            "Tip: For maximum silence, also disable notification sounds\n"
            "in Windows Settings > System > Notifications."
        )
        warn.setStyleSheet(f"color: {self._SUB}; font-size: 11px;")
        warn.setWordWrap(True)
        lay.addWidget(warn)

        lay.addStretch()
        return w

    # ── Actions ─────────────────────────────────────────────
    def _select_preset(self, key: str):
        for k, btn in self._preset_btns.items():
            btn.setChecked(k == key)
            btn.setStyleSheet(self._preset_btn_style(
                self._ACCENT if k == key else self._CARD))
        self._config.apply_preset(key)
        # Update UI to match preset
        self._sched_enabled.setChecked(self._config.get("dnd_schedule_enabled"))
        self._fullscreen_dnd.setChecked(self._config.get("fullscreen_dnd"))
        self._gaming_dnd.setChecked(self._config.get("gaming_dnd"))
        self._digest_spin.setValue(self._config.get("digest_interval_min"))
        self._badge_cb.setChecked(self._config.get("badge_enabled"))
        self._sound_cb.setChecked(self._config.get("sound_enabled"))
        self._reaction_cb.setChecked(self._config.get("pet_reaction_enabled"))

        presets_desc = {
            "balanced": "Normal notifications, 15-min digest, sounds on.",
            "focus": "No sounds, no pet reactions, 30-min digest, fullscreen DND.",
            "gaming": "Total silence, 60-min digest, fullscreen+gaming DND.",
            "sleep": "Scheduled DND 22:00-07:00, no sounds, no badge.",
            "silent": "Everything off. Zero interruptions.",
        }
        self._preset_desc.setText(presets_desc.get(key, ""))

    def _save(self):
        # Gather from UI
        self._config.set("dnd_schedule_enabled", self._sched_enabled.isChecked())
        self._config.set("dnd_start", self._start_time.time().toString("HH:mm"))
        self._config.set("dnd_end", self._end_time.time().toString("HH:mm"))
        self._config.set("digest_interval_min", self._digest_spin.value())
        self._config.set("fullscreen_dnd", self._fullscreen_dnd.isChecked())
        self._config.set("gaming_dnd", self._gaming_dnd.isChecked())
        self._config.set("badge_enabled", self._badge_cb.isChecked())
        self._config.set("sound_enabled", self._sound_cb.isChecked())
        self._config.set("pet_reaction_enabled", self._reaction_cb.isChecked())

        # Apply per-app Windows toggles
        for app_id, cb in self._app_checks:
            _toggle_app_notification(app_id, cb.isChecked())

        # Update digest interval if available
        if self._digest:
            interval = self._digest_spin.value()
            if interval > 0:
                self._digest.set_interval(interval)

        self._config.save()
        self.settings_changed.emit(self._config._data)
        QMessageBox.information(self, "Saved", "Notification settings saved and applied!")

    def _edit_app_list(self, key: str, title: str):
        """Simple dialog to edit a list of app names."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setFixedSize(320, 300)
        dlg.setStyleSheet(
            f"QDialog {{ background: {self._BG}; border: 2px solid {self._ACCENT};"
            f" border-radius: 10px; }}"
        )
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(12, 12, 12, 12)

        info = QLabel(f"Enter app names (one per line) for {title.lower()}:")
        info.setStyleSheet(f"color: {self._SUB}; font-size: 11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        from PyQt6.QtWidgets import QTextEdit
        te = QTextEdit()
        te.setStyleSheet(
            f"QTextEdit {{ background: {self._CARD}; color: {self._TEXT};"
            f" border: 1px solid {self._BORDER}; border-radius: 6px;"
            f" padding: 6px; font-size: 12px; }}"
        )
        current_list = self._config.get(key) or []
        te.setPlainText("\n".join(current_list))
        lay.addWidget(te)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Save")
        ok_btn.setStyleSheet(self._btn_style(self._ACCENT))
        ok_btn.clicked.connect(lambda: self._save_app_list(key, te.toPlainText(), dlg))
        btn_row.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(self._btn_style(self._BORDER))
        cancel_btn.clicked.connect(dlg.close)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        dlg.exec()

    def _save_app_list(self, key: str, text: str, dlg: QDialog):
        items = [line.strip() for line in text.split("\n") if line.strip()]
        self._config.set(key, items)
        dlg.close()

    # ── Styles ──────────────────────────────────────────────
    def _tab_style(self) -> str:
        return (
            f"QTabWidget::pane {{ border: 1px solid {self._BORDER};"
            f" border-radius: 8px; background: {self._BG}; }}"
            f"QTabBar::tab {{ background: {self._CARD}; color: {self._SUB};"
            f" padding: 8px 14px; border-top-left-radius: 6px;"
            f" border-top-right-radius: 6px; margin-right: 2px; font-size: 11px; }}"
            f"QTabBar::tab:selected {{ background: {self._ACCENT}; color: #1e1e2e;"
            f" font-weight: bold; }}"
            f"QTabBar::tab:hover {{ background: {self._HOVER}; color: {self._TEXT}; }}"
        )

    def _btn_style(self, bg: str) -> str:
        return (
            f"QPushButton {{ background: {bg}; color: {self._TEXT}; border: none;"
            f" border-radius: 8px; padding: 8px 18px; font-size: 12px; }}"
            f"QPushButton:hover {{ background: {self._HOVER}; }}"
        )

    def _preset_btn_style(self, bg: str) -> str:
        return (
            f"QPushButton {{ background: {bg}; color: {self._TEXT}; border: none;"
            f" border-radius: 10px; padding: 14px 10px; font-size: 13px;"
            f" font-weight: bold; }}"
            f"QPushButton:hover {{ background: {self._ACCENT}; color: #1e1e2e; }}"
        )

    def _input_style(self) -> str:
        return (
            f"QTimeEdit, QSpinBox {{ background: {self._CARD}; color: {self._TEXT};"
            f" border: 1px solid {self._BORDER}; border-radius: 6px;"
            f" padding: 4px 8px; font-size: 12px; }}"
        )
