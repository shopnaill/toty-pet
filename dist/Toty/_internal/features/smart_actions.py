"""
AI Smart Actions — context-aware AI operations on selected/clipboard text.
Pipes through Ollama for: summarize, translate, fix grammar, explain code,
convert units, generate reply.
"""
import logging
from PyQt6.QtCore import QObject, pyqtSignal, QThread

log = logging.getLogger("toty")


_PROMPTS = {
    "summarize": "Summarize this concisely in 2-3 sentences:\n\n{}",
    "translate_en": "Translate this to English. Reply with ONLY the translation:\n\n{}",
    "translate_ar": "Translate this to Arabic. Reply with ONLY the translation:\n\n{}",
    "fix_grammar": "Fix the grammar and spelling. Reply with ONLY the corrected text:\n\n{}",
    "explain_code": "Explain this code briefly in plain English:\n\n```\n{}\n```",
    "improve": "Improve this text to be clearer and more professional. Reply with ONLY the improved text:\n\n{}",
    "generate_reply": "Generate a brief, professional reply to this message:\n\n{}",
}


SMART_ACTIONS = {
    "summarize":      "📝 Summarize",
    "translate_en":   "🇬🇧 Translate → English",
    "translate_ar":   "🇸🇦 Translate → Arabic",
    "fix_grammar":    "✏️ Fix Grammar",
    "explain_code":   "💡 Explain Code",
    "improve":        "✨ Improve Text",
    "generate_reply": "💬 Generate Reply",
}


class AISmartActions(QObject):
    """Manages smart AI actions on text via Ollama chat API."""
    action_started = pyqtSignal(str)         # action_name
    action_result = pyqtSignal(str, str)     # (action_name, result)
    action_error = pyqtSignal(str)

    def __init__(self, brain):
        super().__init__()
        self._brain = brain
        self._pending = False

    def run_action(self, action: str, text: str):
        """Run an AI action on text using the brain's chat method."""
        if not text.strip():
            self.action_error.emit("No text to process")
            return
        if self._pending:
            self.action_error.emit("AI is already processing a request…")
            return
        if len(text) > 5000:
            text = text[:5000] + "\n...(truncated)"

        self._pending = True
        self.action_started.emit(action)
        template = _PROMPTS.get(action, "{}:\n\n{{}}")
        prompt = template.format(text)

        # Timeout: emit error if no response within 20s
        from PyQt6.QtCore import QTimer
        self._timeout = QTimer()
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(lambda: self._handle_timeout(action))
        self._timeout.start(20000)

        def _callback(reply, error):
            self._pending = False
            self._timeout.stop()
            if error:
                self.action_error.emit(str(error))
            elif reply:
                self.action_result.emit(action, reply)
            else:
                self.action_error.emit("No response from AI")

        context = {"mood": 70, "energy": 70, "memory_context": ""}
        self._brain.chat(prompt, context, _callback)

    def _handle_timeout(self, action: str):
        if self._pending:
            self._pending = False
            self.action_error.emit(f"AI timed out on '{action}' — try again")

    @staticmethod
    def get_actions() -> dict[str, str]:
        return dict(SMART_ACTIONS)

    def stop(self):
        if hasattr(self, "_timeout"):
            self._timeout.stop()
