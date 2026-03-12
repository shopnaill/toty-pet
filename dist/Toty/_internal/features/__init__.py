from .prayer import PrayerTimeManager
from .notifications import WindowsNotificationReader
from .web_tracker import WebsiteTracker, WEB_TRACKER_PATH
from .ai_brain import OllamaBrain, AIChatSignal, AIChatDialog
from .todo_widget import MiniTodoWidget
from .azkar import AzkarManager, AzkarReaderDialog, AZKAR_CATEGORIES, QUICK_AZKAR

__all__ = [
    "PrayerTimeManager",
    "WindowsNotificationReader",
    "WebsiteTracker",
    "WEB_TRACKER_PATH",
    "OllamaBrain",
    "AIChatSignal",
    "AIChatDialog",
    "MiniTodoWidget",
]
