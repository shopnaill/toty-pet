"""Daily briefing and proactive suggestions for the desktop pet.

Aggregates information from todos, habits, reminders, memory, and stats
to provide morning briefings and smart suggestions.
"""

import logging
import os
import random
from datetime import datetime

log = logging.getLogger("toty.briefing")


class DailyBriefing:
    """Generates daily briefings and proactive context-aware suggestions."""

    def __init__(self, stats=None, habits=None, reminders=None, memory=None):
        self.stats = stats
        self.habits = habits
        self.reminders = reminders
        self.memory = memory

    def morning_briefing(self) -> str:
        """Generate a comprehensive morning briefing."""
        now = datetime.now()
        day_name = now.strftime("%A")
        date_str = now.strftime("%B %d, %Y")
        hour = now.hour

        lines = [f"\u2600\ufe0f Good {'morning' if hour < 12 else 'afternoon' if hour < 17 else 'evening'}! "
                 f"Here's your briefing for {day_name}, {date_str}:\n"]

        # Streak & Level
        if self.stats:
            streak = self.stats.data.get("current_streak", 0)
            level = self.stats.data.get("level", 1)
            lines.append(f"\U0001f525 Streak: {streak} days  |  \u2b50 Level: {level}")
            lines.append(f"\U0001f4ca {self.stats.get_level_info()}")

        # Todos
        if self.stats:
            todos = self.stats.get_todos()
            pending = [t for t in todos if not t.get("done")]
            done = [t for t in todos if t.get("done")]
            if pending:
                lines.append(f"\n\U0001f4cb Tasks ({len(pending)} pending, {len(done)} done):")
                for i, t in enumerate(pending[:5]):
                    lines.append(f"  \u2b1c {t['text']}")
                if len(pending) > 5:
                    lines.append(f"  ... and {len(pending) - 5} more")
            else:
                lines.append("\n\u2705 No pending tasks!")

        # Habits
        if self.habits:
            habits = self.habits.data.get("habits", {})
            if habits:
                today_log = self.habits.data.get("log", {}).get(
                    self.habits._today(), {}
                )
                tracked = len(habits)
                done_count = sum(
                    1 for k, info in habits.items()
                    if today_log.get(k, 0) >= info.get("goal", 1)
                )
                lines.append(f"\n\U0001f3af Habits: {done_count}/{tracked} completed today")

        # Reminders
        if self.reminders:
            active = [r for r in self.reminders._reminders if not r.get("fired")]
            if active:
                lines.append(f"\n\u23f0 {len(active)} active reminder(s)")

        # Focus stats
        if self.stats:
            focus = self.stats.data.get("daily_focus_min", 0)
            if focus > 0:
                lines.append(f"\n\U0001f3af Focus today: {focus} min")

        return "\n".join(lines)

    def end_of_day_summary(self) -> str:
        """Generate an end-of-day summary."""
        lines = ["\U0001f319 End of Day Summary:\n"]

        if self.stats:
            focus = self.stats.data.get("daily_focus_min", 0)
            sessions = self.stats.data.get("total_sessions", 0)
            lines.append(f"\U0001f3af Focus time: {focus} min")
            lines.append(f"\U0001f4ca Total sessions: {sessions}")
            lines.append(f"\U0001f4aa {self.stats.get_level_info()}")

        if self.habits:
            habits = self.habits.data.get("habits", {})
            today_log = self.habits.data.get("log", {}).get(
                self.habits._today(), {}
            )
            if habits:
                lines.append("\n\U0001f4cb Habits:")
                for key, info in sorted(habits.items()):
                    current = today_log.get(key, 0)
                    goal = info.get("goal", 1)
                    icon = info.get("icon", "\u2705")
                    check = "\u2705" if current >= goal else "\u274c"
                    lines.append(f"  {check} {icon} {key.title()}: {current}/{goal}")

        if self.stats:
            todos = self.stats.get_todos()
            done = [t for t in todos if t.get("done")]
            pending = [t for t in todos if not t.get("done")]
            if done:
                lines.append(f"\n\u2705 Completed {len(done)} task(s) today")
            if pending:
                lines.append(f"\u23f3 {len(pending)} task(s) still pending")

        return "\n".join(lines)

    def get_proactive_suggestion(self, context: dict) -> str | None:
        """Generate a contextual suggestion based on current state.
        Returns a suggestion string, or None if nothing to suggest."""

        suggestions = []
        now = datetime.now()
        hour = now.hour

        # Break suggestion based on focus time
        if self.stats:
            focus = self.stats.data.get("daily_focus_min", 0)
            if focus >= 45 and context.get("focus", 0) > 70:
                suggestions.append(
                    "\U0001f9d8 You've been focused for a while! Maybe take a short break?"
                )

        # Water reminder based on habits
        if self.habits and "water" in self.habits.data.get("habits", {}):
            today_log = self.habits.data.get("log", {}).get(
                self.habits._today(), {}
            )
            water_count = today_log.get("water", 0)
            water_goal = self.habits.data["habits"]["water"].get("goal", 8)
            if water_count < water_goal and hour >= 10:
                suggestions.append(
                    f"\U0001f4a7 Don't forget to drink water! ({water_count}/{water_goal} today)"
                )

        # Pending todos
        if self.stats:
            todos = self.stats.get_todos()
            pending = [t for t in todos if not t.get("done")]
            if pending and hour >= 14:
                suggestions.append(
                    f"\U0001f4cb You still have {len(pending)} task(s) pending. Want to check them?"
                )

        # Evening wind-down
        if hour >= 22:
            suggestions.append(
                "\U0001f319 It's getting late! Maybe time to wind down? \U0001f634"
            )

        # Low mood/energy
        mood = context.get("mood", 70)
        energy = context.get("energy", 80)
        if mood < 30:
            suggestions.append(
                "\U0001f495 Hey, I noticed you seem down. Want to chat? I'm here for you!"
            )
        if energy < 25:
            suggestions.append(
                "\U0001f634 Your energy is super low... A break might help!"
            )

        if suggestions:
            return random.choice(suggestions)
        return None
