"""Meeting / DND Mode — auto-detect meeting apps and suppress interruptions."""
import logging
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger("toty.meeting_mode")

_MEETING_KEYWORDS = [
    "zoom meeting", "zoom", "microsoft teams", "teams call",
    "google meet", "webex", "slack huddle", "discord call",
    "skype", "facetime",
]


class MeetingDetector(QObject):
    """Watches active window title for meeting apps, emits signals."""
    meeting_started = pyqtSignal(str)   # app name
    meeting_ended = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._in_meeting = False
        self._meeting_app = ""
        self._miss_count = 0        # consecutive non-meeting scans
        self._miss_threshold = 6    # ~30s of no meeting window → end

    @property
    def in_meeting(self) -> bool:
        return self._in_meeting

    @property
    def meeting_app(self) -> str:
        return self._meeting_app

    def check_window(self, title_lower: str):
        """Call from the window scan callback with lowered title."""
        detected = ""
        for kw in _MEETING_KEYWORDS:
            if kw in title_lower:
                detected = kw.title()
                break

        if detected:
            self._miss_count = 0
            if not self._in_meeting:
                self._in_meeting = True
                self._meeting_app = detected
                log.info("Meeting detected: %s", detected)
                self.meeting_started.emit(detected)
        else:
            if self._in_meeting:
                self._miss_count += 1
                if self._miss_count >= self._miss_threshold:
                    self._in_meeting = False
                    self._meeting_app = ""
                    log.info("Meeting ended")
                    self.meeting_ended.emit()

    def force_end(self):
        """Manually end meeting detection."""
        if self._in_meeting:
            self._in_meeting = False
            self._meeting_app = ""
            self.meeting_ended.emit()
