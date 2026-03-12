"""
Pet TTS Voice — optional text-to-speech for pet speech bubbles.
Uses pyttsx3 (offline) with fallback to silent if unavailable.
"""
import threading
import logging

log = logging.getLogger("toty.tts")

_engine = None
_lock = threading.Lock()


def _get_engine():
    global _engine
    if _engine is None:
        try:
            import pyttsx3
            _engine = pyttsx3.init()
            _engine.setProperty("rate", 160)
            _engine.setProperty("volume", 0.8)
            # Try to use a friendly voice
            voices = _engine.getProperty("voices")
            for v in voices:
                if "zira" in v.name.lower() or "female" in v.name.lower():
                    _engine.setProperty("voice", v.id)
                    break
        except Exception as e:
            log.warning("TTS init failed: %s", e)
            _engine = False  # sentinel: don't retry
    return _engine if _engine is not False else None


def speak(text: str):
    """Speak text in a background thread. No-op if TTS unavailable."""
    def _run():
        with _lock:
            engine = _get_engine()
            if engine:
                try:
                    # Strip emojis for cleaner speech
                    import re
                    clean = re.sub(r'[^\w\s.,!?\'"-]', '', text, flags=re.UNICODE).strip()
                    if clean:
                        engine.say(clean)
                        engine.runAndWait()
                except Exception as e:
                    log.warning("TTS speak failed: %s", e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def is_available() -> bool:
    """Check if TTS is available."""
    try:
        import pyttsx3  # noqa: F401
        return True
    except ImportError:
        return False
