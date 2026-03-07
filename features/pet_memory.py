"""Persistent memory for the desktop pet.

Stores facts, notes, and learned preferences that survive across sessions.
Provides search and recall by topic.
"""

import json
import logging
import os
import re
import time
from datetime import datetime

log = logging.getLogger("toty.memory")

MEMORY_PATH = "pet_memory.json"


class PetMemory:
    """Long-term memory storage for the pet character."""

    def __init__(self):
        self.data: dict = {
            "facts": [],         # {text, topic, timestamp}
            "preferences": {},   # key -> value (learned)
            "user_info": {},     # name, birthday, etc.
        }
        self._load()

    def _load(self):
        if os.path.exists(MEMORY_PATH):
            try:
                with open(MEMORY_PATH, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        with open(MEMORY_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def remember(self, text: str, topic: str = "") -> str:
        """Store a fact. Returns confirmation message."""
        if not topic:
            # Try to extract topic from text
            topic = self._extract_topic(text)

        fact = {
            "text": text,
            "topic": topic.lower(),
            "timestamp": datetime.now().isoformat(timespec="minutes"),
        }
        self.data["facts"].append(fact)
        # Keep max 200 facts
        if len(self.data["facts"]) > 200:
            self.data["facts"] = self.data["facts"][-200:]
        self.save()
        log.info("Remembered: %s (topic: %s)", text[:50], topic)
        return f"\U0001f4dd Got it! I'll remember that."

    def recall(self, query: str) -> str:
        """Search memory for facts matching a query."""
        query_lower = query.lower()
        matches = []
        for fact in self.data["facts"]:
            if (query_lower in fact["text"].lower() or
                    query_lower in fact.get("topic", "").lower()):
                matches.append(fact)

        if not matches:
            return f"\U0001f914 I don't remember anything about \"{query}\""

        lines = [f"\U0001f4ad Here's what I remember about \"{query}\":"]
        for fact in matches[-10:]:  # Show last 10 matches
            ts = fact.get("timestamp", "")
            lines.append(f"  \u2022 {fact['text']}  ({ts})")
        return "\n".join(lines)

    def recall_all(self) -> str:
        """Show all memories grouped by topic."""
        facts = self.data.get("facts", [])
        if not facts:
            return "\U0001f4ad I don't have any memories yet. Tell me something to remember!"

        by_topic: dict[str, list] = {}
        for fact in facts:
            topic = fact.get("topic", "general") or "general"
            by_topic.setdefault(topic, []).append(fact)

        lines = [f"\U0001f9e0 My Memories ({len(facts)} total):"]
        for topic, items in sorted(by_topic.items()):
            lines.append(f"\n  \U0001f4cc {topic.title()}:")
            for item in items[-5:]:  # Last 5 per topic
                lines.append(f"    \u2022 {item['text']}")
        return "\n".join(lines)

    def forget(self, query: str) -> str:
        """Remove memories matching a query."""
        query_lower = query.lower()
        before = len(self.data["facts"])
        self.data["facts"] = [
            f for f in self.data["facts"]
            if query_lower not in f["text"].lower()
            and query_lower not in f.get("topic", "").lower()
        ]
        removed = before - len(self.data["facts"])
        self.save()
        if removed:
            return f"\U0001f9f9 Forgot {removed} thing(s) about \"{query}\""
        return f"\U0001f914 Nothing to forget about \"{query}\""

    def set_preference(self, key: str, value: str):
        """Learn a user preference."""
        self.data.setdefault("preferences", {})[key.lower()] = value
        self.save()

    def get_preference(self, key: str) -> str | None:
        """Recall a preference."""
        return self.data.get("preferences", {}).get(key.lower())

    def set_user_info(self, key: str, value: str):
        """Store user personal info (name, etc.)."""
        self.data.setdefault("user_info", {})[key.lower()] = value
        self.save()

    def get_context_for_ai(self) -> str:
        """Build a memory context string to inject into AI system prompt."""
        parts = []
        prefs = self.data.get("preferences", {})
        if prefs:
            parts.append("User preferences: " + ", ".join(f"{k}={v}" for k, v in prefs.items()))

        user_info = self.data.get("user_info", {})
        if user_info:
            parts.append("User info: " + ", ".join(f"{k}: {v}" for k, v in user_info.items()))

        # Recent facts (last 10)
        facts = self.data.get("facts", [])
        if facts:
            recent = facts[-10:]
            parts.append("Things I remember: " + " | ".join(f["text"] for f in recent))

        return "\n".join(parts) if parts else ""

    def _extract_topic(self, text: str) -> str:
        """Try to extract a topic keyword from text."""
        text_lower = text.lower()
        # Common pattern: "my X is Y", "X deadline is Y", etc.
        patterns = [
            r"(?:my\s+)?(\w+)\s+(?:is|are|was|will|deadline|meeting|appointment)",
            r"(?:about|regarding)\s+(?:my\s+)?(\w+)",
            r"(\w+)\s+(?:project|task|work|class|exam|meeting)",
        ]
        for pat in patterns:
            m = re.search(pat, text_lower)
            if m:
                word = m.group(1)
                if word not in {"it", "this", "that", "the", "my", "i", "he", "she"}:
                    return word
        return "general"
