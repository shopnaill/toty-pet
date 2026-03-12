"""
Sound Reactions — monitors microphone input for ambient sound levels.
Pet reacts to loud noises, silence, and typing sounds.
Uses sounddevice for lightweight audio capture.
"""
import logging
import time

from PyQt6.QtCore import QTimer, pyqtSignal, QObject

try:
    import numpy as np
    import sounddevice as sd
    _HAS_SOUND = True
except ImportError:
    _HAS_SOUND = False

log = logging.getLogger("toty")


class SoundReactor(QObject):
    """Processes audio levels and emits pet reactions."""
    reaction = pyqtSignal(str, str)  # (reaction_type, message)

    # Thresholds
    LOUD_THRESHOLD = 0.08      # Sudden loud noise
    SILENCE_THRESHOLD = 0.003  # Very quiet
    MODERATE_THRESHOLD = 0.02  # Normal ambient
    SPIKE_RATIO = 2.0          # How much louder than average to count as spike

    def __init__(self, enabled: bool = True):
        super().__init__()
        self._enabled = enabled
        self._stream = None
        self._level_history: list[float] = []
        self._max_history = 30  # ~9 seconds at 300ms process interval
        self._last_reaction_time: dict[str, float] = {}
        self._reaction_cooldown = 20.0  # seconds between same reaction type
        self._silence_start = 0.0
        self._current_level = 0.0
        self._error: str | None = None

        # Process levels on a timer in the main thread
        self._process_timer = QTimer(self)
        self._process_timer.timeout.connect(self._process)

        if enabled and _HAS_SOUND:
            self._start_stream()

    @staticmethod
    def available() -> bool:
        return _HAS_SOUND

    def get_error(self) -> str | None:
        """Return last error message if stream failed to start."""
        return self._error

    def _start_stream(self):
        """Open mic stream directly — sounddevice manages its own thread."""
        try:
            self._stream = sd.InputStream(
                channels=1, samplerate=16000, blocksize=4096,
                callback=self._audio_callback,
            )
            self._stream.start()
            self._process_timer.start(300)
            self._error = None
            log.info("SoundReactor: mic stream started")
        except Exception as exc:
            self._error = str(exc)
            self._stream = None
            log.warning("SoundReactor: failed to open mic — %s", exc)

    def stop(self):
        self._process_timer.stop()
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        if not enabled:
            self.stop()
        elif not self._stream and _HAS_SOUND:
            self._start_stream()

    def _audio_callback(self, indata, frames, time_info, status):
        """Called by sounddevice from its PortAudio thread.
        Only writes a float — safe under CPython GIL."""
        rms = float(np.sqrt(np.mean(indata ** 2)))
        self._current_level = rms

    def _should_react(self, kind: str) -> bool:
        now = time.time()
        last = self._last_reaction_time.get(kind, 0)
        if now - last < self._reaction_cooldown:
            return False
        self._last_reaction_time[kind] = now
        return True

    def get_current_level(self) -> float:
        return self._current_level

    def _process(self):
        if not self._enabled:
            return
        level = self._current_level
        self._level_history.append(level)
        if len(self._level_history) > self._max_history:
            self._level_history.pop(0)

        now = time.time()

        # Loud noise detection — spike relative to recent average
        if level > self.LOUD_THRESHOLD and len(self._level_history) > 3:
            avg = sum(self._level_history[:-1]) / max(len(self._level_history) - 1, 1)
            if avg < 0.001:
                avg = 0.001  # avoid division oddities when near-silent
            if level > avg * self.SPIKE_RATIO:
                if self._should_react("loud"):
                    self.reaction.emit("startled", "Whoa! That was loud! 😱")
                    return

        # Sustained silence (20+ seconds)
        if level < self.SILENCE_THRESHOLD:
            if self._silence_start == 0:
                self._silence_start = now
            elif now - self._silence_start > 20:
                if self._should_react("silence"):
                    self.reaction.emit("sleepy", "So quiet... *yawn* 😴")
                    self._silence_start = 0
        else:
            self._silence_start = 0

        # Ambient music/noise (moderate sustained level)
        if len(self._level_history) >= 8:
            recent_avg = sum(self._level_history[-8:]) / 8
            if self.MODERATE_THRESHOLD < recent_avg < self.LOUD_THRESHOLD:
                if self._should_react("ambient"):
                    self.reaction.emit("vibing", "Nice ambient vibes! 🎵")
