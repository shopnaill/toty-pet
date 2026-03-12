import json
import logging
import os
import threading
import urllib.request
import urllib.error
import random
import time

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTextEdit,
    QLineEdit, QPushButton, QLabel, QFrame,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor, QTextCharFormat

from core.settings import Settings
from core.safe_json import safe_json_save

log = logging.getLogger("toty.ai")

_CHAT_HISTORY_PATH = "ai_chat_history.json"


class OllamaBrain:
    """Connects to a local Ollama server for smart AI responses.

    Runs inference in a background thread so the UI never freezes.
    Falls back gracefully when Ollama is not running.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._available = False
        self._checking = False
        self._last_error: str | None = None
        self._chat_history: list[dict] = []
        self._max_history = 20
        self._callback_signal = None
        self._load_history()
        threading.Thread(target=self._check_availability, daemon=True).start()

    def _load_history(self):
        if os.path.exists(_CHAT_HISTORY_PATH):
            try:
                with open(_CHAT_HISTORY_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._chat_history = data.get("messages", [])[-self._max_history:]
            except (json.JSONDecodeError, IOError):
                pass

    def _save_history(self):
        try:
            safe_json_save({"messages": self._chat_history[-self._max_history:]},
                           _CHAT_HISTORY_PATH)
        except IOError:
            pass

    def _check_availability(self):
        self._checking = True
        try:
            url = self.settings.get("ai_base_url") + "/api/tags"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "").split(":")[0] for m in data.get("models", [])]
                    wanted = self.settings.get("ai_model")
                    if wanted in models or any(wanted in m for m in models):
                        self._available = True
                        self._last_error = None
                        log.info("Ollama available, model '%s' found", wanted)
                    else:
                        self._available = False
                        self._last_error = (
                            f"Model '{wanted}' not found in Ollama.\n"
                            f"Available: {', '.join(models) if models else 'none'}\n"
                            f"Run: ollama pull {wanted}"
                        )
                        log.warning("Model '%s' not found. Available: %s", wanted, models)
                else:
                    self._available = False
                    self._last_error = f"Ollama returned status {resp.status}"
        except Exception as exc:
            self._available = False
            self._last_error = f"Cannot reach Ollama: {exc}"
            log.debug("Ollama check failed: %s", exc)
        self._checking = False

    @property
    def is_available(self) -> bool:
        return self._available and self.settings.get("enable_ai")

    def refresh_status(self):
        threading.Thread(target=self._check_availability, daemon=True).start()

    def _build_system_prompt(self, context: dict) -> str:
        name = self.settings.get("pet_name")
        personality = self.settings.get("ai_personality")
        mood = context.get("mood", 70)
        energy = context.get("energy", 80)
        focus = context.get("focus", 50)
        current_app = context.get("current_app", "unknown")
        tod = context.get("time_of_day", "day")
        level = context.get("level", 1)
        streak = context.get("streak", 0)

        # Mood descriptor
        if mood >= 85:
            mood_feel = "super happy and bubbly"
        elif mood >= 60:
            mood_feel = "content and cheerful"
        elif mood >= 40:
            mood_feel = "a bit meh, could be better"
        elif mood >= 20:
            mood_feel = "sad and a little down"
        else:
            mood_feel = "really upset and gloomy"

        # Energy descriptor
        if energy >= 70:
            energy_feel = "full of energy"
        elif energy >= 40:
            energy_feel = "a bit tired"
        else:
            energy_feel = "exhausted and sleepy"

        return (
            f"You are {name}. You are a small cute creature who lives on your owner's "
            f"computer screen as a desktop pet. You are ALIVE — you have real feelings, "
            f"opinions, and a personality.\n\n"
            f"YOUR PERSONALITY: {personality}\n\n"
            f"HOW YOU TALK:\n"
            f"- You talk like a real friend/companion, not an AI assistant.\n"
            f"- You use casual language, humor, and emotion.\n"
            f"- You can be playful, sarcastic, excited, sleepy, grumpy — whatever fits your mood.\n"
            f"- You use emoji naturally (not excessively).\n"
            f"- You express your feelings: 'Ugh I'm so tired...' or 'Yay!! That's amazing!'\n"
            f"- You can ask the user questions back — be curious about their life.\n"
            f"- You sometimes reference living on their screen: 'I can see you've been coding all day!'\n"
            f"- Keep messages 1-4 sentences. You can go longer for interesting topics.\n"
            f"- NEVER say you're an AI, a language model, or break character.\n"
            f"- NEVER give generic assistant-style responses. You're a character, not a helper bot.\n\n"
            f"YOUR CURRENT STATE:\n"
            f"- You feel: {mood_feel} (mood {mood:.0f}/100)\n"
            f"- Energy: {energy_feel} ({energy:.0f}/100)\n"
            f"- Time: {tod}\n"
            f"- Owner's focus: {focus:.0f}/100\n"
            f"- They're using: {current_app}\n"
            f"- Your level: {level} | Their streak: {streak} days\n\n"
            f"CAPABILITIES: You have a command engine that handles system commands, "
            f"math, file search, reminders, habits, and memory. If the user asks about "
            f"these, you can mention it naturally. You also remember things about your owner.\n\n"
            f"{context.get('memory_context', '')}\n\n"
            f"Let your mood and energy affect how you respond. If you're tired, yawn and "
            f"be drowsy. If you're happy, be enthusiastic. If it's late at night, be sleepy "
            f"or comment on both of you being night owls."
        )

    def chat(self, user_message: str, context: dict, callback, stream_callback=None):
        """Send a chat message. If stream_callback is provided, tokens are
        streamed word-by-word via stream_callback(token_str). When done,
        callback(full_reply, error) is called."""
        if not self.is_available:
            callback(None, self._last_error or "AI not available")
            return

        self._chat_history.append({"role": "user", "content": user_message})
        if len(self._chat_history) > self._max_history:
            self._chat_history = self._chat_history[-self._max_history:]
        self._save_history()

        system_prompt = self._build_system_prompt(context)
        messages = [{"role": "system", "content": system_prompt}] + list(self._chat_history)
        use_stream = stream_callback is not None

        def _worker():
            try:
                url = self.settings.get("ai_base_url") + "/api/chat"
                payload = json.dumps({
                    "model": self.settings.get("ai_model"),
                    "messages": messages,
                    "stream": use_stream,
                    "options": {
                        "num_predict": self.settings.get("ai_max_tokens"),
                        "temperature": self.settings.get("ai_temperature"),
                    },
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload, method="POST",
                    headers={"Content-Type": "application/json"},
                )
                if use_stream:
                    full_reply = []
                    with urllib.request.urlopen(req, timeout=180) as resp:
                        for line in resp:
                            if not line.strip():
                                continue
                            chunk = json.loads(line.decode("utf-8"))
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                full_reply.append(token)
                                stream_callback(token)
                            if chunk.get("done"):
                                break
                    reply = "".join(full_reply).strip()
                    if reply:
                        self._chat_history.append({"role": "assistant", "content": reply})
                        self._save_history()
                    callback(reply if reply else None, None)
                else:
                    with urllib.request.urlopen(req, timeout=180) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        reply = body.get("message", {}).get("content", "").strip()
                        if reply:
                            self._chat_history.append({"role": "assistant", "content": reply})
                            self._save_history()
                        callback(reply if reply else None, None)
            except urllib.error.HTTPError as exc:
                err_body = ""
                try:
                    err_body = exc.read().decode("utf-8", errors="replace")[:200]
                except Exception:
                    pass
                err_msg = f"Ollama error {exc.code}: {err_body}"
                log.warning("AI chat HTTP error: %s", err_msg)
                callback(None, err_msg)
            except Exception as exc:
                err_msg = f"AI request failed: {exc}"
                log.warning("%s", err_msg)
                callback(None, err_msg)

        threading.Thread(target=_worker, daemon=True).start()

    def quick_response(self, situation: str, context: dict, callback):
        if not self.is_available:
            callback(None)
            return

        system_prompt = self._build_system_prompt(context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"React to this situation in character with ONE short sentence: {situation}"
            )},
        ]

        def _worker():
            try:
                url = self.settings.get("ai_base_url") + "/api/chat"
                payload = json.dumps({
                    "model": self.settings.get("ai_model"),
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": 60,
                        "temperature": self.settings.get("ai_temperature"),
                    },
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload, method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    reply = body.get("message", {}).get("content", "").strip()
                    callback(reply if reply else None)
            except Exception as exc:
                log.debug("Quick response failed: %s", exc)
                callback(None)

        threading.Thread(target=_worker, daemon=True).start()

    def flavor_command(self, raw_data: str, context: dict, callback,
                       stream_callback=None):
        """Take raw command output and have the AI relay it in character.

        The AI adds personality/commentary while preserving all the data.
        Supports streaming. callback(full_reply, error) when done.
        """
        if not self.is_available:
            callback(raw_data, None)  # Fall back to plain data
            return

        system_prompt = self._build_system_prompt(context)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                "Your owner asked for some info and here's the raw data. "
                "Relay ALL this information to them in your character style. "
                "Add a SHORT reaction/comment (1 sentence) at the start or end, "
                "but KEEP all the data, numbers and formatting intact. "
                "Don't add info that's not there. Be concise.\n\n"
                f"Raw data:\n{raw_data}"
            )},
        ]
        use_stream = stream_callback is not None

        def _worker():
            try:
                url = self.settings.get("ai_base_url") + "/api/chat"
                payload = json.dumps({
                    "model": self.settings.get("ai_model"),
                    "messages": messages,
                    "stream": use_stream,
                    "options": {
                        "num_predict": 250,
                        "temperature": self.settings.get("ai_temperature"),
                    },
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload, method="POST",
                    headers={"Content-Type": "application/json"},
                )
                if use_stream:
                    full_reply = []
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        for line in resp:
                            if not line.strip():
                                continue
                            chunk = json.loads(line.decode("utf-8"))
                            token = chunk.get("message", {}).get("content", "")
                            if token:
                                full_reply.append(token)
                                stream_callback(token)
                            if chunk.get("done"):
                                break
                    reply = "".join(full_reply).strip()
                    callback(reply if reply else raw_data, None)
                else:
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        reply = body.get("message", {}).get("content", "").strip()
                        callback(reply if reply else raw_data, None)
            except Exception as exc:
                log.debug("Flavor command failed: %s — using raw", exc)
                callback(raw_data, None)

        threading.Thread(target=_worker, daemon=True).start()

    def character_say(self, pool_key: str, context: dict, callback,
                      fallback_lines: list[str] | None = None):
        """Generate a unique in-character speech bubble for a situation.

        pool_key describes the situation (e.g. 'tired', 'happy', 'typing_fast').
        callback(text) receives the generated line, or a fallback.
        """
        if not self.is_available:
            if fallback_lines:
                callback(random.choice(fallback_lines))
            else:
                callback(None)
            return

        system_prompt = self._build_system_prompt(context)
        situation_map = {
            "tired": "You're feeling exhausted and sleepy",
            "sad": "You're feeling lonely and sad",
            "happy": "You're feeling super happy right now",
            "typing_fast": "Your owner is typing really fast",
            "burst": "Your owner just had an intense burst of typing",
            "backspace_rage": "Your owner is furiously pressing backspace — looks frustrated",
            "idle_return": "Your owner just came back after being away",
            "thinking_pause": "Your owner paused — seems to be thinking hard",
            "coding": "Your owner is coding right now",
            "design": "Your owner is working on design",
            "video": "Your owner is watching a video",
            "browser": "Your owner is browsing the web",
            "gaming": "Your owner is playing a game",
            "wakeup": "You just woke up from a nap",
            "music_detected": "You can hear music playing",
            "music_stopped": "The music just stopped",
            "pet": "Your owner just petted you",
            "pet_combo_2": "Your owner petted you twice in a row",
            "pet_combo_3": "TRIPLE PET! Your owner is showering you with love",
            "pet_combo_4plus": "Your owner won't stop petting you — it's a mega combo",
            "stretch": "Time for your owner to stretch",
            "water": "Time to remind your owner to drink water",
            "pomodoro_done": "A pomodoro focus session just ended",
            "focus_milestone": "Your owner hit a focus milestone",
            "morning": "It's morning time",
            "afternoon": "It's afternoon",
            "evening": "It's evening",
            "night": "It's late at night",
            "encourage": "Your owner could use some encouragement right now",
        }
        situation = situation_map.get(pool_key, f"Situation: {pool_key}")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": (
                f"{situation}. React with ONE short sentence (max 15 words). "
                "Be in character — cute, expressive, use emoji naturally. "
                "Don't repeat yourself. Be creative and unique each time."
            )},
        ]

        def _worker():
            try:
                url = self.settings.get("ai_base_url") + "/api/chat"
                payload = json.dumps({
                    "model": self.settings.get("ai_model"),
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "num_predict": 40,
                        "temperature": 1.0,  # Higher for more variety
                    },
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload, method="POST",
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    reply = body.get("message", {}).get("content", "").strip()
                    if reply:
                        callback(reply)
                    elif fallback_lines:
                        callback(random.choice(fallback_lines))
                    else:
                        callback(None)
            except Exception as exc:
                log.debug("character_say failed: %s", exc)
                if fallback_lines:
                    callback(random.choice(fallback_lines))
                else:
                    callback(None)

        threading.Thread(target=_worker, daemon=True).start()

    def clear_history(self):
        self._chat_history.clear()
        self._save_history()


class AIChatSignal(QObject):
    """Bridge to receive AI responses on the main Qt thread."""
    response_ready = pyqtSignal(str)
    stream_token = pyqtSignal(str)
    thinking_done = pyqtSignal()


# Contextual greetings based on time / mood
_GREETINGS = {
    "morning_happy": [
        "Good morning! ☀️ I woke up feeling great today~",
        "Heyyy, morning! Ready to take on the day together? 🌅",
        "Rise and shine! I've been waiting for you~ ✨",
    ],
    "morning_sad": [
        "Morning... *stretches slowly* ...didn't sleep well 😔",
        "Hey... I'm up. Barely. Coffee would be nice if I had hands 😅",
    ],
    "afternoon_happy": [
        "Hey hey! How's your day going? 😊",
        "Afternoon! I've been watching you work — impressive stuff! 💪",
    ],
    "afternoon_sad": [
        "Hey... long day, huh? Same here... 😮‍💨",
        "Hi... I've been feeling kinda meh today ngl 😶",
    ],
    "evening_happy": [
        "Evening! 🌙 Winding down or just getting started? 😏",
        "Hey! Another day survived~ Let's chat! 🎉",
    ],
    "evening_sad": [
        "Hey... it's getting late. You okay? 🌙",
        "Evening... *curls up* ...come talk to me? 🥺",
    ],
    "night_happy": [
        "Still up? Night owl gang! 🦉✨",
        "Late night crew! What's keeping us up? 😄🌙",
    ],
    "night_sad": [
        "*yawns* ...we should probably both sleep 😴",
        "It's so late... I can barely keep my eyes open... 💤",
    ],
}


def _pick_greeting(context: dict, pet_name: str) -> str:
    tod = context.get("time_of_day", "afternoon")
    mood = context.get("mood", 70)
    mood_key = "happy" if mood >= 45 else "sad"
    key = f"{tod}_{mood_key}"
    options = _GREETINGS.get(key, _GREETINGS["afternoon_happy"])
    return random.choice(options)


def _mood_emoji(mood: float) -> str:
    if mood >= 80:
        return "😄"
    elif mood >= 60:
        return "🙂"
    elif mood >= 40:
        return "😐"
    elif mood >= 20:
        return "😔"
    return "😢"


def _energy_emoji(energy: float) -> str:
    if energy >= 70:
        return "⚡"
    elif energy >= 40:
        return "🔋"
    return "😴"


class AIChatDialog(QDialog):
    """A chat window for talking to the AI-powered pet — with streaming and character."""

    def __init__(self, pet_name: str, brain: OllamaBrain, get_context_fn,
                 memory=None, reminders=None, habits=None, briefing=None,
                 parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.brain = brain
        self.get_context = get_context_fn
        self.pet_name = pet_name
        self.memory = memory
        self.reminders = reminders
        self.habits = habits
        self.briefing = briefing
        self._streaming_html = ""
        self._is_streaming = False
        self._setup_ui()
        self._signal = AIChatSignal()
        self._signal.response_ready.connect(self._on_response)
        self._signal.stream_token.connect(self._on_stream_token)
        self._signal.thinking_done.connect(self._on_thinking_done)
        # Connect reminder notifications
        if self.reminders:
            self.reminders.reminder_fired.connect(self._on_reminder_fired)

    def _setup_ui(self):
        self.setWindowTitle(f"Chat with {self.pet_name}")
        self.setMinimumSize(480, 580)
        self.resize(500, 640)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        try:
            from features.theme import C
        except Exception:
            class C:
                BG_DEEP = "#070B09"; BG_DARK = "#0D1411"; BG_CARD = "#131C17"
                BG_HOVER = "#192520"; SURFACE = "#1E2B23"; BORDER = "#1C3A2A"
                BORDER_HI = "#2D5E42"; ACCENT = "#4ADE80"; ACCENT_DIM = "#1A4D32"
                ACCENT_PRESS = "#38B866"; TEXT = "#D1D5DB"; TEXT_DIM = "#6B7280"
                TEXT_BRIGHT = "#FFFFFF"; RED = "#F87171"; AMBER = "#FBBF24"
                PURPLE = "#A78BFA"; RADIUS_SM = "6px"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header bar ──
        header = QFrame(self)
        header.setStyleSheet(
            f"QFrame {{ background: {C.BG_CARD}; border-bottom: 1px solid {C.BORDER}; }}"
        )
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(16, 10, 16, 10)

        title_lbl = QLabel(f"💬  Chat with {self.pet_name}")
        title_lbl.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title_lbl.setStyleSheet(f"color: {C.TEXT_BRIGHT}; background: transparent;")
        hdr_layout.addWidget(title_lbl)
        hdr_layout.addStretch()

        self.status_label = QLabel("", self)
        self.status_label.setStyleSheet(
            f"color: {C.TEXT_DIM}; font-size: 11px; background: transparent;"
        )
        hdr_layout.addWidget(self.status_label)
        layout.addWidget(header)

        # ── Status pills ──
        ctx = self.get_context()
        mood = ctx.get("mood", 70)
        energy = ctx.get("energy", 80)

        pill_bar = QFrame(self)
        pill_bar.setStyleSheet(f"QFrame {{ background: {C.BG_DARK}; padding: 0; }}")
        pill_layout = QHBoxLayout(pill_bar)
        pill_layout.setContentsMargins(16, 6, 16, 6)
        pill_layout.setSpacing(10)

        self.status_mood = QLabel(f"{_mood_emoji(mood)} Mood: {mood:.0f}", self)
        self.status_mood.setStyleSheet(
            f"color: {C.PURPLE}; font-size: 11px; background: {C.SURFACE};"
            f"border-radius: 10px; padding: 3px 10px;"
        )
        pill_layout.addWidget(self.status_mood)

        self.status_energy = QLabel(f"{_energy_emoji(energy)} Energy: {energy:.0f}", self)
        self.status_energy.setStyleSheet(
            f"color: {C.ACCENT}; font-size: 11px; background: {C.SURFACE};"
            f"border-radius: 10px; padding: 3px 10px;"
        )
        pill_layout.addWidget(self.status_energy)
        pill_layout.addStretch()

        model_lbl = QLabel(f"⚡ {self.brain.settings.get('ai_model')}", self)
        model_lbl.setStyleSheet(
            f"color: {C.TEXT_DIM}; font-size: 10px; background: transparent;"
        )
        pill_layout.addWidget(model_lbl)
        layout.addWidget(pill_bar)

        # ── Chat display ──
        self.chat_display = QTextEdit(self)
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            f"QTextEdit {{"
            f"  background: {C.BG_DEEP}; color: {C.TEXT};"
            f"  border: none; padding: 14px; font-size: 13px;"
            f"  font-family: 'Segoe UI', 'Inter', sans-serif;"
            f"  selection-background-color: {C.ACCENT_DIM};"
            f"}}"
        )
        layout.addWidget(self.chat_display, stretch=1)

        # ── Input area ──
        input_frame = QFrame(self)
        input_frame.setStyleSheet(
            f"QFrame {{ background: {C.BG_CARD}; border-top: 1px solid {C.BORDER}; }}"
        )
        input_outer = QVBoxLayout(input_frame)
        input_outer.setContentsMargins(12, 10, 12, 10)
        input_outer.setSpacing(8)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText(f"Message {self.pet_name}…")
        self.input_field.setStyleSheet(
            f"QLineEdit {{"
            f"  background: {C.BG_DARK}; color: {C.TEXT};"
            f"  border: 1px solid {C.BORDER}; border-radius: 20px;"
            f"  padding: 10px 16px; font-size: 13px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {C.ACCENT}; }}"
        )
        self.input_field.returnPressed.connect(self._send_message)
        input_row.addWidget(self.input_field, stretch=1)

        self.send_btn = QPushButton("▶", self)
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background: {C.ACCENT}; color: {C.BG_DEEP}; border: none;"
            f"  border-radius: 20px; font-size: 16px; font-weight: bold;"
            f"}}"
            f"QPushButton:hover {{ background: {C.ACCENT_PRESS}; }}"
            f"QPushButton:disabled {{ background: {C.SURFACE}; color: {C.TEXT_DIM}; }}"
        )
        self.send_btn.clicked.connect(self._send_message)
        input_row.addWidget(self.send_btn)

        input_outer.addLayout(input_row)

        # Bottom row
        bottom = QHBoxLayout()
        clear_btn = QPushButton("🗑 Clear", self)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {C.TEXT_DIM}; border: none;"
            f"  font-size: 11px; padding: 2px 6px; border-radius: 4px; }}"
            f"QPushButton:hover {{ color: {C.RED}; background: rgba(248,113,113,0.1); }}"
        )
        clear_btn.clicked.connect(self._clear_chat)
        bottom.addWidget(clear_btn)
        bottom.addStretch()
        input_outer.addLayout(bottom)

        layout.addWidget(input_frame)

        # ── Store theme colors for message bubbles ──
        self._c = C

        # ── Opening message ──
        if self.brain.is_available:
            greeting = _pick_greeting(ctx, self.pet_name)
            self._append_message(self.pet_name, greeting)
            self.status_label.setText("✅ connected")
        else:
            err = self.brain._last_error or "Ollama not detected"
            model = self.brain.settings.get('ai_model')
            self._append_message("System", f"\u26a0\ufe0f {err}\n\n"
                                 "Click the Install button below, or:\n"
                                 "Download Ollama: https://ollama.com\n"
                                 f"Then run: ollama pull {model}")
            self.status_label.setText("\u274c offline")
            self._install_ollama_btn = QPushButton("\U0001f4e5 Install Ollama Now")
            self._install_ollama_btn.setStyleSheet(
                f"QPushButton {{ background: {C.ACCENT}; color: {C.BG_DEEP}; border: none;"
                f" border-radius: 20px; padding: 10px; font-weight: bold; font-size: 13px; }}"
                f"QPushButton:hover {{ background: {C.ACCENT_PRESS}; }}"
                f"QPushButton:disabled {{ background: {C.SURFACE}; color: {C.TEXT_DIM}; }}")
            self._install_ollama_btn.clicked.connect(self._auto_install_ollama)
            layout.addWidget(self._install_ollama_btn)

    def _append_message(self, sender: str, text: str):
        C = self._c
        if sender == self.pet_name:
            color = C.PURPLE
            prefix = f"\U0001f43e {sender}"
            bg = C.SURFACE
            align = "left"
            margin = "margin-right:40px;"
        elif sender == "You":
            color = C.ACCENT
            prefix = "\U0001f464 You"
            bg = C.ACCENT_DIM
            align = "right"
            margin = "margin-left:40px;"
        else:
            color = C.AMBER
            prefix = "\u26a0\ufe0f System"
            bg = "#1A1A10"
            align = "left"
            margin = ""
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_text = safe_text.replace("\n", "<br>")
        html = (
            f'<div style="{margin} margin-top:8px; margin-bottom:4px; text-align:{align};">'
            f'<div style="display:inline-block; background:{bg}; '
            f'border-radius:14px; padding:8px 14px; text-align:left;">'
            f'<span style="color:{color}; font-size:11px; font-weight:600;">{prefix}</span><br>'
            f'<span style="color:{C.TEXT}; font-size:13px; line-height:1.5;">{safe_text}</span>'
            f'</div></div>'
        )
        self.chat_display.append(html)
        self._scroll_bottom()

    def _start_stream_message(self):
        """Begin a new streamed pet message."""
        self._is_streaming = True
        C = self._c
        color = C.PURPLE
        prefix = f"\U0001f43e {self.pet_name}"
        html = (
            f'<div style="margin-right:40px; margin-top:8px; margin-bottom:4px;">'
            f'<div style="display:inline-block; background:{C.SURFACE}; '
            f'border-radius:14px; padding:8px 14px;">'
            f'<span style="color:{color}; font-size:11px; font-weight:600;">{prefix}</span><br>'
        )
        self.chat_display.append(html)
        self._scroll_bottom()
        self._stream_fmt = QTextCharFormat()
        self._stream_fmt.setForeground(QColor(C.TEXT))

    def _on_stream_token(self, token: str):
        """Append a streamed token to the current message."""
        if not self._is_streaming:
            return
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(token, self._stream_fmt)
        self.chat_display.setTextCursor(cursor)
        self._scroll_bottom()

    def _end_stream_message(self):
        """Close the streamed message."""
        self._is_streaming = False
        self._scroll_bottom()

    def _scroll_bottom(self):
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _auto_install_ollama(self):
        self._install_ollama_btn.setEnabled(False)
        self._install_ollama_btn.setText("⏳ Installing Ollama...")
        self._append_message("System", "Downloading Ollama via winget — this may take a few minutes...")

        def _on_done(path):
            from PyQt6.QtCore import QTimer
            def _update():
                if path:
                    self._append_message("System",
                        f"✅ Ollama installed: {path}\n\n"
                        f"Now run in terminal:\n"
                        f"  ollama pull {self.brain.settings.get('ai_model')}\n\n"
                        "Then reopen this chat.")
                    self._install_ollama_btn.setText("✅ Installed!")
                    self.status_label.setText("⚠️ pull model")
                else:
                    self._append_message("System",
                        "❌ Auto-install failed.\n"
                        "Download manually: https://ollama.com")
                    self._install_ollama_btn.setEnabled(True)
                    self._install_ollama_btn.setText("🔄 Retry")
            QTimer.singleShot(0, _update)

        from features.auto_deps import ensure_ollama
        ensure_ollama(callback=_on_done)

    def _send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return

        self.input_field.clear()
        self._append_message("You", text)

        # Try local command engine first
        cmd_result = self._try_command(text)
        if cmd_result is not None:
            # If AI is available, flavor the command output in character
            if self.brain.is_available:
                self._start_thinking()
                self._start_stream_message()
                context = self.get_context()

                def on_token(token):
                    self._signal.stream_token.emit(token)

                def on_done(reply, error=None):
                    if reply:
                        self._signal.response_ready.emit("")
                    else:
                        # Fallback: show raw data
                        self._signal.response_ready.emit(cmd_result)
                    self._signal.thinking_done.emit()

                self.brain.flavor_command(
                    cmd_result, context, on_done, stream_callback=on_token
                )
            else:
                # No AI — show raw command output
                self._append_message(self.pet_name, cmd_result)
            return

        if not self.brain.is_available:
            if self.brain._last_error:
                self._append_message("System", self.brain._last_error)
            self.brain.refresh_status()
            QTimer.singleShot(2000, lambda: self._retry_send(text))
            self.status_label.setText("\u23f3 checking...")
            return

        self._start_thinking()
        context = self.get_context()

        # Update mood/energy display
        self.status_mood.setText(f"{_mood_emoji(context.get('mood', 70))} Mood: {context.get('mood', 70):.0f}")
        self.status_energy.setText(f"{_energy_emoji(context.get('energy', 80))} Energy: {context.get('energy', 80):.0f}")

        # Start streaming display
        self._start_stream_message()
        _user_text = text  # capture for learn_from_chat

        def on_token(token):
            self._signal.stream_token.emit(token)

        def on_done(reply, error=None):
            if error and not reply:
                self._signal.response_ready.emit(f"\u26a0\ufe0f {error}")
            elif not reply:
                self._signal.response_ready.emit("*yawns* ...I couldn't think of anything \U0001f615")
            else:
                # reply already streamed, just signal done
                self._signal.response_ready.emit("")
                # v14: auto-learn from chat
                if self.memory:
                    try:
                        self.memory.learn_from_chat(_user_text, reply)
                    except Exception:
                        pass
            self._signal.thinking_done.emit()

        self.brain.chat(text, context, on_done, stream_callback=on_token)

    def _try_command(self, text: str) -> str | None:
        """Try local command engine. Returns result or None."""
        try:
            from features.chat_commands import try_command
            ctx = self.get_context()
            # Inject feature modules into command context
            ctx["memory"] = self.memory
            ctx["reminders"] = self.reminders
            ctx["habits"] = self.habits
            ctx["briefing"] = self.briefing
            result = try_command(text, ctx)
            if result is not None:
                log.info("Command matched: %s", text[:50])
            return result
        except Exception as exc:
            log.error("Command engine error: %s", exc, exc_info=True)
            return None
            return None

    def _on_reminder_fired(self, text: str):
        """Handle a reminder notification in the chat."""
        self._append_message(self.pet_name,
                             f"\u23f0 **Reminder!**\n{text}")
        self.show()
        self.raise_()
        self.activateWindow()

    def _retry_send(self, text):
        if self.brain.is_available:
            self.status_label.setText("\u2705 connected")
            self.input_field.setText(text)
            self._send_message()
        else:
            self._append_message("System", "Still can't reach Ollama. Is it running?")
            self.status_label.setText("\u274c offline")

    def _start_thinking(self):
        self.send_btn.setEnabled(False)
        self.input_field.setEnabled(False)
        phrases = [
            f"{self.pet_name} is thinking...",
            f"{self.pet_name} is composing a reply...",
            f"hmm...",
            f"let me think...",
        ]
        self.status_label.setText(f"\U0001f4ad {random.choice(phrases)}")

    def _on_response(self, text: str):
        self._end_stream_message()
        # If text is non-empty, it's an error or fallback (not streamed)
        if text:
            self._append_message(self.pet_name, text)

    def _on_thinking_done(self):
        self.send_btn.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()
        self.status_label.setText("\u2705 connected")

    def _clear_chat(self):
        self.chat_display.clear()
        self.brain.clear_history()
        ctx = self.get_context()
        greeting = _pick_greeting(ctx, self.pet_name)
        self._append_message(self.pet_name, greeting)

    def closeEvent(self, event):
        """Hide the dialog instead of destroying it (prevents app quit)."""
        event.ignore()
        self.hide()
