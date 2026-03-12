"""
Widget Position Persistence — mixin helper that saves/restores widget positions.
"""
import json
import os

_POS_FILE = "widget_positions.json"


def _load_positions() -> dict:
    if os.path.exists(_POS_FILE):
        try:
            with open(_POS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_positions(data: dict):
    try:
        from core.safe_json import safe_json_save
        safe_json_save(data, _POS_FILE)
    except Exception:
        pass


def save_widget_pos(key: str, x: int, y: int):
    """Save a widget's position by key."""
    data = _load_positions()
    data[key] = {"x": x, "y": y}
    _save_positions(data)


def restore_widget_pos(key: str) -> tuple[int, int] | None:
    """Return saved (x, y) for widget key, or None if not saved."""
    data = _load_positions()
    entry = data.get(key)
    if entry:
        return (entry["x"], entry["y"])
    return None
