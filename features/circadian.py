"""
Pet Circadian Cycle — time-of-day behaviour modifiers.

Controls the pet's energy, state preferences, and automatic sleep/wake
based on the current hour.
"""
from datetime import datetime

# (start_hour, end_hour, phase_name, energy_bias, preferred_states, auto_state)
_PHASES = [
    (5,  8,  "dawn",      "energetic",  ["stretch", "yawn"],         None),
    (8,  12, "morning",   "active",     ["walk_right", "walk_left", "idle"], None),
    (12, 14, "noon",      "neutral",    ["idle", "yawn"],            None),
    (14, 16, "afternoon", "drowsy",     ["idle", "yawn", "sleep"],   None),
    (16, 20, "evening",   "active",     ["walk_right", "walk_left", "idle"], None),
    (20, 23, "night",     "winding",    ["idle", "yawn"],            None),
    (23, 5,  "late_night","sleepy",     ["sleep", "yawn"],           "sleep"),
]


def get_circadian_phase(hour: int | None = None) -> dict:
    """Return the current circadian phase info.

    Returns dict with keys:
      - phase: str name
      - energy_bias: energy label
      - preferred_states: list of animation state names to favour
      - auto_state: forced state or None
      - sleep_suggested: bool
    """
    if hour is None:
        hour = datetime.now().hour

    for start, end, name, bias, states, auto in _PHASES:
        if start <= end:
            if start <= hour < end:
                return {
                    "phase": name,
                    "energy_bias": bias,
                    "preferred_states": states,
                    "auto_state": auto,
                    "sleep_suggested": bias == "sleepy",
                }
        else:  # wraps midnight (23-5)
            if hour >= start or hour < end:
                return {
                    "phase": name,
                    "energy_bias": bias,
                    "preferred_states": states,
                    "auto_state": auto,
                    "sleep_suggested": bias == "sleepy",
                }

    # Fallback
    return {
        "phase": "day",
        "energy_bias": "neutral",
        "preferred_states": ["idle"],
        "auto_state": None,
        "sleep_suggested": False,
    }


def circadian_speech(phase: str) -> str | None:
    """Return a one-time comment for a phase transition."""
    _comments = {
        "dawn":       "🌅 Good morning! A fresh new day~",
        "morning":    None,
        "noon":       "☀️ It's noon! Lunchtime?",
        "afternoon":  "😴 Afternoon slump... maybe a stretch?",
        "evening":    "🌇 Evening already! Time flies~",
        "night":      "🌙 It's getting late... don't forget to rest!",
        "late_night": "💤 Zzz... it's really late... I'm sleepy...",
    }
    return _comments.get(phase)
