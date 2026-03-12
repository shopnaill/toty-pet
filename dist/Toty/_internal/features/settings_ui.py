"""
Settings UI Dialog for Toty Desktop Pet.

Provides a tabbed interface for configuring all pet settings.
Uses the centralised Toty dark theme.
"""

from PyQt6.QtWidgets import (
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QSpinBox, QDoubleSpinBox, QCheckBox,
    QLineEdit, QComboBox, QPushButton, QGroupBox, QScrollArea,
    QFrame,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

try:
    from features.theme import C
except Exception:
    class C:
        ACCENT = "#4ADE80"; TEXT_DIM = "#6B7280"; BG_DEEP = "#070B09"
        BG_DARK = "#0D1411"; RED = "#F87171"


class SettingsDialog(QDialog):
    """Tabbed settings dialog for all pet configuration."""

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._widgets: dict[str, QWidget] = {}
        self.setWindowTitle("Toty Settings")
        self.setMinimumSize(560, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        # ── Header ──
        hdr = QLabel("⚙️  Settings")
        hdr.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACCENT}; background: transparent; padding-bottom: 2px;")
        root.addWidget(hdr)

        sub = QLabel("Configure your Toty desktop pet experience")
        sub.setStyleSheet(f"color: {C.TEXT_DIM}; font-size: 12px; background: transparent;")
        root.addWidget(sub)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C.BG_DARK};")
        root.addWidget(line)

        # ── Tabs ──
        self._tabs = QTabWidget()
        root.addWidget(self._tabs, 1)

        self._build_general_tab()
        self._build_productivity_tab()
        self._build_behavior_tab()
        self._build_prayer_tab()
        self._build_ai_tab()
        self._build_advanced_tab()

        # ── Button bar ──
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        reset_btn = QPushButton("Reset Defaults")
        reset_btn.setObjectName("danger")
        reset_btn.clicked.connect(self._reset_defaults)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("  Save  ")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save_and_close)

        btn_layout.addWidget(reset_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        root.addLayout(btn_layout)

    # ── Tab builders ──

    def _build_general_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow("Pet Name:", self._line("pet_name"))
        form.addRow("Current Skin:", self._combo("current_skin", self._get_skin_choices()))
        form.addRow(self._check("enable_system_tray", "Show System Tray Icon"))
        form.addRow(self._check("enable_achievements", "Enable Achievements"))
        form.addRow(self._check("enable_xp_system", "Enable XP System"))
        form.addRow(self._check("enable_mini_todo", "Enable Mini Todo Widget"))
        form.addRow(self._check("enable_multi_monitor", "Multi-Monitor Roaming"))
        form.addRow(self._check("bubble_mood_colors", "Mood-Colored Speech Bubbles"))
        self._tabs.addTab(w, "🏠 General")

    def _build_productivity_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow("Pomodoro Work (min):", self._spin("pomodoro_work_min", 1, 120))
        form.addRow("Pomodoro Break (min):", self._spin("pomodoro_break_min", 1, 30))
        form.addRow("Stretch Reminder (min):", self._spin("stretch_reminder_min", 5, 120))
        form.addRow("Water Reminder (min):", self._spin("water_reminder_min", 5, 120))
        form.addRow("Daily Focus Goal (min):", self._spin("daily_goal_focus_min", 10, 480))
        form.addRow(self._check("enable_reminders", "Enable Break Reminders"))
        form.addRow(self._check("focus_mode", "Focus Mode (suppress fun)"))
        form.addRow(self._check("enable_desktop_organizer", "Auto-Organize Desktop"))
        form.addRow("Organize Interval (sec):", self._spin("organizer_check_sec", 5, 300))
        self._tabs.addTab(w, "⏱ Productivity")

    def _build_behavior_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow("Speech Cooldown (sec):", self._spin("speech_cooldown_sec", 1, 60))
        form.addRow("Idle Sleep Timeout (sec):", self._spin("idle_sleep_timeout_sec", 5, 120))
        form.addRow("Brain Tick (ms):", self._spin("brain_tick_ms", 500, 10000))
        form.addRow("Context Check (ms):", self._spin("context_check_ms", 500, 10000))
        form.addRow("Mood Decay Rate:", self._dspin("mood_decay_rate", 0.0, 5.0, 1))
        form.addRow("Energy Decay Rate:", self._dspin("energy_decay_rate", 0.0, 5.0, 1))
        form.addRow("Wander-to-Mouse Chance:", self._dspin("wander_to_mouse_chance", 0.0, 1.0, 2))
        form.addRow(self._check("enable_follow_cursor", "Follow Cursor"))
        form.addRow("Follow Speed:", self._spin("follow_cursor_speed", 1, 20))
        form.addRow(self._check("enable_keyboard_tracking", "Track Keyboard"))
        form.addRow(self._check("enable_window_tracking", "Track Active Windows"))
        form.addRow(self._check("taskbar_gravity", "Taskbar Gravity"))
        self._tabs.addTab(w, "🐾 Behavior")

    def _build_prayer_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow(self._check("enable_prayer_times", "Enable Prayer Times"))
        form.addRow("Reminder Before (min):", self._spin("prayer_reminder_min", 1, 60))
        form.addRow("Latitude:", self._dspin("prayer_latitude", -90, 90, 4))
        form.addRow("Longitude:", self._dspin("prayer_longitude", -180, 180, 4))
        form.addRow("Calc Method:", self._combo("prayer_calc_method", [
            ("umm_al_qura", "Umm al-Qura"),
            ("isna", "ISNA"),
            ("mwl", "Muslim World League"),
            ("egypt", "Egyptian"),
            ("karachi", "Karachi"),
        ]))
        form.addRow(QLabel(""))  # spacer
        form.addRow(self._check("enable_azkar", "Enable Azkar Reminders"))
        form.addRow("Azkar Interval (min):", self._spin("azkar_reminder_min", 5, 120))
        self._tabs.addTab(w, "🕌 Prayer & Azkar")

    def _build_ai_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow(self._check("enable_ai", "Enable AI Brain (Ollama)"))
        form.addRow("AI Model:", self._line("ai_model"))
        form.addRow("Ollama URL:", self._line("ai_base_url"))
        form.addRow("Personality:", self._line("ai_personality"))
        form.addRow("Max Tokens:", self._spin("ai_max_tokens", 20, 2000))
        form.addRow("Temperature:", self._dspin("ai_temperature", 0.0, 2.0, 1))
        self._tabs.addTab(w, "🧠 AI Brain")

    def _build_advanced_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow("Fast Typing Threshold:", self._spin("typing_fast_threshold", 1, 20))
        form.addRow("Burst Threshold:", self._spin("burst_threshold", 3, 30))
        form.addRow("Backspace Rage Threshold:", self._spin("backspace_rage_threshold", 2, 20))
        form.addRow("App Switch Warn Count:", self._spin("app_switch_warn_count", 2, 20))
        form.addRow("App Switch Window (sec):", self._spin("app_switch_warn_window_sec", 60, 3600))
        form.addRow("Quiet Hours Start:", self._spin("quiet_hours_start", 0, 23))
        form.addRow("Quiet Hours End:", self._spin("quiet_hours_end", 0, 23))
        form.addRow("XP per Focus Min:", self._spin("xp_per_focus_min", 1, 100))
        form.addRow("XP per Pomodoro:", self._spin("xp_per_pomodoro", 10, 500))
        form.addRow("Combo Window (sec):", self._dspin("pet_combo_window_sec", 0.5, 10.0, 1))
        self._tabs.addTab(w, "⚡ Advanced")

    # ── Widget factories ──

    def _spin(self, key: str, lo: int, hi: int) -> QSpinBox:
        sb = QSpinBox()
        sb.setRange(lo, hi)
        sb.setValue(int(self._settings.get(key)))
        self._widgets[key] = sb
        return sb

    def _dspin(self, key: str, lo: float, hi: float, decimals: int) -> QDoubleSpinBox:
        sb = QDoubleSpinBox()
        sb.setRange(lo, hi)
        sb.setDecimals(decimals)
        sb.setSingleStep(10 ** -decimals)
        sb.setValue(float(self._settings.get(key)))
        self._widgets[key] = sb
        return sb

    def _check(self, key: str, label: str) -> QCheckBox:
        cb = QCheckBox(label)
        cb.setChecked(bool(self._settings.get(key)))
        self._widgets[key] = cb
        return cb

    def _line(self, key: str) -> QLineEdit:
        le = QLineEdit(str(self._settings.get(key)))
        self._widgets[key] = le
        return le

    def _combo(self, key: str, choices: list) -> QComboBox:
        cb = QComboBox()
        current = str(self._settings.get(key))
        idx = 0
        for i, item in enumerate(choices):
            if isinstance(item, tuple):
                value, label = item
            else:
                value = label = str(item)
            cb.addItem(label, userData=value)
            if value == current:
                idx = i
        cb.setCurrentIndex(idx)
        self._widgets[key] = cb
        return cb

    def _get_skin_choices(self) -> list:
        try:
            from core.sprite_engine import get_available_skins
            skins = get_available_skins()
            return [(s["id"], s["name"]) for s in skins] or [("default", "Default")]
        except Exception:
            return [("default", "Default")]

    # ── Actions ──

    def _save_and_close(self):
        for key, widget in self._widgets.items():
            if isinstance(widget, QCheckBox):
                self._settings.set(key, widget.isChecked())
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                self._settings.set(key, widget.value())
            elif isinstance(widget, QLineEdit):
                self._settings.set(key, widget.text())
            elif isinstance(widget, QComboBox):
                self._settings.set(key, widget.currentData())
        self._settings.save()
        self.accept()

    def _reset_defaults(self):
        from core.settings import Settings
        for key, default in Settings.DEFAULTS.items():
            if key in self._widgets:
                w = self._widgets[key]
                if isinstance(w, QCheckBox):
                    w.setChecked(bool(default))
                elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    w.setValue(default)
                elif isinstance(w, QLineEdit):
                    w.setText(str(default))
                elif isinstance(w, QComboBox):
                    for i in range(w.count()):
                        if w.itemData(i) == str(default):
                            w.setCurrentIndex(i)
                            break
