"""
Hunger & Feeding System — hunger stat that decays, food items earned from
productivity, feeding menu to restore energy/mood.
"""
import json
import os
import time
from core.safe_json import safe_json_save
from PyQt6.QtCore import QTimer, pyqtSignal, QObject

_DATA_PATH = "hunger_data.json"

FOOD_ITEMS = {
    "cookie":   {"emoji": "🍪", "hunger": 15, "mood": 5,  "energy": 5},
    "apple":    {"emoji": "🍎", "hunger": 20, "mood": 8,  "energy": 10},
    "pizza":    {"emoji": "🍕", "hunger": 30, "mood": 12, "energy": 8},
    "cake":     {"emoji": "🎂", "hunger": 25, "mood": 20, "energy": 5},
    "coffee":   {"emoji": "☕", "hunger": 5,  "mood": 10, "energy": 25},
    "salad":    {"emoji": "🥗", "hunger": 20, "mood": 5,  "energy": 15},
    "sushi":    {"emoji": "🍣", "hunger": 25, "mood": 15, "energy": 10},
    "candy":    {"emoji": "🍬", "hunger": 10, "mood": 15, "energy": 3},
    "water":    {"emoji": "💧", "hunger": 5,  "mood": 3,  "energy": 10},
    "date_fruit": {"emoji": "🌴", "hunger": 15, "mood": 10, "energy": 12},
}

# How food is earned
FOOD_REWARDS = {
    "pomodoro_complete": ["cookie", "apple", "coffee"],
    "challenge_complete": ["pizza", "cake", "sushi"],
    "focus_30min": ["apple", "water"],
    "streak_bonus": ["cake", "date_fruit"],
    "petting": ["candy"],
}


class HungerSystem(QObject):
    """Manages pet hunger, food inventory, and feeding."""

    hunger_changed = pyqtSignal(float)  # current hunger level (0-100)
    food_earned = pyqtSignal(str, str)  # (food_key, emoji)
    pet_hungry = pyqtSignal()           # fired when hunger drops below 20

    def __init__(self, decay_rate: float = 0.5):
        super().__init__()
        self._decay_rate = decay_rate  # hunger points lost per minute
        self._data = {
            "hunger": 80.0,
            "inventory": {},  # food_key -> count
            "total_fed": 0,
            "last_decay": time.time(),
        }
        self._load()
        self._hungry_warned = False

        # Decay timer every 60s
        self._timer = QTimer()
        self._timer.timeout.connect(self._decay_tick)
        self._timer.start(60000)

    @property
    def hunger(self) -> float:
        return self._data["hunger"]

    @property
    def inventory(self) -> dict[str, int]:
        return self._data["inventory"]

    def get_inventory_display(self) -> list[tuple[str, str, int]]:
        """Returns [(food_key, emoji, count), ...] for items in inventory."""
        result = []
        for key, count in self._data["inventory"].items():
            if count > 0 and key in FOOD_ITEMS:
                result.append((key, FOOD_ITEMS[key]["emoji"], count))
        return sorted(result, key=lambda x: x[2], reverse=True)

    def earn_food(self, reason: str):
        """Award a random food item based on the reason."""
        import random
        options = FOOD_REWARDS.get(reason, ["cookie"])
        food_key = random.choice(options)
        self._data["inventory"][food_key] = self._data["inventory"].get(food_key, 0) + 1
        self._save()
        self.food_earned.emit(food_key, FOOD_ITEMS[food_key]["emoji"])

    def feed(self, food_key: str) -> tuple[float, float, float] | None:
        """Feed the pet. Returns (hunger_gain, mood_gain, energy_gain) or None if not available."""
        if self._data["inventory"].get(food_key, 0) <= 0:
            return None
        if food_key not in FOOD_ITEMS:
            return None

        item = FOOD_ITEMS[food_key]
        self._data["inventory"][food_key] -= 1
        if self._data["inventory"][food_key] <= 0:
            del self._data["inventory"][food_key]

        self._data["hunger"] = min(100, self._data["hunger"] + item["hunger"])
        self._data["total_fed"] += 1
        self._hungry_warned = False
        self._save()
        self.hunger_changed.emit(self._data["hunger"])
        return (item["hunger"], item["mood"], item["energy"])

    def _decay_tick(self):
        now = time.time()
        elapsed_min = (now - self._data["last_decay"]) / 60
        self._data["last_decay"] = now
        self._data["hunger"] = max(0, self._data["hunger"] - self._decay_rate * elapsed_min)
        self._save()
        self.hunger_changed.emit(self._data["hunger"])

        if self._data["hunger"] < 20 and not self._hungry_warned:
            self._hungry_warned = True
            self.pet_hungry.emit()

    def _load(self):
        if os.path.exists(_DATA_PATH):
            try:
                with open(_DATA_PATH, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._data.update(saved)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        try:
            safe_json_save(self._data, _DATA_PATH)
        except OSError:
            pass

    def stop(self):
        self._timer.stop()
        self._save()
