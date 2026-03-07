import sys
import os
import re
import math
import time
import random
import shutil
import sqlite3
import webbrowser
import winsound
import winreg

from datetime import datetime
from pynput import keyboard
import pygetwindow as gw

from PyQt6.QtWidgets import (
    QApplication, QLabel, QMenu, QWidget, QInputDialog,
    QSystemTrayIcon, QVBoxLayout, QHBoxLayout,
    QPushButton, QScrollArea, QFrame, QTextEdit,
    QDialog,
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QObject, pyqtSignal
from PyQt6.QtGui import (
    QAction, QMovie, QPixmap, QColor, QFont, QCursor, QIcon, QPainter,
)

# ── Internal modules ──
from core.settings import Settings
from core.stats import PersistentStats
from core.achievements import ACHIEVEMENTS, AchievementEngine
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
from features.azkar import AzkarManager, AzkarReaderDialog, AZKAR_CATEGORIES


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
        self.pet_label = QLabel(self)
        self.pet_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.pet_width = 100
        self.pet_height = 100
        self.pet_label.setFixedSize(self.pet_width, self.pet_height)

        # 3. Speech Bubble (mood-colored)
        self.bubble = QLabel(self)
        self.bubble.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._update_bubble_style()
        self.bubble.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        self.bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.bubble.setWordWrap(True)
        self.bubble.setMaximumWidth(220)
        self.bubble.hide()

        # XP bar label
        self.xp_label = QLabel(self)
        self.xp_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.xp_label.setFont(QFont("Arial", 7))
        self.xp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.xp_label.setStyleSheet("color: #666; background: transparent;")
        self.xp_label.setFixedWidth(150)
        self._update_xp_label()

        self.setFixedSize(250, 220)
        self.pet_label.move(75, 100)
        self.xp_label.move(50, 200)

        # 4. Physics & Screen Setup — multi-monitor aware
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
        self._bubble_timer = QTimer(self)
        self._bubble_timer.setSingleShot(True)
        self._bubble_timer.timeout.connect(self.hide_bubble)

        # 7. Timers
        self.movement_timer = QTimer(self)
        self.movement_timer.timeout.connect(self.update_movement)
        self.movement_timer.start(30)

        self.brain_timer = QTimer(self)
        self.brain_timer.timeout.connect(self.decide_next_action)
        self.brain_timer.start(self.settings.get("brain_tick_ms"))

        self.context_timer = QTimer(self)
        self.context_timer.timeout.connect(self.check_os_context)
        if self.settings.get("enable_window_tracking"):
            self.context_timer.start(self.settings.get("context_check_ms"))

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
        self.mood_timer.start(1000)

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

        # 17. Achievement check timer (every 10 s)
        self._ach_timer = QTimer(self)
        self._ach_timer.timeout.connect(self._check_achievements)
        if self.settings.get("enable_achievements"):
            self._ach_timer.start(10000)

        # 18. XP award timer (every 60 s)
        self._xp_timer = QTimer(self)
        self._xp_timer.timeout.connect(self._award_focus_xp)
        if self.settings.get("enable_xp_system"):
            self._xp_timer.start(60000)

        # 19. Time-of-day greeting (once per session)
        self._tod_greeted = False

        # 20. Mini todo widget
        self._todo_widget = None

        # 21. System tray icon
        self._tray_icon = None
        if self.settings.get("enable_system_tray"):
            self._setup_tray()

        # 22. Multi-monitor refresh timer
        if self.settings.get("enable_multi_monitor"):
            self._monitor_timer = QTimer(self)
            self._monitor_timer.timeout.connect(self._update_screen_geometry)
            self._monitor_timer.start(5000)

        # 23. Website tracker
        self.web_tracker = WebsiteTracker()

        # 24. Music scheduler + checker (every 30 s)
        self.music_scheduler = MusicScheduler()
        self._music_timer = QTimer(self)
        self._music_timer.timeout.connect(self._check_music_schedule)
        self._music_timer.start(30000)

        # 25. Music detector (every 2s)
        self.music_detector = MusicDetector()
        self._music_playing = False
        self._music_detect_timer = QTimer(self)
        self._music_detect_timer.timeout.connect(self._auto_detect_music)
        self._music_detect_timer.start(2000)

        # 26. Prayer times
        self.prayer_manager = PrayerTimeManager(self.settings)
        if self.settings.get("enable_prayer_times"):
            self._prayer_timer = QTimer(self)
            self._prayer_timer.timeout.connect(self._check_prayer_times)
            self._prayer_timer.start(30000)
            QTimer.singleShot(3000, self._check_prayer_times)

        # 27. AI Brain (Ollama)
        self.ai_brain = OllamaBrain(self.settings)
        self._ai_chat_signal = AIChatSignal()
        self._ai_chat_signal.response_ready.connect(self._on_ai_quick_response)
        self._ai_chat_dialog = None

        # 28. Windows Notification Reader
        self.notif_reader = WindowsNotificationReader()
        self._notif_timer = QTimer(self)
        self._notif_timer.timeout.connect(self._check_notifications)
        self._notif_timer.start(5000)
        self._notif_log: list[dict] = []
        self._load_recent_notifications()

        # 29. Azkar reminders
        self.azkar_manager = AzkarManager(self.settings)
        self._azkar_reader = None
        self._azkar_timer = QTimer(self)
        self._azkar_timer.timeout.connect(self._check_azkar)
        if self.settings.get("enable_azkar"):
            self._azkar_timer.start(60000)  # check every 60s

        # 30. Welcome + time greeting
        QTimer.singleShot(1500, self._show_welcome)

    # ==========================================================
    #  MULTI-MONITOR SUPPORT
    # ==========================================================
    def _update_screen_geometry(self):
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
    #  SYSTEM TRAY
    # ==========================================================
    def _setup_tray(self):
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
    #  MOOD-COLORED BUBBLE
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
        for filename in os.listdir(assets_folder):
            if filename.endswith(".gif"):
                state_name = filename.replace(".gif", "")
                filepath = os.path.join(assets_folder, filename)
                movie = QMovie(filepath)
                if movie.isValid():
                    self.animations[state_name] = movie
                else:
                    print(f"[WARN] Invalid GIF skipped: {filename}")
        self.action_categories = {
            "idle": ["idle", "sit", "yawn", "stretch", "dance"],
            "move_left": ["walk_left", "run_left", "crawl_left", "roll_left"],
            "move_right": ["walk_right", "run_right", "crawl_right", "roll_right"],
            "work": ["work", "type_code", "read_book"],
            "sleep": ["sleep", "snore"],
            "happy": ["smile", "jump"],
        }
        if not self.animations:
            pixmap = QPixmap(self.pet_width, self.pet_height)
            pixmap.fill(QColor(135, 206, 235, 150))
            self.animations["idle"] = pixmap
        self.current_anim = None

    def set_state(self, new_state):
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

    # ==========================================================
    #  BRAIN
    # ==========================================================
    def decide_next_action(self):
        if self.emotion_override or self.pet_state in ["dragging", "falling", "work"]:
            return
        if self.settings.get("enable_follow_cursor"):
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

        if self.settings.get("bubble_mood_colors") and self.bubble.isVisible():
            self._update_bubble_style()

        focus_min = self.mood_engine.get_focus_minutes()
        if focus_min > 0 and focus_min % 15 == 0 and focus_min != self._last_focus_milestone:
            self._last_focus_milestone = focus_min
            self.say_random("focus_milestone", m=focus_min)

        daily_goal = self.settings.get("daily_goal_focus_min")
        today_focus = self.stats.data.get("daily_focus_min", 0) + focus_min
        if today_focus >= daily_goal and not self._daily_goal_notified:
            self._daily_goal_notified = True
            self.say_random("daily_goal", m=today_focus, duration=5000)
            self.mood_engine.boost_mood(20)

        for cat in ("coding", "design"):
            cat_min = self.mood_engine.get_app_time_minutes(cat)
            prev = self._context_milestones.get(cat, 0)
            if cat_min > 0 and cat_min % 20 == 0 and cat_min != prev:
                self._context_milestones[cat] = cat_min
                pool = "coding_milestone" if cat == "coding" else "focus_milestone"
                self.say_random(pool, m=cat_min)

    # ==========================================================
    #  ACHIEVEMENT CHECK (every 10 s)
    # ==========================================================
    def _check_achievements(self):
        self.achievement_engine.check_all(
            session_keys=self.typing_analyzer.get_total_keys(),
            session_focus_min=self.mood_engine.get_focus_minutes(),
        )
        for aid in self.achievement_engine.pop_pending():
            info = ACHIEVEMENTS.get(aid, {})
            name = info.get("name", aid)
            self.say_random("achievement", name=name, duration=5000)
            self.mood_engine.boost_mood(10)
            self._update_xp_label()

        if self._tray_icon:
            unlocked, total = self.achievement_engine.get_unlocked_count()
            self._tray_icon.setToolTip(
                f"{self.settings.get('pet_name')} — Lv.{self.stats.data.get('level', 1)} "
                f"| {unlocked}/{total} achievements"
            )

    # ==========================================================
    #  XP AWARD (every 60 s)
    # ==========================================================
    def _award_focus_xp(self):
        if self.pet_state == "work":
            xp = self.settings.get("xp_per_focus_min")
            leveled = self.stats.add_xp(xp)
            self._update_xp_label()
            if leveled:
                lv = self.stats.data.get("level", 1)
                self.say_random("level_up", lv=lv, duration=5000)
                self.mood_engine.boost_mood(15)
                self.mood_engine.boost_energy(10)

    # ==========================================================
    #  TYPING PATTERNS
    # ==========================================================
    def _analyze_typing_patterns(self):
        if self.settings.get("focus_mode") or self.emotion_override:
            return
        events = self.typing_analyzer.consume_events()

        if events["idle_returned"]:
            self.say_random("idle_return", duration=3000)
            self.mood_engine.boost_mood(5)
            if self.pet_state == "sleep":
                self.emotion_override = False
                self.set_state("idle")
        if events["backspace_rage"]:
            self.say_random("backspace_rage", duration=4000)
            self.mood_engine.drain_mood(5)
        elif events["burst"]:
            self.say_random("burst", duration=2500)
            self.mood_engine.boost_energy(3)
        elif events["pause"]:
            if random.random() < 0.3:
                self.say_random("thinking_pause", duration=3000)

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
                if dx < 0 and "walk_left" in self.animations:
                    self.set_state("walk_left")
                elif dx > 0 and "walk_right" in self.animations:
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
        self.stats.data["total_keys"] = self.stats.data.get("total_keys", 0) + 1

        if self.pet_state == "sleep":
            self.emotion_override = False
            self.set_state("idle")
            self.say_random("wakeup", duration=2000)

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
    #  AUTO MUSIC DETECTION
    # ==========================================================
    def _auto_detect_music(self):
        try:
            music_info = self.music_detector.detect_from_all_windows()
        except Exception:
            return

        if music_info["just_started"]:
            self._music_playing = True
            music_anim = random.choice(
                [a for a in ("play_music", "music_listen") if a in self.animations]
                or ["dance", "smile"]
            )
            self.set_state(music_anim)
            track = music_info["track"]
            if track and len(track) < 50:
                self.say(f"\u266b {track}", duration=4000)
            else:
                self.say_random("music_detected", duration=3000)
            self.mood_engine.boost_mood(10)

        elif music_info["just_stopped"]:
            self._music_playing = False
            self.say_random("music_stopped", duration=2500)
            self.set_state("idle")

        elif music_info["is_playing"] and self._music_playing:
            if self.pet_state not in ("music_listen", "play_music", "dance", "smile", "dragging", "falling"):
                music_anim = random.choice(
                    [a for a in ("play_music", "music_listen") if a in self.animations]
                    or ["dance"]
                )
                self.set_state(music_anim)

    # ==========================================================
    #  CONTEXT ACTING
    # ==========================================================
    def check_os_context(self):
        if self.emotion_override or "run" in self.pet_state:
            return
        try:
            active_window = gw.getActiveWindow()
            if not active_window:
                self.hide_bubble()
                if self.pet_state == "work":
                    self.set_state("idle")
                self.mood_engine.set_context_category("")
                return
            title = active_window.title
            title_lower = title.lower()
            self.mood_engine.record_app_switch(title_lower)

            self.web_tracker.record_window(title_lower)

            category = self._categorize_window(title_lower)
            self.mood_engine.set_context_category(category)

            if category == "coding":
                self.set_state("work")
                if not self.settings.get("focus_mode"):
                    self.say_random("coding")
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

            if self.mood_engine.is_switching_too_fast():
                now = time.time()
                if now - self._last_distraction_warn > 120:
                    self._last_distraction_warn = now
                    self.say_random("distracted", duration=5000)
                    self.mood_engine.drain_mood(5)
        except Exception:
            self.hide_bubble()

    def _categorize_window(self, title: str) -> str:
        coding_kw = ("code", "pycharm", "gym engine", "openclaw", "visual studio",
                     "intellij", "neovim", "sublime", "atom", "terminal", "powershell",
                     "cmd.exe", "git")
        design_kw = ("refreshyourpassionapp", "motiv8", "photoshop", "figma",
                     "illustrator", "canva", "sketch", "blender")
        video_kw  = ("youtube", "netflix", "twitch", "vlc", "mpv", "plex")
        browser_kw = ("chrome", "firefox", "edge", "brave", "opera", "safari")
        gaming_kw  = ("steam", "epic games", "minecraft", "valorant", "discord")
        for kw in coding_kw:
            if kw in title:
                return "coding"
        for kw in design_kw:
            if kw in title:
                return "design"
        for kw in video_kw:
            if kw in title:
                return "video"
        for kw in gaming_kw:
            if kw in title:
                return "gaming"
        for kw in browser_kw:
            if kw in title:
                return "browser"
        return "other"

    # ==========================================================
    #  INTERACTIVE PETTING (combos!)
    # ==========================================================
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.emotion_override = True
            self.mood_engine.pet_interaction()

            combo = self.combo_tracker.register_click()
            self.stats.data["total_pets"] = self.stats.data.get("total_pets", 0) + 1

            if combo >= 4:
                self.say_random("pet_combo_4plus", duration=3000)
                self.mood_engine.boost_mood(25)
                if "dance" in self.animations:
                    self.set_state("dance")
                else:
                    self.set_state("smile")
            elif combo == 3:
                self.say_random("pet_combo_3", duration=3000)
                self.mood_engine.boost_mood(20)
                self.set_state("smile")
                self.achievement_engine.check_combo(combo)
            elif combo == 2:
                self.say_random("pet_combo_2", duration=3000)
                self.mood_engine.boost_mood(10)
                self.set_state("smile")
            else:
                if self.ai_brain.is_available and random.random() < 0.3:
                    self._ai_react("The user just petted/clicked on me lovingly")
                else:
                    self.say_random("pet", duration=3000)
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
            if text == self._last_speech_text and (now - self._last_speech_time) < cooldown:
                return
            if (now - self._last_speech_time) < cooldown * 0.4:
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

        self._update_bubble_style()

        self.bubble.setText(text)
        self.bubble.adjustSize()
        bubble_x = 75 + (self.pet_width // 2) - (self.bubble.width() // 2)
        self.bubble.move(bubble_x, max(5, 70 - self.bubble.height()))
        self.bubble.show()
        if duration > 0:
            self._bubble_timer.start(duration)

    def say_random(self, pool_key, duration=0, **fmt):
        lines = SPEECH_POOL.get(pool_key, [])
        if not lines:
            return
        text = random.choice(lines)
        if fmt:
            text = text.format(**fmt)
        self.say(text, duration=duration)

    def hide_bubble(self):
        self.bubble.hide()
        self._bubble_timer.stop()

    # ==========================================================
    #  WELCOME
    # ==========================================================
    def _show_welcome(self):
        if "startup" in self.animations:
            self.set_state("startup")
            QTimer.singleShot(3000, lambda: self.set_state("idle"))
        msg = self.stats.get_welcome_message()
        self.say(msg, duration=4000)
        if self.settings.get("enable_time_awareness") and not self._tod_greeted:
            self._tod_greeted = True
            tod = self.mood_engine.get_time_of_day_label()
            QTimer.singleShot(5000, lambda: self.say_random(tod, duration=3000))

    # ==========================================================
    #  POMODORO
    # ==========================================================
    def start_pomodoro(self):
        work_min = self.settings.get("pomodoro_work_min")
        self.pomodoro_active = True
        self.pomodoro_is_break = False
        self.pomodoro_remaining = work_min * 60
        self._pomodoro_timer.start(1000)
        self.say(f"Pomodoro started! {work_min} min focus.", duration=3000)

    def stop_pomodoro(self):
        self.pomodoro_active = False
        self._pomodoro_timer.stop()
        self.say("Pomodoro cancelled.", duration=2000)

    def _pomodoro_tick(self):
        if not self.pomodoro_active:
            return
        self.pomodoro_remaining -= 1
        if self.pomodoro_remaining <= 0:
            if self.pomodoro_is_break:
                self.say_random("pomodoro_break_done", duration=5000)
                self.pomodoro_active = False
                self._pomodoro_timer.stop()
            else:
                self.say_random("pomodoro_done", duration=5000)
                self.mood_engine.boost_energy(10)
                self.stats.data["total_pomodoros"] = self.stats.data.get("total_pomodoros", 0) + 1
                self.stats.save()
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
    #  AI BRAIN INTEGRATION
    # ==========================================================
    def _get_ai_context(self) -> dict:
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
        }

    def _open_ai_chat(self):
        name = self.settings.get("pet_name")
        if self._ai_chat_dialog is None or not self._ai_chat_dialog.isVisible():
            self._ai_chat_dialog = AIChatDialog(
                name, self.ai_brain, self._get_ai_context, parent=None
            )
        self._ai_chat_dialog.show()
        self._ai_chat_dialog.raise_()
        self._ai_chat_dialog.activateWindow()
        self._ai_chat_dialog.input_field.setFocus()

    def _on_ai_quick_response(self, text: str):
        if text:
            self.say(text, duration=5000)

    def _ai_react(self, situation: str):
        if not self.ai_brain.is_available:
            return

        def callback(reply):
            if reply:
                self._ai_chat_signal.response_ready.emit(reply)

        self.ai_brain.quick_response(situation, self._get_ai_context(), callback)

    def _configure_ai(self):
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
        current = self.settings.get("enable_ai")
        self.settings.set("enable_ai", not current)
        if not current:
            self.ai_brain.refresh_status()
            self.say("AI Brain activated! 🧠✨", duration=3000)
        else:
            self.say("AI Brain deactivated. Using classic mode.", duration=3000)

    # ==========================================================
    #  QUICK ACTIONS (Screenshot, Run App, Shutdown, Restart)
    # ==========================================================
    def _take_screenshot(self):
        try:
            import subprocess
            if "screenshot" in self.animations:
                self.emotion_override = True
                self.set_state("screenshot")

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
                creationflags=0x08000000,
            )
            self.say(f"\U0001f4f8 Screenshot saved!\n{os.path.basename(filepath)}", duration=4000)
            QTimer.singleShot(3000, self.end_emotion)
        except Exception as e:
            self.say(f"Screenshot failed: {e}", duration=3000)

    def _run_app_dialog(self):
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
        import subprocess
        try:
            if "run_app" in self.animations:
                self.emotion_override = True
                self.set_state("run_app")

            subprocess.Popen(
                app_path, shell=True,
                creationflags=0x08000000,
            )
            app_name = os.path.basename(app_path).replace(".exe", "")
            self.say(f"\U0001f680 Launching {app_name}!", duration=3000)
            QTimer.singleShot(3000, self.end_emotion)
        except Exception as e:
            self.say(f"Could not launch: {e}", duration=3000)

    def _shutdown_pc(self):
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
        if "notification" in self.animations:
            self.emotion_override = True
            self.set_state("notification")
        self.say(text, duration=duration, force=True)
        QTimer.singleShot(duration, self.end_emotion)

    # ==========================================================
    #  WINDOWS NOTIFICATION MONITOR
    # ==========================================================
    def _load_recent_notifications(self):
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
        new = self.notif_reader.check_new()
        if not new:
            return

        for notif in new:
            self._notif_log.append(notif)

        if len(self._notif_log) > 50:
            self._notif_log = self._notif_log[-50:]

        latest = new[-1]
        app = latest["app"]
        title = latest["title"]
        body = latest["body"]

        lines = [f"\U0001f514 {app}"]
        if title:
            lines.append(title)
        if body and body != title:
            lines.append(body[:80] + ("..." if len(body) > 80 else ""))

        display = "\n".join(lines)

        if len(new) > 1:
            display += f"\n(+{len(new) - 1} more)"

        self._show_notification_anim(display, duration=6000)

    def _show_notification_log(self):
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
    #  PAINT
    # ==========================================================
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(
            self.pet_label.x(), self.pet_label.y(),
            self.pet_label.width(), self.pet_label.height(),
            QColor(0, 0, 0, 1),
        )
        painter.end()

    # ==========================================================
    #  MOUSE EVENTS
    # ==========================================================
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.pos()
            self.set_state("dragging")
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
    #  CONTEXT MENU
    # ==========================================================
    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #F5F5F5; border: 1px solid #888; }"
            "QMenu::item { padding: 6px 24px; color: #222222; }"
            "QMenu::item:selected { background: #5599ff; color: white; }"
            "QMenu::item:disabled { color: #888888; }"
            "QMenu::separator { height: 1px; background: #ccc; margin: 4px 8px; }"
        )
        name = self.settings.get("pet_name")
        lv = self.stats.data.get("level", 1)

        # Header
        header = QAction(f"{name}  |  Lv.{lv}", self)
        header.setEnabled(False)
        menu.addAction(header)
        menu.addSeparator()

        # Pomodoro
        if self.pomodoro_active:
            mins_left = self.pomodoro_remaining // 60
            phase = "Break" if self.pomodoro_is_break else "Focus"
            pomo_action = QAction(f"Stop Pomodoro ({phase} {mins_left}m left)", self)
            pomo_action.triggered.connect(self.stop_pomodoro)
        else:
            pomo_action = QAction("Start Pomodoro", self)
            pomo_action.triggered.connect(self.start_pomodoro)
        menu.addAction(pomo_action)

        menu.addSeparator()

        # Stats
        stats_action = QAction("Session Stats", self)
        stats_action.triggered.connect(self._show_stats)
        menu.addAction(stats_action)

        lifetime_action = QAction("Lifetime Stats & Streak", self)
        lifetime_action.triggered.connect(self._show_lifetime_stats)
        menu.addAction(lifetime_action)

        if self.settings.get("enable_achievements"):
            unlocked, total = self.achievement_engine.get_unlocked_count()
            ach_action = QAction(f"Achievements ({unlocked}/{total})", self)
            ach_action.triggered.connect(self._show_achievements)
            menu.addAction(ach_action)

        menu.addSeparator()

        # Music submenu
        music_menu = menu.addMenu("Music")
        music_menu.setStyleSheet(
            "QMenu { background: #F5F5F5; border: 1px solid #888; }"
            "QMenu::item { padding: 6px 20px; color: #222222; }"
            "QMenu::item:selected { background: #5599ff; color: white; }"
        )

        pp_label = "Pause" if self._music_playing else "Play"
        play_pause_action = QAction(f"\u23ef {pp_label}", self)
        play_pause_action.triggered.connect(self._media_play_pause)
        music_menu.addAction(play_pause_action)

        next_action = QAction("\u23ed Next Track", self)
        next_action.triggered.connect(self._media_next)
        music_menu.addAction(next_action)

        prev_action = QAction("\u23ee Previous Track", self)
        prev_action.triggered.connect(self._media_prev)
        music_menu.addAction(prev_action)

        vol_up_action = QAction("\U0001f50a Volume Up", self)
        vol_up_action.triggered.connect(self._media_vol_up)
        music_menu.addAction(vol_up_action)

        vol_down_action = QAction("\U0001f509 Volume Down", self)
        vol_down_action.triggered.connect(self._media_vol_down)
        music_menu.addAction(vol_down_action)

        mute_action = QAction("\U0001f507 Mute", self)
        mute_action.triggered.connect(self._media_mute)
        music_menu.addAction(mute_action)

        music_menu.addSeparator()

        if self.music_detector.is_playing and self.music_detector.current_track:
            now_playing = QAction(f"\u266b {self.music_detector.current_track[:35]}", self)
            now_playing.setEnabled(False)
            music_menu.addAction(now_playing)
            music_menu.addSeparator()

        play_yt = QAction("Play YouTube URL...", self)
        play_yt.triggered.connect(self._play_youtube_url)
        music_menu.addAction(play_yt)

        search_yt = QAction("Search YouTube...", self)
        search_yt.triggered.connect(self._search_youtube)
        music_menu.addAction(search_yt)

        music_menu.addSeparator()

        add_sched = QAction("Schedule Music...", self)
        add_sched.triggered.connect(self._add_music_schedule)
        music_menu.addAction(add_sched)

        view_sched = QAction("View Schedules", self)
        view_sched.triggered.connect(self._view_music_schedules)
        music_menu.addAction(view_sched)

        remove_sched = QAction("Remove Schedule...", self)
        remove_sched.triggered.connect(self._remove_music_schedule)
        music_menu.addAction(remove_sched)

        # Web tracking
        web_report = QAction("Website Report", self)
        web_report.triggered.connect(self._show_web_report)
        menu.addAction(web_report)

        menu.addSeparator()

        # AI Chat
        ai_status = "🟢" if self.ai_brain.is_available else "🔴"
        chat_action = QAction(f"{ai_status} Chat with {name}...", self)
        chat_action.triggered.connect(self._open_ai_chat)
        menu.addAction(chat_action)

        ai_model_action = QAction("AI Model Settings...", self)
        ai_model_action.triggered.connect(self._configure_ai)
        menu.addAction(ai_model_action)

        ai_toggle = self.settings.get("enable_ai")
        ai_toggle_action = QAction("Disable AI Brain" if ai_toggle else "Enable AI Brain", self)
        ai_toggle_action.triggered.connect(self._toggle_ai)
        menu.addAction(ai_toggle_action)

        menu.addSeparator()

        # Quick Actions submenu
        actions_menu = menu.addMenu("\u26a1 Quick Actions")
        actions_menu.setStyleSheet(
            "QMenu { background: #F5F5F5; border: 1px solid #888; }"
            "QMenu::item { padding: 6px 20px; color: #222222; }"
            "QMenu::item:selected { background: #5599ff; color: white; }"
        )

        screenshot_act = QAction("\U0001f4f8 Take Screenshot", self)
        screenshot_act.triggered.connect(self._take_screenshot)
        actions_menu.addAction(screenshot_act)

        actions_menu.addSeparator()

        run_app_act = QAction("\U0001f680 Run App...", self)
        run_app_act.triggered.connect(self._run_app_dialog)
        actions_menu.addAction(run_app_act)

        actions_menu.addSeparator()

        shutdown_act = QAction("\u23fb Shutdown PC", self)
        shutdown_act.triggered.connect(self._shutdown_pc)
        actions_menu.addAction(shutdown_act)

        restart_act = QAction("\U0001f504 Restart PC", self)
        restart_act.triggered.connect(self._restart_pc)
        actions_menu.addAction(restart_act)

        menu.addSeparator()

        # Notifications
        notif_count = len(self._notif_log)
        notif_action = QAction(f"\U0001f514 Notifications ({notif_count})", self)
        notif_action.triggered.connect(self._show_notification_log)
        menu.addAction(notif_action)

        # Encourage
        encourage_action = QAction("Encourage Me!", self)
        encourage_action.triggered.connect(lambda: self.say_random("encourage", duration=4000))
        menu.addAction(encourage_action)

        # Quick Note
        note_action = QAction("Quick Note...", self)
        note_action.triggered.connect(self._quick_note)
        menu.addAction(note_action)

        # Mini Todo
        if self.settings.get("enable_mini_todo"):
            todo_action = QAction("To-Do List", self)
            todo_action.triggered.connect(self._toggle_todo_widget)
            menu.addAction(todo_action)

        menu.addSeparator()

        # Follow cursor
        following = self.settings.get("enable_follow_cursor")
        follow_action = QAction("Stop Following" if following else "Follow My Cursor", self)
        follow_action.triggered.connect(self._toggle_follow)
        menu.addAction(follow_action)

        # Focus mode
        focus_on = self.settings.get("focus_mode")
        focus_action = QAction("Exit Focus Mode" if focus_on else "Focus Mode (Mute)", self)
        focus_action.triggered.connect(self._toggle_focus_mode)
        menu.addAction(focus_action)

        # Reminders
        reminders_on = self.settings.get("enable_reminders")
        reminder_action = QAction("Disable Reminders" if reminders_on else "Enable Reminders", self)
        reminder_action.triggered.connect(self._toggle_reminders)
        menu.addAction(reminder_action)

        # Prayer times submenu
        if self.settings.get("enable_prayer_times"):
            prayer_menu = menu.addMenu("\U0001f54c Prayer Times")
            prayer_menu.setStyleSheet(
                "QMenu { background: #F5F5F5; border: 1px solid #888; }"
                "QMenu::item { padding: 6px 20px; color: #222222; }"
                "QMenu::item:selected { background: #5599ff; color: white; }"
            )

            times = self.prayer_manager.get_times()
            now = datetime.now()
            for pname in PrayerTimeManager.PRAYER_NAMES:
                pt = times.get(pname)
                if pt:
                    ar = PrayerTimeManager.PRAYER_NAMES_AR[PrayerTimeManager.PRAYER_NAMES.index(pname)]
                    passed = " \u2713" if pt <= now else ""
                    time_str = pt.strftime("%I:%M %p")
                    action = QAction(f"{ar}  {pname}:  {time_str}{passed}", self)
                    action.setEnabled(False)
                    prayer_menu.addAction(action)

            prayer_menu.addSeparator()

            nxt_name, nxt_ar, nxt_dt = self.prayer_manager.get_next_prayer()
            if nxt_dt:
                diff = nxt_dt - now
                mins_left = int(diff.total_seconds() / 60)
                hrs = mins_left // 60
                mns = mins_left % 60
                if hrs > 0:
                    remaining = f"{hrs}h {mns}m"
                else:
                    remaining = f"{mns}m"
                next_action = QAction(f"\u23f3 Next: {nxt_ar} {nxt_name} in {remaining}", self)
                next_action.setEnabled(False)
                prayer_menu.addAction(next_action)

            prayer_menu.addSeparator()

            loc_action = QAction("Set Location...", self)
            loc_action.triggered.connect(self._set_prayer_location)
            prayer_menu.addAction(loc_action)

            method_action = QAction("Calculation Method...", self)
            method_action.triggered.connect(self._set_prayer_method)
            prayer_menu.addAction(method_action)

        # Azkar submenu
        if self.settings.get("enable_azkar"):
            azkar_menu = menu.addMenu("\U0001f4ff Azkar / \u0623\u0630\u0643\u0627\u0631")
            azkar_menu.setStyleSheet(
                "QMenu { background: #F5F5F5; border: 1px solid #888; }"
                "QMenu::item { padding: 6px 20px; color: #222222; }"
                "QMenu::item:selected { background: #5599ff; color: white; }"
            )

            for cat_key, cat_data in AZKAR_CATEGORIES.items():
                icon = cat_data["icon"]
                name_ar = cat_data["name_ar"]
                count = len(cat_data["items"])
                cat_action = QAction(f"{icon} {name_ar} ({count})", self)
                cat_action.triggered.connect(
                    lambda checked, k=cat_key: self._open_azkar_reader(k)
                )
                azkar_menu.addAction(cat_action)

            azkar_menu.addSeparator()

            quick_dhikr = QAction("\U0001f4ff Quick Dhikr", self)
            quick_dhikr.triggered.connect(self._show_quick_dhikr)
            azkar_menu.addAction(quick_dhikr)

            azkar_menu.addSeparator()

            azkar_toggle = self.settings.get("enable_azkar")
            azkar_interval = self.settings.get("azkar_reminder_min")
            interval_action = QAction(f"\u23f0 Reminder every {azkar_interval} min", self)
            interval_action.triggered.connect(self._set_azkar_interval)
            azkar_menu.addAction(interval_action)

        menu.addSeparator()

        # Rename
        rename_action = QAction(f"Rename {name}...", self)
        rename_action.triggered.connect(self._rename_pet)
        menu.addAction(rename_action)

        # Run on startup toggle
        is_startup = self._is_startup_enabled()
        startup_action = QAction(
            "\u2705 Run on Startup" if is_startup else "\u274c Run on Startup", self
        )
        startup_action.triggered.connect(self._toggle_startup)
        menu.addAction(startup_action)

        menu.addSeparator()

        # Quit
        quit_action = QAction(f"Say Goodbye to {name} (Quit)", self)
        quit_action.triggered.connect(self._graceful_quit)
        menu.addAction(quit_action)

        menu.exec(pos)

    def _show_stats(self):
        self.say(self.mood_engine.get_stats_text(), duration=6000)

    def _show_lifetime_stats(self):
        self.say(self.stats.get_summary(), duration=6000)

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

    # ==========================================================
    #  AZKAR FEATURES
    # ==========================================================
    def _check_azkar(self):
        """Periodic azkar reminder check."""
        if not self.settings.get("enable_azkar"):
            return
        result = self.azkar_manager.should_remind()
        if not result:
            return

        msg = result["message"]
        if result["type"] == "timed":
            # Morning/evening azkar — bigger notification
            if "pray" in self.animations:
                self.set_state("pray")
            self.say(msg, duration=10000, force=True)
            self._play_prayer_sound()
        else:
            # Quick periodic dhikr
            self.say(msg, duration=6000)

    def _open_azkar_reader(self, category: str = "morning"):
        """Open the azkar reader dialog."""
        if self._azkar_reader is None or not self._azkar_reader.isVisible():
            self._azkar_reader = AzkarReaderDialog(
                initial_category=category, parent=None
            )
        else:
            self._azkar_reader._load_category(category)
        self._azkar_reader.show()
        self._azkar_reader.raise_()
        self._azkar_reader.activateWindow()

    def _show_quick_dhikr(self):
        """Show a random quick dhikr in the speech bubble."""
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
    #  PRAYER TIME FEATURES
    # ==========================================================
    def _play_prayer_sound(self):
        wav_path = os.path.join(os.path.dirname(__file__), "assets", "tasbeh_alert.wav")
        if os.path.exists(wav_path):
            try:
                winsound.PlaySound(
                    wav_path,
                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
                )
            except Exception:
                winsound.Beep(660, 300)
                winsound.Beep(880, 300)
                winsound.Beep(1100, 500)
        else:
            winsound.Beep(660, 300)
            winsound.Beep(880, 300)
            winsound.Beep(1100, 500)

    def _shake_screen(self, intensity=12, cycles=20, interval_ms=40):
        self._shake_origin = self.pos()
        self._shake_step = 0
        self._shake_cycles = cycles
        self._shake_intensity = intensity

        if not hasattr(self, '_shake_timer'):
            self._shake_timer = QTimer(self)
            self._shake_timer.timeout.connect(self._do_shake_step)

        self._shake_timer.start(interval_ms)

    def _do_shake_step(self):
        if self._shake_step >= self._shake_cycles:
            self._shake_timer.stop()
            self.move(self._shake_origin)
            return

        progress = self._shake_step / self._shake_cycles
        decay = 1.0 - progress
        amp = int(self._shake_intensity * decay)

        dx = random.randint(-amp, amp)
        dy = random.randint(-amp, amp)
        self.move(self._shake_origin + QPoint(dx, dy))
        self._shake_step += 1

    def _check_prayer_times(self):
        if not self.settings.get("enable_prayer_times"):
            return
        result = self.prayer_manager.check()
        if not result:
            return

        prayer = result["prayer"]
        ar = result["prayer_ar"]
        time_str = result["time"]

        if result["type"] == "alert":
            specific_pool = f"prayer_{prayer.lower()}"
            if specific_pool in SPEECH_POOL:
                msg = random.choice(SPEECH_POOL[specific_pool])
            else:
                msg = random.choice(SPEECH_POOL["prayer_alert"])
            if "pray" in self.animations:
                self.set_state("pray")
            elif "smile" in self.animations:
                self.set_state("smile")
            self.say(f"\U0001f54c {ar} - {prayer}\n{time_str}\n{msg}", duration=15000)
            self.mood_engine.boost_mood(5)
            self._play_prayer_sound()
            self._shake_screen(intensity=14, cycles=25, interval_ms=35)

        elif result["type"] == "reminder":
            mins = result["minutes_left"]
            msg = random.choice(SPEECH_POOL["prayer_reminder"])
            self.say(f"\u23f0 {ar} {prayer} in {mins} min\n{msg}", duration=8000)

    def _set_prayer_location(self):
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
            self.prayer_manager._cache_date = None
            self.say(f"Using {labels.get(method, method)}", duration=3000)

    # ==========================================================
    #  MUSIC FEATURES
    # ==========================================================
    def _media_play_pause(self):
        MediaController.play_pause()
        self.say_random("media_play_pause", duration=2000)
        self._music_playing = not self._music_playing
        if self._music_playing:
            if "music_listen" in self.animations:
                self.set_state("music_listen")
            elif "dance" in self.animations:
                self.set_state("dance")
        elif not self._music_playing:
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
        time_str = time_str.strip()
        if not re.match(r'^\d{1,2}:\d{2}$', time_str):
            self.say("Invalid time format. Use HH:MM", duration=3000)
            return
        parts = time_str.split(':')
        time_str = f"{int(parts[0]):02d}:{parts[1]}"

        url, ok2 = QInputDialog.getText(
            self, "Schedule Music", "YouTube URL or search term:"
        )
        if not ok2 or not url.strip():
            return
        url = url.strip()
        if "youtube.com" not in url and "youtu.be" not in url:
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
        fired = self.music_scheduler.check_and_fire()
        for entry in fired:
            label = entry.get("label", "music")
            self.say_random("music_scheduled", label=label, duration=4000)
            self.mood_engine.boost_mood(5)

    # ==========================================================
    #  WEB TRACKING REPORT
    # ==========================================================
    def _show_web_report(self):
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
        python_exe = sys.executable
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
        return f'"{python_exe}" "{script_path}"'

    def _is_startup_enabled(self) -> bool:
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
        QApplication.instance().quit()

    def closeEvent(self, event):
        focus_min = self.mood_engine.get_focus_minutes()
        self.stats.record_session_end(focus_min)
        self.stats.save()
        self.web_tracker.save()
        self.music_scheduler.save()
        super().closeEvent(event)
