import time

from core.settings import Settings


class ComboTracker:
    """Tracks rapid double-click combos for escalating reactions."""
    def __init__(self, settings: Settings):
        self.settings = settings
        self._click_times: list[float] = []

    def register_click(self) -> int:
        """Register a pet interaction, return current combo count."""
        now = time.time()
        window = self.settings.get("pet_combo_window_sec")
        self._click_times = [t for t in self._click_times if now - t < window]
        self._click_times.append(now)
        return len(self._click_times)
