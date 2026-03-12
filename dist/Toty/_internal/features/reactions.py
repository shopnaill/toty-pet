"""Advanced dynamic reaction engine for the desktop pet.

Handles: cursor awareness, reaction chains, startled/surprise events,
deep context commentary, emotional memory, idle fidgets, mood contagion,
multi-phase greetings, physical comedy, time pattern learning,
seasonal awareness, dream bubbles, and clipboard/mouse-rage detection.
"""

import json
import logging
import math
import os
import random
import re
from core.safe_json import safe_json_save
import time
from collections import deque
from datetime import date, datetime, timedelta

log = logging.getLogger("toty.reactions")

REACTION_DATA_PATH = "reaction_data.json"

# ── Seasonal / Holiday calendar ──────────────────────────────
_HOLIDAYS = [
    # (month, day, name, greeting)
    (1, 1, "New Year", "Happy New Year! 🎉 New adventures await!"),
    (2, 14, "Valentine's Day", "Happy Valentine's Day! 💕 Love is in the air~"),
    (3, 21, "Mother's Day (ME)", "Happy Mother's Day! 🌹 Go hug your mom!"),
    (10, 31, "Halloween", "Boo! 🎃 Spooky season vibes~"),
    (12, 25, "Christmas", "Merry Christmas! 🎄 Ho ho ho~"),
    (12, 31, "New Year's Eve", "Last day of the year! 🥳 What a journey!"),
]

# Ramadan dates (approximate — shifts yearly, these are sample)
_RAMADAN_GREETINGS = [
    "Ramadan Kareem! 🌙 May this month be blessed",
    "Ramadan Mubarak! ✨ Stay strong during fasting~",
    "Another blessed day of Ramadan 🌙💫",
]

# ── Dream content while sleeping ─────────────────────────────
_DREAM_BUBBLES = [
    "💭 Zzz... *dreams of infinite code*...",
    "💭 *mumbles* ...no bugs... all green tests...",
    "💭 Zzz... *chasing butterflies*... 🦋",
    "💭 *sleep-talks* ...five more minutes...",
    "💭 Zzz... *dreaming of level 100*... ⭐",
    "💭 *mumbles* ...pizza... with extra cheese...",
    "💭 Zzz... *floating in the cloud*... ☁️",
    "💭 *dreaming* ...my owner is the best...",
    "💭 Zzz... *riding a unicorn*... 🦄",
    "💭 *mumbles* ...sudo make me a sandwich...",
    "💭 Zzz... *in a world of candy*... 🍭",
    "💭 *sleep-talks* ...commit... push... merge...",
]

# ── Physical comedy (rare random events) ─────────────────────
_COMEDY_EVENTS = [
    {"text": "*trips over nothing* ...I meant to do that! 😅", "state": "stretch", "chance": 0.02},
    {"text": "*tries to dance, falls over* ...gravity is mean! 💫", "state": "yawn", "chance": 0.015},
    {"text": "*sneezes* ACHOO! ...excuse me 🤧", "state": "stretch", "chance": 0.02},
    {"text": "*hiccup* ...hic! ...hic! ...where did that come from? 😳", "state": "idle", "chance": 0.015},
    {"text": "*walks into screen edge* OW! That wasn't there before! 😤", "state": "idle", "chance": 0.01},
    {"text": "*yawns so big it gets stuck* ...help... 😮", "state": "yawn", "chance": 0.01},
    {"text": "*tries to look cool, slips* ...nobody saw that right? 😎", "state": "idle", "chance": 0.015},
]

# ── Deep window title commentary ─────────────────────────────
_WINDOW_COMMENTS = [
    # (pattern_in_title, comments_list)
    (r"stack\s*overflow", [
        "Stack Overflow? Debugging time! 🐛",
        "Ah, the programmer's best friend~",
        "Copy-paste responsibly! 😏",
    ]),
    (r"github.*pull|pull.*request", [
        "PR review? May the merge be clean! 🙏",
        "Code review mode activated! 👀",
        "Hope there are no merge conflicts~ 🤞",
    ]),
    (r"github", [
        "GitHub! Building something cool? 🚀",
        "Open source hero! 💪",
    ]),
    (r"chatgpt|openai|claude|copilot", [
        "Talking to another AI? I'm not jealous... 😤",
        "Am I not enough for you?! 😢 ...jk jk~",
        "Getting AI help? Smart move! 🧠",
    ]),
    (r"stackoverflow|reddit.*programming", [
        "Research mode! Knowledge is power~ 📚",
    ]),
    (r"youtube.*tutorial|learn|course", [
        "Learning something new? I'm proud of you! 📖✨",
        "Tutorial time! Absorb that knowledge~",
    ]),
    (r"youtube.*music|spotify|soundcloud", [
        "Good taste in music! 🎵",
    ]),
    (r"youtube", [
        "YouTube break? Don't fall into the rabbit hole! 🐰",
        "One more video... right? 😏",
    ]),
    (r"twitter|x\.com", [
        "Scrolling Twitter? Set a timer! ⏰",
        "Social media break — don't get sucked in~",
    ]),
    (r"instagram|tiktok", [
        "Social media time! Just a quick peek, right? 👀",
        "Careful, that's a time vortex! ⏳",
    ]),
    (r"notion|obsidian|onenote", [
        "Taking notes? Organized human! 📝✨",
        "Knowledge management! You're adulting~",
    ]),
    (r"slack|teams|zoom|meet", [
        "Meeting time? Good luck! 🤝",
        "Hope it's a productive meeting~",
        "This could've been an email 😏",
    ]),
    (r"netflix|disney|hulu|prime\s*video", [
        "Movie time! 🍿 What are we watching?",
        "Entertainment break detected! Enjoy~",
    ]),
    (r"amazon|shopping|buy|cart", [
        "Online shopping? 🛒 Don't overspend!",
        "Wallet is trembling right now... 💸",
    ]),
    (r"gmail|outlook|mail", [
        "Checking mail? Hope it's good news! 📧",
        "Email time — inbox zero is a myth 😅",
    ]),
    (r"word|docs.*google|document", [
        "Writing time! ✍️ The words will flow~",
    ]),
    (r"excel|sheets|spreadsheet", [
        "Spreadsheets! The real endgame boss 📊",
    ]),
    (r"photoshop|gimp|canva", [
        "Art mode! Make something beautiful! 🎨",
    ]),
    (r"terminal|powershell|cmd", [
        "Terminal! The power user zone ⚡",
        "Command line vibes~",
    ]),
]


class ReactionEngine:
    """Central engine for advanced, dynamic pet reactions."""

    def __init__(self, settings, mood_engine, stats, pet_memory=None):
        self.settings = settings
        self.mood = mood_engine
        self.stats = stats
        self.memory = pet_memory

        # Cursor tracking
        self._last_cursor_x = 0
        self._last_cursor_y = 0
        self._cursor_speed_history = deque(maxlen=20)
        self._last_cursor_check = 0.0

        # Reaction chains
        self._active_chains: dict[str, dict] = {}  # chain_id -> {stage, start_time, last_fire}
        self._chain_cooldown: dict[str, float] = {}

        # Startled system
        self._last_app_switch_time = 0.0
        self._rapid_switch_count = 0
        self._last_startled_time = 0.0

        # Context commentary
        self._last_window_comment_time = 0.0
        self._last_commented_pattern = ""

        # Idle fidgets
        self._last_fidget_time = time.time()
        self._fidget_interval = random.uniform(8, 20)

        # Mood contagion (staged petting)
        self._pet_session_count = 0
        self._pet_session_start = 0.0

        # Multi-phase greeting state
        self._greeting_phase = 0
        self._greeting_done = False

        # Physical comedy
        self._last_comedy_time = 0.0

        # Time patterns
        self._session_log: list[dict] = []  # {date, start_hour, end_hour, focus_min}

        # Dream state
        self._last_dream_time = 0.0

        # Clipboard monitoring
        self._last_clipboard = ""
        self._clipboard_count = 0
        self._clipboard_time = 0.0

        # Mouse rage
        self._click_times = deque(maxlen=20)

        # Emotional memory (bounded to ~1 day at 2-min intervals)
        self._daily_mood_log: deque[tuple[str, float]] = deque(maxlen=720)

        # Holiday check
        self._holiday_greeted_today = False

        # Persistent data
        self.data: dict = {
            "time_patterns": {},    # day_of_week -> {avg_start, avg_end}
            "mood_patterns": {},    # hour -> avg_mood
            "session_history": [],  # last 30 sessions
            "holiday_last": "",
        }
        self._load()

    def _load(self):
        if os.path.exists(REACTION_DATA_PATH):
            try:
                with open(REACTION_DATA_PATH, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        safe_json_save(self.data, REACTION_DATA_PATH)

    # ──────────────────────────────────────────────────────────
    #  1. CURSOR AWARENESS
    # ──────────────────────────────────────────────────────────
    def track_cursor(self, cx: int, cy: int, pet_x: int, pet_y: int) -> dict | None:
        """Call every ~100ms. Returns reaction dict or None.

        Returns: {type: 'look_left'|'look_right'|'startled_cursor'|'curious'|None}
        """
        now = time.time()
        dt = now - self._last_cursor_check
        if dt < 0.08:
            return None
        self._last_cursor_check = now

        # Calculate cursor speed
        dx = cx - self._last_cursor_x
        dy = cy - self._last_cursor_y
        speed = math.hypot(dx, dy) / max(dt, 0.01)
        self._cursor_speed_history.append(speed)
        self._last_cursor_x = cx
        self._last_cursor_y = cy

        result = {}

        # Direction the pet should look
        if cx < pet_x:
            result["look_direction"] = "left"
        else:
            result["look_direction"] = "right"

        # Distance from pet
        dist = math.hypot(cx - pet_x, cy - pet_y)
        result["cursor_distance"] = dist

        # Startled by fast cursor zoom-by
        if speed > 3000 and dist < 300 and (now - self._last_startled_time > 10):
            self._last_startled_time = now
            result["type"] = "startled_cursor"
            return result

        # Curious when cursor lingers near pet
        if dist < 80 and speed < 50:
            result["type"] = "curious"
            return result

        result["type"] = None
        return result

    # ──────────────────────────────────────────────────────────
    #  2. REACTION CHAINS
    # ──────────────────────────────────────────────────────────
    def start_chain(self, chain_id: str):
        """Start a reaction chain (e.g. 'coding_session', 'gaming_session')."""
        if chain_id in self._active_chains:
            return
        self._active_chains[chain_id] = {
            "stage": 0,
            "start_time": time.time(),
            "last_fire": time.time(),
        }

    def stop_chain(self, chain_id: str):
        if chain_id in self._active_chains:
            del self._active_chains[chain_id]

    def tick_chains(self) -> list[str]:
        """Call periodically. Returns list of messages for chains that advanced."""
        messages = []
        now = time.time()
        for cid, chain in list(self._active_chains.items()):
            elapsed_min = (now - chain["start_time"]) / 60
            since_last = (now - chain["last_fire"]) / 60
            stage = chain["stage"]

            msg = self._check_chain_stage(cid, stage, elapsed_min, since_last)
            if msg:
                chain["stage"] += 1
                chain["last_fire"] = now
                messages.append(msg)
        return messages

    def _check_chain_stage(self, cid: str, stage: int,
                           elapsed_min: float, since_last: float) -> str | None:
        chains = {
            "coding_session": [
                (10, "You've been coding for 10 min — nice flow! 💻"),
                (30, "30 min of coding! You're in the zone 🔥"),
                (60, "1 HOUR of coding! You're a machine! 🤖💪"),
                (120, "2 HOURS?! Take a break, legend! 👑"),
            ],
            "gaming_session": [
                (15, "15 min of gaming — having fun? 🎮"),
                (45, "Almost an hour of gaming... don't forget your tasks! 😅"),
                (90, "That's a lot of gaming! Your tasks are getting jealous~ 📋"),
            ],
            "video_session": [
                (10, "10 min of videos — just one more right? 📺"),
                (30, "Half hour of videos! Rabbit hole alert! 🐰"),
                (60, "An hour of videos... I'm getting concerned 😅"),
            ],
            "browser_session": [
                (20, "20 min browsing — find anything interesting? 🔍"),
                (60, "An hour of browsing! That's dedication~ 🌐"),
            ],
            "late_night": [
                (30, "It's late... you sure you don't wanna sleep? 🌙"),
                (60, "Still up after an hour? Night owl energy~ 🦉"),
                (120, "2 hours past bedtime?! We're both rebels 😈"),
            ],
            "design_session": [
                (15, "Design is looking great so far! 🎨"),
                (45, "45 min of design — pixel perfection takes time~"),
                (90, "1.5 hours designing! Artist mode! 🖌️✨"),
            ],
        }
        stages = chains.get(cid, [])
        if stage >= len(stages):
            return None
        threshold_min, msg = stages[stage]
        if elapsed_min >= threshold_min and since_last >= 5:
            return msg
        return None

    # ──────────────────────────────────────────────────────────
    #  3. STARTLED / SURPRISE REACTIONS
    # ──────────────────────────────────────────────────────────
    def on_app_switch(self) -> str | None:
        """Track rapid app switching for startled reactions."""
        now = time.time()
        if now - self._last_app_switch_time < 2.0:
            self._rapid_switch_count += 1
        else:
            self._rapid_switch_count = 0
        self._last_app_switch_time = now

        if self._rapid_switch_count >= 5 and (now - self._last_startled_time > 30):
            self._last_startled_time = now
            self._rapid_switch_count = 0
            return random.choice([
                "Whoa! So many apps! You okay?! 😵‍💫",
                "App switching speedrun?! Slow down! 🌪️",
                "*gets dizzy from all the switching* 💫",
            ])
        return None

    def on_battery_low(self, percent: int) -> str | None:
        """React to low battery."""
        if percent <= 5:
            return "BATTERY CRITICAL!! 🔴🔴 PLUG IN NOW!! ⚡"
        if percent <= 10:
            return random.choice([
                f"Battery at {percent}%!! 😱 We're gonna die!",
                f"⚠️ {percent}% battery! This is an emergency!",
            ])
        if percent <= 20:
            return f"🔋 {percent}% battery... getting nervous... 😰"
        return None

    def on_notification(self, title: str = "") -> str | None:
        """React to an incoming notification."""
        if random.random() < 0.3:
            reactions = [
                "*jumps* What was that?! 🔔",
                "Ooh, a notification! Something exciting? ✨",
                "Ding! Someone needs you~ 📱",
            ]
            if title:
                t = title[:30]
                reactions.append(f"*peeks* ...is that from {t}? 👀")
            return random.choice(reactions)
        return None

    # ──────────────────────────────────────────────────────────
    #  4. DEEP CONTEXT COMMENTARY (window title parsing)
    # ──────────────────────────────────────────────────────────
    def get_window_comment(self, title: str) -> str | None:
        """Check window title for deep contextual commentary."""
        now = time.time()
        if now - self._last_window_comment_time < 120:  # 2 min cooldown
            return None

        title_lower = title.lower()
        for pattern, comments in _WINDOW_COMMENTS:
            if re.search(pattern, title_lower):
                if pattern == self._last_commented_pattern:
                    continue  # Don't repeat same pattern
                self._last_commented_pattern = pattern
                self._last_window_comment_time = now
                return random.choice(comments)
        return None

    # ──────────────────────────────────────────────────────────
    #  5. EMOTIONAL MEMORY & PATTERNS
    # ──────────────────────────────────────────────────────────
    def log_mood_snapshot(self):
        """Call every few minutes to track mood over time."""
        now = datetime.now()
        hour = now.hour
        mood_val = self.mood.mood

        # Track hourly mood pattern
        patterns = self.data.setdefault("mood_patterns", {})
        key = str(hour)
        if key in patterns:
            # Running average
            patterns[key] = patterns[key] * 0.8 + mood_val * 0.2
        else:
            patterns[key] = mood_val

        self._daily_mood_log.append((now.strftime("%H:%M"), mood_val))

    def get_mood_insight(self) -> str | None:
        """Get an insight about mood patterns."""
        patterns = self.data.get("mood_patterns", {})
        if len(patterns) < 5:
            return None

        # Find lowest mood hour
        worst_hour = min(patterns, key=lambda h: patterns[h])
        worst_val = patterns[worst_hour]
        if worst_val < 40:
            return (f"I've noticed you tend to feel low around {worst_hour}:00... "
                    f"maybe take a break then? 💛")

        # Find best hour
        best_hour = max(patterns, key=lambda h: patterns[h])
        return f"Your happiest time is usually around {best_hour}:00! ✨"

    def log_session_start(self):
        """Record when a session starts for time pattern learning."""
        now = datetime.now()
        day = now.strftime("%A")
        hour = now.hour

        # Update day-of-week patterns
        patterns = self.data.setdefault("time_patterns", {})
        day_data = patterns.setdefault(day, {"starts": [], "count": 0})
        day_data["starts"].append(hour)
        day_data["starts"] = day_data["starts"][-20:]  # Keep last 20
        day_data["count"] += 1
        self.save()

    def get_time_pattern_comment(self) -> str | None:
        """Comment on whether user is early/late compared to their pattern."""
        now = datetime.now()
        day = now.strftime("%A")
        hour = now.hour

        patterns = self.data.get("time_patterns", {})
        day_data = patterns.get(day)
        if not day_data or day_data.get("count", 0) < 3:
            return None

        starts = day_data.get("starts", [])
        if not starts:
            return None

        avg_start = sum(starts) / len(starts)
        diff = hour - avg_start

        if diff < -1.5:
            return random.choice([
                f"Early bird today! 🐦 You usually start around {int(avg_start)}:00 on {day}s",
                f"Up early! This is {abs(diff):.0f}h ahead of your usual {day} schedule~",
            ])
        if diff > 2:
            return random.choice([
                f"Running late today? You usually start around {int(avg_start)}:00 on {day}s 😏",
                f"A late start, huh? That's okay, we all need rest~",
            ])
        return None

    # ──────────────────────────────────────────────────────────
    #  6. IDLE FIDGETS & MICRO-EXPRESSIONS
    # ──────────────────────────────────────────────────────────
    def get_idle_fidget(self) -> str | None:
        """Returns a fidget action name if it's time. Call during brain tick."""
        now = time.time()
        if now - self._last_fidget_time < self._fidget_interval:
            return None

        self._last_fidget_time = now
        self._fidget_interval = random.uniform(8, 25)

        mood = self.mood.mood
        energy = self.mood.energy

        # Higher energy = more active fidgets
        if energy > 70:
            fidgets = ["blink", "look_around", "tail_wag", "bounce"]
        elif energy > 40:
            fidgets = ["blink", "look_around", "sigh", "shift"]
        else:
            fidgets = ["blink", "slow_blink", "droop", "yawn_small"]

        # Mood affects fidget character
        if mood < 30:
            fidgets.extend(["sigh", "droop"])
        elif mood > 80:
            fidgets.extend(["bounce", "tail_wag"])

        return random.choice(fidgets)

    # ──────────────────────────────────────────────────────────
    #  7. MOOD CONTAGION & STAGED PETTING
    # ──────────────────────────────────────────────────────────
    def on_pet_interaction(self, current_mood: float) -> dict:
        """Track petting sessions for staged mood contagion.

        Returns {mood_boost, reaction_text, stage}
        """
        now = time.time()
        if now - self._pet_session_start > 10:
            # New petting session
            self._pet_session_count = 0
            self._pet_session_start = now

        self._pet_session_count += 1
        count = self._pet_session_count

        if current_mood < 30:
            # Sad → gradually cheering up
            stages = [
                {"mood_boost": 5, "reaction_text": "*sniffles* ...thanks... 🥺", "stage": "sad"},
                {"mood_boost": 10, "reaction_text": "That... actually helps... *small smile* 😢→😊", "stage": "warming"},
                {"mood_boost": 15, "reaction_text": "I'm feeling a little better... thank you 💛", "stage": "recovering"},
                {"mood_boost": 20, "reaction_text": "You healed me with pets!! 😄✨ I love you!", "stage": "healed"},
            ]
        elif current_mood < 60:
            stages = [
                {"mood_boost": 8, "reaction_text": "Aww~ that's nice! 😊", "stage": "content"},
                {"mood_boost": 12, "reaction_text": "More more more! 🥰", "stage": "happy"},
                {"mood_boost": 18, "reaction_text": "I'm SO happy right now!! 💖✨", "stage": "ecstatic"},
            ]
        else:
            stages = [
                {"mood_boost": 5, "reaction_text": "Hehe! Thank you! 😊", "stage": "happy"},
                {"mood_boost": 10, "reaction_text": "You really love me don't you~ 🥰", "stage": "loved"},
                {"mood_boost": 15, "reaction_text": "MAXIMUM HAPPINESS!! 💖✨🎉", "stage": "maximum"},
            ]

        idx = min(count - 1, len(stages) - 1)
        return stages[idx]

    # ──────────────────────────────────────────────────────────
    #  8. MULTI-PHASE GREETINGS
    # ──────────────────────────────────────────────────────────
    def get_greeting_phase(self, phase: int) -> str | None:
        """Returns the next greeting phase message. Call with incrementing phase."""
        now = datetime.now()
        tod = self.mood.get_time_of_day_label()
        streak = self.stats.data.get("current_streak", 0)
        level = self.stats.data.get("level", 1)

        phases = []
        # Phase 0: Time-aware hello
        if tod == "morning":
            phases.append("Good morning! ☀️ Ready for a new day?")
        elif tod == "afternoon":
            phases.append("Good afternoon! 🌤️ Let's be productive~")
        elif tod == "evening":
            phases.append("Good evening! 🌅 Winding down or powering through?")
        else:
            phases.append("Hey night owl! 🌙 Can't sleep either?")

        # Phase 1: Reference yesterday / streak
        if streak > 1:
            phases.append(f"That's a {streak}-day streak! 🔥 Keep it up!")
        else:
            phases.append("Let's build a great day together! 💪")

        # Phase 2: Time pattern comment or level
        time_comment = self.get_time_pattern_comment()
        if time_comment:
            phases.append(time_comment)
        else:
            phases.append(f"You're Level {level} — let's earn some XP today! ⭐")

        # Phase 3: Seasonal / holiday check
        holiday_msg = self._check_holiday()
        if holiday_msg:
            phases.append(holiday_msg)

        # Phase 4: Mood insight (if enough data)
        insight = self.get_mood_insight()
        if insight:
            phases.append(insight)

        if phase < len(phases):
            return phases[phase]
        return None

    # ──────────────────────────────────────────────────────────
    #  9. PHYSICAL COMEDY
    # ──────────────────────────────────────────────────────────
    def try_comedy_event(self) -> dict | None:
        """Occasionally trigger a funny event. Call during brain tick.
        Returns {text, state} or None."""
        now = time.time()
        if now - self._last_comedy_time < 300:  # 5 min cooldown
            return None

        for event in _COMEDY_EVENTS:
            if random.random() < event["chance"]:
                self._last_comedy_time = now
                return {"text": event["text"], "state": event["state"]}
        return None

    # ──────────────────────────────────────────────────────────
    # 10. TIME PATTERN LEARNING
    # ──────────────────────────────────────────────────────────
    def record_session_end(self, focus_min: int):
        """Record session end for pattern learning."""
        now = datetime.now()
        session = {
            "date": now.isoformat(timespec="minutes"),
            "day": now.strftime("%A"),
            "start_hour": (now - timedelta(minutes=focus_min)).hour if focus_min else now.hour,
            "end_hour": now.hour,
            "focus_min": focus_min,
        }
        history = self.data.setdefault("session_history", [])
        history.append(session)
        self.data["session_history"] = history[-30:]  # Keep last 30

        # Track end times too
        day = now.strftime("%A")
        patterns = self.data.setdefault("time_patterns", {})
        day_data = patterns.setdefault(day, {"starts": [], "count": 0})
        day_data.setdefault("ends", []).append(now.hour)
        day_data["ends"] = day_data["ends"][-20:]
        self.save()

    # ──────────────────────────────────────────────────────────
    # 11. SEASONAL / HOLIDAY AWARENESS
    # ──────────────────────────────────────────────────────────
    def _check_holiday(self) -> str | None:
        """Check if today is a special day."""
        today = date.today()
        today_key = today.isoformat()
        if self.data.get("holiday_last") == today_key:
            return None

        for month, day, name, greeting in _HOLIDAYS:
            if today.month == month and today.day == day:
                self.data["holiday_last"] = today_key
                self.save()
                return greeting

        return None

    def check_seasonal_greeting(self) -> str | None:
        """Get a seasonal greeting if applicable."""
        return self._check_holiday()

    # ──────────────────────────────────────────────────────────
    # 12. DREAM BUBBLES (while sleeping)
    # ──────────────────────────────────────────────────────────
    def get_dream_bubble(self) -> str | None:
        """Returns a dream bubble message if pet is sleeping."""
        now = time.time()
        if now - self._last_dream_time < 15:  # Every 15s while sleeping
            return None
        self._last_dream_time = now

        # Include memory-based dreams
        if self.memory and random.random() < 0.3:
            facts = self.memory.data.get("facts", [])
            if facts:
                fact = random.choice(facts[-10:])
                return f"💭 Zzz... *dreams about {fact['text'][:30]}*..."

        return random.choice(_DREAM_BUBBLES)

    # ──────────────────────────────────────────────────────────
    # 13. CLIPBOARD & MOUSE RAGE
    # ──────────────────────────────────────────────────────────
    def on_clipboard_activity(self) -> str | None:
        """Track clipboard usage. Call when copy event detected."""
        now = time.time()
        if now - self._clipboard_time > 30:
            self._clipboard_count = 0
        self._clipboard_time = now
        self._clipboard_count += 1

        if self._clipboard_count == 5:
            return "That's a lot of copy-pasting! Working on something big? 📋"
        if self._clipboard_count == 10:
            return "Copy-paste marathon! 😅 Hope it's not from Stack Overflow... 😏"
        return None

    def on_rapid_clicks(self, x: int, y: int) -> str | None:
        """Track rapid clicking for rage detection."""
        now = time.time()
        self._click_times.append(now)

        # Count clicks in last 3 seconds
        recent = [t for t in self._click_times if now - t < 3]
        if len(recent) >= 8 and (now - self._last_startled_time > 30):
            self._last_startled_time = now
            return random.choice([
                "Whoa! Easy on the clicks! 😰💥",
                "*hides* ...are you angry at something? 😨",
                "Click rage detected! Take a deep breath~ 🧘",
                "That mouse didn't do anything wrong! 🐭",
            ])
        return None

    # ──────────────────────────────────────────────────────────
    # COMPOSITE TICK (call from main timer)
    # ──────────────────────────────────────────────────────────
    def tick(self) -> list[dict]:
        """Main tick — returns list of {type, text, state?, ...} events."""
        events = []

        # Reaction chain progression
        chain_msgs = self.tick_chains()
        for msg in chain_msgs:
            events.append({"type": "chain", "text": msg})

        return events
