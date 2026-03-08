"""
Pet Sound Effects — generates and plays small WAV sounds for pet actions.
Uses winsound (Windows) for playback and numpy for synthesis.
All sounds are generated programmatically — no external audio files needed.
"""
import io
import os
import struct
import math
import wave
import logging
import winsound
import threading
from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger("toty")

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "assets", "sfx")
_SAMPLE_RATE = 22050


def _ensure_cache():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _save_wav(path: str, samples: list[float], rate: int = _SAMPLE_RATE):
    """Save float samples (-1.0 to 1.0) as 16-bit WAV."""
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        data = b""
        for s in samples:
            s = max(-1.0, min(1.0, s))
            data += struct.pack("<h", int(s * 32767))
        wf.writeframes(data)


def _sine(freq: float, duration: float, volume: float = 0.3,
          rate: int = _SAMPLE_RATE) -> list[float]:
    """Generate a sine wave."""
    n = int(rate * duration)
    return [volume * math.sin(2 * math.pi * freq * i / rate) for i in range(n)]


def _fade(samples: list[float], fade_in: int = 200, fade_out: int = 400) -> list[float]:
    """Apply fade-in and fade-out to avoid clicks."""
    n = len(samples)
    for i in range(min(fade_in, n)):
        samples[i] *= i / fade_in
    for i in range(min(fade_out, n)):
        samples[n - 1 - i] *= i / fade_out
    return samples


def _chirp(f_start: float, f_end: float, duration: float,
           volume: float = 0.3, rate: int = _SAMPLE_RATE) -> list[float]:
    """Generate a frequency sweep (chirp)."""
    n = int(rate * duration)
    samples = []
    for i in range(n):
        t = i / rate
        f = f_start + (f_end - f_start) * (t / duration)
        samples.append(volume * math.sin(2 * math.pi * f * t))
    return _fade(samples)


def _noise_burst(duration: float, volume: float = 0.1,
                 rate: int = _SAMPLE_RATE) -> list[float]:
    """Short noise burst (for hiss/static effects)."""
    import random
    n = int(rate * duration)
    samples = [volume * (random.random() * 2 - 1) for _ in range(n)]
    return _fade(samples, 50, 100)


# ── Sound generators ──

def _gen_click() -> list[float]:
    """Short click/tap sound."""
    s = _sine(800, 0.03, 0.25) + _sine(400, 0.02, 0.15)
    return _fade(s, 10, 30)


def _gen_pet() -> list[float]:
    """Soft purr/pet sound — warm low tone."""
    s = _sine(180, 0.15, 0.2) + _sine(200, 0.15, 0.18) + _sine(170, 0.1, 0.12)
    return _fade(s, 100, 200)


def _gen_happy() -> list[float]:
    """Happy chirp — rising two-tone."""
    return _chirp(400, 800, 0.15, 0.3) + _chirp(600, 1000, 0.15, 0.25)


def _gen_sad() -> list[float]:
    """Sad sound — falling tone."""
    return _chirp(500, 200, 0.3, 0.2)


def _gen_startled() -> list[float]:
    """Startled — quick high spike."""
    return _chirp(300, 1200, 0.08, 0.35) + _sine(1200, 0.05, 0.2)


def _gen_yawn() -> list[float]:
    """Yawn — slow descending sweep."""
    return _chirp(400, 150, 0.5, 0.15)


def _gen_achievement() -> list[float]:
    """Achievement unlocked — triumphant 3-note arpeggio."""
    s = _sine(523, 0.12, 0.3)   # C5
    s += _sine(659, 0.12, 0.3)  # E5
    s += _sine(784, 0.2, 0.35)  # G5
    return _fade(s, 50, 200)


def _gen_notification() -> list[float]:
    """Notification ping — two soft tones."""
    s = _sine(880, 0.08, 0.2) + _sine(1100, 0.1, 0.2)
    return _fade(s, 30, 100)


def _gen_alert() -> list[float]:
    """Alert/warning — two quick beeps."""
    s = _sine(600, 0.1, 0.3)
    s += [0.0] * int(_SAMPLE_RATE * 0.05)  # gap
    s += _sine(600, 0.1, 0.3)
    return _fade(s, 30, 50)


def _gen_typing() -> list[float]:
    """Typing click — very short mechanical click."""
    s = _sine(1000, 0.015, 0.15) + _sine(500, 0.01, 0.1)
    return _fade(s, 5, 15)


def _gen_level_up() -> list[float]:
    """Level up — grand ascending scale."""
    notes = [523, 587, 659, 784, 880, 1047]  # C5 to C6
    s = []
    for f in notes:
        s += _sine(f, 0.08, 0.3)
    s += _sine(1047, 0.2, 0.35)  # hold final note
    return _fade(s, 50, 300)


def _gen_sleep() -> list[float]:
    """Sleep sound — gentle low hum fade-out."""
    s = _sine(120, 0.6, 0.12) + _sine(100, 0.4, 0.08)
    return _fade(s, 200, 600)


def _gen_wake() -> list[float]:
    """Wake up — bright short chirp."""
    return _chirp(300, 700, 0.2, 0.25)


def _gen_error() -> list[float]:
    """Error — buzzy low tone."""
    s = _sine(200, 0.15, 0.3)
    s += [0.0] * int(_SAMPLE_RATE * 0.05)
    s += _sine(150, 0.2, 0.3)
    return _fade(s, 30, 100)


def _gen_eating() -> list[float]:
    """Eating/nom — quick repeated soft clicks."""
    s = []
    for _ in range(4):
        s += _sine(500, 0.03, 0.2)
        s += [0.0] * int(_SAMPLE_RATE * 0.04)
    return _fade(s, 10, 30)


def _gen_fall() -> list[float]:
    """Falling — rapid descending sweep."""
    return _chirp(800, 100, 0.25, 0.3)


def _gen_bounce() -> list[float]:
    """Bounce/land — quick low thud."""
    s = _sine(100, 0.06, 0.35) + _sine(60, 0.04, 0.2)
    return _fade(s, 10, 40)


def _gen_meow() -> list[float]:
    """Cat-like meow — rising then falling sweep."""
    s = _chirp(300, 600, 0.15, 0.3) + _chirp(600, 350, 0.2, 0.25)
    return _fade(s, 50, 200)


def _gen_purr() -> list[float]:
    """Purring — low rumble with vibrato."""
    n = int(_SAMPLE_RATE * 0.6)
    samples = []
    for i in range(n):
        t = i / _SAMPLE_RATE
        vibrato = 0.5 * math.sin(2 * math.pi * 20 * t)
        freq = 80 + vibrato * 15
        samples.append(0.15 * math.sin(2 * math.pi * freq * t))
    return _fade(samples, 200, 400)


def _gen_giggle() -> list[float]:
    """Giggle — quick alternating high tones."""
    s = []
    for i in range(5):
        f = 700 if i % 2 == 0 else 900
        s += _sine(f, 0.05, 0.2)
        s += [0.0] * int(_SAMPLE_RATE * 0.02)
    return _fade(s, 30, 50)


# ── Sound registry ──

SOUND_GENERATORS = {
    "click":        _gen_click,
    "pet":          _gen_pet,
    "happy":        _gen_happy,
    "sad":          _gen_sad,
    "startled":     _gen_startled,
    "yawn":         _gen_yawn,
    "achievement":  _gen_achievement,
    "notification": _gen_notification,
    "alert":        _gen_alert,
    "typing":       _gen_typing,
    "level_up":     _gen_level_up,
    "sleep":        _gen_sleep,
    "wake":         _gen_wake,
    "error":        _gen_error,
    "eating":       _gen_eating,
    "fall":         _gen_fall,
    "bounce":       _gen_bounce,
    "meow":         _gen_meow,
    "purr":         _gen_purr,
    "giggle":       _gen_giggle,
}


class PetSFX(QObject):
    """Pet sound effects engine. Generates WAV files on first use, caches them."""
    sound_played = pyqtSignal(str)  # sound name

    def __init__(self, enabled: bool = True, volume: float = 0.5):
        super().__init__()
        self._enabled = enabled
        self._volume = max(0.0, min(1.0, volume))
        self._cache: dict[str, str] = {}  # name → file path
        _ensure_cache()
        self._pregenerate()

    def _pregenerate(self):
        """Generate all sound files on init (fast — pure math)."""
        for name, gen_fn in SOUND_GENERATORS.items():
            path = os.path.join(_CACHE_DIR, f"{name}.wav")
            if not os.path.exists(path):
                try:
                    samples = gen_fn()
                    # Apply volume
                    samples = [s * self._volume for s in samples]
                    _save_wav(path, samples)
                except Exception as exc:
                    log.warning("PetSFX: failed to generate %s: %s", name, exc)
                    continue
            self._cache[name] = path
        log.info("PetSFX: %d sounds ready", len(self._cache))

    def play(self, name: str):
        """Play a named sound effect (non-blocking)."""
        if not self._enabled:
            return
        path = self._cache.get(name)
        if not path or not os.path.exists(path):
            return
        # Play async in a thread to avoid blocking the GUI
        threading.Thread(
            target=self._play_wav, args=(path,), daemon=True
        ).start()
        self.sound_played.emit(name)

    def _play_wav(self, path: str):
        try:
            winsound.PlaySound(path, winsound.SND_FILENAME)
        except Exception:
            pass

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def set_volume(self, volume: float):
        """Set volume (0.0-1.0) and regenerate sounds."""
        self._volume = max(0.0, min(1.0, volume))
        # Regenerate with new volume
        for name, gen_fn in SOUND_GENERATORS.items():
            path = os.path.join(_CACHE_DIR, f"{name}.wav")
            try:
                samples = gen_fn()
                samples = [s * self._volume for s in samples]
                _save_wav(path, samples)
                self._cache[name] = path
            except Exception:
                pass

    def is_enabled(self) -> bool:
        return self._enabled

    def get_volume(self) -> float:
        return self._volume

    def get_sound_names(self) -> list[str]:
        return list(SOUND_GENERATORS.keys())
