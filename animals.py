import sys
import random
import os
import json
import time
import math
import logging
import webbrowser
import re
import ctypes
import winsound
import winreg
import threading
import urllib.request
import urllib.error
import sqlite3
import shutil
import tempfile
import xml.etree.ElementTree as ET
from collections import deque
from datetime import datetime, date, timedelta
import pygetwindow as gw
from pynput import keyboard
from PyQt6.QtWidgets import (
    QApplication, QLabel, QMenu, QWidget, QInputDialog,
    QSystemTrayIcon, QVBoxLayout, QHBoxLayout, QCheckBox,
    QPushButton, QLineEdit, QScrollArea, QFrame, QTextEdit,
    QDialog, QSplitter, QGraphicsOpacityEffect, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal, QObject, QSize, QPropertyAnimation, QThread
from PyQt6.QtGui import (
    QAction, QMovie, QPixmap, QColor, QFont, QCursor, QIcon, QPainter,
)
from core.sprite_engine import SpriteRenderer, get_available_skins, generate_skin_assets, generate_skin_thumbnail

# ── Internal modules (extracted from monolith) ──
from core.settings import Settings
from core.stats import PersistentStats, STATS_PATH
from core.achievements import AchievementEngine, ACHIEVEMENTS
from core.mood import MoodEngine
from core.speech import SPEECH_POOL
from input.keyboard import KeyboardBridge, TypingPatternAnalyzer
from input.combo import ComboTracker
from media.controller import MediaController
from media.detector import MusicDetector
from media.scheduler import MusicScheduler
from features.prayer import PrayerTimeManager
from features.notifications import WindowsNotificationReader
from features.web_tracker import WebsiteTracker
from features.ai_brain import OllamaBrain, AIChatSignal, AIChatDialog
from features.todo_widget import MiniTodoWidget
from features.azkar import AzkarManager, AzkarReaderDialog, AZKAR_CATEGORIES, QUICK_AZKAR
from features.progress_monitor import ProgressMonitor, _format_speed, _format_size
from features.pet_memory import PetMemory
from features.reminders import ReminderManager
from features.habits import HabitTracker
from features.streak_calendar import StreakCalendarDialog
from features.circadian import get_circadian_phase, circadian_speech
from features.voice_commands import VoiceCommands
from features.wardrobe import Wardrobe, WardrobeDialog, WARDROBE_ITEMS
from features.accessory_drawer import COSMETIC_DRAWERS
from features.daily_briefing import DailyBriefing
from features.reactions import ReactionEngine
from features.tasbeeh import TasbeehCounter, TASBEEH_PRESETS
from features.clipboard_assistant import ClipboardAssistant
from features.system_health import SystemHealthMonitor
from features.file_drop import FileDropHandler
from features.quick_launcher import QuickLauncherWheel, LauncherEditDialog
from features.notification_digest import NotificationDigest
from features.productivity_dashboard import ProductivityDashboard
from features.sound_reactor import SoundReactor
from features.code_companion import CodeCompanion
from features.social import SocialFeatures
from features.global_hotkeys import GlobalHotkeys
from features.smart_reminders import SmartReminderManager, parse_time_input
from features.eye_care import EyeCareManager
from features.sticky_notes import StickyNotesManager, StickyArchiveDialog
from features.smart_actions import AISmartActions, SMART_ACTIONS
from features.tray_manager import TrayManager
from features.weather import WeatherReactor
from features.screenshot_tool import ScreenshotTool
from features.journal import DailyJournal, JournalDialog
from features.backup import BackupManager
from features.pet_sfx import PetSFX
from features.clipboard_history import ClipboardHistory
from features.quick_timer import QuickTimer
from features.app_time_report import AppTimeTracker, AppTimeDialog
from features.morning_routine import MorningRoutine
from features.focus_planner import FocusPlanner
from features.mood_journal import MoodJournal, MoodJournalDialog
from features.keyboard_heatmap import KeyboardHeatmapTracker, KeyboardHeatmapDialog
from features.meeting_mode import MeetingDetector
from features.real_events import RealEventReactor
from features.global_hotkeys import HotkeyHelpDialog
from features.screen_recorder import ScreenRecorder, RecordDialog
from features.folder_locker import FolderLocker, FolderLockerDialog
from features.file_compressor import FileCompressorDialog

__version__ = "14.0.0"

# ── Menu stylesheet (shared by all context menus) ──
_MENU_SS = (
    "QMenu { background: #F5F5F5; border: 1px solid #888; }"
    "QMenu::item { padding: 6px 24px; color: #222222; }"
    "QMenu::item:selected { background: #5599ff; color: white; }"
    "QMenu::item:disabled { color: #888888; }"
    "QMenu::separator { height: 1px; background: #ccc; margin: 4px 8px; }"
)
_SUB_MENU_SS = (
    "QMenu { background: #F5F5F5; border: 1px solid #888; }"
    "QMenu::item { padding: 6px 20px; color: #222222; }"
    "QMenu::item:selected { background: #5599ff; color: white; }"
)

# ── Window category keywords (shared reference) ──
_CODING_KW = ("code", "pycharm", "gym engine", "openclaw", "visual studio",
              "intellij", "neovim", "sublime", "atom", "terminal", "powershell",
              "cmd.exe", "git")
_DESIGN_KW = ("refreshyourpassionapp", "motiv8", "photoshop", "figma",
              "illustrator", "canva", "sketch", "blender")
_VIDEO_KW  = ("youtube", "netflix", "twitch", "vlc", "mpv", "plex")
_BROWSER_KW = ("chrome", "firefox", "edge", "brave", "opera", "safari")
_GAMING_KW  = ("steam", "epic games", "minecraft", "valorant", "discord")

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("toty")


# ============================================================
#  BACKGROUND WINDOW SCANNER
# ============================================================
class _WindowScanner(QObject):
    """Runs pygetwindow in a background thread, emits result on the main thread."""
    result_ready = pyqtSignal(str)  # window title (or empty string)
    _busy = False  # simple reentrance guard

    def scan(self):
        if self._busy:
            return
        self._busy = True
        try:
            w = gw.getActiveWindow()
            self.result_ready.emit(w.title if w else "")
        except Exception:
            self.result_ready.emit("")
        finally:
            self._busy = False


# ============================================================
#  THE DESKTOP PET  (v10)
# ============================================================
class DesktopPet(QWidget):
    def __init__(self):
        super().__init__()

        # 0. Core systems
        self.settings = Settings()
        self.mood_engine = MoodEngine(self.settings)
        self.stats = PersistentStats()
        self.typing_analyzer = TypingPatternAnalyzer(self.settings)
        self.achievement_engine = AchievementEngine(self.stats, self.settings)
        self.combo_tracker = ComboTracker(self.settings)

        # 1. Window Properties
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._dragging = False
        self._drag_pos = QPoint()

        # 2. Pet Body
        self.pet_width = 100
        self.pet_height = 100
        self._use_sprites = False
        self._sprite_renderer = SpriteRenderer(self, size=self.pet_width)
        self.pet_label = QLabel(self)
        self.pet_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.pet_label.setFixedSize(self.pet_width, self.pet_height)

        # 3. Speech Bubble (v3: mood-colored) with fade animations
        self.bubble = QLabel(self)
        self.bubble.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._bubble_opacity = QGraphicsOpacityEffect(self.bubble)
        self._bubble_opacity.setOpacity(0.0)
        self.bubble.setGraphicsEffect(self._bubble_opacity)
        self._bubble_fade = QPropertyAnimation(self._bubble_opacity, b"opacity")
        self._bubble_fade.setDuration(250)
        self._update_bubble_style()
        self.bubble.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble.setWordWrap(True)
        self.bubble.setMaximumWidth(220)
        self.bubble.hide()

        # v3: XP bar label (tiny, under the pet)
        self.xp_label = QLabel(self)
        self.xp_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.xp_label.setFont(QFont("Arial", 7))
        self.xp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.xp_label.setStyleSheet("color: #666; background: transparent;")
        self.xp_label.setFixedWidth(150)
        self._update_xp_label()

        self.setFixedSize(250, 220)
        self.pet_label.move(75, 100)
        self._sprite_renderer.move(75, 100)
        self.xp_label.move(50, 200)

        # Accessory overlay system (tools the pet wears/holds based on activity)
        self._accessory_label = QLabel(self)
        self._accessory_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._accessory_label.setFixedSize(self.pet_width, self.pet_height)
        self._accessory_label.move(75, 100)
        self._accessory_label.hide()
        self._current_accessory = ""
        self._accessory_cache: dict[str, QPixmap] = {}  # pre-rendered pixmaps

        # Error tracking for feature init failures
        self._feature_errors: list[str] = []

        # 4. Physics & Screen Setup — v3: multi-monitor aware
        self._update_screen_geometry()

        self.base_speed = 3
        self.gravity_speed = 8
        self.offset = QPoint()

        # 5. Visuals
        self.load_animations()
        self.pet_state = "idle"
        self.emotion_override = False
        self.set_state("idle")
        self.move(self.screen_width // 2, 50)

        # 6. Speech cooldown
        self._last_speech_time = 0.0
        self._last_speech_text = ""
        self._bubble_expires_at = 0.0  # timestamp when current bubble should disappear
        self._speech_queue: deque[tuple[str, int]] = deque(maxlen=8)  # (text, duration) queue
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self._on_bubble_expired)

        # 7. Timers
        self.movement_timer = QTimer(self)
        self.movement_timer.timeout.connect(self.update_movement)
        self.movement_timer.start(50)  # 50ms (was 30ms — saves CPU)

        self.brain_timer = QTimer(self)
        self.brain_timer.timeout.connect(self.decide_next_action)
        self.brain_timer.start(self.settings.get("brain_tick_ms"))

        self.context_timer = QTimer(self)
        self.context_timer.timeout.connect(self._request_window_scan)
        if self.settings.get("enable_window_tracking"):
            self.context_timer.start(self.settings.get("context_check_ms"))

        # Background thread for window scanning
        self._scan_thread = QThread(self)
        self._window_scanner = _WindowScanner()
        self._window_scanner.moveToThread(self._scan_thread)
        self._window_scanner.result_ready.connect(self._on_window_scan_result)
        self._scan_thread.start()

        # 8. Keyboard
        self.keystroke_count = 0
        self.idle_seconds = 0
        self.kb_bridge = KeyboardBridge()
        self.kb_bridge.key_pressed.connect(self._on_key_main_thread)
        if self.settings.get("enable_keyboard_tracking"):
            self.keyboard_listener = keyboard.Listener(on_press=self._on_key_bg_thread)
            self.keyboard_listener.start()
        else:
            self.keyboard_listener = None
        self.typing_timer = QTimer(self)
        self.typing_timer.timeout.connect(self.analyze_typing_speed)
        self.typing_timer.start(1000)

        # 9. Mood tick
        self.mood_timer = QTimer(self)
        self.mood_timer.timeout.connect(self._mood_tick)
        self.mood_timer.start(2000)  # 2s (was 1s — mood lerp smooths fine at this rate)

        # 10. Productivity
        self.pomodoro_active = False
        self.pomodoro_remaining = 0
        self.pomodoro_is_break = False
        self._pomodoro_timer = QTimer(self)
        self._pomodoro_timer.timeout.connect(self._pomodoro_tick)
        self._stretch_counter = 0
        self._water_counter = 0
        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._reminder_tick)

        # 10b. Focus milestones
        self._focus_milestones_hit: set[int] = set()  # thresholds already announced
        self._FOCUS_MILESTONES = {
            30:  ("🏅 30-Minute Focus!", "Half hour of focus! Great start!"),
            60:  ("🥉 1-Hour Focus!", "A full hour of deep work! Amazing! 🔥"),
            120: ("🥈 2-Hour Focus!", "TWO hours straight?! You're on fire! 💪"),
            180: ("🥇 3-Hour Focus!", "3 HOURS! You're a focus machine! 🤖"),
            300: ("🏆 5-Hour Focus!", "FIVE HOURS! Absolute legend status! 👑"),
        }
        if self.settings.get("enable_reminders"):
            self._reminder_timer.start(1000)

        # 11. Focus milestone
        self._last_focus_milestone = 0

        # 12. Typing patterns
        self._pattern_timer = QTimer(self)
        self._pattern_timer.timeout.connect(self._analyze_typing_patterns)
        self._pattern_timer.start(2000)

        # 13. Follow-cursor / wander
        self._follow_target = QPoint()
        self._wander_target = QPoint()
        self._has_wander_target = False

        # 14. Daily goal
        self._daily_goal_notified = False

        # 15. Context milestones
        self._context_milestones: dict[str, int] = {}

        # 16. Distraction warn cooldown
        self._last_distraction_warn = 0.0

        # 17. v3: Achievement check timer (every 10 s)
        self._ach_timer = QTimer(self)
        self._ach_timer.timeout.connect(self._check_achievements)
        if self.settings.get("enable_achievements"):
            self._ach_timer.start(10000)

        # 18. v3: XP award timer (every 60 s awards XP for focus)
        self._xp_timer = QTimer(self)
        self._xp_timer.timeout.connect(self._award_focus_xp)
        if self.settings.get("enable_xp_system"):
            self._xp_timer.start(60000)

        # 19. v3: Time-of-day greeting (once per session)
        self._tod_greeted = False

        # 20. v3: Mini todo widget
        self._todo_widget = None

        # 21. v3: System tray icon
        self._tray_icon = None
        if self.settings.get("enable_system_tray"):
            self._setup_tray()

        # 22. v3: Multi-monitor refresh timer
        if self.settings.get("enable_multi_monitor"):
            self._monitor_timer = QTimer(self)
            self._monitor_timer.timeout.connect(self._update_screen_geometry)
            self._monitor_timer.start(5000)

        # 23. v4: Website tracker
        self.web_tracker = WebsiteTracker()

        # 24. v4: Music scheduler + checker (every 30 s)
        self.music_scheduler = MusicScheduler()
        self._music_timer = QTimer(self)
        self._music_timer.timeout.connect(self._check_music_schedule)
        self._music_timer.start(30000)

        # 25. v4.1: Music detector (dedicated timer, runs every 2s independently)
        self.music_detector = MusicDetector()
        self._music_playing = False  # track state for animation
        self._music_detect_timer = QTimer(self)
        self._music_detect_timer.timeout.connect(self._auto_detect_music)
        self._music_detect_timer.start(2000)  # check every 2 seconds

        # 26. v5: Prayer times
        self.prayer_manager = PrayerTimeManager(self.settings)
        if self.settings.get("enable_prayer_times"):
            self._prayer_timer = QTimer(self)
            self._prayer_timer.timeout.connect(self._check_prayer_times)
            self._prayer_timer.start(30000)  # check every 30 seconds
            # Also check once shortly after startup
            QTimer.singleShot(3000, self._check_prayer_times)

        # 28. v6: AI Brain (Ollama)
        self.ai_brain = OllamaBrain(self.settings)
        self._ai_chat_signal = AIChatSignal()
        self._ai_chat_signal.response_ready.connect(self._on_ai_quick_response)
        self._ai_chat_dialog = None

        # 28b. Chat feature modules (memory, reminders, habits, briefing)
        self.pet_memory = PetMemory()
        self.reminder_mgr = ReminderManager(self)
        self.reminder_mgr.reminder_fired.connect(self._on_reminder_fired)
        self.habit_tracker = HabitTracker()
        self.daily_briefing = DailyBriefing(
            stats=self.stats,
            habits=self.habit_tracker,
            reminders=self.reminder_mgr,
            memory=self.pet_memory,
        )

        # 28c. Reaction engine (cursor awareness, chains, startled, comedy, etc.)
        self.reaction_engine = ReactionEngine(
            self.settings, self.mood_engine, self.stats, pet_memory=self.pet_memory,
        )
        self.reaction_engine.log_session_start()
        self._reaction_timer = QTimer(self)
        self._reaction_timer.timeout.connect(self._reaction_tick)
        self._reaction_timer.start(3000)  # every 3s for chains/fidgets/comedy/dreams

        # Cursor awareness timer (faster — every 100ms)
        self._cursor_track_timer = QTimer(self)
        self._cursor_track_timer.timeout.connect(self._cursor_awareness_tick)
        self._cursor_track_timer.start(100)

        # Mood snapshot timer (every 5 min for emotional memory)
        self._mood_snapshot_timer = QTimer(self)
        self._mood_snapshot_timer.timeout.connect(self.reaction_engine.log_mood_snapshot)
        self._mood_snapshot_timer.start(5 * 60 * 1000)

        # Multi-phase greeting state
        self._greeting_phase = 0
        self._greeting_scheduled = False

        # 29. v7: Windows Notification Reader
        self.notif_reader = WindowsNotificationReader()
        self._notif_timer = QTimer(self)
        self._notif_timer.timeout.connect(self._check_notifications)
        self._notif_timer.start(5000)  # check every 5 seconds
        self._notif_log: list[dict] = []  # keep recent notifications for menu
        # Load recent notifications on startup (last 20) so the log isn't empty
        self._load_recent_notifications()

        # 30. v8: Azkar reminders
        self.azkar_manager = AzkarManager(self.settings)
        self._azkar_reader = None
        self._azkar_timer = QTimer(self)
        self._azkar_timer.timeout.connect(self._check_azkar)
        if self.settings.get("enable_azkar"):
            self._azkar_timer.start(60000)

        # 30b. Proactive suggestions timer (every 15 min)
        self._suggestion_timer = QTimer(self)
        self._suggestion_timer.timeout.connect(self._check_proactive_suggestion)
        self._suggestion_timer.start(15 * 60 * 1000)

        # 31. v9: Desktop Auto-Organizer
        from features.desktop_organizer import DesktopOrganizer
        self._desktop_organizer = DesktopOrganizer(self.settings)
        self._desktop_organizer.initialize()
        self._organizer_timer = QTimer(self)
        self._organizer_timer.timeout.connect(self._check_desktop_organizer)
        if self.settings.get("enable_desktop_organizer"):
            interval = self.settings.get("organizer_check_sec") * 1000
            self._organizer_timer.start(max(interval, 5000))
        self._organizer_busy = False  # prevent overlapping animations

        # 32. Crash recovery checkpoints
        self._checkpoint_path = os.path.join(tempfile.gettempdir(), "toty_checkpoint.json")
        self._restore_checkpoint()
        self._checkpoint_timer = QTimer(self)
        self._checkpoint_timer.timeout.connect(self._save_checkpoint)
        self._checkpoint_timer.start(30000)  # save every 30 seconds

        # 33. Progress monitor (downloads & system progress bars)
        self._progress_overlay = self._build_progress_overlay()
        self._progress_items: list[dict] = []
        self._progress_monitor = ProgressMonitor(self, interval_ms=2000)
        self._progress_monitor.updated.connect(self._on_progress_updated)
        self._progress_monitor.item_started.connect(self._on_progress_started)
        self._progress_monitor.item_finished.connect(self._on_progress_finished)

        # 34. Tasbeeh counter
        self.tasbeeh = TasbeehCounter()

        # 35. Clipboard assistant
        self._clipboard_assistant = None
        if self.settings.get("enable_clipboard_assistant"):
            self._clipboard_assistant = ClipboardAssistant()
            self._clipboard_assistant.event_detected.connect(self._on_clipboard_event)

        # 36. System health monitor
        self._system_health = None
        if self.settings.get("enable_system_health"):
            try:
                self._system_health = SystemHealthMonitor(interval_ms=15000)
                self._system_health.alert.connect(self._on_system_health_alert)
            except Exception as exc:
                self._feature_errors.append(f"System Health: {exc}")
                log.warning("SystemHealthMonitor init failed: %s", exc)

        # 37. File drop handler
        self._file_drop = FileDropHandler()
        if self.settings.get("enable_file_drop"):
            self.setAcceptDrops(True)

        # 38. Quick launcher wheel
        self._quick_launcher = QuickLauncherWheel(None)
        self._quick_launcher.action_triggered.connect(self._on_quick_action)

        # 39. Smart notification digest
        self._notif_digest = NotificationDigest(
            interval_min=self.settings.get("notification_digest_min")
        )
        self._notif_digest.digest_ready.connect(self._on_notif_digest)

        # 40. Productivity dashboard
        self._prod_dashboard = ProductivityDashboard(
            self.stats, self.mood_engine, self.habit_tracker, self.settings
        )

        # 41. Sound reactor (microphone)
        self._sound_reactor = None
        if self.settings.get("enable_sound_reactor"):
            try:
                self._sound_reactor = SoundReactor(enabled=True)
                self._sound_reactor.reaction.connect(self._on_sound_reaction)
            except Exception as exc:
                self._feature_errors.append(f"Sound Reactor: {exc}")
                log.warning("SoundReactor init failed: %s", exc)

        # 42. Code companion (git watcher)
        self._code_companion = None
        if self.settings.get("enable_code_companion"):
            try:
                self._code_companion = CodeCompanion(check_interval_ms=60000)
                self._code_companion.alert.connect(self._on_code_companion_alert)
            except Exception as exc:
                self._feature_errors.append(f"Code Companion: {exc}")
                log.warning("CodeCompanion init failed: %s", exc)

        # 43. Social features (challenges, evolution)
        self.social = SocialFeatures(self.stats)
        self.social.challenge_completed.connect(self._on_challenge_completed)
        self.social.evolution_unlocked.connect(self._on_evolution_unlocked)
        self._challenge_check_timer = QTimer(self)
        self._challenge_check_timer.timeout.connect(self._check_daily_challenges)
        if self.settings.get("enable_daily_challenges"):
            self._challenge_check_timer.start(60000)  # check every minute

        # 44. Pet Sound Effects
        self._sfx = PetSFX(
            enabled=self.settings.get("enable_pet_sounds"),
            volume=self.settings.get("pet_sound_volume"),
        )

        # 45. Global Hotkeys
        self._hotkeys = GlobalHotkeys()
        self._hotkeys.triggered.connect(self._on_hotkey)
        if self.settings.get("enable_global_hotkeys"):
            self._hotkeys.start()

        # 46. Smart Reminders v2
        self._smart_reminders = SmartReminderManager()
        self._smart_reminders.reminder_fired.connect(self._on_smart_reminder)

        # 47. Eye Care (20-20-20)
        self._eye_care = None
        if self.settings.get("enable_eye_care"):
            self._eye_care = EyeCareManager(
                eye_min=self.settings.get("eye_break_min"),
                water_min=self.settings.get("water_reminder_min"),
                stretch_min=self.settings.get("stretch_reminder_min"),
            )
            self._eye_care.break_needed.connect(self._on_health_break)
            self._eye_care.break_finished.connect(self._on_break_done)

        # 48. Sticky Notes
        self._sticky_notes = StickyNotesManager()

        # 49. AI Smart Actions
        self._smart_actions = AISmartActions(self.ai_brain)
        self._smart_actions.action_started.connect(
            lambda action: self.say("💭 AI is thinking...", duration=3000)
        )
        self._smart_actions.action_result.connect(self._on_smart_action_result)
        self._smart_actions.action_error.connect(
            lambda msg: self.say(f"❌ {msg}", duration=4000, force=True)
        )

        # 50. System Tray
        self._tray = None
        if self.settings.get("enable_system_tray"):
            self._tray = TrayManager(self.settings.get("pet_name"))
            self._tray.show_pet.connect(self.show)
            self._tray.hide_pet.connect(self.hide)
            self._tray.toggle_dnd.connect(self._toggle_dnd)
            self._tray.toggle_focus.connect(self._toggle_focus_mode)
            self._tray.open_dashboard.connect(self._toggle_dashboard)
            self._tray.open_launcher.connect(
                lambda: self._quick_launcher.show_at(
                    self.pos() + QPoint(self.width() // 2, self.height() // 2)
                )
            )
            self._tray.quit_app.connect(self._graceful_quit)
            self._tray.show()

        # 51. Weather Reactor
        self._weather = None
        if self.settings.get("enable_weather"):
            self._weather = WeatherReactor(
                lat=self.settings.get("prayer_latitude"),
                lon=self.settings.get("prayer_longitude"),
            )
            self._weather.weather_comment.connect(
                lambda msg: self.say(msg, duration=5000)
            )
            self._weather.accessory_suggest.connect(self._weather_accessory)
            self._weather.rain_warning.connect(
                lambda msg: self.say(msg, duration=6000, force=True)
            )

        # 52. Screenshot Tool
        self._screenshot = ScreenshotTool()
        self._screenshot.captured.connect(self._on_screenshot)

        # 53. Daily Journal
        self._journal = DailyJournal(prompt_hour=21)
        self._journal.prompt_journal.connect(self._prompt_journal)
        self._journal.entry_saved.connect(self._on_journal_saved)

        # 54. Backup Manager
        self._backup = BackupManager(".")

        # 55. Circadian Cycle
        self._circadian_phase = get_circadian_phase()["phase"]
        self._circadian_timer = QTimer(self)
        self._circadian_timer.timeout.connect(self._check_circadian)
        self._circadian_timer.start(120_000)  # check every 2 min

        # 56. Voice Commands
        self._voice = VoiceCommands()
        if self.settings.get("enable_voice_commands") and self._voice.is_available():
            self._voice.command_recognized.connect(self._on_voice_command)
            self._voice.start()

        # 57. Wardrobe (cosmetic accessories)
        self._wardrobe = Wardrobe()

        # 58. Clipboard History Panel
        self._clipboard_history = ClipboardHistory()

        # 59. Quick Timer / Stopwatch
        self._quick_timer = QuickTimer()
        self._quick_timer.timer_finished.connect(
            lambda msg: self.say(f"⏱️ {msg}", duration=5000, force=True))

        # 60. App Time Tracker
        self._app_time_tracker = AppTimeTracker()

        # 61. Morning Routine Checklist
        self._morning_routine = MorningRoutine()
        self._morning_routine.all_done.connect(
            lambda: self.say("🌅 Morning routine complete! Great start!", duration=4000, force=True))
        hour_now = datetime.now().hour
        if 5 <= hour_now <= 10:
            QTimer.singleShot(3000, self._morning_routine.show)

        # 62. Focus Session Planner
        self._focus_planner = FocusPlanner()
        self._focus_planner.break_time.connect(
            lambda: self.say("☕ Focus break! Stretch and relax.", duration=4000, force=True))
        self._focus_planner.session_ended.connect(
            lambda: self.say("✅ Focus session complete!", duration=4000, force=True))

        # 63. Mood Journal
        self._mood_journal = MoodJournal()
        self._mood_journal.prompt_mood.connect(self._show_mood_journal)

        # 64. Keyboard Heatmap Tracker
        self._kb_heatmap = KeyboardHeatmapTracker()

        # 65. Meeting Detector
        self._meeting_detector = MeetingDetector()
        self._meeting_detector.meeting_started.connect(self._on_meeting_start)
        self._meeting_detector.meeting_ended.connect(self._on_meeting_end)

        # 66. Real Event Reactor
        self._real_events = RealEventReactor()
        self._real_events.real_event.connect(
            lambda etype, msg: self.say(msg, duration=4000, force=True))

        # 67. Screen Recorder
        self._screen_recorder = ScreenRecorder()
        self._screen_recorder.recording_started.connect(
            lambda: self.say("🔴 Recording started!", duration=2000, force=True))
        self._screen_recorder.recording_stopped.connect(
            lambda p: self.say(f"✅ Recording saved!", duration=3000, force=True))

        # 68. Folder Locker
        self._folder_locker = FolderLocker()

        # 27. Welcome + time greeting
        QTimer.singleShot(1500, self._show_welcome)

    # ==========================================================
    #  MULTI-MONITOR SUPPORT (v3)
    # ==========================================================
    def _update_screen_geometry(self):
        """Compute the bounding rect of all screens for roaming."""
        screens = QApplication.screens()
        if not screens:
            sg = QApplication.primaryScreen().geometry()
            self.screen_left = 0
            self.screen_top = 0
            self.screen_width = sg.width()
            self.screen_height = sg.height()
        elif self.settings.get("enable_multi_monitor") and len(screens) > 1:
            min_x = min(s.geometry().x() for s in screens)
            min_y = min(s.geometry().y() for s in screens)
            max_x = max(s.geometry().x() + s.geometry().width() for s in screens)
            max_y = max(s.geometry().y() + s.geometry().height() for s in screens)
            self.screen_left = min_x
            self.screen_top = min_y
            self.screen_width = max_x - min_x
            self.screen_height = max_y - min_y
        else:
            sg = QApplication.primaryScreen().geometry()
            self.screen_left = sg.x()
            self.screen_top = sg.y()
            self.screen_width = sg.width()
            self.screen_height = sg.height()

        self.floor_y = self.screen_top + self.screen_height - self.height() - 50

    # ==========================================================
    #  CRASH RECOVERY CHECKPOINTS
    # ==========================================================
    def _save_checkpoint(self):
        """Persist recoverable session state to a temp file."""
        try:
            data = {
                "version": __version__,
                "pos_x": self.x(),
                "pos_y": self.y(),
                "pet_state": self.pet_state,
                "pomodoro_active": self.pomodoro_active,
                "pomodoro_remaining": self.pomodoro_remaining,
                "pomodoro_is_break": self.pomodoro_is_break,
                "mood": self.mood_engine.mood,
                "timestamp": time.time(),
            }
            tmp = self._checkpoint_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self._checkpoint_path)
        except OSError:
            pass

    def _restore_checkpoint(self):
        """Restore session state from a prior crash checkpoint if fresh."""
        try:
            if not os.path.isfile(self._checkpoint_path):
                return
            with open(self._checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Only restore if checkpoint is less than 5 minutes old
            if time.time() - data.get("timestamp", 0) > 300:
                return
            if data.get("pomodoro_active"):
                self.pomodoro_active = True
                self.pomodoro_remaining = data.get("pomodoro_remaining", 0)
                self.pomodoro_is_break = data.get("pomodoro_is_break", False)
                self._pomodoro_timer.start(1000)
                log.info("Restored pomodoro checkpoint: %ds remaining", self.pomodoro_remaining)
            if data.get("mood") is not None:
                self.mood_engine.mood = max(0, min(100, data["mood"]))
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    def _clear_checkpoint(self):
        """Remove the checkpoint file on clean shutdown."""
        try:
            os.remove(self._checkpoint_path)
        except OSError:
            pass

    # ==========================================================
    #  SYSTEM TRAY (v3)
    # ==========================================================
    def _setup_tray(self):
        # Create a small colored pixmap as tray icon
        pix = QPixmap(32, 32)
        pix.fill(QColor(60, 179, 113))
        icon = QIcon(pix)

        self._tray_icon = QSystemTrayIcon(icon, self)
        self._tray_icon.setToolTip(f"{self.settings.get('pet_name')} — Desktop Pet")

        tray_menu = QMenu()
        show_action = QAction("Show Pet", self)
        show_action.triggered.connect(self._show_pet)
        tray_menu.addAction(show_action)

        hide_action = QAction("Hide Pet", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)

        tray_menu.addSeparator()

        stats_action = QAction("Session Stats", self)
        stats_action.triggered.connect(lambda: (self._show_pet(), self._show_stats()))
        tray_menu.addAction(stats_action)

        pomo_action = QAction("Start Pomodoro", self)
        pomo_action.triggered.connect(lambda: (self._show_pet(), self.start_pomodoro()))
        tray_menu.addAction(pomo_action)

        tray_menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._graceful_quit)
        tray_menu.addAction(quit_action)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._tray_activated)
        self._tray_icon.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_pet()

    def _show_pet(self):
        self.show()
        self.raise_()

    # ==========================================================
    #  MOOD-COLORED BUBBLE (v3)
    # ==========================================================
    def _update_bubble_style(self):
        if self.settings.get("bubble_mood_colors"):
            bg = self.mood_engine.get_mood_color()
            border = self.mood_engine.get_mood_border_color()
        else:
            bg = "white"
            border = "black"
        self.bubble.setStyleSheet(
            f"background-color: {bg};"
            f"border: 2px solid {border};"
            "border-radius: 10px;"
            "padding: 5px;"
            "color: black;"
        )

    def _update_xp_label(self):
        self.xp_label.setText(self.stats.get_level_info())

    # ==========================================================
    #  ANIMATION LOADER
    # ==========================================================
    def load_animations(self):
        self.animations = {}
        assets_folder = "assets"
        if not os.path.exists(assets_folder):
            os.makedirs(assets_folder)

        # Try sprite engine first
        # Generate skin assets if sheet doesn't exist yet
        sheet_path = os.path.join(assets_folder, "pet_sheet.png")
        if not os.path.exists(sheet_path):
            skin_id = self.settings.get("current_skin")
            generate_skin_assets(skin_id)

        if self._sprite_renderer.load(assets_folder):
            self._use_sprites = True
            self.pet_label.hide()
            self._sprite_renderer.show()
            # Populate animations dict so "X in self.animations" checks work
            from core.sprite_engine import STATE_MAP
            for name in self._sprite_renderer.get_animation_names():
                self.animations[name] = True
            for state_name in STATE_MAP:
                self.animations[state_name] = True
            log.info("Loaded sprite sheet pipeline (%d animation keys)", len(self.animations))
        else:
            self._use_sprites = False
            self._sprite_renderer.hide()
            self.pet_label.show()
            # Fallback: load GIFs
            for filename in os.listdir(assets_folder):
                if filename.endswith(".gif"):
                    state_name = filename.replace(".gif", "")
                    filepath = os.path.join(assets_folder, filename)
                    movie = QMovie(filepath)
                    if movie.isValid():
                        self.animations[state_name] = movie
                    else:
                        log.warning("Invalid GIF skipped: %s", filename)
            if not self.animations:
                pixmap = QPixmap(self.pet_width, self.pet_height)
                pixmap.fill(QColor(135, 206, 235, 150))
                self.animations["idle"] = pixmap

        self.action_categories = {
            "idle": ["idle", "sit", "yawn", "stretch", "dance"],
            "move_left": ["walk_left", "run_left", "crawl_left", "roll_left"],
            "move_right": ["walk_right", "run_right", "crawl_right", "roll_right"],
            "work": ["work", "type_code", "read_book"],
            "sleep": ["sleep", "snore"],
            "happy": ["smile", "jump"],
        }
        self.current_anim = None

    # State → SFX mapping for automatic sound on state change
    _STATE_SFX_MAP = {
        "sleep": "sleep", "yawn": "yawn", "falling": "fall",
        "dance": "happy", "smile": "happy", "excited": "giggle",
        "sad": "sad", "work": "typing",
    }

    def set_state(self, new_state):
        # Sprite engine path
        if self._use_sprites:
            if self.pet_state == new_state and self._sprite_renderer._current_anim is not None:
                return
            self.pet_state = new_state
            self._sprite_renderer.play(new_state)
            self._auto_equip_for_state(new_state)
            sfx_name = self._STATE_SFX_MAP.get(new_state)
            if sfx_name and hasattr(self, '_sfx'):
                self._sfx.play(sfx_name)
            return

        # GIF fallback path
        if new_state not in self.animations:
            new_state = "idle" if "idle" in self.animations else list(self.animations.keys())[0]
        if self.pet_state == new_state and self.current_anim is not None:
            return
        self.pet_state = new_state
        if isinstance(self.current_anim, QMovie):
            self.current_anim.stop()
        self.current_anim = self.animations[new_state]
        if isinstance(self.current_anim, QMovie):
            self.pet_label.setMovie(self.current_anim)
            self.current_anim.start()
        else:
            self.pet_label.setPixmap(self.current_anim)
            self.pet_label.setText(f" {new_state.upper()} ")
            self.pet_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._auto_equip_for_state(new_state)
        sfx_name = self._STATE_SFX_MAP.get(new_state)
        if sfx_name and hasattr(self, '_sfx'):
            self._sfx.play(sfx_name)

    # ==========================================================
    #  BRAIN (v3: + time-of-day greeting)
    # ==========================================================
    def decide_next_action(self):
        if self.emotion_override or self.pet_state in ["dragging", "falling", "work"]:
            return
        if self.settings.get("enable_follow_cursor"):
            return

        # Circadian auto-sleep
        circ = get_circadian_phase()
        if circ["auto_state"] and self.pet_state != circ["auto_state"]:
            if circ["auto_state"] in (self.animations if not self._use_sprites
                                      else [a for a in ["sleep"] if self._sprite_renderer.has_animation(a)]):
                self.set_state(circ["auto_state"])
                return

        dominant = self.mood_engine.get_dominant_state()
        weight_map = {
            "exhausted": [70, 10, 10],
            "tired":     [60, 15, 15],
            "happy":     [30, 30, 30],
            "sad":       [65, 15, 15],
            "focused":   [80, 8, 8],
        }
        weights = weight_map.get(dominant, [50, 25, 25])

        action_type = random.choices(
            ["idle", "move_left", "move_right"], weights=weights, k=1
        )[0]
        available_gifs = self.action_categories.get(action_type, ["idle"])

        # Blend in circadian preferred states (30% chance)
        if random.random() < 0.3 and circ["preferred_states"]:
            available_gifs = circ["preferred_states"]

        if self._use_sprites:
            valid_gifs = [g for g in available_gifs if self._sprite_renderer.has_animation(g)]
        else:
            valid_gifs = [g for g in available_gifs if g in self.animations]
        if valid_gifs:
            self.set_state(random.choice(valid_gifs))
        else:
            self.set_state("idle")

        # Wander toward mouse
        if (not self.settings.get("enable_follow_cursor")
                and random.random() < self.settings.get("wander_to_mouse_chance")):
            cursor_pos = QCursor.pos()
            self._wander_target = QPoint(
                cursor_pos.x() - self.width() // 2,
                min(cursor_pos.y(), self.floor_y),
            )
            self._has_wander_target = True

        # Mood speech (skip in focus mode)
        if not self.settings.get("focus_mode"):
            if dominant == "tired" and random.random() < 0.25:
                self.say_random("tired")
            elif dominant == "sad" and random.random() < 0.2:
                self.say_random("sad")
            elif dominant == "happy" and random.random() < 0.15:
                self.say_random("happy")

    # ==========================================================
    #  MOOD TICK
    # ==========================================================
    def _mood_tick(self):
        is_typing = self.keystroke_count > 0
        is_working = self.pet_state == "work"
        self.mood_engine.tick(is_typing, is_working)

        # Update bubble color periodically
        if self.settings.get("bubble_mood_colors") and self.bubble.isVisible():
            self._update_bubble_style()

        # Focus milestones (every 15 min)
        focus_min = self.mood_engine.get_focus_minutes()
        if focus_min > 0 and focus_min % 15 == 0 and focus_min != self._last_focus_milestone:
            self._last_focus_milestone = focus_min
            self.say_random("focus_milestone", m=focus_min)

        # Big focus milestones (badges)
        for threshold, (badge, msg) in self._FOCUS_MILESTONES.items():
            if focus_min >= threshold and threshold not in self._focus_milestones_hit:
                self._focus_milestones_hit.add(threshold)
                self.say(f"{badge}\n{msg}", duration=6000, force=True)
                self.mood_engine.boost_mood(10)
                if self.settings.get("enable_xp_system"):
                    self.stats.add_xp(threshold // 10)
                    self._update_xp_label()
                # Unlock cape at 3h focus
                if threshold >= 180:
                    self._wardrobe.unlock("cape")

        # Daily goal
        daily_goal = self.settings.get("daily_goal_focus_min")
        today_focus = self.stats.data.get("daily_focus_min", 0) + focus_min
        if today_focus >= daily_goal and not self._daily_goal_notified:
            self._daily_goal_notified = True
            self.say_random("daily_goal", m=today_focus, duration=5000)
            self.mood_engine.boost_mood(20)

        # Per-category milestones
        for cat in ("coding", "design"):
            cat_min = self.mood_engine.get_app_time_minutes(cat)
            prev = self._context_milestones.get(cat, 0)
            if cat_min > 0 and cat_min % 20 == 0 and cat_min != prev:
                self._context_milestones[cat] = cat_min
                pool = "coding_milestone" if cat == "coding" else "focus_milestone"
                self.say_random(pool, m=cat_min)

    # ==========================================================
    #  v3: ACHIEVEMENT CHECK (every 10 s)
    # ==========================================================
    def _check_achievements(self):
        self.achievement_engine.check_all(
            session_keys=self.typing_analyzer.get_total_keys(),
            session_focus_min=self.mood_engine.get_focus_minutes(),
        )
        for aid in self.achievement_engine.pop_pending():
            info = ACHIEVEMENTS.get(aid, {})
            name = info.get("name", aid)
            self._sfx.play("achievement")
            self.say_random("achievement", name=name, duration=5000)
            self.mood_engine.boost_mood(10)
            self._update_xp_label()

        # Tray icon tooltip update
        if self._tray_icon:
            unlocked, total = self.achievement_engine.get_unlocked_count()
            self._tray_icon.setToolTip(
                f"{self.settings.get('pet_name')} — Lv.{self.stats.data.get('level', 1)} "
                f"| {unlocked}/{total} achievements"
            )

        # Wardrobe unlock check
        newly = self._wardrobe.check_unlocks(self.stats, self.habit_tracker)
        for item_id in newly:
            name = next((n for i, n, *_ in WARDROBE_ITEMS if i == item_id), item_id)
            self.say(f"🎉 New wardrobe item unlocked: {name}!", duration=5000, force=True)

    # ==========================================================
    #  v3: XP AWARD (every 60 s)
    # ==========================================================
    def _award_focus_xp(self):
        if self.pet_state == "work":
            xp = self.settings.get("xp_per_focus_min")
            leveled = self.stats.add_xp(xp)
            self._update_xp_label()
            if leveled:
                lv = self.stats.data.get("level", 1)
                self._sfx.play("level_up")
                self.say_random("level_up", lv=lv, duration=5000)
                self.mood_engine.boost_mood(15)
                self.mood_engine.boost_energy(10)

    # ==========================================================
    #  TYPING PATTERNS
    # ==========================================================
    def _analyze_typing_patterns(self):
        if self.settings.get("focus_mode") or self.emotion_override:
            return
        # Skip analysis when user hasn't typed recently (no events to process)
        if self.keystroke_count == 0 and self.idle_seconds > 10:
            return
        events = self.typing_analyzer.consume_events()

        if events["idle_returned"]:
            self.say_random("idle_return", duration=5000)
            self.mood_engine.boost_mood(5)
            if self.pet_state == "sleep":
                self.emotion_override = False
                self.set_state("idle")
        if events["backspace_rage"]:
            self.say_random("backspace_rage", duration=5000)
            self.mood_engine.drain_mood(5)
        elif events["burst"]:
            self.say_random("burst", duration=5000)
            self.mood_engine.boost_energy(3)
        elif events["pause"]:
            if random.random() < 0.3:
                self.say_random("thinking_pause", duration=5000)

    # ==========================================================
    #  PHYSICS (multi-monitor aware)
    # ==========================================================
    def update_movement(self):
        if self.pet_state == "dragging":
            return
        if self.pet_state == "falling":
            new_y = self.y() + self.gravity_speed
            if new_y >= self.floor_y:
                self.move(self.x(), self.floor_y)
                self._sfx.play("bounce")
                self.set_state("idle")
            else:
                self.move(self.x(), new_y)
            return

        if self.settings.get("enable_follow_cursor"):
            self._move_toward_cursor()
            return

        if self._has_wander_target:
            dx = self._wander_target.x() - self.x()
            dy = self._wander_target.y() - self.y()
            dist = math.hypot(dx, dy)
            if dist < 10:
                self._has_wander_target = False
            else:
                speed = self.base_speed
                nx = dx / dist * speed
                ny = dy / dist * speed
                self.move(int(self.x() + nx), int(self.y() + ny))
                # Use carry GIF if currently carrying a file, else walk
                is_carrying = self.pet_state.startswith("carry_")
                if dx < 0:
                    if is_carrying and "carry_left" in self.animations:
                        self.set_state("carry_left")
                    elif "walk_left" in self.animations:
                        self.set_state("walk_left")
                elif dx > 0:
                    if is_carrying and "carry_right" in self.animations:
                        self.set_state("carry_right")
                    elif "walk_right" in self.animations:
                        self.set_state("walk_right")
            return

        current_speed = self.base_speed
        if "run" in self.pet_state:
            current_speed = int(self.base_speed * 2.5)
        elif "crawl" in self.pet_state or "roll" in self.pet_state:
            current_speed = int(self.base_speed * 0.5)

        left_bound = getattr(self, "screen_left", 0)
        right_bound = left_bound + self.screen_width

        if self.pet_state.endswith("_left"):
            self.move(self.x() - current_speed, self.y())
            if self.x() < left_bound:
                self.set_state(self.pet_state.replace("_left", "_right"))
        elif self.pet_state.endswith("_right"):
            self.move(self.x() + current_speed, self.y())
            if self.x() + self.width() > right_bound:
                self.set_state(self.pet_state.replace("_right", "_left"))

        if self.settings.get("taskbar_gravity") and self.pet_state in ("idle", "sit", "yawn"):
            if self.y() < self.floor_y:
                self.move(self.x(), min(self.y() + 1, self.floor_y))

    def _move_toward_cursor(self):
        cursor_pos = QCursor.pos()
        target_x = cursor_pos.x() - self.width() // 2
        target_y = min(cursor_pos.y() - self.height() // 2, self.floor_y)
        dx = target_x - self.x()
        dy = target_y - self.y()
        dist = math.hypot(dx, dy)
        if dist < 15:
            self.set_state("idle")
            return
        speed = self.settings.get("follow_cursor_speed")
        nx = dx / dist * speed
        ny = dy / dist * speed
        self.move(int(self.x() + nx), int(self.y() + ny))
        if dx < 0 and "walk_left" in self.animations:
            self.set_state("walk_left")
        elif dx > 0 and "walk_right" in self.animations:
            self.set_state("walk_right")

    # ==========================================================
    #  KEYBOARD
    # ==========================================================
    def _on_key_bg_thread(self, key):
        try:
            name = key.char if hasattr(key, "char") and key.char else key.name
        except AttributeError:
            name = "unknown"
        self.kb_bridge.key_pressed.emit(name or "unknown")

    def _on_key_main_thread(self, key_name: str):
        self.keystroke_count += 1
        self.idle_seconds = 0
        self.typing_analyzer.record_key(key_name)
        # v3: track total keys for achievements
        self.stats.data["total_keys"] = self.stats.data.get("total_keys", 0) + 1
        # v14: keyboard heatmap
        self._kb_heatmap.record_keys(1)

        if self.pet_state == "sleep":
            self.emotion_override = False
            self.set_state("idle")
            self.say_random("wakeup", duration=5000)

    def analyze_typing_speed(self):
        kps = self.keystroke_count
        self.keystroke_count = 0
        if kps > self.settings.get("typing_fast_threshold"):
            if not self.emotion_override:
                self.say_random("typing_fast")
                if "run_left" in self.animations and "run_right" in self.animations:
                    self.set_state(random.choice(["run_left", "run_right"]))
        else:
            self.idle_seconds += 1
            timeout = self.settings.get("idle_sleep_timeout_sec")
            if self.idle_seconds == timeout and not self.emotion_override:
                self.emotion_override = True
                self.set_state("sleep")
                self.say("Zzz...")

    # ==========================================================
    #  ACCESSORY / TOOL SYSTEM  (v5 — visual overlays)
    # ==========================================================
    # Maps context/activity → accessory name
    _CONTEXT_ACCESSORY_MAP: dict[str, str] = {
        "coding":  "glasses",
        "design":  "beret",
        "gaming":  "controller",
        "video":   "popcorn",
        "browser": "magnifier",
    }
    _STATE_ACCESSORY_MAP: dict[str, str] = {
        "sleep":   "sleep_mask",
        "snore":   "sleep_mask",
        "pray":    "tasbeeh",
        "work":    "glasses",
        "type_code": "glasses",
        "read_book": "glasses",
        "screenshot": "camera",
        "notification": "megaphone",
        "carry":   "hardhat",
        "music_listen": "headphones",
        "play_music":   "headphones",
    }

    def _get_accessory_pixmap(self, name: str) -> QPixmap:
        """Return (cached) pixmap for an accessory drawn with QPainter."""
        if name in self._accessory_cache:
            return self._accessory_cache[name]
        draw_fn = getattr(self, f"_draw_{name}", None)
        if not draw_fn:
            return QPixmap()
        size = self.pet_width
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw_fn(p, size)
        p.end()
        self._accessory_cache[name] = pm
        return pm

    def equip_accessory(self, name: str):
        """Show an accessory overlay on the pet."""
        if name == self._current_accessory and self._accessory_label.isVisible():
            return
        pm = self._get_accessory_pixmap(name)
        if pm.isNull():
            return
        self._current_accessory = name
        self._accessory_label.setPixmap(pm)
        self._accessory_label.raise_()
        self._accessory_label.show()

    def unequip_accessory(self):
        """Remove the current accessory overlay."""
        self._current_accessory = ""
        self._accessory_label.hide()

    def _auto_equip_for_state(self, state: str):
        """Automatically pick the right accessory for a pet state."""
        acc = self._STATE_ACCESSORY_MAP.get(state)
        if acc:
            self.equip_accessory(acc)
        elif self._current_accessory and self._current_accessory not in ("headphones",):
            # Don't strip headphones (managed by music detector)
            self.unequip_accessory()

    def _auto_equip_for_context(self, category: str):
        """Automatically pick the right accessory for detected OS context."""
        acc = self._CONTEXT_ACCESSORY_MAP.get(category)
        if acc:
            self.equip_accessory(acc)

    # ---------- individual accessory painters ----------

    def _draw_headphones(self, p: QPainter, size: int):
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QPen
        pen = QPen(QColor(50, 50, 50), 5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(20, 2, 60, 40), 0 * 16, 180 * 16)
        p.setPen(Qt.PenStyle.NoPen)
        # Left earpiece
        p.setBrush(QColor(60, 60, 60)); p.drawRoundedRect(14, 22, 18, 24, 6, 6)
        p.setBrush(QColor(90, 90, 90)); p.drawRoundedRect(16, 25, 14, 18, 4, 4)
        p.setBrush(QColor(130, 130, 130, 80)); p.drawRoundedRect(18, 27, 5, 10, 2, 2)
        # Right earpiece
        p.setBrush(QColor(60, 60, 60)); p.drawRoundedRect(68, 22, 18, 24, 6, 6)
        p.setBrush(QColor(90, 90, 90)); p.drawRoundedRect(70, 25, 14, 18, 4, 4)
        p.setBrush(QColor(130, 130, 130, 80)); p.drawRoundedRect(72, 27, 5, 10, 2, 2)

    def _draw_glasses(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen
        pen = QPen(QColor(40, 40, 40), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(QColor(180, 220, 255, 60))
        # Left lens
        p.drawRoundedRect(22, 32, 22, 18, 5, 5)
        # Right lens
        p.drawRoundedRect(56, 32, 22, 18, 5, 5)
        # Bridge
        p.drawLine(44, 40, 56, 40)
        # Left arm
        p.drawLine(22, 38, 10, 34)
        # Right arm
        p.drawLine(78, 38, 90, 34)

    def _draw_beret(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen
        p.setPen(Qt.PenStyle.NoPen)
        # Beret body
        p.setBrush(QColor(180, 50, 50))
        p.drawEllipse(25, 2, 55, 30)
        # Beret brim
        p.setBrush(QColor(140, 35, 35))
        p.drawRoundedRect(23, 22, 50, 8, 4, 4)
        # Bobble on top
        p.setBrush(QColor(200, 70, 70))
        p.drawEllipse(48, 0, 10, 10)
        # Highlight
        p.setBrush(QColor(220, 100, 100, 80))
        p.drawEllipse(35, 6, 20, 12)

    def _draw_controller(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen
        p.setPen(Qt.PenStyle.NoPen)
        # Controller body
        p.setBrush(QColor(50, 50, 70))
        p.drawRoundedRect(25, 70, 50, 22, 8, 8)
        # Grips
        p.setBrush(QColor(40, 40, 60))
        p.drawRoundedRect(18, 75, 14, 18, 5, 5)
        p.drawRoundedRect(68, 75, 14, 18, 5, 5)
        # D-pad (left side)
        p.setBrush(QColor(80, 80, 100))
        p.drawRect(33, 77, 3, 10)
        p.drawRect(30, 80, 9, 3)
        # Buttons (right side — colored dots)
        p.setBrush(QColor(220, 60, 60)); p.drawEllipse(58, 76, 5, 5)   # red
        p.setBrush(QColor(60, 160, 60)); p.drawEllipse(64, 80, 5, 5)   # green
        p.setBrush(QColor(60, 100, 220)); p.drawEllipse(58, 84, 5, 5)  # blue
        p.setBrush(QColor(220, 200, 50)); p.drawEllipse(52, 80, 5, 5)  # yellow
        # Analog sticks
        p.setBrush(QColor(100, 100, 120))
        p.drawEllipse(36, 86, 6, 6)
        p.drawEllipse(56, 86, 6, 6)

    def _draw_sleep_mask(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen
        p.setPen(Qt.PenStyle.NoPen)
        # Mask band
        p.setBrush(QColor(60, 40, 100))
        p.drawRoundedRect(12, 32, 76, 18, 8, 8)
        # Eye covers
        p.setBrush(QColor(80, 55, 130))
        p.drawEllipse(20, 33, 24, 16)
        p.drawEllipse(56, 33, 24, 16)
        # Zzz text
        from PyQt6.QtGui import QFont
        p.setPen(QColor(200, 180, 255, 200))
        font = QFont("Arial", 8, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(78, 28, "z")
        font.setPointSize(10)
        p.setFont(font)
        p.drawText(84, 20, "Z")
        font.setPointSize(12)
        p.setFont(font)
        p.drawText(88, 10, "Z")

    def _draw_tasbeeh(self, p: QPainter, size: int):
        from PyQt6.QtCore import QRectF
        from PyQt6.QtGui import QPen
        import math
        # Prayer beads in a loop at bottom-right (held in hand)
        cx, cy, r = 74, 78, 12
        bead_r = 3
        p.setPen(Qt.PenStyle.NoPen)
        for i in range(12):
            angle = math.radians(i * 30)
            bx = cx + r * math.cos(angle)
            by = cy + r * math.sin(angle)
            col = QColor(120, 80, 40) if i % 3 else QColor(160, 120, 60)
            p.setBrush(col)
            p.drawEllipse(int(bx - bead_r), int(by - bead_r), bead_r * 2, bead_r * 2)
        # Tassel
        pen = QPen(QColor(100, 60, 30), 2)
        p.setPen(pen)
        p.drawLine(cx, cy - r - 2, cx, cy - r - 12)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(140, 100, 50))
        p.drawEllipse(cx - 3, cy - r - 14, 6, 6)

    def _draw_camera(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen
        p.setPen(Qt.PenStyle.NoPen)
        # Camera body
        p.setBrush(QColor(50, 50, 55))
        p.drawRoundedRect(30, 68, 40, 26, 5, 5)
        # Viewfinder bump
        p.setBrush(QColor(60, 60, 65))
        p.drawRoundedRect(42, 63, 16, 8, 3, 3)
        # Lens
        p.setBrush(QColor(30, 30, 35))
        p.drawEllipse(40, 72, 20, 20)
        p.setBrush(QColor(60, 90, 140))
        p.drawEllipse(44, 76, 12, 12)
        # Lens glare
        p.setBrush(QColor(200, 200, 255, 100))
        p.drawEllipse(47, 78, 4, 4)
        # Flash
        p.setBrush(QColor(255, 220, 100))
        p.drawEllipse(62, 69, 6, 6)
        # Strap hints
        pen = QPen(QColor(80, 80, 80), 2)
        p.setPen(pen)
        p.drawLine(30, 75, 22, 70)
        p.drawLine(70, 75, 78, 70)

    def _draw_popcorn(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen
        p.setPen(Qt.PenStyle.NoPen)
        # Bucket
        p.setBrush(QColor(200, 40, 40))
        pts = [
            (60, 68), (80, 68), (78, 95), (62, 95)
        ]
        from PyQt6.QtGui import QPolygon
        from PyQt6.QtCore import QPoint as QP
        poly = QPolygon([QP(x, y) for x, y in pts])
        p.drawPolygon(poly)
        # Stripes
        pen = QPen(QColor(230, 230, 230), 2)
        p.setPen(pen)
        p.drawLine(66, 68, 65, 95)
        p.drawLine(74, 68, 73, 95)
        # Popcorn kernels overflowing
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 245, 200))
        for kx, ky in [(62, 64), (68, 60), (75, 62), (72, 56), (65, 58), (78, 66)]:
            p.drawEllipse(kx, ky, 7, 6)
        # Kernel shadows
        p.setBrush(QColor(230, 210, 150, 100))
        for kx, ky in [(63, 65), (69, 61), (76, 63)]:
            p.drawEllipse(kx, ky, 4, 3)

    def _draw_magnifier(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen
        # Handle
        pen = QPen(QColor(120, 80, 40), 4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(80, 90, 68, 78)
        # Glass ring
        pen = QPen(QColor(160, 140, 100), 3)
        p.setPen(pen)
        p.setBrush(QColor(200, 230, 255, 60))
        p.drawEllipse(52, 60, 24, 24)
        # Glare
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 100))
        p.drawEllipse(57, 64, 6, 6)

    def _draw_megaphone(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen, QPolygon
        from PyQt6.QtCore import QPoint as QP
        p.setPen(Qt.PenStyle.NoPen)
        # Cone
        p.setBrush(QColor(220, 160, 40))
        cone = QPolygon([QP(60, 72), QP(88, 62), QP(88, 88), QP(60, 82)])
        p.drawPolygon(cone)
        # Mouth piece
        p.setBrush(QColor(180, 130, 30))
        p.drawRoundedRect(54, 70, 10, 14, 3, 3)
        # Bell opening
        p.setBrush(QColor(200, 150, 40))
        p.drawEllipse(84, 62, 8, 26)
        # Handle
        p.setBrush(QColor(100, 70, 30))
        p.drawRoundedRect(58, 84, 8, 10, 2, 2)

    def _draw_hardhat(self, p: QPainter, size: int):
        from PyQt6.QtGui import QPen
        p.setPen(Qt.PenStyle.NoPen)
        # Hat dome
        p.setBrush(QColor(240, 200, 40))
        p.drawEllipse(22, 2, 56, 30)
        # Brim
        p.setBrush(QColor(220, 180, 30))
        p.drawRoundedRect(18, 22, 64, 8, 4, 4)
        # Center ridge
        p.setBrush(QColor(250, 220, 80))
        p.drawRoundedRect(46, 2, 8, 24, 3, 3)
        # Highlight
        p.setBrush(QColor(255, 240, 150, 100))
        p.drawEllipse(30, 6, 18, 12)

    # Legacy compatibility wrappers
    def _show_headphones(self):
        self.equip_accessory("headphones")

    def _hide_headphones(self):
        if self._current_accessory == "headphones":
            self.unequip_accessory()

    # ---------- Cosmetic accessory painters (wardrobe) ----------
    # Delegated to features/accessory_drawer.py for maintainability.
    # _get_accessory_pixmap calls getattr(self, f"_draw_{name}", None),
    # so we register thin wrappers for each cosmetic item.

    def _draw_crown(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["crown"](p, size)

    def _draw_party_hat(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["party_hat"](p, size)

    def _draw_bow_tie(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["bow_tie"](p, size)

    def _draw_wizard_hat(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["wizard_hat"](p, size)

    def _draw_cape(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["cape"](p, size)

    def _draw_flower(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["flower"](p, size)

    def _draw_star_badge(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["star_badge"](p, size)

    def _draw_sunglasses(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["sunglasses"](p, size)

    def _draw_halo(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["halo"](p, size)

    def _draw_pirate_hat(self, p: QPainter, size: int):
        COSMETIC_DRAWERS["pirate_hat"](p, size)

    def _auto_detect_music(self):
        """Scans ALL open windows for music playback — runs every 2s independently."""
        try:
            music_info = self.music_detector.detect_from_all_windows()
        except Exception:
            return

        if music_info["just_started"]:
            self._music_playing = True
            self._show_headphones()
            # Switch to play_music or music_listen animation
            music_anim = random.choice(
                [a for a in ("play_music", "music_listen") if a in self.animations]
                or ["dance", "smile"]
            )
            self.set_state(music_anim)
            track = music_info["track"]
            if track and len(track) < 50:
                self.say(f"\u266b {track}", duration=4000)
            else:
                self.say_random("music_detected", duration=5000)
            self.mood_engine.boost_mood(10)

        elif music_info["just_stopped"]:
            self._music_playing = False
            self._hide_headphones()
            self.say_random("music_stopped", duration=5000)
            self.set_state("idle")

        elif music_info["is_playing"] and self._music_playing:
            # Keep headphones visible and music animation going
            if self._current_accessory != "headphones":
                self._show_headphones()
            if self.pet_state not in ("music_listen", "play_music", "dance", "smile", "dragging", "falling"):
                music_anim = random.choice(
                    [a for a in ("play_music", "music_listen") if a in self.animations]
                    or ["dance"]
                )
                self.set_state(music_anim)

    # ==========================================================
    #  CONTEXT ACTING
    # ==========================================================
    def _request_window_scan(self):
        """Trigger a background window scan (replaces direct gw call)."""
        if self.emotion_override or "run" in self.pet_state:
            return
        QTimer.singleShot(0, self._window_scanner.scan)

    def _on_window_scan_result(self, title: str):
        """Handle the scanned window title on the main thread."""
        title_lower = title.lower() if title else ""
        # v14: meeting detection
        self._meeting_detector.check_window(title_lower)
        # v14: app time tracking
        if title:
            self._app_time_tracker.switch_app(title)
        self.check_os_context(title)

    def check_os_context(self, title: str = ""):
        if self.emotion_override or "run" in self.pet_state:
            return
        try:
            if not title:
                self.hide_bubble()
                if self.pet_state == "work":
                    self.set_state("idle")
                self.mood_engine.set_context_category("")
                if self._current_accessory != "headphones":
                    self.unequip_accessory()
                # Stop any active session chains
                for cid in list(self.reaction_engine._active_chains):
                    self.reaction_engine.stop_chain(cid)
                return
            title_lower = title.lower()
            self.mood_engine.record_app_switch(title_lower)

            # v4: track website visits from browser windows
            self.web_tracker.record_window(title_lower)

            # Startled by rapid app switching
            startled_msg = self.reaction_engine.on_app_switch()
            if startled_msg:
                self.say(startled_msg, duration=3000, force=True)

            category = self._categorize_window(title_lower)
            self.mood_engine.set_context_category(category)
            self._auto_equip_for_context(category)

            # Manage reaction chains based on category
            chain_map = {
                "coding": "coding_session",
                "design": "design_session",
                "gaming": "gaming_session",
                "video": "video_session",
                "browser": "browser_session",
            }
            active_chain = chain_map.get(category)
            # Start the matching chain, stop others
            for cat, cid in chain_map.items():
                if cat == category:
                    self.reaction_engine.start_chain(cid)
                else:
                    self.reaction_engine.stop_chain(cid)

            # Late-night chain
            hour = datetime.now().hour
            if hour >= 23 or hour < 4:
                self.reaction_engine.start_chain("late_night")
            else:
                self.reaction_engine.stop_chain("late_night")

            if category == "coding":
                self.set_state("work")
                if not self.settings.get("focus_mode"):
                    self.say_random("coding")
                # Auto-detect git repo from window title
                if self._code_companion:
                    self._code_companion.detect_repo_from_window(title)
            elif category == "design":
                self.set_state("work")
                if not self.settings.get("focus_mode"):
                    self.say_random("design")
            elif category == "video":
                self.set_state("idle")
                if not self.settings.get("focus_mode"):
                    self.say_random("video")
            elif category == "browser":
                self.set_state("idle")
                if not self.settings.get("focus_mode"):
                    self.say_random("browser")
            elif category == "gaming":
                self.set_state("idle")
                if not self.settings.get("focus_mode"):
                    self.say_random("gaming")
            else:
                self.hide_bubble()
                if self.pet_state == "work":
                    self.set_state("idle")

            # Deep context-aware window commentary
            if not self.settings.get("focus_mode"):
                comment = self.reaction_engine.get_window_comment(title)
                if comment:
                    # Use AI to deliver it in character if available
                    if self.ai_brain.is_available and self.settings.get("enable_ai"):
                        self._ai_react(f"I noticed the user is on: {title[:50]}. Comment: {comment}")
                    else:
                        self.say(comment, duration=4000)

            if self.mood_engine.is_switching_too_fast():
                now = time.time()
                if now - self._last_distraction_warn > 120:
                    self._last_distraction_warn = now
                    self.say_random("distracted", duration=5000)
                    self.mood_engine.drain_mood(5)
        except Exception:
            self.hide_bubble()

    def _categorize_window(self, title: str) -> str:
        for kw in _CODING_KW:
            if kw in title:
                return "coding"
        for kw in _DESIGN_KW:
            if kw in title:
                return "design"
        for kw in _VIDEO_KW:
            if kw in title:
                return "video"
        for kw in _GAMING_KW:
            if kw in title:
                return "gaming"
        for kw in _BROWSER_KW:
            if kw in title:
                return "browser"
        return "other"

    # ==========================================================
    #  INTERACTIVE PETTING (v3: combos!)
    # ==========================================================
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            # If tasbeeh accessory is active, increment counter instead of petting
            if self._current_accessory == "tasbeeh":
                self._tasbeeh_click()
                return

            self.emotion_override = True
            self.mood_engine.pet_interaction()
            self._sfx.play("pet")

            # v3: combo tracking
            combo = self.combo_tracker.register_click()
            self.stats.data["total_pets"] = self.stats.data.get("total_pets", 0) + 1

            if combo >= 4:
                self.say_random("pet_combo_4plus", duration=5000)
                self.mood_engine.boost_mood(25)
                if "dance" in self.animations:
                    self.set_state("dance")
                else:
                    self.set_state("smile")
            elif combo == 3:
                self.say_random("pet_combo_3", duration=5000)
                self.mood_engine.boost_mood(20)
                self.set_state("smile")
                self.achievement_engine.check_combo(combo)
            elif combo == 2:
                self.say_random("pet_combo_2", duration=5000)
                self.mood_engine.boost_mood(10)
                self.set_state("smile")
            else:
                # Staged mood contagion — pet reacts based on current mood level
                contagion = self.reaction_engine.on_pet_interaction(self.mood_engine.mood)
                self.mood_engine.boost_mood(contagion["mood_boost"])
                if self.ai_brain.is_available and random.random() < 0.3:
                    self._ai_react(f"User petted me! I'm in stage '{contagion['stage']}'. React: {contagion['reaction_text']}")
                else:
                    self.say(contagion["reaction_text"], duration=5000)

                # Visual: escalate from current mood state
                if contagion["stage"] in ("healed", "maximum", "ecstatic"):
                    if "dance" in self.animations:
                        self.set_state("dance")
                    else:
                        self.set_state("smile")
                elif contagion["stage"] in ("sad",):
                    if "sad" in self.animations:
                        self.set_state("sad")
                    else:
                        self.set_state("idle")
                else:
                    self.set_state("smile")

            QTimer.singleShot(3000, self.end_emotion)

    def end_emotion(self):
        self.emotion_override = False
        self.hide_bubble()
        self.set_state("idle")

    # ==========================================================
    #  SPEECH BUBBLE
    # ==========================================================
    def say(self, text, duration=0, force=False):
        now = time.time()
        cooldown = self.settings.get("speech_cooldown_sec")
        if not force:
            # Queue if a bubble is currently showing
            if now < self._bubble_expires_at:
                self._speech_queue.append((text, duration))  # deque(maxlen=8) auto-drops oldest
                return
            if text == self._last_speech_text and (now - self._last_speech_time) < cooldown:
                return

            hour = time.localtime().tm_hour
            qs = self.settings.get("quiet_hours_start")
            qe = self.settings.get("quiet_hours_end")
            if qs > qe:
                if hour >= qs or hour < qe:
                    return
            elif qs <= hour < qe:
                return

        self._last_speech_time = now
        self._last_speech_text = text

        # v3: update bubble color before showing
        self._update_bubble_style()

        self.bubble.setText(text)
        self.bubble.adjustSize()
        bubble_x = 75 + (self.pet_width // 2) - (self.bubble.width() // 2)
        bubble_x = max(2, min(bubble_x, self.width() - self.bubble.width() - 2))
        self.bubble.move(bubble_x, max(5, 70 - self.bubble.height()))
        self.bubble.show()
        # Fade in — disconnect any leftover hide signal from previous fade-out
        self._bubble_fade.stop()
        try:
            self._bubble_fade.finished.disconnect()
        except TypeError:
            pass
        self._bubble_fade.setStartValue(0.0)
        self._bubble_fade.setEndValue(1.0)
        self._bubble_fade.start()

        # Calculate how long to show this bubble
        min_dur = self.settings.get("bubble_min_duration_ms")
        if duration > 0:
            show_dur = max(duration, min_dur)
        else:
            # Auto-calculate from text length: 80ms per char + base
            chars = len(text)
            show_dur = max(min_dur, 4000 + chars * 80)
        self._bubble_timer.start(show_dur)
        self._bubble_expires_at = now + show_dur / 1000.0

    def say_random(self, pool_key, duration=0, **fmt):
        lines = SPEECH_POOL.get(pool_key, [])
        # Try AI-generated character speech first
        if (self.ai_brain.is_available
                and self.settings.get("enable_ai")
                and pool_key not in ("note_saved",)):  # Skip trivial pools
            fallback_lines = lines
            if fmt and fallback_lines:
                fallback_lines = [l.format(**fmt) for l in fallback_lines]

            def on_ai_say(text):
                if text:
                    self._ai_chat_signal.response_ready.emit(text)

            self.ai_brain.character_say(
                pool_key, self._get_ai_context(), on_ai_say,
                fallback_lines=fallback_lines,
            )
            return
        # Fallback: static speech pool
        if not lines:
            return
        text = random.choice(lines)
        if fmt:
            text = text.format(**fmt)
        self.say(text, duration=duration)

    def hide_bubble(self, force=False):
        # Don't hide if the bubble hasn't expired yet (unless forced/timer-triggered)
        if not force and time.time() < self._bubble_expires_at:
            return
        self._bubble_expires_at = 0.0
        self._bubble_timer.stop()
        self._bubble_fade.stop()
        self._bubble_fade.setStartValue(self._bubble_opacity.opacity())
        self._bubble_fade.setEndValue(0.0)
        try:
            self._bubble_fade.finished.disconnect()
        except TypeError:
            pass
        self._bubble_fade.finished.connect(self.bubble.hide)
        self._bubble_fade.start()

    def _on_bubble_expired(self):
        """Called when bubble timer fires — hide current, show next queued."""
        self.hide_bubble(force=True)
        if self._speech_queue:
            text, dur = self._speech_queue.popleft()
            QTimer.singleShot(400, lambda: self.say(text, duration=dur))

    # ==========================================================
    #  WELCOME (v3: + time-of-day greeting)
    # ==========================================================
    def _show_welcome(self):
        # Play startup animation on launch
        if "startup" in self.animations:
            self.set_state("startup")
            QTimer.singleShot(3000, lambda: self.set_state("idle"))
        msg = self.stats.get_welcome_message()
        self.say(msg, duration=4000)

        # Multi-phase greeting sequence (replaces simple tod greeting)
        if self.settings.get("enable_time_awareness") and not self._tod_greeted:
            self._tod_greeted = True
            # Phase 0 after welcome fades, then phases chain themselves
            self._greeting_phase = 0
            QTimer.singleShot(6000, self._do_multi_phase_greeting)

        # Seasonal/holiday check on startup
        holiday = self.reaction_engine.check_seasonal_greeting()
        if holiday:
            QTimer.singleShot(15000, lambda: self.say(holiday, duration=6000))

    # ==========================================================
    #  POMODORO
    # ==========================================================
    def start_pomodoro(self):
        work_min = self.settings.get("pomodoro_work_min")
        self.pomodoro_active = True
        self.pomodoro_is_break = False
        self.pomodoro_remaining = work_min * 60
        self._pomodoro_timer.start(1000)
        self.say(f"Pomodoro started! {work_min} min focus.", duration=5000)

    def stop_pomodoro(self):
        self.pomodoro_active = False
        self._pomodoro_timer.stop()
        self.say("Pomodoro cancelled.", duration=5000)

    def _pomodoro_tick(self):
        if not self.pomodoro_active:
            return
        self.pomodoro_remaining -= 1
        self.update()  # repaint pomodoro ring
        if self.pomodoro_remaining <= 0:
            if self.pomodoro_is_break:
                self.say_random("pomodoro_break_done", duration=5000)
                self.pomodoro_active = False
                self._pomodoro_timer.stop()
                self.update()  # clear ring
            else:
                self.say_random("pomodoro_done", duration=5000)
                self.mood_engine.boost_energy(10)
                self.stats.data["total_pomodoros"] = self.stats.data.get("total_pomodoros", 0) + 1
                self.stats.save()
                # XP for pomodoro
                if self.settings.get("enable_xp_system"):
                    leveled = self.stats.add_xp(self.settings.get("xp_per_pomodoro"))
                    self._update_xp_label()
                    if leveled:
                        lv = self.stats.data.get("level", 1)
                        self.say_random("level_up", lv=lv, duration=5000)
                self.pomodoro_is_break = True
                self.pomodoro_remaining = self.settings.get("pomodoro_break_min") * 60

    # ==========================================================
    #  REMINDERS
    # ==========================================================
    def _reminder_tick(self):
        self._stretch_counter += 1
        self._water_counter += 1
        stretch_interval = self.settings.get("stretch_reminder_min") * 60
        water_interval = self.settings.get("water_reminder_min") * 60
        if self._stretch_counter >= stretch_interval:
            self._stretch_counter = 0
            self.say_random("stretch", duration=5000)
        if self._water_counter >= water_interval:
            self._water_counter = 0
            self.say_random("water", duration=5000)

    # ==========================================================
    #  v6: AI BRAIN INTEGRATION
    # ==========================================================
    def _get_ai_context(self) -> dict:
        """Gather current pet/user context for AI prompts."""
        hour = datetime.now().hour
        if 5 <= hour < 12:
            tod = "morning"
        elif 12 <= hour < 17:
            tod = "afternoon"
        elif 17 <= hour < 21:
            tod = "evening"
        else:
            tod = "night"

        return {
            "mood": self.mood_engine.mood,
            "energy": self.mood_engine.energy,
            "focus": self.mood_engine.focus,
            "current_app": self.mood_engine._last_context_category or self.mood_engine.last_active_window or "unknown",
            "time_of_day": tod,
            "level": self.stats.data.get("level", 1),
            "streak": self.stats.data.get("streak", 0),
            "memory_context": self.pet_memory.get_context_for_ai(),
        }

    def _open_ai_chat(self):
        """Open the AI chat dialog window."""
        name = self.settings.get("pet_name")
        if self._ai_chat_dialog is None or not self._ai_chat_dialog.isVisible():
            self._ai_chat_dialog = AIChatDialog(
                name, self.ai_brain, self._get_ai_context,
                memory=self.pet_memory,
                reminders=self.reminder_mgr,
                habits=self.habit_tracker,
                briefing=self.daily_briefing,
                parent=None,
            )
        self._ai_chat_dialog.show()
        self._ai_chat_dialog.raise_()
        self._ai_chat_dialog.activateWindow()
        self._ai_chat_dialog.input_field.setFocus()

    def _on_ai_quick_response(self, text: str):
        """Handle a quick AI response (for contextual reactions)."""
        if text:
            self.say(text, duration=5000)

    def _on_reminder_fired(self, text: str):
        """Handle a reminder firing — show speech bubble and open chat."""
        self.say(f"\u23f0 {text}", duration=8000)
        # Also push to chat if open
        if self._ai_chat_dialog and self._ai_chat_dialog.isVisible():
            self._ai_chat_dialog._on_reminder_fired(text)

    def _ai_react(self, situation: str):
        """Ask the AI for a short contextual reaction (non-blocking)."""
        if not self.ai_brain.is_available:
            return

        self.say("💭 Thinking...", duration=2000)

        def callback(reply):
            if reply:
                self._ai_chat_signal.response_ready.emit(reply)

        self.ai_brain.quick_response(situation, self._get_ai_context(), callback)

    def _check_proactive_suggestion(self):
        """Periodically check if there's a useful suggestion to show."""
        suggestion = self.daily_briefing.get_proactive_suggestion(self._get_ai_context())
        if suggestion:
            self.say(suggestion, duration=8000)

    # ==========================================================
    #  DYNAMIC REACTION ENGINE INTEGRATION
    # ==========================================================
    def _cursor_awareness_tick(self):
        """Fast timer (100ms) — tracks cursor for eye direction & startled."""
        cursor = QCursor.pos()
        result = self.reaction_engine.track_cursor(
            cursor.x(), cursor.y(), self.x() + self.width() // 2, self.y() + self.height() // 2,
        )
        if not result:
            return

        # Startled by fast cursor zoom-by
        if result.get("type") == "startled_cursor" and not self.emotion_override:
            self.emotion_override = True
            self.say(random.choice([
                "*jumps* WHOAA that was fast!! 😱",
                "*ducks* Don't scare me like that! 💫",
                "ZOOM! Was that the cursor or a rocket?! 🚀",
            ]), duration=3000, force=True)
            if "stretch" in self.animations:
                self.set_state("stretch")
            QTimer.singleShot(3000, self.end_emotion)

        # Curious when cursor lingers near pet
        elif result.get("type") == "curious" and not self.emotion_override:
            if random.random() < 0.02:  # Don't spam — ~2% per 100ms tick while lingering
                self.say(random.choice([
                    "Hmm? What are you looking at? 👀",
                    "*stares back* ...hi! 😊",
                    "Poke me! Go on~ 🐾",
                    "I can feel you watching me~ 👁️",
                ]), duration=5000)

    def _reaction_tick(self):
        """3s timer — handles chains, fidgets, comedy, dreams, seasonal."""
        if self.emotion_override:
            return

        re = self.reaction_engine

        # Reaction chain progression
        events = re.tick()
        for ev in events:
            if ev.get("text"):
                self.say(ev["text"], duration=5000)

        # Dream bubbles while sleeping
        if self.pet_state == "sleep":
            dream = re.get_dream_bubble()
            if dream:
                self.say(dream, duration=4000, force=True)
            return  # Skip other reactions while sleeping

        # Idle fidgets
        if self.pet_state in ("idle", "sit"):
            fidget = re.get_idle_fidget()
            if fidget:
                self._do_fidget(fidget)

        # Physical comedy (rare random event)
        comedy = re.try_comedy_event()
        if comedy:
            self.say(comedy["text"], duration=4000)
            state = comedy.get("state")
            if state and state in self.animations:
                self.emotion_override = True
                self.set_state(state)
                QTimer.singleShot(4000, self.end_emotion)

    def _do_fidget(self, fidget_type: str):
        """Execute a fidget micro-expression."""
        if fidget_type in ("blink", "slow_blink"):
            # Quick blink via brief state change
            pass  # No visible change needed — just a concept slot
        elif fidget_type == "look_around":
            if not self.settings.get("focus_mode"):
                self.say(random.choice([
                    "*looks around* 👀",
                    "*peeks left and right* 🔍",
                ]), duration=5000)
        elif fidget_type in ("tail_wag", "bounce"):
            if "smile" in self.animations and random.random() < 0.4:
                self.set_state("smile")
                QTimer.singleShot(2000, lambda: self.set_state("idle") if not self.emotion_override else None)
        elif fidget_type in ("sigh", "droop"):
            if not self.settings.get("focus_mode"):
                self.say(random.choice(["*sigh* 😔", "*droopy eyes* 😪"]), duration=5000)
        elif fidget_type == "yawn_small":
            if "yawn" in self.animations:
                self.set_state("yawn")
                QTimer.singleShot(2000, lambda: self.set_state("idle") if not self.emotion_override else None)
        elif fidget_type == "shift":
            pass  # Subtle position shift placeholder

    def _do_multi_phase_greeting(self):
        """Advance the multi-phase greeting sequence."""
        msg = self.reaction_engine.get_greeting_phase(self._greeting_phase)
        if msg:
            self.say(msg, duration=5000)
            self._greeting_phase += 1
            # Schedule next phase
            if self._greeting_phase < 5:
                QTimer.singleShot(8000, self._do_multi_phase_greeting)
        # else: greeting sequence done

    def _configure_ai(self):
        """Show dialog to configure AI model settings."""
        current_model = self.settings.get("ai_model")
        model, ok = QInputDialog.getText(
            self, "AI Model",
            "Enter Ollama model name:\n\n"
            "Popular models:\n"
            "  phi3 — fast, 4GB RAM\n"
            "  llama3.2 — balanced, 4GB RAM\n"
            "  mistral — quality, 8GB RAM\n"
            "  gemma2:2b — tiny, 3GB RAM\n\n"
            f"Current: {current_model}",
            text=current_model,
        )
        if ok and model.strip():
            self.settings.set("ai_model", model.strip())
            self.ai_brain.refresh_status()
            self.say(f"Switched brain to {model.strip()}! 🧠", duration=4000)

    def _toggle_ai(self):
        """Enable/disable AI brain."""
        current = self.settings.get("enable_ai")
        self.settings.set("enable_ai", not current)
        if not current:
            self.ai_brain.refresh_status()
            self.say("AI Brain activated! 🧠✨", duration=5000)
        else:
            self.say("AI Brain deactivated. Using classic mode.", duration=5000)

    # ==========================================================
    #  v6: QUICK ACTIONS (Screenshot, Run App, Shutdown, Restart)
    # ==========================================================
    def _take_screenshot(self):
        """Take a screenshot and save to Desktop."""
        try:
            import subprocess
            # Use the 'screenshot' animation
            if "screenshot" in self.animations:
                self.emotion_override = True
                self.set_state("screenshot")

            # Use PowerShell to screenshot
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = os.path.join(desktop, f"screenshot_{ts}.png")

            ps_cmd = (
                f"Add-Type -AssemblyName System.Windows.Forms;"
                f"$bmp = [System.Windows.Forms.Screen]::PrimaryScreen;"
                f"$bounds = $bmp.Bounds;"
                f"$bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height);"
                f"$graphics = [System.Drawing.Graphics]::FromImage($bitmap);"
                f"$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size);"
                f"$bitmap.Save('{filepath}');"
                f"$graphics.Dispose(); $bitmap.Dispose()"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            self.say(f"\U0001f4f8 Screenshot saved!\n{os.path.basename(filepath)}", duration=4000)
            QTimer.singleShot(3000, self.end_emotion)
        except Exception as e:
            self.say(f"Screenshot failed: {e}", duration=5000)

    def _run_app_dialog(self):
        """Ask user for an app/command to run."""
        text, ok = QInputDialog.getText(
            self, "Run App",
            "Enter app name or full path:\n\n"
            "Examples:\n"
            "  notepad\n"
            "  calc\n"
            "  explorer\n"
            "  C:\\path\\to\\app.exe",
        )
        if ok and text.strip():
            self._launch_app(text.strip())

    def _launch_app(self, app_path: str):
        """Launch an application and show run_app animation."""
        import subprocess
        try:
            if "run_app" in self.animations:
                self.emotion_override = True
                self.set_state("run_app")

            subprocess.Popen(
                app_path, shell=True,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            app_name = os.path.basename(app_path).replace(".exe", "")
            self.say(f"\U0001f680 Launching {app_name}!", duration=3000)
            QTimer.singleShot(3000, self.end_emotion)
        except Exception as e:
            self.say(f"Could not launch: {e}", duration=3000)

    def _shutdown_pc(self):
        """Shutdown the PC after confirmation."""
        text, ok = QInputDialog.getText(
            self, "Shutdown PC",
            "Type 'yes' to confirm shutdown:\n\n"
            "(PC will shut down in 30 seconds)",
        )
        if ok and text.strip().lower() == "yes":
            import subprocess
            if "shutdown" in self.animations:
                self.emotion_override = True
                self.set_state("shutdown")
            self.say("Shutting down... goodbye! \U0001f44b\U0001f4a4", duration=5000)
            QTimer.singleShot(3000, lambda: subprocess.Popen(
                "shutdown /s /t 30", shell=True,
                creationflags=0x08000000,
            ))
        else:
            self.say("Shutdown cancelled.", duration=2000)

    def _restart_pc(self):
        """Restart the PC after confirmation."""
        text, ok = QInputDialog.getText(
            self, "Restart PC",
            "Type 'yes' to confirm restart:\n\n"
            "(PC will restart in 30 seconds)",
        )
        if ok and text.strip().lower() == "yes":
            import subprocess
            if "restart" in self.animations:
                self.emotion_override = True
                self.set_state("restart")
            self.say("Restarting... hold on! \U0001f504\u26a1", duration=5000)
            QTimer.singleShot(3000, lambda: subprocess.Popen(
                "shutdown /r /t 30", shell=True,
                creationflags=0x08000000,
            ))
        else:
            self.say("Restart cancelled.", duration=2000)

    def _show_notification_anim(self, text: str, duration: int = 5000):
        """Show a notification with the notification GIF — bypasses speech cooldown."""
        if "notification" in self.animations:
            self.emotion_override = True
            self.set_state("notification")
        self.say(text, duration=duration, force=True)
        QTimer.singleShot(duration, self.end_emotion)

    # ==========================================================
    #  v11: REAL-TIME PROGRESS MONITOR
    # ==========================================================
    def _build_progress_overlay(self):
        """Create the floating progress overlay widget (child of pet)."""
        overlay = QWidget(self)
        overlay.setFixedWidth(230)
        overlay.setStyleSheet(
            "QWidget#progress_overlay {"
            "   background: rgba(30, 30, 30, 200);"
            "   border-radius: 10px;"
            "}"
            "QLabel { color: white; background: transparent; }"
            "QProgressBar {"
            "   background: rgba(255,255,255,40);"
            "   border: none; border-radius: 3px;"
            "   max-height: 6px; min-height: 6px;"
            "}"
            "QProgressBar::chunk {"
            "   background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            "       stop:0 #4fc3f7, stop:1 #29b6f6);"
            "   border-radius: 3px;"
            "}"
        )
        overlay.setObjectName("progress_overlay")
        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        title = QLabel("\u2b07 Active Progress")
        title.setFont(QFont("Arial", 8, QFont.Weight.Bold))
        title.setStyleSheet("color: #4fc3f7; background: transparent;")
        layout.addWidget(title)
        overlay._title_label = title
        overlay._rows_layout = QVBoxLayout()
        overlay._rows_layout.setSpacing(4)
        layout.addLayout(overlay._rows_layout)
        overlay._row_widgets = []  # list of (name_label, bar, info_label) tuples
        overlay.hide()
        return overlay

    def _ensure_progress_rows(self, count):
        """Make sure the overlay has exactly *count* item rows."""
        rows = self._progress_overlay._row_widgets
        while len(rows) < count:
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 2, 0, 2)
            rl.setSpacing(1)
            name_lbl = QLabel()
            name_lbl.setFont(QFont("Arial", 7, QFont.Weight.Bold))
            name_lbl.setStyleSheet("color: #eee; background: transparent;")
            bar = QProgressBar()
            bar.setTextVisible(False)
            bar.setRange(0, 100)
            info_lbl = QLabel()
            info_lbl.setFont(QFont("Arial", 7))
            info_lbl.setStyleSheet("color: #aaa; background: transparent;")
            rl.addWidget(name_lbl)
            rl.addWidget(bar)
            rl.addWidget(info_lbl)
            self._progress_overlay._rows_layout.addWidget(row)
            rows.append((name_lbl, bar, info_lbl, row))
        # hide extra rows
        for i, (_, _, _, w) in enumerate(rows):
            w.setVisible(i < count)

    def _on_progress_updated(self, items: list):
        """Called every ~2 s with the latest progress snapshot."""
        self._progress_items = items
        if not items:
            if self._progress_overlay.isVisible():
                self._progress_overlay.hide()
            return

        self._ensure_progress_rows(len(items))
        rows = self._progress_overlay._row_widgets

        for i, item in enumerate(items):
            name_lbl, bar, info_lbl, _ = rows[i]
            name_lbl.setText(item["name"])

            if item["percent"] >= 0:
                bar.setRange(0, 100)
                bar.setValue(int(item["percent"]))
                info_lbl.setText(f"{item['percent']:.0f}%")
            else:
                # Indeterminate — use 0-0 range for "busy" animation
                bar.setRange(0, 0)
                parts = []
                if item.get("speed") and item["speed"] > 0:
                    parts.append(_format_speed(item["speed"]))
                if item.get("size") and item["size"] > 0:
                    parts.append(_format_size(item["size"]))
                info_lbl.setText("  ".join(parts) if parts else "downloading…")

        self._progress_overlay.adjustSize()
        # Position above the pet
        px = 75 + (self.pet_width // 2) - (self._progress_overlay.width() // 2)
        py = max(2, 95 - self._progress_overlay.height())
        self._progress_overlay.move(px, py)
        if not self._progress_overlay.isVisible():
            self._progress_overlay.show()
        self._progress_overlay.raise_()

    def _on_progress_started(self, name: str):
        """A new download or operation was detected."""
        log.info("Progress started: %s", name)
        if "excited" in self.animations:
            self.set_state("excited")
            QTimer.singleShot(3000, lambda: self.set_state("idle") if not self.emotion_override else None)
        self.say(f"\u2b07 Downloading: {name}", duration=4000, force=True)

    def _on_progress_finished(self, name: str, detail: str):
        """A download or operation just completed."""
        log.info("Progress finished: %s", name)
        self._show_notification_anim(f"\u2705 Done: {name}", duration=5000)

    def _toggle_progress_monitor(self):
        """Toggle the progress monitor on/off via the context menu."""
        enabled = self.settings.get("enable_progress_monitor")
        if enabled:
            self.settings.set("enable_progress_monitor", False)
            self._progress_monitor.stop()
            self._progress_overlay.hide()
            self.say("Progress monitor OFF", duration=2000, force=True)
        else:
            self.settings.set("enable_progress_monitor", True)
            self._progress_monitor = ProgressMonitor(self, interval_ms=2000)
            self._progress_monitor.updated.connect(self._on_progress_updated)
            self._progress_monitor.item_started.connect(self._on_progress_started)
            self._progress_monitor.item_finished.connect(self._on_progress_finished)
            self.say("Progress monitor ON", duration=2000, force=True)

    # ==========================================================
    #  v7: WINDOWS NOTIFICATION MONITOR
    # ==========================================================
    def _load_recent_notifications(self):
        """Load the last 20 notifications into the log on startup (no popup)."""
        try:
            tmp = self.notif_reader._tmp_path
            shutil.copy2(self.notif_reader._db_path, tmp)
            conn = sqlite3.connect(tmp)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT n.Id, h.PrimaryId, n.ArrivalTime, n.Payload
                FROM Notification n
                LEFT JOIN NotificationHandler h ON n.HandlerId = h.RecordId
                WHERE n.Type = 'toast'
                ORDER BY n.ArrivalTime DESC LIMIT 20
            """)
            rows = cursor.fetchall()
            conn.close()
            try:
                os.remove(tmp)
            except OSError:
                pass

            for row in reversed(rows):
                nid, primary_id, arrival, payload = row
                texts = self.notif_reader._parse_payload(payload)
                title = texts[0] if texts else ""
                body = texts[1] if len(texts) > 1 else ""
                app_name = self.notif_reader._friendly_app_name(primary_id or "")
                arrival_dt = self.notif_reader._filetime_to_datetime(arrival) if arrival else datetime.now()
                self._notif_log.append({
                    "id": nid,
                    "app": app_name,
                    "title": title,
                    "body": body,
                    "time": arrival_dt,
                })
        except Exception:
            pass

    def _check_notifications(self):
        """Poll for new Windows notifications every 8 seconds."""
        new = self.notif_reader.check_new()
        if not new:
            return

        for notif in new:
            self._notif_log.append(notif)
            # Feed into digest system
            self._notif_digest.add(
                app=notif.get("app", "Unknown"),
                title=notif.get("title", ""),
                body=notif.get("body", ""),
            )

        # Keep only last 50 in the log
        if len(self._notif_log) > 50:
            self._notif_log = self._notif_log[-50:]

        # In DND mode, don't show individual notifications
        if self._notif_digest.is_dnd:
            return

        self._sfx.play("notification")
        # Show the most recent notification to the user
        latest = new[-1]
        app = latest["app"]
        title = latest["title"]
        body = latest["body"]

        # Build display text
        lines = [f"\U0001f514 {app}"]
        if title:
            lines.append(title)
        if body and body != title:
            # Truncate long body
            lines.append(body[:80] + ("..." if len(body) > 80 else ""))

        display = "\n".join(lines)

        # If multiple new at once, mention the count
        if len(new) > 1:
            display += f"\n(+{len(new) - 1} more)"

        self._show_notification_anim(display, duration=6000)

        # Reaction engine may add a fun comment about the notification
        reaction = self.reaction_engine.on_notification(title)
        if reaction:
            QTimer.singleShot(7000, lambda: self.say(reaction, duration=3000))

    def _show_notification_log(self):
        """Show a dialog with recent notifications."""
        if not self._notif_log:
            self.say("No notifications yet!", duration=2000)
            return

        dlg = QDialog(None)
        dlg.setWindowTitle("Recent Notifications")
        dlg.setFixedSize(460, 400)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        dlg.setStyleSheet("QDialog { background: #1E1E2E; }")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(10, 10, 10, 10)

        header = QLabel(f"\U0001f514 Recent Notifications ({len(self._notif_log)})")
        header.setStyleSheet("color: #CDD6F4; font-size: 15px; font-weight: bold; padding: 6px;")
        layout.addWidget(header)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 8px; background: #313244; }"
            "QScrollBar::handle:vertical { background: #585B70; border-radius: 4px; }"
        )

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(6)

        # Show newest first
        for notif in reversed(self._notif_log[-30:]):
            frame = QFrame()
            frame.setStyleSheet(
                "QFrame { background: #313244; border-radius: 8px; padding: 8px; }"
            )
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(8, 6, 8, 6)
            fl.setSpacing(2)

            app_label = QLabel(f"\U0001f4f1 {notif['app']}")
            app_label.setStyleSheet("color: #89B4FA; font-size: 12px; font-weight: bold;")
            fl.addWidget(app_label)

            if notif["title"]:
                title_lbl = QLabel(notif["title"])
                title_lbl.setStyleSheet("color: #CDD6F4; font-size: 12px;")
                title_lbl.setWordWrap(True)
                fl.addWidget(title_lbl)

            if notif["body"] and notif["body"] != notif["title"]:
                body_lbl = QLabel(notif["body"][:150])
                body_lbl.setStyleSheet("color: #A6ADC8; font-size: 11px;")
                body_lbl.setWordWrap(True)
                fl.addWidget(body_lbl)

            time_str = notif["time"].strftime("%I:%M %p") if isinstance(notif["time"], datetime) else ""
            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet("color: #585B70; font-size: 10px;")
            fl.addWidget(time_lbl)

            container_layout.addWidget(frame)

        container_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "  border-radius: 6px; padding: 8px 20px; font-weight: bold; }"
            "QPushButton:hover { background: #74C7EC; }"
        )
        close_btn.clicked.connect(dlg.close)
        layout.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dlg.exec()

    # ==========================================================
    #  POMODORO RING — visual circular progress around the pet
    # ==========================================================
    def _paint_pomodoro_ring(self, painter: QPainter):
        """Draw a circular arc around the pet showing pomodoro time remaining."""
        cx = self.pet_label.x() + self.pet_width // 2
        cy = self.pet_label.y() + self.pet_height // 2
        radius = max(self.pet_width, self.pet_height) // 2 + 10
        rect_x = cx - radius
        rect_y = cy - radius
        rect_size = radius * 2

        # Calculate progress
        total = (self.settings.get("pomodoro_break_min" if self.pomodoro_is_break
                                   else "pomodoro_work_min") * 60)
        progress = 1.0 - (self.pomodoro_remaining / max(total, 1))
        span_angle = int(progress * 360 * 16)  # Qt uses 1/16 degree

        # Colors: blue for work, green for break
        if self.pomodoro_is_break:
            ring_color = QColor(80, 200, 120, 180)
            bg_color = QColor(80, 200, 120, 40)
        else:
            ring_color = QColor(80, 140, 255, 180)
            bg_color = QColor(80, 140, 255, 40)

        from PyQt6.QtGui import QPen
        # Background ring
        painter.setPen(QPen(bg_color, 4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect_x, rect_y, rect_size, rect_size)

        # Progress arc (starts at 12 o'clock = 90° in Qt coords)
        painter.setPen(QPen(ring_color, 4))
        painter.drawArc(rect_x, rect_y, rect_size, rect_size,
                        90 * 16, -span_angle)

        # Time remaining text
        mins = self.pomodoro_remaining // 60
        secs = self.pomodoro_remaining % 60
        label = "Break" if self.pomodoro_is_break else "Focus"
        painter.setPen(ring_color)
        painter.setFont(QFont("Arial", 7, QFont.Weight.Bold))
        painter.drawText(rect_x, rect_y - 6, rect_size, 14,
                         Qt.AlignmentFlag.AlignCenter,
                         f"{label} {mins}:{secs:02d}")

    # ==========================================================
    #  PAINT — draw a nearly invisible rect over the pet area
    #  so Windows recognizes it as hittable (alpha > 0 required)
    # ==========================================================
    def paintEvent(self, event):
        painter = QPainter(self)
        # Paint an alpha=1 rect over the pet area — invisible but hittable
        painter.fillRect(
            self.pet_label.x(), self.pet_label.y(),
            self.pet_label.width(), self.pet_label.height(),
            QColor(0, 0, 0, 1),
        )
        # Pomodoro ring overlay
        if self.pomodoro_active and self.pomodoro_remaining > 0:
            self._paint_pomodoro_ring(painter)
        # Focus mode indicator — subtle pulsing blue border
        if self.settings.get("focus_mode"):
            from PyQt6.QtGui import QPen
            painter.setPen(QPen(QColor(80, 140, 255, 100), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            cx = self.pet_label.x() + self.pet_width // 2
            cy = self.pet_label.y() + self.pet_height // 2
            r = max(self.pet_width, self.pet_height) // 2 + 4
            painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)
            painter.setPen(QColor(80, 140, 255, 160))
            painter.setFont(QFont("Segoe UI", 6))
            painter.drawText(cx - 20, cy - r - 10, 40, 10,
                             Qt.AlignmentFlag.AlignCenter, "🔒 Focus")
        # Error indicator — red dot top-right of pet
        if self._feature_errors:
            painter.setBrush(QColor(220, 50, 50, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(self.pet_label.x() + self.pet_width - 6,
                                self.pet_label.y(), 12, 12)
        painter.end()

    # ==========================================================
    #  MOUSE EVENTS — drag by global cursor position for reliability
    # ==========================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            self._sfx.play("click")
            self.set_state("dragging")
        elif event.button() == Qt.MouseButton.MiddleButton:
            # Middle-click → Quick Launcher Wheel
            center = self.pos() + QPoint(self.width() // 2, self.height() // 2)
            self._quick_launcher.show_at(center)
        elif event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self._dragging:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            if self.y() < self.floor_y:
                self.set_state("falling")
            else:
                self.set_state("idle")

    # ==========================================================
    #  FILE DROP ZONE (v11)
    # ==========================================================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and self.settings.get("enable_file_drop"):
            event.acceptProposedAction()
            self.say_random("file_dropped", duration=3000)

    def dropEvent(self, event):
        if not event.mimeData().hasUrls():
            return
        try:
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if not paths:
                return
            results = self._file_drop.handle_drop(paths)
            if not results:
                return
            # Show info about first file and execute default action
            first = results[0]
            info_text = f"📦 {first['name']} ({first['detail']})"
            if first["actions"]:
                action = first["actions"][0]
                result_msg = self._file_drop.execute_action(first, action)
                info_text += f"\n{result_msg}"
            self.say(info_text, duration=6000, force=True)
        except Exception as e:
            log.warning("File drop error: %s", e)
            self.say("📦 Oops, couldn't process that file!", duration=3000)

    # ==========================================================
    #  v11: FEATURE HANDLERS
    # ==========================================================
    def _on_clipboard_event(self, event):
        if self.settings.get("focus_mode"):
            return
        pool_map = {
            "color": "clipboard_color",
            "error": "clipboard_error",
            "url": "clipboard_url",
            "code": "clipboard_code",
        }
        pool_key = pool_map.get(event.kind)
        if pool_key:
            self.say_random(pool_key, duration=4000)

    def _on_system_health_alert(self, alert_type: str, message: str):
        if self.settings.get("focus_mode"):
            return
        # Visual state changes based on system health
        if alert_type == "cpu_high":
            if "work" in self.animations:
                self.set_state("work")
            self.say(f"🔥 {message}", duration=5000, force=True)
        elif alert_type == "battery_low":
            if "sad" in self.animations:
                self.set_state("sad")
            self.say(f"🔋 {message}", duration=6000, force=True)
        elif alert_type == "battery_critical":
            self.say(f"⚠️ {message}", duration=8000, force=True)
        elif alert_type == "battery_charging":
            self.say(f"⚡ {message}", duration=4000)
        elif alert_type == "disk_low":
            self.say(f"💾 {message}", duration=5000, force=True)
        else:
            self.say(message, duration=4000)

    def _edit_launcher(self):
        dlg = LauncherEditDialog(self._quick_launcher, self)
        dlg.exec()

    def _show_note_archive(self):
        dlg = StickyArchiveDialog(self._sticky_notes, self)
        dlg.exec()

    def _show_streak_calendar(self):
        dlg = StreakCalendarDialog(self.stats, self.habit_tracker, self)
        dlg.exec()

    def _check_circadian(self):
        """Detect phase transitions and announce them."""
        circ = get_circadian_phase()
        new_phase = circ["phase"]
        if new_phase != self._circadian_phase:
            self._circadian_phase = new_phase
            comment = circadian_speech(new_phase)
            if comment:
                self.say(comment, duration=5000)

    def _on_voice_command(self, action: str):
        """Dispatch voice command actions."""
        handlers = {
            "screenshot":    self._take_screenshot,
            "pomodoro":      self.start_pomodoro,
            "stop_pomodoro": self.stop_pomodoro,
            "sticky_notes":  self._sticky_notes.toggle_all,
            "stats":         self._show_stats,
            "dashboard":     self._toggle_dashboard,
            "journal":       self._show_journal,
            "weather":       lambda: self.say(
                self._weather.get_display() if self._weather else "Weather not enabled",
                duration=5000,
            ),
            "launcher":      lambda: self._quick_launcher.show_at(
                self.pos() + QPoint(self.width() // 2, self.height() // 2)),
            "habits":        lambda: self.say(self.habit_tracker.status(), duration=6000),
            "todo":          self._toggle_todo_widget,
            "sleep":         lambda: self.set_state("sleep"),
            "wake":          lambda: self.set_state("idle"),
        }
        fn = handlers.get(action)
        if fn:
            self.say(f"🎤 Voice: {action}", duration=2000)
            fn()

    def _toggle_voice_commands(self):
        on = not self.settings.get("enable_voice_commands")
        self.settings.set("enable_voice_commands", on)
        if on and self._voice.is_available():
            self._voice.command_recognized.connect(self._on_voice_command)
            self._voice.start()
            self.say("🎤 Voice commands enabled! Say 'Hey Toty' to start.", duration=4000)
        else:
            self._voice.stop()
            self.say("🎤 Voice commands disabled.", duration=3000)

    def _show_wardrobe(self):
        # Check for new unlocks first
        newly = self._wardrobe.check_unlocks(self.stats, self.habit_tracker)
        for item_id in newly:
            name = next((n for i, n, *_ in WARDROBE_ITEMS if i == item_id), item_id)
            self.say(f"🎉 New accessory unlocked: {name}!", duration=4000, force=True)

        def _draw_preview(name: str) -> QPixmap:
            return self._get_accessory_pixmap(name)

        dlg = WardrobeDialog(self._wardrobe, _draw_preview, self)
        dlg.accessory_changed.connect(self._on_wardrobe_change)
        dlg.exec()

    def _on_wardrobe_change(self, item_id: str):
        if item_id:
            self.equip_accessory(item_id)
        else:
            self.unequip_accessory()

    def _on_quick_action(self, action: str):
        """Handle quick launcher wheel actions."""
        if action == "screenshot":
            self._take_screenshot()
        elif action == "pomodoro":
            if self.pomodoro_active:
                self.stop_pomodoro()
            else:
                self.start_pomodoro()
        elif action == "todo":
            self._toggle_todo_widget()
        elif action == "chat":
            self._open_ai_chat()
        elif action == "tasbeeh":
            self._open_tasbeeh_menu()
        elif action == "organize":
            self._manual_organize()
        elif action == "focus":
            self._toggle_focus_mode()
        elif action == "stats":
            self._show_stats()
        elif action == "dashboard":
            self._toggle_dashboard()
        elif action.startswith("app:"):
            app_path = action[4:]
            self._launch_app(app_path)

    def _on_notif_digest(self, text: str):
        self.say(text, duration=8000, force=True)

    def _on_sound_reaction(self, reaction_type: str, message: str):
        if self.settings.get("focus_mode"):
            return
        if reaction_type == "startled":
            self.emotion_override = True
            self._sfx.play("startled")
            if "excited" in self.animations:
                self.set_state("excited")
            self.say(message, duration=3000, force=True)
            QTimer.singleShot(2000, self.end_emotion)
        elif reaction_type == "sleepy":
            if self.pet_state not in ("work", "dragging", "falling"):
                self._sfx.play("yawn")
                if "yawn" in self.animations:
                    self.set_state("yawn")
                self.say(message, duration=4000)
        elif reaction_type == "vibing":
            self._sfx.play("purr")
            self.say(message, duration=3000)

    def _on_code_companion_alert(self, alert_type: str, message: str):
        if self.settings.get("focus_mode"):
            return
        self.say(f"🔧 {message}", duration=5000)

    def _on_challenge_completed(self, text: str, xp: int):
        self.say_random("challenge_complete", duration=5000)
        self.say(f"🏆 {text}\n+{xp} XP!", duration=5000, force=True)
        if self.settings.get("enable_xp_system"):
            self.stats.data["xp"] = self.stats.data.get("xp", 0) + xp
            self._update_xp_label()

    def _on_evolution_unlocked(self, stage_name: str, level: int):
        self._sfx.play("level_up")
        self.say_random("evolution_unlocked", duration=5000)
        self.say(f"✨ Evolved into: {stage_name}! (Lv.{level})", duration=6000, force=True)
        if "dance" in self.animations:
            self.emotion_override = True
            self.set_state("dance")
            QTimer.singleShot(4000, self.end_emotion)

    # ==========================================================
    #  v12: HOTKEY HANDLER
    # ==========================================================
    def _on_hotkey(self, action: str):
        """Route global hotkey actions."""
        actions = {
            "launcher": lambda: self._quick_launcher.show_at(
                self.pos() + QPoint(self.width() // 2, self.height() // 2)),
            "sticky_note": lambda: self._sticky_notes.create_note(
                pos=(self.x() + 80, self.y() - 150)),
            "reminder": self._add_smart_reminder,
            "screenshot": self._screenshot.start_capture,
            "dashboard": self._toggle_dashboard,
            "journal": self._show_journal,
            "tasbeeh": self._open_tasbeeh_menu,
            "clipboard_history": self._toggle_clipboard_history,
            "timer": self._toggle_quick_timer,
            "help": self._show_hotkey_help,
        }
        fn = actions.get(action)
        if fn:
            fn()

    # ==========================================================
    #  v12: SMART REMINDERS
    # ==========================================================
    def _on_smart_reminder(self, text: str, rid: int = 0):
        self._sfx.play("alert")
        self.say(text, duration=6000, force=True)
        self._last_fired_reminder_rid = rid

    def _add_smart_reminder(self):
        text, ok = QInputDialog.getText(
            self, "⏰ Quick Reminder",
            "e.g. 'in 30 min push code' or 'at 14:00 meeting':"
        )
        if ok and text.strip():
            r = self._smart_reminders.add_raw(text.strip())
            if r:
                self._sfx.play("notification")
                self.say_random("reminder_set", duration=3000)
            else:
                self.say("❌ Couldn't parse time. Try 'in 30 min ...' or 'at HH:MM ...'",
                         duration=5000, force=True)

    # ==========================================================
    #  v12: EYE CARE / HEALTH BREAKS
    # ==========================================================
    def _on_health_break(self, break_type: str, message: str):
        if self.settings.get("focus_mode"):
            return
        self._sfx.play("alert")
        self.say(message, duration=6000, force=True)
        if self._tray:
            self._tray.show_message("Health Break", message)

    def _on_break_done(self, break_type: str):
        self._sfx.play("happy")
        self.say_random("break_done", duration=3000)

    # ==========================================================
    #  v12: AI SMART ACTIONS
    # ==========================================================
    def _show_smart_actions(self):
        """Show AI action menu on clipboard text."""
        clipboard = QApplication.clipboard()
        text = clipboard.text() if clipboard else ""
        if not text.strip():
            self.say("📋 Copy some text first, then try Smart Actions!", duration=3000)
            return
        items = list(SMART_ACTIONS.values())
        choice, ok = QInputDialog.getItem(
            self, "🤖 AI Smart Actions", f"Text: {text[:50]}...\nChoose action:",
            items, 0, False
        )
        if ok and choice:
            action_key = [k for k, v in SMART_ACTIONS.items() if v == choice][0]
            self.say(f"🤖 Processing: {choice}...", duration=3000)
            self._smart_actions.run_action(action_key, text)

    def _on_smart_action_result(self, action: str, result: str):
        self._sfx.play("notification")
        label = SMART_ACTIONS.get(action, action)
        # Copy result to clipboard
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(result)
        self.say(f"{label}:\n{result[:300]}\n\n📋 Copied!", duration=8000, force=True)

    # ==========================================================
    #  v12: WEATHER
    # ==========================================================
    def _weather_accessory(self, accessory: str):
        if accessory in self._ACCESSORY_DRAW and not self._current_accessory:
            self.equip_accessory(accessory)

    # ==========================================================
    #  v12: SCREENSHOT
    # ==========================================================
    def _on_screenshot(self, path: str):
        self._sfx.play("notification")
        self.say_random("screenshot_taken", duration=3000)

    # ==========================================================
    #  v12: DAILY JOURNAL
    # ==========================================================
    def _prompt_journal(self):
        self._sfx.play("notification")
        self.say_random("journal_prompt", duration=4000)

    def _show_journal(self):
        dlg = JournalDialog(self)
        dlg.submitted.connect(self._journal.add_entry)
        dlg.show()

    def _on_journal_saved(self, mood: int, note: str):
        moods = {5: "😊 Great", 4: "🙂 Good", 3: "😐 Okay", 2: "😔 Low", 1: "😢 Bad"}
        self._sfx.play("happy")
        self.say(f"📓 Journal saved! Mood: {moods.get(mood, '?')}\n{self._journal.get_mood_trend()}",
                 duration=5000, force=True)

    # ==========================================================
    #  v12: BACKUP
    # ==========================================================
    def _export_backup(self):
        path = self._backup.export_backup()
        if path:
            self._sfx.play("achievement")
            self.say(f"💾 Backup saved!\n{os.path.basename(path)}", duration=4000, force=True)
        else:
            self.say("❌ Backup failed!", duration=3000, force=True)

    def _import_backup(self):
        backups = self._backup.list_backups()
        if not backups:
            self.say("No backups found!", duration=3000)
            return
        choice, ok = QInputDialog.getItem(
            self, "📦 Import Backup", "Select backup:", backups, 0, False
        )
        if ok and choice:
            count = self._backup.import_backup(choice)
            self.say(f"📦 Restored {count} files! Restart to apply.", duration=5000, force=True)

    # ==========================================================
    #  v12: FOCUS MODE TOGGLE
    # ==========================================================
    def _toggle_focus_mode(self):
        on = self.settings.get("focus_mode")
        self.settings.set("focus_mode", not on)
        if not on:
            self.say("🎯 Focus Mode ON — minimal distractions", duration=3000)
        else:
            self.say("🎯 Focus Mode OFF", duration=3000)
        if self._tray:
            self._tray.set_focus(not on)

    def _check_daily_challenges(self):
        """Gather current stats and check challenge progress."""
        current = {
            "total_keys": self.stats.data.get("total_keys", 0),
            "focus_min": self.mood_engine.get_focus_minutes(),
            "total_pets": self.stats.data.get("total_pets", 0),
            "pomodoros_today": self.stats.data.get("pomodoros_today", 0),
            "streak": self.stats.data.get("streak", 0),
        }
        self.social.check_challenges(current)
        # Also check evolution
        level = self.stats.data.get("level", 1)
        self.social.check_evolution(level)

    def _toggle_dashboard(self):
        pet_pos = self.pos() + QPoint(75, 100)
        self._prod_dashboard.toggle(pet_pos, self.pet_width)

    def _open_tasbeeh_menu(self):
        """Show tasbeeh preset selection and start counting."""
        items = [f"{v['ar']} ({v['en']})" for v in TASBEEH_PRESETS.values()]
        choice, ok = QInputDialog.getItem(
            self, "📿 Tasbeeh / تسبيح", "Choose dhikr:", items, 0, False
        )
        if ok and choice:
            key = list(TASBEEH_PRESETS.keys())[items.index(choice)]
            self.tasbeeh.set_preset(key)
            self.equip_accessory("tasbeeh")
            self.say(f"📿 {self.tasbeeh.get_display()}", duration=4000, force=True)

    def _tasbeeh_click(self):
        """Handle a tasbeeh count increment (called on double-click when tasbeeh active)."""
        result = self.tasbeeh.increment()
        if result["completed"]:
            self.say(f"✅ {result['ar']} done! ({result['target']}x)\nToday: {result['today_total']}", duration=5000, force=True)
            self.mood_engine.boost_mood(5)
        else:
            display = self.tasbeeh.get_display()
            self.say(f"📿 {display}", duration=2000, force=True)

    # ==========================================================
    #  CONTEXT MENU (v3: achievements, todo, XP display)
    # ==========================================================
    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(_MENU_SS)
        name = self.settings.get("pet_name")
        lv = self.stats.data.get("level", 1)

        # ── Header ────────────────────────────────────────────
        header = QAction(f"{name}  ·  Lv.{lv}  ·  v{__version__}", self)
        header.setEnabled(False)
        menu.addAction(header)

        if self._feature_errors:
            err_act = QAction(f"⚠️ {len(self._feature_errors)} feature error(s)", self)
            err_act.triggered.connect(self._show_feature_errors)
            menu.addAction(err_act)

        if self._meeting_detector.in_meeting:
            mtg_act = QAction(f"🎥 In Meeting: {self._meeting_detector.meeting_app}", self)
            mtg_act.setEnabled(False)
            menu.addAction(mtg_act)

        menu.addSeparator()

        # ── Quick Actions (top-level for fast access) ─────────
        if self.pomodoro_active:
            mins_left = self.pomodoro_remaining // 60
            phase = "Break" if self.pomodoro_is_break else "Focus"
            pomo_action = QAction(f"🍅 Stop Pomodoro ({phase} {mins_left}m left)", self)
            pomo_action.triggered.connect(self.stop_pomodoro)
        else:
            pomo_action = QAction("🍅 Start Pomodoro", self)
            pomo_action.triggered.connect(self.start_pomodoro)
        menu.addAction(pomo_action)

        ai_status = "🟢" if self.ai_brain.is_available else "🔴"
        chat_action = QAction(f"{ai_status} Chat with {name}...", self)
        chat_action.triggered.connect(self._open_ai_chat)
        menu.addAction(chat_action)

        if self.settings.get("enable_mini_todo"):
            todo_action = QAction("📝 To-Do List", self)
            todo_action.triggered.connect(self._toggle_todo_widget)
            menu.addAction(todo_action)

        encourage_action = QAction("💪 Encourage Me!", self)
        encourage_action.triggered.connect(lambda: self.say_random("encourage", duration=4000))
        menu.addAction(encourage_action)

        menu.addSeparator()

        # ── 📊 Stats & Progress ───────────────────────────────
        stats_menu = menu.addMenu("📊 Stats & Progress")
        stats_menu.setStyleSheet(_SUB_MENU_SS)

        stats_menu.addAction(self._make_action("📈 Session Stats", self._show_stats))
        stats_menu.addAction(self._make_action("🏅 Lifetime Stats & Streak", self._show_lifetime_stats))
        stats_menu.addAction(self._make_action("📊 Analytics Dashboard", self._show_analytics))
        stats_menu.addAction(self._make_action("🔥 Streak Calendar", self._show_streak_calendar))
        stats_menu.addAction(self._make_action("🌐 Website Report", self._show_web_report))

        if self.settings.get("enable_achievements"):
            unlocked, total = self.achievement_engine.get_unlocked_count()
            stats_menu.addAction(self._make_action(f"🏆 Achievements ({unlocked}/{total})", self._show_achievements))

        wardrobe_count = len(self._wardrobe.get_unlocked())
        stats_menu.addAction(self._make_action(f"👗 Wardrobe ({wardrobe_count}/{len(WARDROBE_ITEMS)})", self._show_wardrobe))

        challenges = self.social.get_daily_challenges()
        ch_done = sum(1 for c in challenges if c.get("completed"))
        stats_menu.addAction(self._make_action(
            f"🎮 Challenges ({ch_done}/{len(challenges)})",
            lambda: self.say(self.social.get_challenge_display(), duration=8000, force=True)))

        stats_menu.addAction(self._make_action("🃏 Generate Stats Card", self._generate_stats_card))

        # ── 🎯 Focus & Productivity ──────────────────────────
        focus_menu = menu.addMenu("🎯 Focus & Productivity")
        focus_menu.setStyleSheet(_SUB_MENU_SS)

        focus_menu.addAction(self._make_action("📊 Productivity Dashboard", self._toggle_dashboard))
        focus_menu.addAction(self._make_action("🎯 Focus Planner", self._toggle_focus_planner))
        focus_menu.addAction(self._make_action("📊 App Time Report", self._show_app_time_report))
        focus_menu.addAction(self._make_action("⌨️ Keyboard Heatmap", self._show_keyboard_heatmap))

        focus_menu.addSeparator()

        focus_menu.addAction(self._make_action(
            "🎯 Smart Daily Goals",
            lambda: self.say(self.daily_briefing.smart_daily_goals(), duration=8000, force=True)))
        focus_menu.addAction(self._make_action(
            "📅 Weekly Review",
            lambda: self.say(self.daily_briefing.weekly_review(), duration=10000, force=True)))

        focus_menu.addSeparator()

        eye_on = self.settings.get("enable_eye_care")
        focus_menu.addAction(self._make_action(
            f"👁️ Eye Care 20-20-20 {'ON' if eye_on else 'OFF'}", self._toggle_eye_care))

        if self._code_companion:
            focus_menu.addAction(self._make_action(
                "🔧 Code Companion",
                lambda: self.say(self._code_companion.get_repo_summary(), duration=6000, force=True)))

        # ── 🛠️ Tools ─────────────────────────────────────────
        tools_menu = menu.addMenu("🛠️ Tools")
        tools_menu.setStyleSheet(_SUB_MENU_SS)

        tools_menu.addAction(self._make_action("⏱️ Quick Timer", self._toggle_quick_timer))
        tools_menu.addAction(self._make_action("📸 Screenshot", self._screenshot.start_capture))
        tools_menu.addAction(self._make_action("📋 Clipboard History", self._toggle_clipboard_history))

        tools_menu.addSeparator()

        # Utilities
        if self._screen_recorder.is_recording:
            m, s = divmod(self._screen_recorder.elapsed_sec, 60)
            tools_menu.addAction(self._make_action(
                f"⏹ Stop Recording ({m:02d}:{s:02d})", self._stop_screen_recording))
        else:
            tools_menu.addAction(self._make_action("🎬 Screen Recorder", self._show_screen_recorder))

        locked_ct = len(self._folder_locker.get_locked())
        tools_menu.addAction(self._make_action(
            f"🔒 Folder Locker ({locked_ct} locked)", self._show_folder_locker))

        tools_menu.addAction(self._make_action("📦 Compress / Extract", self._show_file_compressor))

        tools_menu.addSeparator()

        rem_count = self._smart_reminders.get_pending_count()
        tools_menu.addAction(self._make_action(f"⏰ Smart Reminders ({rem_count})", self._add_smart_reminder))

        note_count = self._sticky_notes.get_count()
        tools_menu.addAction(self._make_action(f"🗒️ Sticky Notes ({note_count})", self._sticky_notes.toggle_all))
        archive_count = len(self._sticky_notes.get_archive())
        if archive_count:
            tools_menu.addAction(self._make_action(f"📦 Note Archive ({archive_count})", self._show_note_archive))

        tools_menu.addAction(self._make_action("📝 Quick Note...", self._quick_note))

        tools_menu.addSeparator()

        tools_menu.addAction(self._make_action("🤖 AI Smart Actions", self._show_smart_actions))
        tools_menu.addAction(self._make_action("🎯 Quick Launcher", lambda: self._quick_launcher.show_at(
            self.pos() + QPoint(self.width() // 2, self.height() // 2))))
        tools_menu.addAction(self._make_action("✏️ Edit Launcher...", self._edit_launcher))

        tools_menu.addSeparator()

        tools_menu.addAction(self._make_action("🌅 Morning Routine", self._toggle_morning_routine))

        # Journal
        journal_today = self._journal.get_today()
        j_label = "📓 Journal"
        if journal_today:
            moods_e = {5: "😊", 4: "🙂", 3: "😐", 2: "😔", 1: "😢"}
            j_label += f" (today: {moods_e.get(journal_today['mood'], '?')})"
        tools_menu.addAction(self._make_action(j_label, self._show_journal))

        # Mood Journal
        mood_today = self._mood_journal.get_today()
        mood_label = "💭 Mood Journal"
        if mood_today:
            emojis_m = {1: "😢", 2: "😔", 3: "😐", 4: "🙂", 5: "😄"}
            mood_label += f" ({emojis_m.get(mood_today['score'], '?')})"
        tools_menu.addAction(self._make_action(mood_label, self._show_mood_journal))

        # ── 🎵 Music ─────────────────────────────────────────
        music_menu = menu.addMenu("🎵 Music")
        music_menu.setStyleSheet(_SUB_MENU_SS)

        if self.music_detector.is_playing and self.music_detector.current_track:
            now_playing = QAction(f"♫ {self.music_detector.current_track[:35]}", self)
            now_playing.setEnabled(False)
            music_menu.addAction(now_playing)
            music_menu.addSeparator()

        pp_label = "Pause" if self._music_playing else "Play"
        music_menu.addAction(self._make_action(f"⏯ {pp_label}", self._media_play_pause))
        music_menu.addAction(self._make_action("⏭ Next", self._media_next))
        music_menu.addAction(self._make_action("⏮ Previous", self._media_prev))
        music_menu.addAction(self._make_action("🔊 Vol Up", self._media_vol_up))
        music_menu.addAction(self._make_action("🔉 Vol Down", self._media_vol_down))
        music_menu.addAction(self._make_action("🔇 Mute", self._media_mute))

        music_menu.addSeparator()

        music_menu.addAction(self._make_action("▶ Play YouTube URL...", self._play_youtube_url))
        music_menu.addAction(self._make_action("🔍 Search YouTube...", self._search_youtube))

        music_menu.addSeparator()

        music_menu.addAction(self._make_action("📅 Schedule Music...", self._add_music_schedule))
        music_menu.addAction(self._make_action("📋 View Schedules", self._view_music_schedules))
        music_menu.addAction(self._make_action("🗑️ Remove Schedule...", self._remove_music_schedule))

        # ── 🖥️ System ────────────────────────────────────────
        sys_menu = menu.addMenu("🖥️ System")
        sys_menu.setStyleSheet(_SUB_MENU_SS)

        if self._system_health and self._system_health.available():
            snap = self._system_health.get_snapshot()
            cpu = snap.get("cpu_percent", 0)
            ram = snap.get("ram_percent", 0)
            health_act = QAction(f"💻 CPU {cpu:.0f}% | RAM {ram:.0f}%", self)
            health_act.setEnabled(False)
            sys_menu.addAction(health_act)
            bat = snap.get("battery_percent")
            if bat is not None:
                charging = "⚡" if snap.get("battery_charging") else "🔋"
                bat_act = QAction(f"{charging} Battery: {bat:.0f}%", self)
                bat_act.setEnabled(False)
                sys_menu.addAction(bat_act)
            sys_menu.addSeparator()

        notif_count = len(self._notif_log)
        sys_menu.addAction(self._make_action(f"🔔 Notifications ({notif_count})", self._show_notification_log))

        prog_count = len(self._progress_items)
        sys_menu.addAction(self._make_action(f"📥 Progress Monitor ({prog_count})", self._toggle_progress_monitor))

        if self._weather:
            w_display = self._weather.get_display()
            w_act = QAction(f"🌤️ {w_display}", self)
            w_act.setEnabled(False)
            sys_menu.addAction(w_act)
            sys_menu.addAction(self._make_action(
                "⏰ Hourly Forecast",
                lambda: self.say(self._weather.get_hourly_summary(), duration=8000, force=True)))

        sys_menu.addSeparator()

        # Desktop Organizer
        org_sub = sys_menu.addMenu("🗂️ Desktop Organizer")
        org_sub.setStyleSheet(_SUB_MENU_SS)
        org_enabled = self.settings.get("enable_desktop_organizer")
        org_sub.addAction(self._make_action(
            "✅ Organizer ON" if org_enabled else "❌ Organizer OFF",
            self._toggle_desktop_organizer))
        org_sub.addAction(self._make_action("🔍 Scan Now", self._manual_organize))
        org_sub.addAction(self._make_action("⏱️ Set Interval...", self._set_organizer_interval))
        org_stats = self._desktop_organizer.get_stats()
        if org_stats:
            org_sub.addSeparator()
            for rname, rinfo in org_stats.items():
                stat_act = QAction(f"{rinfo['icon']} {rname}: {rinfo['count']} files", self)
                stat_act.setEnabled(False)
                org_sub.addAction(stat_act)

        sys_menu.addSeparator()

        # Quick system actions
        sys_menu.addAction(self._make_action("📸 Take Screenshot", self._take_screenshot))
        sys_menu.addAction(self._make_action("🚀 Run App...", self._run_app_dialog))

        sys_menu.addSeparator()

        sys_menu.addAction(self._make_action("⏻ Shutdown PC", self._shutdown_pc))
        sys_menu.addAction(self._make_action("🔄 Restart PC", self._restart_pc))

        sys_menu.addSeparator()

        # Backup
        backup_sub = sys_menu.addMenu("💾 Backup & Restore")
        backup_sub.setStyleSheet(_SUB_MENU_SS)
        backup_sub.addAction(self._make_action("📤 Export Backup", self._export_backup))
        backup_sub.addAction(self._make_action("📥 Import Backup", self._import_backup))

        # ── 🕌 Islamic ───────────────────────────────────────
        islamic_visible = (self.settings.get("enable_prayer_times")
                           or self.settings.get("enable_azkar"))
        if islamic_visible:
            islamic_menu = menu.addMenu("🕌 Islamic")
            islamic_menu.setStyleSheet(_SUB_MENU_SS)

            # Prayer Times
            if self.settings.get("enable_prayer_times"):
                prayer_sub = islamic_menu.addMenu("🕌 Prayer Times")
                prayer_sub.setStyleSheet(_SUB_MENU_SS)

                times = self.prayer_manager.get_times()
                now = datetime.now()
                for pname in PrayerTimeManager.PRAYER_NAMES:
                    pt = times.get(pname)
                    if pt:
                        ar = PrayerTimeManager.PRAYER_NAMES_AR[PrayerTimeManager.PRAYER_NAMES.index(pname)]
                        passed = " ✓" if pt <= now else ""
                        time_str = pt.strftime("%I:%M %p")
                        action = QAction(f"{ar}  {pname}:  {time_str}{passed}", self)
                        action.setEnabled(False)
                        prayer_sub.addAction(action)

                prayer_sub.addSeparator()

                nxt_name, nxt_ar, nxt_dt = self.prayer_manager.get_next_prayer()
                if nxt_dt:
                    diff = nxt_dt - now
                    mins_left = int(diff.total_seconds() / 60)
                    hrs = mins_left // 60
                    mns = mins_left % 60
                    remaining = f"{hrs}h {mns}m" if hrs > 0 else f"{mns}m"
                    next_action = QAction(f"⏳ Next: {nxt_ar} {nxt_name} in {remaining}", self)
                    next_action.setEnabled(False)
                    prayer_sub.addAction(next_action)

                prayer_sub.addSeparator()
                prayer_sub.addAction(self._make_action("📍 Set Location...", self._set_prayer_location))
                prayer_sub.addAction(self._make_action("🧮 Calculation Method...", self._set_prayer_method))

            # Azkar
            if self.settings.get("enable_azkar"):
                azkar_sub = islamic_menu.addMenu("📿 Azkar / أذكار")
                azkar_sub.setStyleSheet(_SUB_MENU_SS)
                for cat_key, cat_data in AZKAR_CATEGORIES.items():
                    icon = cat_data["icon"]
                    name_ar = cat_data["name_ar"]
                    count = len(cat_data["items"])
                    azkar_sub.addAction(self._make_action(
                        f"{icon} {name_ar} ({count})",
                        lambda checked=False, k=cat_key: self._open_azkar_reader(k)))

                azkar_sub.addSeparator()
                azkar_sub.addAction(self._make_action("📿 Quick Dhikr", self._show_quick_dhikr))
                azkar_sub.addSeparator()
                azkar_interval = self.settings.get("azkar_reminder_min")
                azkar_sub.addAction(self._make_action(
                    f"⏰ Reminder every {azkar_interval} min", self._set_azkar_interval))

            # Tasbeeh
            islamic_menu.addSeparator()
            islamic_menu.addAction(self._make_action(
                f"📿 Tasbeeh ({self.tasbeeh.get_display()})", self._open_tasbeeh_menu))

        # ── ⚙️ Settings ──────────────────────────────────────
        settings_menu = menu.addMenu("⚙️ Settings")
        settings_menu.setStyleSheet(_SUB_MENU_SS)

        # AI settings
        ai_toggle = self.settings.get("enable_ai")
        settings_menu.addAction(self._make_action(
            f"🧠 AI Brain {'ON' if ai_toggle else 'OFF'}", self._toggle_ai))
        settings_menu.addAction(self._make_action("🤖 AI Model Settings...", self._configure_ai))

        settings_menu.addSeparator()

        # Behavior toggles
        following = self.settings.get("enable_follow_cursor")
        settings_menu.addAction(self._make_action(
            "🐾 Stop Following" if following else "🐾 Follow My Cursor",
            self._toggle_follow))

        focus_on = self.settings.get("focus_mode")
        settings_menu.addAction(self._make_action(
            "🔇 Exit Focus Mode" if focus_on else "🔇 Focus Mode (Mute)",
            self._toggle_focus_mode))

        reminders_on = self.settings.get("enable_reminders")
        settings_menu.addAction(self._make_action(
            "🔔 Reminders ON" if reminders_on else "🔕 Reminders OFF",
            self._toggle_reminders))

        digest_ct = self._notif_digest.peek_count()
        dnd = self._notif_digest.is_dnd
        settings_menu.addAction(self._make_action(
            f"🔕 DND {'ON' if dnd else 'OFF'} ({digest_ct} queued)",
            self._toggle_dnd))

        if self._voice.is_available():
            voice_on = self.settings.get("enable_voice_commands")
            settings_menu.addAction(self._make_action(
                f"🎤 Voice {'ON' if voice_on else 'OFF'}", self._toggle_voice_commands))

        clip_on = self.settings.get("enable_clipboard_assistant")
        settings_menu.addAction(self._make_action(
            f"📋 Clipboard Assistant {'ON' if clip_on else 'OFF'}",
            self._toggle_clipboard_assistant))

        sound_on = self.settings.get("enable_sound_reactor")
        settings_menu.addAction(self._make_action(
            f"🎤 Sound Reactions {'ON' if sound_on else 'OFF'}",
            self._toggle_sound_reactor))

        sfx_on = self._sfx.is_enabled()
        settings_menu.addAction(self._make_action(
            f"🔊 Pet Sounds {'ON' if sfx_on else 'OFF'}", self._toggle_pet_sounds))

        settings_menu.addSeparator()

        # Skins
        skin_sub = settings_menu.addMenu("🎨 Change Skin")
        skin_sub.setStyleSheet(_SUB_MENU_SS)
        current_skin = self.settings.get("current_skin")
        for skin_info in get_available_skins():
            prefix = "✔ " if skin_info["id"] == current_skin else "  "
            act = QAction(f"{prefix}{skin_info['name']}", self)
            thumb = generate_skin_thumbnail(skin_info["id"])
            if thumb:
                act.setIcon(QIcon(thumb))
            skin_id = skin_info["id"]
            act.triggered.connect(lambda checked, sid=skin_id: self._apply_skin(sid))
            skin_sub.addAction(act)

        settings_menu.addSeparator()

        settings_menu.addAction(self._make_action(f"✏️ Rename {name}...", self._rename_pet))

        is_startup = self._is_startup_enabled()
        settings_menu.addAction(self._make_action(
            "✅ Run on Startup" if is_startup else "❌ Run on Startup",
            self._toggle_startup))

        settings_menu.addAction(self._make_action("❓ Hotkey Help (F1)", self._show_hotkey_help))
        settings_menu.addSeparator()
        settings_menu.addAction(self._make_action("⚙️ All Settings...", self._open_settings_ui))

        menu.addSeparator()

        # ── Quit ──────────────────────────────────────────────
        quit_action = QAction(f"👋 Say Goodbye to {name} (Quit)", self)
        quit_action.triggered.connect(self._graceful_quit)
        menu.addAction(quit_action)

        menu.exec(pos)

    def _make_action(self, text: str, callback) -> QAction:
        """Helper to create a QAction with a connected callback."""
        act = QAction(text, self)
        act.triggered.connect(callback)
        return act

    def _show_feature_errors(self):
        text = "⚠️ Feature Errors:\n" + "\n".join(f"• {e}" for e in self._feature_errors)
        self.say(text, duration=8000, force=True)

    def _show_stats(self):
        self.say(self.mood_engine.get_stats_text(), duration=6000)

    def _show_lifetime_stats(self):
        self.say(self.stats.get_summary(), duration=6000)

    def _open_settings_ui(self):
        from features.settings_ui import SettingsDialog
        dlg = SettingsDialog(self.settings, parent=self)
        if dlg.exec():
            self.say("⚙️ Settings saved!", duration=2000)

    def _show_analytics(self):
        from features.analytics import AnalyticsDashboard
        dlg = AnalyticsDashboard(self.stats, self.mood_engine, parent=self)
        dlg.exec()

    def _show_achievements(self):
        text = self.achievement_engine.get_achievements_text()
        from PyQt6.QtWidgets import QMessageBox
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Achievements")
        dlg.setText(text)
        dlg.setStyleSheet(
            "QMessageBox { background: #F0F0F0; }"
            "QLabel { font-size: 11px; color: #222222; }"
            "QPushButton { background: #5599ff; color: white; border: none;"
            "             border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background: #3377dd; }"
        )
        dlg.exec()

    def _toggle_todo_widget(self):
        if self._todo_widget is None or not self._todo_widget.isVisible():
            self._todo_widget = MiniTodoWidget(self.stats)
            # Position near the pet
            self._todo_widget.move(self.x() + self.width() + 5, self.y())
            self._todo_widget.show()
        else:
            self._todo_widget.hide()

    def _quick_note(self):
        text, ok = QInputDialog.getText(self, "Quick Note", "Jot something down:")
        if ok and text.strip():
            self.stats.add_note(text.strip())
            self.say_random("note_saved", duration=2000)

    def _toggle_follow(self):
        current = self.settings.get("enable_follow_cursor")
        self.settings.set("enable_follow_cursor", not current)
        if not current:
            self.say_random("follow_start", duration=2000)
        else:
            self.say_random("follow_stop", duration=2000)
            self._has_wander_target = False

    def _toggle_focus_mode(self):
        current = self.settings.get("focus_mode")
        self.settings.set("focus_mode", not current)
        if not current:
            self.say_random("focus_mode_on", duration=2000)
        else:
            self.say_random("focus_mode_off", duration=2000)

    def _toggle_reminders(self):
        current = self.settings.get("enable_reminders")
        self.settings.set("enable_reminders", not current)
        if not current:
            self._reminder_timer.start(1000)
            self.say("Reminders ON", duration=2000)
        else:
            self._reminder_timer.stop()
            self.say("Reminders OFF", duration=2000)

    def _rename_pet(self):
        current_name = self.settings.get("pet_name")
        new_name, ok = QInputDialog.getText(self, "Rename Pet", "New name:", text=current_name)
        if ok and new_name.strip():
            self.settings.set("pet_name", new_name.strip())
            self.say(f"I'm {new_name.strip()} now!", duration=3000)

    def _toggle_clipboard_assistant(self):
        on = self.settings.get("enable_clipboard_assistant")
        self.settings.set("enable_clipboard_assistant", not on)
        if not on:
            if not self._clipboard_assistant:
                self._clipboard_assistant = ClipboardAssistant()
                self._clipboard_assistant.event_detected.connect(self._on_clipboard_event)
            self.say("📋 Clipboard Assistant ON", duration=3000)
        else:
            if self._clipboard_assistant:
                self._clipboard_assistant.stop()
            self.say("📋 Clipboard Assistant OFF", duration=3000)

    def _toggle_sound_reactor(self):
        on = self.settings.get("enable_sound_reactor")
        self.settings.set("enable_sound_reactor", not on)
        if not on:
            if not self._sound_reactor:
                self._sound_reactor = SoundReactor(enabled=True)
                self._sound_reactor.reaction.connect(self._on_sound_reaction)
            else:
                self._sound_reactor.set_enabled(True)
            err = self._sound_reactor.get_error() if self._sound_reactor else None
            if err:
                self.say(f"🎤 Mic error: {err}", duration=5000, force=True)
            else:
                self.say("🎤 Sound Reactions ON", duration=3000)
        else:
            if self._sound_reactor:
                self._sound_reactor.set_enabled(False)
            self.say("🎤 Sound Reactions OFF", duration=3000)

    def _toggle_dnd(self):
        dnd = self._notif_digest.is_dnd
        self._notif_digest.set_dnd(not dnd)
        if not dnd:
            self.say("🔕 Do Not Disturb ON", duration=3000)
        else:
            self.say("🔔 Do Not Disturb OFF", duration=3000)
        if self._tray:
            self._tray.set_dnd(not dnd)

    def _on_meeting_start(self, app_name: str):
        """Auto-enable DND when meeting detected."""
        if not self._notif_digest.is_dnd:
            self._notif_digest.set_dnd(True)
            if self._tray:
                self._tray.set_dnd(True)
        self.say(f"🎥 Meeting detected ({app_name}) — DND ON", duration=3000, force=True)

    def _on_meeting_end(self):
        """Auto-disable DND when meeting ends."""
        if self._notif_digest.is_dnd:
            self._notif_digest.set_dnd(False)
            if self._tray:
                self._tray.set_dnd(False)
        self.say("🎥 Meeting ended — DND OFF", duration=3000, force=True)

    def _toggle_clipboard_history(self):
        if self._clipboard_history.isVisible():
            self._clipboard_history.hide()
        else:
            self._clipboard_history.move(self.x() + 80, self.y() - 300)
            self._clipboard_history.show()

    def _toggle_quick_timer(self):
        if self._quick_timer.isVisible():
            self._quick_timer.hide()
        else:
            self._quick_timer.move(self.x() + 80, self.y() - 250)
            self._quick_timer.show()

    def _show_hotkey_help(self):
        dlg = HotkeyHelpDialog(self._hotkeys.get_bindings(), self)
        dlg.exec()

    def _show_mood_journal(self):
        dlg = MoodJournalDialog(self._mood_journal, self)
        dlg.exec()

    def _show_app_time_report(self):
        dlg = AppTimeDialog(self._app_time_tracker, self)
        dlg.exec()

    def _show_keyboard_heatmap(self):
        self._kb_heatmap.flush()
        dlg = KeyboardHeatmapDialog(self._kb_heatmap, self)
        dlg.exec()

    def _toggle_focus_planner(self):
        if self._focus_planner.isVisible():
            self._focus_planner.hide()
        else:
            self._focus_planner.move(self.x() + 80, self.y() - 300)
            self._focus_planner.show()

    def _toggle_morning_routine(self):
        if self._morning_routine.isVisible():
            self._morning_routine.hide()
        else:
            self._morning_routine.move(self.x() + 80, self.y() - 300)
            self._morning_routine.show()

    def _show_screen_recorder(self):
        dlg = RecordDialog(self._screen_recorder, self)
        dlg.exec()

    def _stop_screen_recording(self):
        self._screen_recorder.stop()

    def _show_folder_locker(self):
        dlg = FolderLockerDialog(self._folder_locker, self)
        dlg.exec()

    def _show_file_compressor(self):
        dlg = FileCompressorDialog(self)
        dlg.exec()

    def _toggle_eye_care(self):
        on = self.settings.get("enable_eye_care")
        self.settings.set("enable_eye_care", not on)
        if not on:
            if not self._eye_care:
                self._eye_care = EyeCareManager(
                    eye_min=self.settings.get("eye_break_min"),
                    water_min=self.settings.get("water_reminder_min"),
                    stretch_min=self.settings.get("stretch_reminder_min"),
                )
                self._eye_care.break_needed.connect(self._on_health_break)
                self._eye_care.break_finished.connect(self._on_break_done)
            self.say("👁️ Eye Care ON — 20-20-20 active", duration=3000)
        else:
            if self._eye_care:
                self._eye_care.stop()
            self.say("👁️ Eye Care OFF", duration=3000)

    def _toggle_pet_sounds(self):
        on = self._sfx.is_enabled()
        self._sfx.set_enabled(not on)
        self.settings.set("enable_pet_sounds", not on)
        if not on:
            self._sfx.play("happy")
            self.say("🔊 Pet Sounds ON", duration=2000)
        else:
            self.say("🔇 Pet Sounds OFF", duration=2000)

    def _generate_stats_card(self):
        name = self.settings.get("pet_name")
        level = self.stats.data.get("level", 1)
        pm = self.social.generate_stats_card(name, level, self.stats.data)
        # Save to desktop
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        path = os.path.join(desktop, f"{name}_stats_card.png")
        pm.save(path, "PNG")
        self.say(f"🃏 Stats card saved to Desktop!", duration=4000, force=True)

    # ==========================================================
    #  v8: AZKAR FEATURES
    # ==========================================================
    def _check_azkar(self):
        if not self.settings.get("enable_azkar"):
            return
        result = self.azkar_manager.should_remind()
        if not result:
            return
        msg = result["message"]
        if result["type"] == "timed":
            if "pray" in self.animations:
                self.set_state("pray")
            self.say(msg, duration=10000, force=True)
            self._play_prayer_sound()
        else:
            self.say(msg, duration=6000)

    def _open_azkar_reader(self, category: str = "morning"):
        if self._azkar_reader is None or not self._azkar_reader.isVisible():
            self._azkar_reader = AzkarReaderDialog(initial_category=category, parent=None)
        else:
            self._azkar_reader._load_category(category)
        self._azkar_reader.show()
        self._azkar_reader.raise_()
        self._azkar_reader.activateWindow()

    def _show_quick_dhikr(self):
        dhikr = self.azkar_manager.get_random_quick_dhikr()
        self.say(f"\U0001f4ff {dhikr}", duration=5000, force=True)

    def _set_azkar_interval(self):
        current = self.settings.get("azkar_reminder_min")
        val, ok = QInputDialog.getInt(
            self, "Azkar Reminder Interval",
            f"Remind every N minutes (current: {current}):",
            value=current, min=5, max=180, step=5,
        )
        if ok:
            self.settings.set("azkar_reminder_min", val)
            self.say(f"Azkar reminder set to every {val} min \U0001f4ff", duration=3000)

    # ==========================================================
    #  v9: DESKTOP AUTO-ORGANIZER
    # ==========================================================
    def _check_desktop_organizer(self):
        """Periodic scan — detect files and animate the pet carrying them."""
        if not self.settings.get("enable_desktop_organizer"):
            return
        if self._organizer_busy:
            return
        items = self._desktop_organizer.detect_files_to_organize()
        if not items:
            return
        self._organizer_busy = True
        self._org_queue = list(items)  # queue of files to process
        self._process_next_org_item()

    def _process_next_org_item(self):
        """Process the next file in the organizer queue with full animation."""
        if not self._org_queue:
            self._finish_organize_anim()
            return
        item = self._org_queue.pop(0)
        self._current_org_item = item

        # Step 1: Walk to the file's icon position on the desktop
        file_pos = item.get("file_pos")
        if file_pos:
            target_x = file_pos[0] - self.width() // 2
            target_y = min(file_pos[1], self.floor_y)
        else:
            # Fallback: walk to the left side (where icons usually start)
            target_x = self.screen_left + 60
            target_y = self.floor_y

        self._wander_target = QPoint(target_x, target_y)
        self._has_wander_target = True
        self.emotion_override = True

        # Calculate walk duration
        dist = abs(target_x - self.x()) + abs(target_y - self.y())
        walk_ms = max(800, min(int(dist / max(self.base_speed, 1) * 35), 3500))

        QTimer.singleShot(walk_ms, self._org_pickup_file)

    def _org_pickup_file(self):
        """Pet arrived at file — pick it up (switch to carry GIF)."""
        self._has_wander_target = False
        item = self._current_org_item

        # Show pickup speech
        self.say(f"📦 Grabbing {item['file']}!", duration=1500, force=True)

        # Use excited animation briefly as "pickup" effect
        if "excited" in self.animations:
            self.set_state("excited")

        # After a short pickup delay, start carrying to folder
        QTimer.singleShot(1200, self._org_carry_to_folder)

    def _org_carry_to_folder(self):
        """Carry the file to the destination folder's position."""
        item = self._current_org_item

        # Determine folder position
        folder_pos = item.get("folder_pos")
        if folder_pos:
            target_x = folder_pos[0] - self.width() // 2
            target_y = min(folder_pos[1], self.floor_y)
        else:
            # Fallback: bottom-right area (typical for new folders)
            target_x = self.screen_left + self.screen_width - self.width() - 100
            target_y = self.floor_y

        # Switch to carry GIF (walk with file overlay)
        dx = target_x - self.x()
        if dx >= 0 and "carry_right" in self.animations:
            self.set_state("carry_right")
        elif dx < 0 and "carry_left" in self.animations:
            self.set_state("carry_left")

        self._wander_target = QPoint(target_x, target_y)
        self._has_wander_target = True

        # Calculate carry walk duration
        dist = abs(target_x - self.x()) + abs(target_y - self.y())
        carry_ms = max(800, min(int(dist / max(self.base_speed, 1) * 35), 4000))

        QTimer.singleShot(carry_ms, self._org_drop_file)

    def _org_drop_file(self):
        """Pet arrived at folder — drop the file and announce."""
        self._has_wander_target = False
        item = self._current_org_item

        # Actually move the file now
        success = self._desktop_organizer.move_file(item)

        if success:
            # Show drop animation
            anim_key = "screenshot" if "screenshot" in self.animations else "notification"
            if anim_key in self.animations:
                self.set_state(anim_key)

            # Build speech
            pool_key = item.get("speech_key", "organize_photo")
            if pool_key in SPEECH_POOL:
                msg = random.choice(SPEECH_POOL[pool_key]).format(
                    file=item["file"], folder=item["dest_folder"]
                )
            else:
                msg = f"{item['icon']} Moved {item['file']} → {item['dest_folder']}/"
            self.say(msg, duration=3500, force=True)
        else:
            self.say(f"❌ Couldn't move {item['file']}...", duration=2000, force=True)

        # Process next item after a pause
        QTimer.singleShot(3500 if success else 1500, self._process_next_org_item)

    def _finish_organize_anim(self):
        """Reset after all files have been organized."""
        self.emotion_override = False
        self._has_wander_target = False
        self.set_state("idle")
        self._organizer_busy = False

    def _toggle_desktop_organizer(self):
        """Toggle the desktop organizer on/off from menu."""
        current = self.settings.get("enable_desktop_organizer")
        self.settings.set("enable_desktop_organizer", not current)
        if not current:
            interval = self.settings.get("organizer_check_sec") * 1000
            self._organizer_timer.start(max(interval, 5000))
            self._desktop_organizer.initialize()  # re-snapshot desktop
            self.say("🗂️ Desktop organizer ON! I'll keep your desktop tidy!", duration=3000)
        else:
            self._organizer_timer.stop()
            self.say("🗂️ Desktop organizer OFF.", duration=2000)

    def _manual_organize(self):
        """Manual scan triggered from menu."""
        if self._organizer_busy:
            self.say("🔄 Already organizing...", duration=2000)
            return
        self.say_random("organize_scanning", duration=2000)
        # Small delay so user sees the scanning message
        QTimer.singleShot(2000, self._do_manual_organize)

    def _do_manual_organize(self):
        items = self._desktop_organizer.detect_files_to_organize(force_all=True)
        if items:
            self._organizer_busy = True
            self._org_queue = list(items)
            self._process_next_org_item()
        else:
            self.say_random("organize_clean", duration=3000)

    def _set_organizer_interval(self):
        current = self.settings.get("organizer_check_sec")
        val, ok = QInputDialog.getInt(
            self, "Organizer Check Interval",
            f"Check desktop every N seconds (current: {current}):",
            value=current, min=5, max=300, step=5,
        )
        if ok:
            self.settings.set("organizer_check_sec", val)
            if self.settings.get("enable_desktop_organizer"):
                self._organizer_timer.start(val * 1000)
            self.say(f"🗂️ Organizer checks every {val}s now!", duration=3000)

    # ==========================================================
    #  v10: SKIN SWITCHING
    # ==========================================================

    def _apply_skin(self, skin_id: str):
        """Switch to a different skin — regenerate sprite sheet and reload."""
        self.say(f"🎨 Changing skin to {skin_id}...", duration=2000)
        if self._use_sprites and hasattr(self, '_sprite_renderer'):
            ok = self._sprite_renderer.switch_skin(skin_id)
            if ok:
                self.settings.set("current_skin", skin_id)
                self.say(f"🎨 Skin changed to {skin_id}!", duration=3000)
            else:
                self.say("❌ Failed to apply skin.", duration=3000)
        else:
            # Not using sprites yet — generate assets and try switching
            ok = generate_skin_assets(skin_id)
            if ok:
                self.settings.set("current_skin", skin_id)
                # Try to load sprite renderer
                if hasattr(self, '_sprite_renderer') and self._sprite_renderer.load("assets"):
                    self._use_sprites = True
                    self._sprite_renderer.show()
                    self.pet_label.hide()
                    self.say(f"🎨 Skin '{skin_id}' applied! Sprite mode activated!", duration=3000)
                else:
                    self.say(f"🎨 Skin '{skin_id}' assets generated (restart to use).", duration=3000)

    # ==========================================================
    #  v5: PRAYER TIME FEATURES
    # ==========================================================

    # ---------- prayer sound + screen shake ----------
    def _play_prayer_sound(self):
        """Play tasbeh chime WAV in a non-blocking way."""
        wav_path = os.path.join(os.path.dirname(__file__), "assets", "tasbeh_alert.wav")
        if os.path.exists(wav_path):
            try:
                winsound.PlaySound(
                    wav_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except Exception:
                # Fallback: system beep sequence
                winsound.Beep(660, 300)
                winsound.Beep(880, 300)
                winsound.Beep(1100, 500)
        else:
            # No WAV file — play simple beep melody
            winsound.Beep(660, 300)
            winsound.Beep(880, 300)
            winsound.Beep(1100, 500)

    def _shake_screen(self, intensity=12, cycles=20, interval_ms=40):
        """Shake the pet widget rapidly to grab attention.

        The widget oscillates around its original position for *cycles*
        steps every *interval_ms* milliseconds, then snaps back.
        Also flashes a translucent overlay.
        """
        self._shake_origin = self.pos()
        self._shake_step = 0
        self._shake_cycles = cycles
        self._shake_intensity = intensity

        if not hasattr(self, '_shake_timer'):
            self._shake_timer = QTimer(self)
            self._shake_timer.timeout.connect(self._do_shake_step)

        self._shake_timer.start(interval_ms)

    def _do_shake_step(self):
        """One frame of the shake animation."""
        if self._shake_step >= self._shake_cycles:
            self._shake_timer.stop()
            self.move(self._shake_origin)
            return

        # Alternate direction for each step with decreasing intensity
        progress = self._shake_step / self._shake_cycles
        decay = 1.0 - progress  # shake weakens over time
        amp = int(self._shake_intensity * decay)

        dx = random.randint(-amp, amp)
        dy = random.randint(-amp, amp)
        self.move(self._shake_origin + QPoint(dx, dy))
        self._shake_step += 1

    def _check_prayer_times(self):
        """Called every 30s — check for prayer reminders/alerts."""
        if not self.settings.get("enable_prayer_times"):
            return
        result = self.prayer_manager.check()
        if not result:
            return

        prayer = result["prayer"]
        ar = result["prayer_ar"]
        time_str = result["time"]

        if result["type"] == "alert":
            # AT prayer time — strong alert
            # Try specific prayer pool first, then generic
            specific_pool = f"prayer_{prayer.lower()}"
            if specific_pool in SPEECH_POOL:
                msg = random.choice(SPEECH_POOL[specific_pool])
            else:
                msg = random.choice(SPEECH_POOL["prayer_alert"])
            # Show with large duration + change animation
            if "pray" in self.animations:
                self.set_state("pray")
            elif "smile" in self.animations:
                self.set_state("smile")
            self.say(f"\U0001f54c {ar} - {prayer}\n{time_str}\n{msg}", duration=15000)
            self.mood_engine.boost_mood(5)
            # 🔊 Play tasbeh sound + shake the pet
            self._play_prayer_sound()
            self._shake_screen(intensity=14, cycles=25, interval_ms=35)

        elif result["type"] == "reminder":
            mins = result["minutes_left"]
            msg = random.choice(SPEECH_POOL["prayer_reminder"])
            self.say(f"\u23f0 {ar} {prayer} in {mins} min\n{msg}", duration=8000)

    def _set_prayer_location(self):
        """Let user set latitude/longitude for prayer calculation."""
        lat = self.settings.get("prayer_latitude")
        lng = self.settings.get("prayer_longitude")
        tz = self.settings.data.get("prayer_timezone", round(lng / 15.0))

        text, ok = QInputDialog.getText(
            self, "Prayer Location",
            f"Current: {lat}, {lng} (UTC{'+' if tz >= 0 else ''}{int(tz)})\n\n"
            "Enter latitude, longitude (or lat, lng, timezone):\n"
            "Examples:\n"
            "  Riyadh: 24.7136, 46.6753, 3\n"
            "  Mecca: 21.4225, 39.8262, 3\n"
            "  Cairo: 30.0444, 31.2357, 2\n"
            "  Istanbul: 41.0082, 28.9784, 3\n"
            "  London: 51.5074, -0.1278, 0\n"
            "  New York: 40.7128, -74.0060, -5\n"
            "  Kuala Lumpur: 3.139, 101.6869, 8\n\n"
            "Timezone is optional (auto-estimated from longitude)",
        )
        if ok and text.strip():
            try:
                parts = [p.strip() for p in text.split(",")]
                new_lat = float(parts[0])
                new_lng = float(parts[1])
                self.prayer_manager.configure_location(new_lat, new_lng)
                # Override timezone if user specified it
                if len(parts) >= 3:
                    user_tz = float(parts[2])
                    self.settings.set("prayer_timezone", user_tz)
                    self.prayer_manager._cache_date = None
                new_tz = self.settings.data.get("prayer_timezone", round(new_lng / 15.0))
                self.say(f"Location: {new_lat}, {new_lng}\n"
                         f"Timezone: UTC{'+' if new_tz >= 0 else ''}{int(new_tz)}\n"
                         f"Prayer times updated!", duration=5000)
            except (ValueError, IndexError):
                self.say("Invalid format! Use: lat, lng\nor: lat, lng, timezone", duration=3000)

    def _set_prayer_method(self):
        """Let user choose calculation method."""
        methods = list(PrayerTimeManager.CALC_METHODS.keys())
        current = self.settings.get("prayer_calc_method")
        labels = {
            "umm_al_qura": "Umm Al-Qura (Saudi Arabia)",
            "mwl": "Muslim World League",
            "isna": "ISNA (North America)",
            "egypt": "Egyptian General Authority",
        }
        items = [f"{labels.get(m, m)}{' ✓' if m == current else ''}" for m in methods]

        item, ok = QInputDialog.getItem(
            self, "Calculation Method",
            "Choose prayer calculation method:",
            items, methods.index(current) if current in methods else 0, False
        )
        if ok:
            idx = items.index(item)
            method = methods[idx]
            self.settings.set("prayer_calc_method", method)
            self.prayer_manager._cache_date = None  # force recalc
            self.say(f"Using {labels.get(method, method)}", duration=3000)

    # ==========================================================
    #  v4: MUSIC FEATURES
    # ==========================================================
    def _media_play_pause(self):
        MediaController.play_pause()
        self.say_random("media_play_pause", duration=2000)
        # Toggle local state
        self._music_playing = not self._music_playing
        if self._music_playing:
            self._show_headphones()
            if "music_listen" in self.animations:
                self.set_state("music_listen")
            elif "dance" in self.animations:
                self.set_state("dance")
        elif not self._music_playing:
            self._hide_headphones()
            self.set_state("idle")

    def _media_next(self):
        MediaController.next_track()
        self.say_random("media_next", duration=2000)

    def _media_prev(self):
        MediaController.prev_track()
        self.say_random("media_prev", duration=2000)

    def _media_vol_up(self):
        MediaController.volume_up()
        self.say("Volume up!", duration=1500)

    def _media_vol_down(self):
        MediaController.volume_down()
        self.say("Volume down!", duration=1500)

    def _media_mute(self):
        MediaController.mute()
        self.say("Muted!", duration=1500)

    def _play_youtube_url(self):
        url, ok = QInputDialog.getText(
            self, "Play YouTube", "Paste YouTube URL:"
        )
        if ok and url.strip():
            url = url.strip()
            if "youtube.com" not in url and "youtu.be" not in url:
                url = f"https://www.youtube.com/results?search_query={url.replace(' ', '+')}"
            webbrowser.open(url)
            self.say_random("music_play", duration=3000)

    def _search_youtube(self):
        query, ok = QInputDialog.getText(
            self, "Search YouTube", "What do you want to listen to?"
        )
        if ok and query.strip():
            search_url = f"https://www.youtube.com/results?search_query={query.strip().replace(' ', '+')}"
            webbrowser.open(search_url)
            self.say_random("music_search", duration=3000)

    def _add_music_schedule(self):
        time_str, ok1 = QInputDialog.getText(
            self, "Schedule Music", "Time to play (HH:MM, 24h format):",
            text=datetime.now().strftime("%I:%M %p")
        )
        if not ok1 or not time_str.strip():
            return
        # Validate time format
        time_str = time_str.strip()
        if not re.match(r'^\d{1,2}:\d{2}$', time_str):
            self.say("Invalid time format. Use HH:MM", duration=3000)
            return
        # Pad hour
        parts = time_str.split(':')
        time_str = f"{int(parts[0]):02d}:{parts[1]}"

        url, ok2 = QInputDialog.getText(
            self, "Schedule Music", "YouTube URL or search term:"
        )
        if not ok2 or not url.strip():
            return
        url = url.strip()
        if "youtube.com" not in url and "youtu.be" not in url:
            # Treat as search — build a direct search URL
            label = url
            url = f"https://www.youtube.com/results?search_query={url.replace(' ', '+')}"
        else:
            label = url[:40]

        name, ok3 = QInputDialog.getText(
            self, "Schedule Music", "Label (optional):", text=label
        )
        if ok3 and name.strip():
            label = name.strip()

        self.music_scheduler.add_schedule(time_str, url, label)
        self.say_random("music_added", t=time_str, duration=3000)

    def _view_music_schedules(self):
        text = self.music_scheduler.get_schedules_text()
        from PyQt6.QtWidgets import QMessageBox
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Music Schedules")
        dlg.setText(text)
        dlg.setStyleSheet(
            "QMessageBox { background: #F0F0F0; }"
            "QLabel { font-size: 11px; color: #222222; }"
            "QPushButton { background: #5599ff; color: white; border: none;"
            "             border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background: #3377dd; }"
        )
        dlg.exec()

    def _remove_music_schedule(self):
        schedules = self.music_scheduler.schedules
        if not schedules:
            self.say("No schedules to remove.", duration=2000)
            return
        items = []
        for i, s in enumerate(schedules):
            label = s.get("label", s["url"])[:30]
            items.append(f"{i+1}. {s['time']} — {label}")
        text = "\n".join(items)
        idx_str, ok = QInputDialog.getText(
            self, "Remove Schedule", f"Enter number to remove:\n{text}"
        )
        if ok and idx_str.strip().isdigit():
            idx = int(idx_str.strip()) - 1
            self.music_scheduler.remove_schedule(idx)
            self.say("Schedule removed!", duration=2000)

    def _check_music_schedule(self):
        """Called every 30s to check if music should play."""
        fired = self.music_scheduler.check_and_fire()
        for entry in fired:
            label = entry.get("label", "music")
            self.say_random("music_scheduled", label=label, duration=4000)
            self.mood_engine.boost_mood(5)

    # ==========================================================
    #  v4: WEB TRACKING REPORT
    # ==========================================================
    def _show_web_report(self):
        # Save tracker data before showing
        self.web_tracker.save()
        text = self.web_tracker.get_report_text()
        from PyQt6.QtWidgets import QMessageBox
        dlg = QMessageBox(self)
        dlg.setWindowTitle("Website Report")
        dlg.setText(text)
        dlg.setStyleSheet(
            "QMessageBox { background: #F0F0F0; }"
            "QLabel { font-size: 11px; color: #222222; }"
            "QPushButton { background: #5599ff; color: white; border: none;"
            "             border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background: #3377dd; }"
        )
        dlg.exec()

    # ==========================================================
    #  RUN ON WINDOWS STARTUP
    # ==========================================================
    _STARTUP_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    _STARTUP_APP_NAME = "DesktopPetToty"

    def _get_startup_command(self) -> str:
        """Return the command that Windows should run at startup."""
        python_exe = sys.executable
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "animals.py"))
        return f'"{python_exe}" "{script_path}"'

    def _is_startup_enabled(self) -> bool:
        """Check if the app is registered to run on Windows startup."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._STARTUP_REG_KEY, 0, winreg.KEY_READ
            )
            val, _ = winreg.QueryValueEx(key, self._STARTUP_APP_NAME)
            winreg.CloseKey(key)
            return bool(val)
        except (FileNotFoundError, OSError):
            return False

    def _enable_startup(self):
        """Register the app to run on Windows startup via Registry."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(
                key, self._STARTUP_APP_NAME, 0, winreg.REG_SZ, self._get_startup_command()
            )
            winreg.CloseKey(key)
            return True
        except OSError:
            return False

    def _disable_startup(self):
        """Remove the app from Windows startup."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self._STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE
            )
            winreg.DeleteValue(key, self._STARTUP_APP_NAME)
            winreg.CloseKey(key)
            return True
        except (FileNotFoundError, OSError):
            return False

    def _toggle_startup(self):
        """Toggle run-on-startup on or off."""
        if self._is_startup_enabled():
            if self._disable_startup():
                self.say("Removed from startup. I won't auto-launch anymore.", duration=3000)
            else:
                self.say("Failed to remove from startup.", duration=3000)
        else:
            if self._enable_startup():
                self.say("Added to Windows startup! I'll be here when you boot up! \U0001f680", duration=4000)
            else:
                self.say("Failed to add to startup.", duration=3000)

    def _graceful_quit(self):
        focus_min = self.mood_engine.get_focus_minutes()
        self.stats.record_session_end(focus_min)
        self.stats.data["total_keys"] = (
            self.stats.data.get("total_keys", 0)
        )
        self.stats.save()
        self.web_tracker.save()
        self.music_scheduler.save()
        self.tasbeeh.save()
        self.social.save()
        if self._clipboard_assistant:
            self._clipboard_assistant.stop()
        if self._system_health:
            self._system_health.stop()
        if self._sound_reactor:
            self._sound_reactor.stop()
        if self._code_companion:
            self._code_companion.stop()
        # v12 cleanup
        self._hotkeys.stop()
        self._smart_reminders.stop()
        if self._eye_care:
            self._eye_care.stop()
        self._sticky_notes.stop()
        if self._weather:
            self._weather.stop()
        self._journal.stop()
        if self._tray:
            self._tray.stop()
        self._voice.stop()
        # v14 cleanup
        self._clipboard_history.stop()
        self._quick_timer.stop()
        self._app_time_tracker.save()
        self._kb_heatmap.stop()
        self._mood_journal.stop()
        self._real_events.stop()
        self._clear_checkpoint()
        self._progress_monitor.stop()
        self._scan_thread.quit()
        self._scan_thread.wait(3000)
        QApplication.instance().quit()

    def closeEvent(self, event):
        focus_min = self.mood_engine.get_focus_minutes()
        self.stats.record_session_end(focus_min)
        self.stats.save()
        self.web_tracker.save()
        self.music_scheduler.save()
        self.tasbeeh.save()
        self.social.save()
        # Save reaction engine data (time patterns, mood patterns, session history)
        self.reaction_engine.record_session_end(focus_min)
        self.reaction_engine.save()
        if self._clipboard_assistant:
            self._clipboard_assistant.stop()
        if self._system_health:
            self._system_health.stop()
        if self._sound_reactor:
            self._sound_reactor.stop()
        if self._code_companion:
            self._code_companion.stop()
        # v12 cleanup
        self._hotkeys.stop()
        self._smart_reminders.stop()
        if self._eye_care:
            self._eye_care.stop()
        self._sticky_notes.stop()
        if self._weather:
            self._weather.stop()
        self._journal.stop()
        if self._tray:
            self._tray.stop()
        self._voice.stop()
        # v14 cleanup
        self._clipboard_history.stop()
        self._quick_timer.stop()
        self._app_time_tracker.save()
        self._kb_heatmap.stop()
        self._mood_journal.stop()
        self._real_events.stop()
        self._clear_checkpoint()
        super().closeEvent(event)


# ============================================================
#  ENTRY POINT
# ============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    pet = DesktopPet()
    pet.show()
    sys.exit(app.exec())