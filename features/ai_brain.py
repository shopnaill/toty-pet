import json
import logging
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

log = logging.getLogger("toty.ai")


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
        threading.Thread(target=self._check_availability, daemon=True).start()

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
                    with urllib.request.urlopen(req, timeout=60) as resp:
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
                    callback(reply if reply else None, None)
                else:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        reply = body.get("message", {}).get("content", "").strip()
                        if reply:
                            self._chat_history.append({"role": "assistant", "content": reply})
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
                with urllib.request.urlopen(req, timeout=15) as resp:
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
                    with urllib.request.urlopen(req, timeout=30) as resp:
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
                    with urllib.request.urlopen(req, timeout=30) as resp:
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
                with urllib.request.urlopen(req, timeout=10) as resp:
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
        self.setMinimumSize(450, 550)
        self.resize(460, 580)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        # Top bar: pet status
        top_bar = QFrame(self)
        top_bar.setStyleSheet(
            "QFrame { background: #181825; border-radius: 8px; padding: 4px; }"
        )
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(10, 4, 10, 4)

        ctx = self.get_context()
        mood = ctx.get("mood", 70)
        energy = ctx.get("energy", 80)

        self.status_mood = QLabel(f"{_mood_emoji(mood)} Mood: {mood:.0f}", self)
        self.status_mood.setStyleSheet("color: #CBA6F7; font-size: 11px; background: transparent;")
        top_layout.addWidget(self.status_mood)

        self.status_energy = QLabel(f"{_energy_emoji(energy)} Energy: {energy:.0f}", self)
        self.status_energy.setStyleSheet("color: #A6E3A1; font-size: 11px; background: transparent;")
        top_layout.addWidget(self.status_energy)

        top_layout.addStretch()

        self.status_label = QLabel("", self)
        self.status_label.setStyleSheet("color: #A6ADC8; font-size: 11px; background: transparent;")
        top_layout.addWidget(self.status_label)

        layout.addWidget(top_bar)

        # Chat display
        self.chat_display = QTextEdit(self)
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            "QTextEdit {"
            "  background: #1E1E2E; color: #CDD6F4; border: 1px solid #45475A;"
            "  border-radius: 8px; padding: 10px; font-size: 13px;"
            "  font-family: 'Segoe UI', sans-serif;"
            "  selection-background-color: #45475A;"
            "}"
        )
        layout.addWidget(self.chat_display, stretch=1)

        # Input area
        input_layout = QHBoxLayout()
        input_layout.setSpacing(6)
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Say something to " + self.pet_name + "...")
        self.input_field.setStyleSheet(
            "QLineEdit {"
            "  background: #313244; color: #CDD6F4; border: 1px solid #45475A;"
            "  border-radius: 8px; padding: 10px; font-size: 13px;"
            "}"
            "QLineEdit:focus { border-color: #89B4FA; }"
        )
        self.input_field.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_field, stretch=1)

        self.send_btn = QPushButton("Send", self)
        self.send_btn.setStyleSheet(
            "QPushButton {"
            "  background: #89B4FA; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 10px 20px; font-weight: bold; font-size: 13px;"
            "}"
            "QPushButton:hover { background: #74C7EC; }"
            "QPushButton:disabled { background: #585B70; color: #A6ADC8; }"
        )
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        layout.addLayout(input_layout)

        # Bottom row
        bottom = QHBoxLayout()
        clear_btn = QPushButton("Clear Chat", self)
        clear_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #A6ADC8; border: none;"
            "  font-size: 11px; padding: 4px; }"
            "QPushButton:hover { color: #F38BA8; }"
        )
        clear_btn.clicked.connect(self._clear_chat)
        bottom.addWidget(clear_btn)
        bottom.addStretch()

        model_lbl = QLabel(f"model: {self.brain.settings.get('ai_model')}", self)
        model_lbl.setStyleSheet("color: #585B70; font-size: 10px;")
        bottom.addWidget(model_lbl)
        layout.addLayout(bottom)

        self.setStyleSheet("QDialog { background: #1E1E2E; }")

        # Opening message
        if self.brain.is_available:
            greeting = _pick_greeting(ctx, self.pet_name)
            self._append_message(self.pet_name, greeting)
            self.status_label.setText("\u2705 connected")
        else:
            err = self.brain._last_error or "Ollama not detected"
            model = self.brain.settings.get('ai_model')
            self._append_message("System", f"\u26a0\ufe0f {err}\n\n"
                                 "Download Ollama: https://ollama.com\n"
                                 f"Then run: ollama pull {model}")
            self.status_label.setText("\u274c offline")

    def _append_message(self, sender: str, text: str):
        if sender == self.pet_name:
            color = "#CBA6F7"
            prefix = f"\U0001f43e {sender}"
        elif sender == "You":
            color = "#A6E3A1"
            prefix = "\U0001f464 You"
        else:
            color = "#F9E2AF"
            prefix = "\u26a0\ufe0f System"
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_text = safe_text.replace("\n", "<br>")
        html = (
            f'<div style="margin:6px 0; padding:4px 0;">'
            f'<b style="color:{color}; font-size:12px;">{prefix}</b><br>'
            f'<span style="color:#CDD6F4; line-height:1.4;">{safe_text}</span>'
            f'</div>'
        )
        self.chat_display.append(html)
        self._scroll_bottom()

    def _start_stream_message(self):
        """Begin a new streamed pet message."""
        self._is_streaming = True
        color = "#CBA6F7"
        prefix = f"\U0001f43e {self.pet_name}"
        html = (
            f'<div style="margin:6px 0; padding:4px 0;">'
            f'<b style="color:{color}; font-size:12px;">{prefix}</b><br>'
        )
        self.chat_display.append(html)
        self._scroll_bottom()
        # Prepare a text format for streamed tokens
        self._stream_fmt = QTextCharFormat()
        self._stream_fmt.setForeground(QColor("#CDD6F4"))

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
