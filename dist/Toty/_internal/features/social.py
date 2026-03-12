"""
Social Features — daily challenges, pet evolution, and shareable stats cards.
Tracks challenge completion, evolves the pet visually at level milestones.
"""
import json
import os
import random
from datetime import date, datetime
from core.safe_json import safe_json_save
from PyQt6.QtCore import pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QPainter, QColor, QFont, QPen
from PyQt6.QtCore import Qt

_DATA_PATH = "social_data.json"

# Daily challenges with varying difficulty
CHALLENGE_POOL = [
    # Easy
    {"id": "type_500", "text": "Type 500 keys today", "target": 500, "stat": "total_keys", "xp": 30, "diff": "easy"},
    {"id": "focus_15", "text": "Focus for 15 minutes", "target": 15, "stat": "focus_min", "xp": 30, "diff": "easy"},
    {"id": "pet_3", "text": "Pet Toty 3 times", "target": 3, "stat": "total_pets", "xp": 20, "diff": "easy"},
    # Medium
    {"id": "type_2000", "text": "Type 2000 keys today", "target": 2000, "stat": "total_keys", "xp": 60, "diff": "medium"},
    {"id": "focus_60", "text": "Focus for 60 minutes", "target": 60, "stat": "focus_min", "xp": 60, "diff": "medium"},
    {"id": "pomodoro_2", "text": "Complete 2 Pomodoros", "target": 2, "stat": "pomodoros_today", "xp": 50, "diff": "medium"},
    {"id": "no_distract", "text": "No distraction warnings for 1 hour", "target": 60, "stat": "undistracted_min", "xp": 70, "diff": "medium"},
    # Hard
    {"id": "type_5000", "text": "Type 5000 keys today", "target": 5000, "stat": "total_keys", "xp": 100, "diff": "hard"},
    {"id": "focus_120", "text": "Focus for 2 hours", "target": 120, "stat": "focus_min", "xp": 100, "diff": "hard"},
    {"id": "streak_7", "text": "Maintain a 7-day streak", "target": 7, "stat": "streak", "xp": 150, "diff": "hard"},
]

# Pet evolution stages based on level
EVOLUTION_STAGES = {
    1:  {"name": "Baby Blob", "color": "#7EC8E3", "size_mult": 0.8, "aura": None},
    5:  {"name": "Growing Blob", "color": "#4CA1C7", "size_mult": 0.9, "aura": None},
    10: {"name": "Teen Blob", "color": "#2E86AB", "size_mult": 1.0, "aura": "sparkle"},
    20: {"name": "Adult Blob", "color": "#1B5E7B", "size_mult": 1.0, "aura": "glow"},
    30: {"name": "Elder Blob", "color": "#FFD700", "size_mult": 1.0, "aura": "golden"},
    50: {"name": "Legendary Blob", "color": "#FF6B6B", "size_mult": 1.0, "aura": "rainbow"},
}


class SocialFeatures(QObject):
    """Manages daily challenges, evolution tracking, and stats cards."""
    challenge_completed = pyqtSignal(str, int)  # (challenge_text, xp_reward)
    evolution_unlocked = pyqtSignal(str, int)    # (stage_name, level)

    def __init__(self, stats):
        super().__init__()
        self._stats = stats
        self._data = {
            "today_challenges": [],
            "completed_today": [],
            "challenge_date": "",
            "total_challenges_done": 0,
            "evolution_announced": [],
        }
        self._load()

    def _load(self):
        if os.path.exists(_DATA_PATH):
            try:
                with open(_DATA_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        try:
            safe_json_save(self._data, _DATA_PATH)
        except OSError:
            pass

    def get_daily_challenges(self) -> list[dict]:
        """Get today's 3 challenges (one per difficulty). Generate if new day."""
        today = date.today().isoformat()
        if self._data["challenge_date"] != today:
            # New day — pick challenges
            easy = [c for c in CHALLENGE_POOL if c["diff"] == "easy"]
            medium = [c for c in CHALLENGE_POOL if c["diff"] == "medium"]
            hard = [c for c in CHALLENGE_POOL if c["diff"] == "hard"]
            picks = []
            if easy:
                picks.append(random.choice(easy))
            if medium:
                picks.append(random.choice(medium))
            if hard:
                picks.append(random.choice(hard))
            self._data["today_challenges"] = [c["id"] for c in picks]
            self._data["completed_today"] = []
            self._data["challenge_date"] = today
            self.save()

        # Build rich list
        result = []
        for cid in self._data["today_challenges"]:
            challenge = next((c for c in CHALLENGE_POOL if c["id"] == cid), None)
            if challenge:
                completed = cid in self._data["completed_today"]
                result.append({**challenge, "completed": completed})
        return result

    def check_challenges(self, current_stats: dict) -> list[dict]:
        """Check if any daily challenges are now completed. Returns newly completed."""
        newly_done = []
        challenges = self.get_daily_challenges()
        for ch in challenges:
            if ch["completed"]:
                continue
            stat_val = current_stats.get(ch["stat"], 0)
            if stat_val >= ch["target"]:
                self._data["completed_today"].append(ch["id"])
                self._data["total_challenges_done"] = self._data.get("total_challenges_done", 0) + 1
                newly_done.append(ch)
                self.challenge_completed.emit(ch["text"], ch["xp"])
        if newly_done:
            self.save()
        return newly_done

    def get_evolution_stage(self, level: int) -> dict:
        """Get the evolution stage for a given level."""
        stage = EVOLUTION_STAGES[1]
        for min_level, info in sorted(EVOLUTION_STAGES.items()):
            if level >= min_level:
                stage = info
        return stage

    def check_evolution(self, level: int) -> dict | None:
        """Check if a new evolution stage was just unlocked."""
        announced = self._data.get("evolution_announced", [])
        for min_level, info in sorted(EVOLUTION_STAGES.items()):
            if level >= min_level and min_level not in announced:
                announced.append(min_level)
                self._data["evolution_announced"] = announced
                self.save()
                self.evolution_unlocked.emit(info["name"], min_level)
                return info
        return None

    def generate_stats_card(self, pet_name: str, level: int, stats_data: dict) -> QPixmap:
        """Generate a shareable stats card as a pixmap."""
        w, h = 400, 250
        pm = QPixmap(w, h)
        pm.fill(QColor(25, 25, 35))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background gradient effect
        for i in range(h):
            alpha = int(30 + (i / h) * 40)
            p.setPen(QColor(60, 100, 180, alpha))
            p.drawLine(0, i, w, i)

        # Border
        p.setPen(QPen(QColor(100, 160, 255, 150), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(2, 2, w - 4, h - 4, 12, 12)

        # Title
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        p.drawText(20, 40, f"🐾 {pet_name}")

        # Level & evolution
        stage = self.get_evolution_stage(level)
        p.setFont(QFont("Arial", 12))
        p.setPen(QColor(180, 220, 255))
        p.drawText(20, 65, f"Level {level} — {stage['name']}")

        # Stats
        p.setFont(QFont("Arial", 10))
        p.setPen(QColor(200, 200, 200))
        y = 90
        stat_items = [
            ("🔥 Streak", f"{stats_data.get('streak', 0)} days"),
            ("⌨️ Total Keys", f"{stats_data.get('total_keys', 0):,}"),
            ("🎯 Focus", f"{stats_data.get('daily_focus_min', 0)} min today"),
            ("🏆 Achievements", f"{stats_data.get('achievements_unlocked', 0)}"),
            ("💪 Challenges Done", f"{self._data.get('total_challenges_done', 0)}"),
            ("🐾 Pets", f"{stats_data.get('total_pets', 0):,}"),
        ]
        for label, value in stat_items:
            p.drawText(30, y, f"{label}: {value}")
            y += 22

        # Date
        p.setFont(QFont("Arial", 8))
        p.setPen(QColor(120, 120, 140))
        p.drawText(w - 130, h - 15, datetime.now().strftime("%Y-%m-%d %H:%M"))

        p.end()
        return pm

    def get_challenge_display(self) -> str:
        """Get a formatted string of today's challenges."""
        challenges = self.get_daily_challenges()
        if not challenges:
            return "No challenges today."
        lines = ["🏆 Daily Challenges:"]
        for ch in challenges:
            icon = "✅" if ch["completed"] else "⬜"
            diff_icon = {"easy": "🟢", "medium": "🟡", "hard": "🔴"}.get(ch["diff"], "")
            lines.append(f"  {icon} {diff_icon} {ch['text']} (+{ch['xp']} XP)")
        done = sum(1 for c in challenges if c["completed"])
        lines.append(f"  Progress: {done}/{len(challenges)}")
        return "\n".join(lines)
