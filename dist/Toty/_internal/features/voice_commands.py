"""
Voice Commands — hands-free pet control using Windows SAPI via comtypes.

Listens for wake-word "hey toty" then processes the next phrase as a command.
Runs recognition in a background thread to avoid blocking the UI.
"""
import logging
import threading
import time
from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger("toty.voice")

_MIC_INIT_TIMEOUT = 5  # seconds to wait for microphone init

# Command mappings: keyword(s) → action string
_VOICE_COMMANDS = {
    "screenshot":   "screenshot",
    "take screenshot": "screenshot",
    "pomodoro":     "pomodoro",
    "start focus":  "pomodoro",
    "stop focus":   "stop_pomodoro",
    "show notes":   "sticky_notes",
    "sticky notes": "sticky_notes",
    "show stats":   "stats",
    "my stats":     "stats",
    "dashboard":    "dashboard",
    "open dashboard": "dashboard",
    "journal":      "journal",
    "open journal": "journal",
    "weather":      "weather",
    "what's the weather": "weather",
    "launcher":     "launcher",
    "quick launch": "launcher",
    "habits":       "habits",
    "my habits":    "habits",
    "todo":         "todo",
    "to do":        "todo",
    "sleep":        "sleep",
    "go to sleep":  "sleep",
    "wake up":      "wake",
    "good morning": "wake",
}


class VoiceCommands(QObject):
    """Background voice command listener.

    Signals:
        command_recognized(str): Emitted with the action key from _VOICE_COMMANDS
        heard_text(str): Raw recognized text (for debug/display)
        listening_changed(bool): True when actively listening for a command
    """
    command_recognized = pyqtSignal(str)
    heard_text = pyqtSignal(str)
    listening_changed = pyqtSignal(bool)

    def __init__(self, wake_word: str = "hey toty"):
        super().__init__()
        self._wake_word = wake_word.lower()
        self._running = False
        self._thread = None
        self._available = False
        self._lock = threading.Lock()  # guards _running and _available

        # Test if speech_recognition is available; auto-install if missing
        try:
            import speech_recognition  # noqa: F401
            self._available = True
        except ImportError:
            log.info("speech_recognition not found, auto-installing...")
            try:
                from features.auto_deps import ensure_speech_recognition
                if ensure_speech_recognition():
                    import speech_recognition  # noqa: F401
                    self._available = True
                    log.info("speech_recognition auto-installed OK")
                else:
                    log.warning("VoiceCommands: speech_recognition auto-install failed")
            except Exception:
                log.warning("VoiceCommands: speech_recognition not installed")

    def is_available(self) -> bool:
        with self._lock:
            return self._available

    def start(self):
        with self._lock:
            if not self._available or self._running:
                return
            self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        log.info("VoiceCommands started (wake word: %r)", self._wake_word)

    def stop(self):
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None

    def _listen_loop(self):
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True

        # Mic init with timeout watchdog to prevent hanging
        mic = None
        init_done = threading.Event()

        def _init_mic():
            nonlocal mic
            try:
                mic = sr.Microphone()
            except (OSError, AttributeError):
                pass
            finally:
                init_done.set()

        t = threading.Thread(target=_init_mic, daemon=True)
        t.start()
        if not init_done.wait(timeout=_MIC_INIT_TIMEOUT):
            log.error("VoiceCommands: microphone init timed out after %ds", _MIC_INIT_TIMEOUT)
            with self._lock:
                self._available = False
            return
        if mic is None:
            log.error("VoiceCommands: no microphone found")
            with self._lock:
                self._available = False
            return

        while True:
            with self._lock:
                if not self._running:
                    break
            try:
                with mic as source:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)

                text = recognizer.recognize_google(audio).lower().strip()
                self.heard_text.emit(text)

                # Check for wake word
                if self._wake_word in text:
                    # Extract command after wake word
                    cmd_text = text.split(self._wake_word, 1)[-1].strip()
                    if cmd_text:
                        self._process_command(cmd_text)
                    else:
                        # Wait for next phrase as the command
                        self.listening_changed.emit(True)
                        try:
                            with mic as source:
                                audio2 = recognizer.listen(source, timeout=5, phrase_time_limit=4)
                            cmd_text = recognizer.recognize_google(audio2).lower().strip()
                            self.heard_text.emit(cmd_text)
                            self._process_command(cmd_text)
                        except Exception:
                            pass
                        finally:
                            self.listening_changed.emit(False)

            except Exception:
                # Timeout, recognition failure, etc. — just retry
                time.sleep(0.2)
    def _process_command(self, text: str):
        """Match text against known commands."""
        for phrase, action in _VOICE_COMMANDS.items():
            if phrase in text:
                log.info("Voice command: %r -> %s", text, action)
                self.command_recognized.emit(action)
                return
        log.debug("Voice: no command match for %r", text)
