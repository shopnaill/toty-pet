"""
server_bridge.py — Thread-safe bridge between FastAPI server and DesktopPet (PyQt6).

All public methods can be called from any thread. Qt slot invocations are
marshalled onto the main thread via signals + threading.Event for return values.
"""

import io
import json
import asyncio
import threading
import time
import base64
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot


# ── Helpers ────────────────────────────────────────────────

def _get_time_of_day() -> str:
    h = datetime.now().hour
    if 5 <= h < 12:
        return "morning"
    elif 12 <= h < 17:
        return "afternoon"
    elif 17 <= h < 21:
        return "evening"
    return "night"


def _main_thread_call(signal, *args, timeout=5):
    """Emit a signal with a threading.Event appended; wait for result."""
    event = threading.Event()
    event.result = None
    signal.emit(*args, event)
    event.wait(timeout=timeout)
    return event.result


class PetBridge(QObject):
    """Wraps DesktopPet for safe cross-thread access from FastAPI."""

    # ── Signals (server thread → main thread) ─────────────
    _say_signal = pyqtSignal(str)
    _command_signal = pyqtSignal(str, object)
    _add_reminder_signal = pyqtSignal(str, float, object)
    _list_reminders_signal = pyqtSignal(object)
    _cancel_reminder_signal = pyqtSignal(str, object)
    _screenshot_signal = pyqtSignal(object)
    _create_note_signal = pyqtSignal(str, object)
    _toggle_notes_signal = pyqtSignal()
    _equip_signal = pyqtSignal(str, object)
    _unequip_signal = pyqtSignal()
    _backup_signal = pyqtSignal(object)
    _get_clipboard_signal = pyqtSignal(object)
    _set_clipboard_signal = pyqtSignal(str)
    _sharing_done_signal = pyqtSignal(str)  # notification message
    _new_device_signal = pyqtSignal(str, str)  # device_name, device_emoji
    _device_left_signal = pyqtSignal(str, str)  # device_name, device_emoji

    def __init__(self, pet):
        super().__init__()
        self._pet = pet
        # Connect signals to main-thread slots
        self._say_signal.connect(self._do_say)
        self._command_signal.connect(self._do_command)
        self._add_reminder_signal.connect(self._do_add_reminder)
        self._list_reminders_signal.connect(self._do_list_reminders)
        self._cancel_reminder_signal.connect(self._do_cancel_reminder)
        self._screenshot_signal.connect(self._do_screenshot)
        self._create_note_signal.connect(self._do_create_note)
        self._toggle_notes_signal.connect(lambda: pet._sticky_notes.toggle_all())
        self._equip_signal.connect(self._do_equip)
        self._unequip_signal.connect(lambda: pet._wardrobe.unequip())
        self._backup_signal.connect(self._do_backup)
        self._get_clipboard_signal.connect(self._do_get_clipboard)
        self._set_clipboard_signal.connect(self._do_set_clipboard)
        self._sharing_done_signal.connect(self._do_sharing_done)
        self._new_device_signal.connect(self._do_new_device)
        self._device_left_signal.connect(self._do_device_left)
        # Shared dict for live sharing progress (written by server thread, read by Qt timer)
        import threading
        self._sharing_lock = threading.Lock()
        self._sharing_items: dict[str, dict] = {}
        # Connected devices tracking
        self._devices_lock = threading.Lock()
        self._devices: dict[str, dict] = {}  # key → {name, emoji, ip, ua, first_seen, last_seen}

    # ══════════════════════════════════════════════════════
    #  STATUS & STATS
    # ══════════════════════════════════════════════════════

    def get_status(self) -> dict:
        p = self._pet
        return {
            "state": p.pet_state,
            "mood": round(p.mood_engine.mood, 1),
            "energy": round(p.mood_engine.energy, 1),
            "focus": round(p.mood_engine.focus, 1),
            "level": p.stats.data.get("level", 1),
            "xp": p.stats.data.get("xp", 0),
            "xp_to_next": p.stats.data.get("xp_to_next", 100),
            "streak": p.stats.data.get("current_streak", 0),
            "keystrokes": p.keystroke_count,
            "pomodoro": {
                "active": p.pomodoro_active,
                "remaining": p.pomodoro_remaining,
                "is_break": getattr(p, "pomodoro_is_break", False),
            },
            "ai_available": getattr(p.ai_brain, "is_available", False),
            "active_window": getattr(p, "current_window_title", ""),
            "timestamp": datetime.now().isoformat(),
        }

    def get_stats(self) -> dict:
        s = self._pet.stats.data
        return {
            "level": s.get("level", 1),
            "xp": s.get("xp", 0),
            "xp_to_next": s.get("xp_to_next", 100),
            "current_streak": s.get("current_streak", 0),
            "longest_streak": s.get("longest_streak", 0),
            "achievements_unlocked": s.get("achievements_unlocked", 0),
            "total_focus_minutes": s.get("total_focus_minutes", 0),
            "total_keystrokes": s.get("total_keystrokes", 0),
        }

    # ══════════════════════════════════════════════════════
    #  CHAT (async — OllamaBrain callback → future)
    # ══════════════════════════════════════════════════════

    async def chat(self, message: str) -> str:
        loop = asyncio.get_event_loop()
        future = loop.create_future()

        def callback(reply, error=None):
            loop.call_soon_threadsafe(
                future.set_result, reply if reply else (error or "No response")
            )

        p = self._pet
        ctx = {
            "mood": p.mood_engine.mood,
            "energy": p.mood_engine.energy,
            "focus": p.mood_engine.focus,
            "current_app": "Remote Dashboard",
            "time_of_day": _get_time_of_day(),
            "level": p.stats.data.get("level", 1),
            "streak": p.stats.data.get("current_streak", 0),
            "memory_context": "",
        }
        p.ai_brain.chat(message, ctx, callback)
        return await future

    # ══════════════════════════════════════════════════════
    #  SAY
    # ══════════════════════════════════════════════════════

    def say(self, text: str):
        self._say_signal.emit(text)

    @pyqtSlot(str)
    def _do_say(self, text: str):
        self._pet.say(text, duration=5000, force=True)

    # ══════════════════════════════════════════════════════
    #  COMMANDS (main-thread, returns result)
    # ══════════════════════════════════════════════════════

    def execute_command(self, cmd: str) -> str:
        return _main_thread_call(self._command_signal, cmd) or f"Command '{cmd}' sent"

    @pyqtSlot(str, object)
    def _do_command(self, cmd: str, event):
        p = self._pet
        c = cmd.lower().strip()
        msg = f"Command '{cmd}' executed"
        if c == "pomodoro_start":
            p.start_pomodoro()
        elif c == "pomodoro_stop":
            p.stop_pomodoro()
        elif c == "dance":
            p.set_state("dance"); p.say("💃 Let's dance!", force=True)
        elif c == "sleep":
            p.set_state("sleep"); p.say("😴 Zzz...", force=True)
        elif c == "idle":
            p.set_state("idle")
        elif c == "wave":
            p.set_state("wave"); p.say("👋 Hi!", force=True)
        elif c == "happy":
            p.set_state("happy"); p.say("😊", force=True)
        elif c == "sad":
            p.set_state("sad")
        elif c == "flip":
            p.set_state("backflip")
        elif c == "dnd_on":
            p._toggle_dnd(); msg = "DND toggled"
        elif c == "dnd_off":
            p._toggle_dnd(); msg = "DND toggled"
        elif c == "focus_on":
            p._toggle_focus_mode(); msg = "Focus mode toggled"
        elif c == "focus_off":
            p._toggle_focus_mode(); msg = "Focus mode toggled"
        else:
            msg = f"Unknown command: {cmd}"
        event.result = msg
        event.set()

    # ══════════════════════════════════════════════════════
    #  REMINDERS (main thread — QTimers)
    # ══════════════════════════════════════════════════════

    def list_reminders(self) -> str:
        return _main_thread_call(self._list_reminders_signal) or "No active reminders"

    @pyqtSlot(object)
    def _do_list_reminders(self, event):
        event.result = self._pet.reminder_mgr.list_active()
        event.set()

    def add_reminder(self, text: str, minutes: float) -> str:
        return _main_thread_call(self._add_reminder_signal, text, minutes) or "Reminder added"

    @pyqtSlot(str, float, object)
    def _do_add_reminder(self, text, minutes, event):
        event.result = self._pet.reminder_mgr.add(text, minutes=minutes)
        event.set()

    def cancel_reminder(self, keyword: str) -> str:
        return _main_thread_call(self._cancel_reminder_signal, keyword) or "Cancelled"

    @pyqtSlot(str, object)
    def _do_cancel_reminder(self, keyword, event):
        event.result = self._pet.reminder_mgr.cancel(None, keyword)
        event.set()

    # ══════════════════════════════════════════════════════
    #  HABITS (thread-safe — JSON file ops only)
    # ══════════════════════════════════════════════════════

    def list_habits(self) -> dict:
        ht = self._pet.habit_tracker
        data = ht.data if hasattr(ht, "data") else {}
        result = {}
        for key, info in data.items():
            if key == "_meta":
                continue
            result[key] = {
                "goal": info.get("goal", 1),
                "icon": info.get("icon", "✅"),
                "today": info.get("log", {}).get(str(datetime.now().date()), 0),
                "streak": ht._get_streak(key) if hasattr(ht, "_get_streak") else 0,
            }
        return result

    def log_habit(self, name: str, count: int = 1) -> str:
        return self._pet.habit_tracker.log_habit(name, count)

    def add_habit(self, name: str, goal: int = 1, icon: str = "✅") -> str:
        return self._pet.habit_tracker.add_habit(name, goal, icon)

    # ══════════════════════════════════════════════════════
    #  MEMORY
    # ══════════════════════════════════════════════════════

    def remember(self, text: str, topic: str = "") -> str:
        return self._pet.pet_memory.remember(text, topic)

    def recall(self, query: str = "") -> str:
        if query:
            return self._pet.pet_memory.recall(query)
        return self._pet.pet_memory.recall_all()

    # ══════════════════════════════════════════════════════
    #  STICKY NOTES (main thread — QWidgets)
    # ══════════════════════════════════════════════════════

    def create_note(self, text: str) -> str:
        return _main_thread_call(self._create_note_signal, text) or "Note created"

    @pyqtSlot(str, object)
    def _do_create_note(self, text, event):
        self._pet._sticky_notes.create_note(text)
        event.result = "Note created"
        event.set()

    def toggle_notes(self):
        self._toggle_notes_signal.emit()

    def get_notes(self) -> list:
        sn = self._pet._sticky_notes
        notes = []
        for n in getattr(sn, "_notes", []):
            d = n.get_data() if hasattr(n, "get_data") else {}
            notes.append({"id": d.get("nid", 0), "text": d.get("text", ""), "created": d.get("created", "")})
        return notes

    # ══════════════════════════════════════════════════════
    #  MOOD JOURNAL
    # ══════════════════════════════════════════════════════

    def log_mood(self, score: int, note: str = "") -> str:
        self._pet._mood_journal.log_mood(score, note)
        return "Mood logged"

    def get_mood_history(self, limit: int = 14) -> list:
        return self._pet._mood_journal.get_history(limit)

    def get_mood_week(self) -> str:
        return self._pet._mood_journal.get_week_summary()

    # ══════════════════════════════════════════════════════
    #  WARDROBE (main thread for equip — triggers repaint)
    # ══════════════════════════════════════════════════════

    def get_wardrobe(self) -> dict:
        w = self._pet._wardrobe
        return {
            "equipped": w.get_equipped(),
            "unlocked": list(w.get_unlocked()),
        }

    def equip_item(self, item_id: str) -> str:
        return _main_thread_call(self._equip_signal, item_id) or "Done"

    @pyqtSlot(str, object)
    def _do_equip(self, item_id, event):
        ok = self._pet._wardrobe.equip(item_id)
        self._pet.update()  # repaint
        event.result = f"Equipped {item_id}" if ok else f"{item_id} not unlocked"
        event.set()

    def unequip_item(self) -> str:
        self._unequip_signal.emit()
        return "Unequipped"

    # ══════════════════════════════════════════════════════
    #  SCREENSHOT (main thread)
    # ══════════════════════════════════════════════════════

    def take_screenshot(self) -> str:
        """Returns base64 JPEG of full screen capture."""
        return _main_thread_call(self._screenshot_signal, timeout=10) or ""

    @pyqtSlot(object)
    def _do_screenshot(self, event):
        try:
            path = self._pet._screenshot.capture_fullscreen()
            if path and Path(path).exists():
                event.result = path
            else:
                event.result = ""
        except Exception:
            event.result = ""
        event.set()

    # ══════════════════════════════════════════════════════
    #  SCREEN CAPTURE (for live streaming — runs in any thread)
    # ══════════════════════════════════════════════════════

    _monitors = None            # cached monitor list

    def list_monitors(self) -> list:
        """Return list of monitors [{index, width, height, x, y}]."""
        try:
            from screeninfo import get_monitors
            mons = get_monitors()
            return [{"index": i, "width": m.width, "height": m.height,
                     "x": m.x, "y": m.y, "name": m.name or f"Monitor {i}"}
                    for i, m in enumerate(mons)]
        except Exception:
            return [{"index": 0, "width": 1920, "height": 1080, "x": 0, "y": 0, "name": "Primary"}]

    def capture_screen_frame(self, quality: int = 40, scale: float = 0.5,
                             monitor: int = -1, cursor: bool = True,
                             use_webp: bool = False) -> bytes:
        """Capture screen as JPEG/WebP bytes for streaming."""
        try:
            from PIL import ImageGrab, Image, ImageDraw
            # Multi-monitor: capture specific monitor or all
            if monitor >= 0:
                try:
                    from screeninfo import get_monitors
                    mons = get_monitors()
                    if monitor < len(mons):
                        m = mons[monitor]
                        bbox = (m.x, m.y, m.x + m.width, m.y + m.height)
                        img = ImageGrab.grab(bbox=bbox)
                    else:
                        img = ImageGrab.grab()
                except Exception:
                    img = ImageGrab.grab()
            else:
                img = ImageGrab.grab()

            # Draw cursor overlay
            if cursor:
                try:
                    import ctypes
                    pt = ctypes.wintypes.POINT()
                    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                    cx, cy = pt.x, pt.y
                    # Adjust for monitor offset if capturing specific monitor
                    if monitor >= 0:
                        try:
                            from screeninfo import get_monitors
                            mons = get_monitors()
                            if monitor < len(mons):
                                cx -= mons[monitor].x
                                cy -= mons[monitor].y
                        except Exception:
                            pass
                    draw = ImageDraw.Draw(img)
                    r = 8
                    draw.line([(cx - r, cy), (cx + r, cy)], fill="red", width=2)
                    draw.line([(cx, cy - r), (cx, cy + r)], fill="red", width=2)
                    draw.ellipse([(cx - 3, cy - 3), (cx + 3, cy + 3)], fill="red")
                except Exception:
                    pass

            if scale != 1.0:
                w, h = img.size
                img = img.resize((int(w * scale), int(h * scale)), Image.BILINEAR)

            buf = io.BytesIO()
            if use_webp:
                img.save(buf, format="WEBP", quality=quality, method=0)
            else:
                img.save(buf, format="JPEG", quality=quality)
            return buf.getvalue()
        except Exception:
            return b""

    # ══════════════════════════════════════════════════════
    #  REMOTE INPUT (mouse & keyboard)
    # ══════════════════════════════════════════════════════

    _input_timestamps = {}  # rate-limiter: {action: last_time}
    _INPUT_RATE_MS = 33     # ~30 events/sec max

    def _rate_ok(self, action: str) -> bool:
        now = time.monotonic()
        last = self._input_timestamps.get(action, 0)
        if (now - last) * 1000 < self._INPUT_RATE_MS:
            return False
        self._input_timestamps[action] = now
        return True

    def mouse_move(self, x: int, y: int):
        if not self._rate_ok("mouse_move"):
            return
        import ctypes
        ctypes.windll.user32.SetCursorPos(x, y)

    def mouse_click(self, x: int, y: int, button: str = "left"):
        import ctypes
        ctypes.windll.user32.SetCursorPos(x, y)
        if button == "right":
            ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
        elif button == "middle":
            ctypes.windll.user32.mouse_event(0x0020, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(0x0040, 0, 0, 0, 0)
        else:
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

    def mouse_down(self, x: int, y: int, button: str = "left"):
        import ctypes
        ctypes.windll.user32.SetCursorPos(x, y)
        if button == "right":
            ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
        else:
            ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)

    def mouse_up(self, x: int, y: int, button: str = "left"):
        import ctypes
        ctypes.windll.user32.SetCursorPos(x, y)
        if button == "right":
            ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
        else:
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

    def mouse_scroll(self, delta: int):
        import ctypes
        ctypes.windll.user32.mouse_event(0x0800, 0, 0, delta, 0)

    def keyboard_type(self, text: str):
        """Type text using SendInput with KEYEVENTF_UNICODE."""
        import ctypes
        import ctypes.wintypes as wt

        INPUT_KEYBOARD = 1
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wt.WORD),
                ("wScan", wt.WORD),
                ("dwFlags", wt.DWORD),
                ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", wt.LONG), ("dy", wt.LONG),
                ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class _INPUTunion(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", wt.DWORD), ("union", _INPUTunion)]

        user32 = ctypes.windll.user32
        for ch in text:
            down = INPUT(type=INPUT_KEYBOARD)
            down.union.ki.wVk = 0
            down.union.ki.wScan = ord(ch)
            down.union.ki.dwFlags = KEYEVENTF_UNICODE

            up = INPUT(type=INPUT_KEYBOARD)
            up.union.ki.wVk = 0
            up.union.ki.wScan = ord(ch)
            up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

            arr = (INPUT * 2)(down, up)
            user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))

    def keyboard_key(self, key: str, action: str = "press"):
        """Send a special key (enter, tab, escape, backspace, etc.)."""
        import ctypes
        VK_MAP = {
            "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "backspace": 0x08,
            "delete": 0x2E, "space": 0x20, "up": 0x26, "down": 0x28,
            "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23,
            "pageup": 0x21, "pagedown": 0x22, "f1": 0x70, "f2": 0x71,
            "f3": 0x72, "f4": 0x73, "f5": 0x74, "f11": 0x7A,
            "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
        }
        vk = VK_MAP.get(key.lower(), 0)
        if not vk:
            return
        user32 = ctypes.windll.user32
        if action in ("press", "down"):
            user32.keybd_event(vk, 0, 0, 0)
        if action in ("press", "up"):
            user32.keybd_event(vk, 0, 0x0002, 0)

    def keyboard_combo(self, keys: list):
        """Send a key combo like ['ctrl', 'c']."""
        import ctypes
        VK_MAP = {
            "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B,
            "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "delete": 0x2E,
            "backspace": 0x08, "space": 0x20,
            "a": 0x41, "c": 0x43, "v": 0x56, "x": 0x58, "z": 0x5A,
            "s": 0x53, "f": 0x46, "n": 0x4E, "w": 0x57, "t": 0x54,
            "r": 0x52, "l": 0x4C, "p": 0x50,
            "f4": 0x73, "f5": 0x74, "f11": 0x7A,
        }
        user32 = ctypes.windll.user32
        for k in keys:
            vk = VK_MAP.get(k.lower(), 0)
            if vk:
                user32.keybd_event(vk, 0, 0, 0)
        for k in reversed(keys):
            vk = VK_MAP.get(k.lower(), 0)
            if vk:
                user32.keybd_event(vk, 0, 0x0002, 0)

    # ══════════════════════════════════════════════════════
    #  CLIPBOARD SYNC  (must run on Qt main thread)
    # ══════════════════════════════════════════════════════

    def get_clipboard(self) -> str:
        return _main_thread_call(self._get_clipboard_signal) or ""

    def set_clipboard(self, text: str):
        self._set_clipboard_signal.emit(text)

    @pyqtSlot(object)
    def _do_get_clipboard(self, event):
        from PyQt6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        event.result = cb.text() if cb else ""
        event.set()

    @pyqtSlot(str)
    def _do_set_clipboard(self, text):
        from PyQt6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        if cb:
            cb.setText(text)

    # ── Sharing progress (shown on pet overlay) ───────────

    def notify_sharing(self, transfer_id: str, label: str, done: int, total: int):
        """Thread-safe: update progress dict (read by pet's QTimer)."""
        pct = int(done * 100 / total) if total > 0 else 0
        with self._sharing_lock:
            self._sharing_items[transfer_id] = {
                "name": label, "percent": pct, "speed": 0, "size": 0,
            }

    def notify_sharing_done(self, transfer_id: str, message: str):
        """Thread-safe: remove transfer and send notification to pet."""
        with self._sharing_lock:
            self._sharing_items.pop(transfer_id, None)
        self._sharing_done_signal.emit(message)

    def get_sharing_items(self) -> list[dict]:
        """Read current sharing items (called by pet's QTimer on main thread)."""
        with self._sharing_lock:
            return list(self._sharing_items.values())

    @pyqtSlot(str)
    def _do_sharing_done(self, message):
        """Show notification on pet (runs on main thread)."""
        self._pet._show_notification_anim(message, duration=4000)

    # ── Connected devices tracking ────────────────────────

    @staticmethod
    def _parse_device(ua: str, ip: str) -> tuple[str, str]:
        """Extract a friendly device name & emoji from User-Agent."""
        ua_low = ua.lower()
        # Detect device type & OS
        if "iphone" in ua_low:
            return "iPhone", "📱"
        if "ipad" in ua_low:
            return "iPad", "📱"
        if "android" in ua_low:
            # Try to extract model: "...Build/MODEL..." or generic
            if "samsung" in ua_low:
                return "Samsung Phone", "📱"
            if "pixel" in ua_low:
                return "Pixel Phone", "📱"
            if "huawei" in ua_low:
                return "Huawei Phone", "📱"
            if "xiaomi" in ua_low or "redmi" in ua_low:
                return "Xiaomi Phone", "📱"
            if "tablet" in ua_low or "tab" in ua_low:
                return "Android Tablet", "📱"
            return "Android Phone", "📱"
        if "macintosh" in ua_low or "mac os" in ua_low:
            return "Mac", "💻"
        if "windows" in ua_low:
            return "Windows PC", "🖥️"
        if "linux" in ua_low:
            return "Linux PC", "🐧"
        if "chromeos" in ua_low:
            return "Chromebook", "💻"
        if "playstation" in ua_low:
            return "PlayStation", "🎮"
        if "xbox" in ua_low:
            return "Xbox", "🎮"
        if "smart-tv" in ua_low or "smarttv" in ua_low or "tizen" in ua_low or "webos" in ua_low:
            return "Smart TV", "📺"
        # Fallback
        return f"Device ({ip.split(':')[0]})", "🌐"

    def track_device(self, ip: str, ua: str):
        """Called from server thread on every authenticated request."""
        import time as _time
        name, emoji = self._parse_device(ua, ip)
        key = f"{ip}|{name}"
        now = _time.time()
        with self._devices_lock:
            is_new = key not in self._devices
            self._devices[key] = {
                "name": name, "emoji": emoji, "ip": ip, "ua": ua,
                "first_seen": self._devices.get(key, {}).get("first_seen", now),
                "last_seen": now,
            }
            # Clean up stale devices (not seen in 10 min)
            stale = [k for k, v in self._devices.items() if (now - v["last_seen"]) > 600]
            for k in stale:
                gone = self._devices.pop(k)
                self._device_left_signal.emit(gone["name"], gone["emoji"])
        if is_new:
            self._new_device_signal.emit(name, emoji)

    _ACTIVE_TIMEOUT = 30  # seconds — device considered offline after this

    def get_devices(self) -> list[dict]:
        """Return list of tracked devices (called from any thread)."""
        import time as _time
        now = _time.time()
        with self._devices_lock:
            result = []
            for d in self._devices.values():
                result.append({
                    "name": d["name"],
                    "emoji": d["emoji"],
                    "ip": d["ip"],
                    "active": (now - d["last_seen"]) < self._ACTIVE_TIMEOUT,
                    "last_seen": d["last_seen"],
                })
            return result

    def get_active_device_count(self) -> int:
        """Return number of currently active devices."""
        import time as _time
        now = _time.time()
        with self._devices_lock:
            return sum(1 for d in self._devices.values()
                       if (now - d["last_seen"]) < self._ACTIVE_TIMEOUT)

    @pyqtSlot(str, str)
    def _do_new_device(self, name, emoji):
        """Fun notification on pet when a new device connects."""
        greetings = [
            f"{emoji} Hey! {name} just joined the party!",
            f"{emoji} Ooh, {name} is here! Hi there!",
            f"{emoji} New friend alert: {name}!",
            f"{emoji} *waves* Welcome, {name}!",
            f"{emoji} {name} connected! Let's gooo!",
        ]
        import random
        msg = random.choice(greetings)
        self._pet._show_notification_anim(msg, duration=5000)

    @pyqtSlot(str, str)
    def _do_device_left(self, name, emoji):
        """Notification when a device disconnects."""
        farewells = [
            f"{emoji} {name} left the party… bye!",
            f"{emoji} {name} went offline 👋",
            f"{emoji} See ya later, {name}!",
        ]
        import random
        self._pet.say(random.choice(farewells), duration=3000, force=True)

    # ══════════════════════════════════════════════════════
    #  SYSTEM HEALTH
    # ══════════════════════════════════════════════════════

    def get_system_health(self) -> dict:
        sh = self._pet._system_health
        if sh and hasattr(sh, "get_snapshot"):
            return sh.get_snapshot()
        # Fallback if system health monitor is disabled
        try:
            import psutil
            vm = psutil.virtual_memory()
            d = psutil.disk_usage("/")
            bat = psutil.sensors_battery()
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "ram_percent": vm.percent,
                "ram_used_gb": round(vm.used / 1e9, 1),
                "ram_total_gb": round(vm.total / 1e9, 1),
                "disk_percent": d.percent,
                "disk_free_gb": round(d.free / 1e9, 1),
                "battery_percent": bat.percent if bat else None,
                "battery_charging": bat.power_plugged if bat else None,
            }
        except Exception:
            return {}

    # ══════════════════════════════════════════════════════
    #  APP TIME TRACKER
    # ══════════════════════════════════════════════════════

    def get_app_time(self) -> dict:
        try:
            return self._pet._app_time_tracker.get_report()
        except Exception:
            return {}

    # ══════════════════════════════════════════════════════
    #  KEYBOARD HEATMAP
    # ══════════════════════════════════════════════════════

    def get_keyboard_heatmap(self) -> dict:
        try:
            return {
                "today": self._pet._kb_heatmap.get_today_hours(),
                "week": self._pet._kb_heatmap.get_week_hours(),
            }
        except Exception:
            return {"today": {}, "week": {}}

    # ══════════════════════════════════════════════════════
    #  BACKUP (main thread)
    # ══════════════════════════════════════════════════════

    def create_backup(self) -> str:
        return _main_thread_call(self._backup_signal, timeout=30) or ""

    @pyqtSlot(object)
    def _do_backup(self, event):
        try:
            path = self._pet._backup.export_backup()
            event.result = path or ""
        except Exception:
            event.result = ""
        event.set()

    def list_backups(self) -> list:
        try:
            return self._pet._backup.list_backups()
        except Exception:
            return []

    # ══════════════════════════════════════════════════════
    #  FILE TRANSFER
    # ══════════════════════════════════════════════════════

    def _file_base(self) -> Path:
        """Consistent base directory for all file operations."""
        return Path(".").resolve()

    def _safe_path(self, subpath: str) -> Path | None:
        """Resolve subpath under file base, return None if traversal detected."""
        base = self._file_base()
        target = (base / subpath).resolve()
        if not str(target).startswith(str(base)):
            return None
        return target

    def list_files(self, subdir: str = "") -> list:
        """List files in the pet directory (or a subdirectory)."""
        target = self._safe_path(subdir)
        if target is None or not target.is_dir():
            return []
        result = []
        for item in sorted(target.iterdir()):
            try:
                result.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0,
                })
            except (PermissionError, OSError):
                continue
        return result

    def get_file_path(self, filepath: str) -> Path | None:
        """Return the resolved safe path if valid file, else None."""
        target = self._safe_path(filepath)
        if target is None or not target.is_file():
            return None
        return target

    def get_file_bytes(self, filepath: str) -> bytes | None:
        """Read a file. Security: restrict to base dir, 2 GB limit."""
        target = self._safe_path(filepath)
        if target is None or not target.is_file():
            return None
        if target.stat().st_size > 2 * 1024 * 1024 * 1024:
            return None
        return target.read_bytes()

    def delete_file(self, filepath: str) -> dict:
        """Delete a file or empty directory."""
        target = self._safe_path(filepath)
        if target is None:
            return {"error": "Invalid path"}
        if target == self._file_base():
            return {"error": "Cannot delete root"}
        try:
            if target.is_file():
                target.unlink()
                return {"ok": True, "deleted": filepath}
            elif target.is_dir():
                import shutil
                shutil.rmtree(target)
                return {"ok": True, "deleted": filepath}
            return {"error": "Not found"}
        except Exception as e:
            return {"error": str(e)}

    def rename_file(self, old_path: str, new_name: str) -> dict:
        """Rename a file/folder (new_name is just the filename, no path)."""
        target = self._safe_path(old_path)
        if target is None or not target.exists():
            return {"error": "Not found"}
        # new_name must be a simple name (no slashes)
        if '/' in new_name or '\\' in new_name or '..' in new_name:
            return {"error": "Invalid name"}
        new_target = target.parent / new_name
        if new_target.exists():
            return {"error": "Name already exists"}
        try:
            target.rename(new_target)
            return {"ok": True, "new_name": new_name}
        except Exception as e:
            return {"error": str(e)}

    def create_folder(self, path: str) -> dict:
        """Create a folder."""
        target = self._safe_path(path)
        if target is None:
            return {"error": "Invalid path"}
        if target.exists():
            return {"error": "Already exists"}
        try:
            target.mkdir(parents=True, exist_ok=True)
            return {"ok": True, "path": path}
        except Exception as e:
            return {"error": str(e)}

    def get_file_info(self, filepath: str) -> dict:
        """Get file metadata for preview."""
        target = self._safe_path(filepath)
        if target is None or not target.exists():
            return {"error": "Not found"}
        stat = target.stat()
        suffix = target.suffix.lower()
        is_text = suffix in ('.txt', '.py', '.js', '.html', '.css', '.json', '.md',
                             '.csv', '.xml', '.yml', '.yaml', '.ini', '.cfg', '.log',
                             '.bat', '.sh', '.toml', '.env', '.gitignore')
        is_image = suffix in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.ico')
        return {
            "name": target.name,
            "size": stat.st_size,
            "is_dir": target.is_dir(),
            "is_text": is_text,
            "is_image": is_image,
            "suffix": suffix,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    # ══════════════════════════════════════════════════════
    #  SCHEDULED COMMANDS
    # ══════════════════════════════════════════════════════

    _scheduled_commands = []  # [{id, command, hour, minute, enabled, last_run}]
    _schedule_file = Path(__file__).parent / "scheduled_commands.json"
    _schedule_lock = threading.Lock()

    def _load_schedule(self):
        if self._schedule_file.exists():
            try:
                self._scheduled_commands = json.loads(
                    self._schedule_file.read_text(encoding="utf-8"))
            except Exception:
                self._scheduled_commands = []

    def _save_schedule(self):
        self._schedule_file.write_text(
            json.dumps(self._scheduled_commands, indent=2), encoding="utf-8")

    def list_scheduled(self) -> list:
        with self._schedule_lock:
            self._load_schedule()
            return self._scheduled_commands

    def add_scheduled(self, command: str, hour: int, minute: int) -> dict:
        with self._schedule_lock:
            self._load_schedule()
            entry = {
                "id": len(self._scheduled_commands) + 1,
                "command": command,
                "hour": hour, "minute": minute,
                "enabled": True, "last_run": "",
            }
            self._scheduled_commands.append(entry)
            self._save_schedule()
            return entry

    def remove_scheduled(self, sched_id: int) -> bool:
        with self._schedule_lock:
            self._load_schedule()
            before = len(self._scheduled_commands)
            self._scheduled_commands = [s for s in self._scheduled_commands if s.get("id") != sched_id]
            self._save_schedule()
            return len(self._scheduled_commands) < before

    def check_scheduled(self):
        """Called periodically from server to fire due commands."""
        now = datetime.now()
        with self._schedule_lock:
            self._load_schedule()
            for entry in self._scheduled_commands:
                if not entry.get("enabled"):
                    continue
                if entry["hour"] == now.hour and entry["minute"] == now.minute:
                    today = str(now.date())
                    if entry.get("last_run") != today:
                        entry["last_run"] = today
                        self._save_schedule()
                        self.execute_command(entry["command"])

    # ══════════════════════════════════════════════════════
    #  DATA EXPORT (CSV)
    # ══════════════════════════════════════════════════════

    def export_mood_csv(self) -> str:
        rows = self.get_mood_history(365)
        lines = ["date,score,note"]
        for r in rows:
            note = str(r.get("note", "")).replace('"', '""')
            lines.append(f'{r.get("date","")},{r.get("score","")},"{note}"')
        return "\n".join(lines)

    def export_habits_csv(self) -> str:
        habits = self.list_habits()
        lines = ["name,icon,goal,today,streak"]
        for name, info in habits.items():
            lines.append(f'{name},{info["icon"]},{info["goal"]},{info["today"]},{info.get("streak",0)}')
        return "\n".join(lines)

    def export_app_time_csv(self) -> str:
        data = self.get_app_time()
        lines = ["app,minutes"]
        for app, mins in sorted(data.items(), key=lambda x: -x[1]):
            lines.append(f'"{app}",{mins:.1f}')
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════
    #  VOLUME CONTROL (Windows)
    # ══════════════════════════════════════════════════════

    def get_volume(self) -> dict:
        """Return current system volume & mute state."""
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            level = vol.GetMasterVolumeLevelScalar()
            muted = vol.GetMute()
            return {"volume": round(level * 100), "muted": bool(muted)}
        except Exception:
            # Fallback: use nircmd-style approach or return unknown
            return {"volume": -1, "muted": False, "error": "pycaw not available"}

    def set_volume(self, level: int) -> dict:
        """Set system volume (0-100)."""
        level = max(0, min(100, level))
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            vol.SetMasterVolumeLevelScalar(level / 100.0, None)
            return {"volume": level, "ok": True}
        except Exception as e:
            return {"error": str(e)}

    def toggle_mute(self) -> dict:
        """Toggle system mute."""
        try:
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            vol = cast(interface, POINTER(IAudioEndpointVolume))
            current = vol.GetMute()
            vol.SetMute(not current, None)
            return {"muted": not current, "ok": True}
        except Exception as e:
            return {"error": str(e)}

    # ══════════════════════════════════════════════════════
    #  MEDIA CONTROL (via virtual key presses)
    # ══════════════════════════════════════════════════════

    _MEDIA_KEYS = {
        "play_pause": 0xB3,   # VK_MEDIA_PLAY_PAUSE
        "next":       0xB0,   # VK_MEDIA_NEXT_TRACK
        "prev":       0xB1,   # VK_MEDIA_PREV_TRACK
        "stop":       0xB2,   # VK_MEDIA_STOP
        "vol_up":     0xAF,   # VK_VOLUME_UP
        "vol_down":   0xAE,   # VK_VOLUME_DOWN
        "vol_mute":   0xAD,   # VK_VOLUME_MUTE
    }

    def media_key(self, action: str) -> dict:
        """Send a media key. action: play_pause, next, prev, stop, vol_up, vol_down, vol_mute"""
        vk = self._MEDIA_KEYS.get(action)
        if vk is None:
            return {"error": f"Unknown media action: {action}"}
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.keybd_event(vk, 0, 0, 0)
            user32.keybd_event(vk, 0, 2, 0)  # KEYEVENTF_KEYUP
            return {"ok": True, "action": action}
        except Exception as e:
            return {"error": str(e)}

    # ══════════════════════════════════════════════════════
    #  RUNNING PROCESSES
    # ══════════════════════════════════════════════════════

    def list_processes(self, sort_by: str = "cpu", limit: int = 30) -> list:
        """Return top processes sorted by cpu or memory."""
        try:
            import psutil
            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'status']):
                try:
                    info = p.info
                    mem_mb = (info['memory_info'].rss / 1048576) if info.get('memory_info') else 0
                    procs.append({
                        "pid": info['pid'],
                        "name": info['name'] or "Unknown",
                        "cpu": info.get('cpu_percent', 0) or 0,
                        "mem_mb": round(mem_mb, 1),
                        "status": info.get('status', ''),
                    })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            key = "cpu" if sort_by == "cpu" else "mem_mb"
            procs.sort(key=lambda x: x[key], reverse=True)
            return procs[:limit]
        except Exception:
            return []

    def kill_process(self, pid: int) -> dict:
        """Kill a process by PID."""
        try:
            import psutil
            p = psutil.Process(pid)
            name = p.name()
            p.terminate()
            return {"ok": True, "name": name, "pid": pid}
        except Exception as e:
            return {"error": str(e)}

    # ══════════════════════════════════════════════════════
    #  POWER MANAGEMENT
    # ══════════════════════════════════════════════════════

    def power_action(self, action: str) -> dict:
        """Execute power action: lock, sleep, shutdown, restart."""
        import ctypes
        import subprocess
        try:
            if action == "lock":
                ctypes.windll.user32.LockWorkStation()
                return {"ok": True, "action": "lock"}
            elif action == "sleep":
                # SetSuspendState(hibernate, force, disable_wake_events)
                ctypes.windll.PowrProf.SetSuspendState(0, 1, 0)
                return {"ok": True, "action": "sleep"}
            elif action == "shutdown":
                subprocess.Popen(["shutdown", "/s", "/t", "30", "/c", "Toty Remote: Shutdown in 30s"], creationflags=subprocess.CREATE_NO_WINDOW)
                return {"ok": True, "action": "shutdown", "delay": 30}
            elif action == "restart":
                subprocess.Popen(["shutdown", "/r", "/t", "30", "/c", "Toty Remote: Restart in 30s"], creationflags=subprocess.CREATE_NO_WINDOW)
                return {"ok": True, "action": "restart", "delay": 30}
            elif action == "cancel_shutdown":
                subprocess.Popen(["shutdown", "/a"], creationflags=subprocess.CREATE_NO_WINDOW)
                return {"ok": True, "action": "cancel_shutdown"}
            else:
                return {"error": f"Unknown action: {action}"}
        except Exception as e:
            return {"error": str(e)}

    # ══════════════════════════════════════════════════════
    #  NETWORK INFO
    # ══════════════════════════════════════════════════════

    def get_network_info(self) -> dict:
        """Return network interfaces, IPs, WiFi name."""
        result = {"interfaces": [], "wifi_name": ""}
        try:
            import psutil
            addrs = psutil.net_if_addrs()
            stats = psutil.net_if_stats()
            for name, addr_list in addrs.items():
                is_up = stats.get(name, None)
                if is_up and not is_up.isup:
                    continue
                for addr in addr_list:
                    if addr.family.name == 'AF_INET' and not addr.address.startswith('127.'):
                        result["interfaces"].append({
                            "name": name,
                            "ip": addr.address,
                            "netmask": addr.netmask,
                        })
        except Exception:
            pass
        # WiFi SSID (Windows)
        try:
            import subprocess
            out = subprocess.check_output(
                ["netsh", "wlan", "show", "interfaces"],
                creationflags=subprocess.CREATE_NO_WINDOW,
                text=True, timeout=5
            )
            for line in out.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    result["wifi_name"] = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass
        return result

    # ══════════════════════════════════════════════════════
    #  QUICK LAUNCH
    # ══════════════════════════════════════════════════════

    _QUICK_APPS = {
        "explorer":     "explorer.exe",
        "browser":      "start https://google.com",
        "notepad":      "notepad.exe",
        "calc":         "calc.exe",
        "taskmgr":      "taskmgr.exe",
        "cmd":          "cmd.exe",
        "settings":     "ms-settings:",
        "snip":         "SnippingTool.exe",
    }

    def quick_launch(self, app_id: str) -> dict:
        """Launch a predefined application."""
        import subprocess
        cmd = self._QUICK_APPS.get(app_id)
        if not cmd:
            return {"error": f"Unknown app: {app_id}"}
        try:
            if app_id in ("browser", "settings"):
                import os
                os.startfile(cmd if app_id == "settings" else cmd.split(" ", 1)[1])
            else:
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
            return {"ok": True, "app": app_id}
        except Exception as e:
            return {"error": str(e)}

    # ══════════════════════════════════════════════════════
    #  DISPLAY BRIGHTNESS (Windows)
    # ══════════════════════════════════════════════════════

    def get_brightness(self) -> dict:
        # Try screen_brightness_control first (works on laptops + external DDC monitors)
        try:
            import screen_brightness_control as sbc
            val = sbc.get_brightness()
            # Returns list for multi-monitor or int
            if isinstance(val, list):
                val = val[0] if val else -1
            return {"brightness": int(val)}
        except Exception:
            pass
        # Fallback: WMI (laptops only)
        try:
            import subprocess
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness).CurrentBrightness"],
                creationflags=subprocess.CREATE_NO_WINDOW, text=True, timeout=5
            )
            return {"brightness": int(out.strip())}
        except Exception:
            return {"brightness": -1, "error": "Not supported on this display"}

    def set_brightness(self, level: int) -> dict:
        level = max(0, min(100, level))
        # Try screen_brightness_control first
        try:
            import screen_brightness_control as sbc
            sbc.set_brightness(level)
            return {"brightness": level, "ok": True}
        except Exception:
            pass
        # Fallback: WMI (laptops only)
        try:
            import subprocess
            subprocess.check_call(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods)"
                 f".WmiSetBrightness(1,{level})"],
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=5
            )
            return {"brightness": level, "ok": True}
        except Exception as e:
            return {"error": "Brightness control not supported on this display"}
