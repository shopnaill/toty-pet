"""Video URL Detector — watches clipboard & window titles for downloadable video URLs."""
import re
import time
import logging

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

log = logging.getLogger("toty.video_url_detector")

# Patterns for supported video platforms
_VIDEO_URL_PATTERNS = [
    # YouTube
    re.compile(r'https?://(?:www\.|m\.)?youtube\.com/watch\?[^\s]*v=[\w-]+', re.I),
    re.compile(r'https?://youtu\.be/[\w-]+', re.I),
    re.compile(r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+', re.I),
    # Facebook
    re.compile(r'https?://(?:www\.|m\.)?facebook\.com/.+/videos/', re.I),
    re.compile(r'https?://(?:www\.|m\.)?facebook\.com/watch/?\?v=\d+', re.I),
    re.compile(r'https?://fb\.watch/[\w-]+', re.I),
    re.compile(r'https?://(?:www\.|m\.)?facebook\.com/reel/', re.I),
    # Instagram
    re.compile(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[\w-]+', re.I),
    # Twitter/X
    re.compile(r'https?://(?:www\.)?(?:twitter|x)\.com/\w+/status/\d+', re.I),
    # TikTok
    re.compile(r'https?://(?:www\.|vm\.)?tiktok\.com/', re.I),
    # Reddit video
    re.compile(r'https?://(?:www\.)?reddit\.com/r/\w+/comments/\w+/', re.I),
    # Vimeo
    re.compile(r'https?://(?:www\.)?vimeo\.com/\d+', re.I),
    # Dailymotion
    re.compile(r'https?://(?:www\.)?dailymotion\.com/video/[\w-]+', re.I),
    # Twitch clips
    re.compile(r'https?://(?:www\.)?twitch\.tv/\w+/clip/', re.I),
    re.compile(r'https?://clips\.twitch\.tv/[\w-]+', re.I),
]

# Map window title keywords to platform names
_WINDOW_SITE_MAP = {
    "youtube": "YouTube",
    "facebook": "Facebook",
    "instagram": "Instagram",
    "twitter": "Twitter",
    "tiktok": "TikTok",
}

# Patterns that suggest an actual video page (not just the homepage)
# YouTube: "Video Title - YouTube" (has content before "- YouTube")
# Facebook: anything with "facebook" (videos autoplay everywhere)
# Instagram: anything with "instagram"
_VIDEO_PAGE_HINTS = {
    "YouTube": re.compile(r'.+\s[-–]\s*youtube', re.I),       # "Title - YouTube"
    "Facebook": re.compile(r'facebook', re.I),
    "Instagram": re.compile(r'instagram', re.I),
    "Twitter": re.compile(r'.+[/|–-]\s*(?:twitter|x\b)', re.I),
    "TikTok": re.compile(r'tiktok', re.I),
}

# Phrases the pet says per platform
_PLATFORM_SPEECH = {
    "YouTube":   ["🎬 Watching YouTube? I can download this video for you! 👇",
                  "📹 Nice video! Want me to save it? 👇",
                  "⬇️ I spotted a YouTube video — want to download it?"],
    "Facebook":  ["📘 Found a Facebook video! Want to download it? 👇",
                  "⬇️ I can grab this Facebook video for you!"],
    "Instagram": ["📸 Instagram reel detected! Shall I download it? 👇",
                  "⬇️ Want me to save this Instagram video?"],
    "Twitter":   ["🐦 Found a Twitter/X video! Download it? 👇",
                  "⬇️ I can save this post's video for you!"],
    "TikTok":    ["🎵 TikTok video detected! Want to download? 👇",
                  "⬇️ I can save this TikTok!"],
    "Video":     ["🎬 I found a video URL! Want me to download it? 👇",
                  "⬇️ Video link detected — shall I grab it?"],
}


def detect_video_url(text: str) -> tuple[str | None, str | None]:
    """Check if text contains a video URL.

    Returns (url, platform) or (None, None).
    """
    if not text or len(text) > 2000:
        return None, None

    for pattern in _VIDEO_URL_PATTERNS:
        m = pattern.search(text)
        if m:
            url = m.group(0)
            platform = _guess_platform(url)
            return url, platform
    return None, None


def _guess_platform(url: str) -> str:
    url_lower = url.lower()
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "YouTube"
    if "facebook.com" in url_lower or "fb.watch" in url_lower:
        return "Facebook"
    if "instagram.com" in url_lower:
        return "Instagram"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "Twitter"
    if "tiktok.com" in url_lower:
        return "TikTok"
    if "vimeo.com" in url_lower:
        return "Vimeo"
    if "dailymotion.com" in url_lower:
        return "Dailymotion"
    if "twitch.tv" in url_lower:
        return "Twitch"
    if "reddit.com" in url_lower:
        return "Reddit"
    return "Video"


def detect_video_site_from_title(title: str) -> str | None:
    """Check if a window title suggests a video-watching page.

    Returns platform name or None.
    Uses smarter patterns to detect actual video pages, not just homepages.
    """
    if not title:
        return None
    title_lower = title.lower()

    # First: quick keyword check
    matched_platform = None
    for keyword, platform in _WINDOW_SITE_MAP.items():
        if keyword in title_lower:
            matched_platform = platform
            break

    if not matched_platform:
        # Check for "/ X" pattern (Twitter/X rebranding)
        if re.search(r'[/|–-]\s*x\s*$', title_lower) or re.search(r'[/|–-]\s*x\s*[-–]', title_lower):
            matched_platform = "Twitter"

    if not matched_platform:
        return None

    # Second: verify it looks like an actual content page (not just the homepage)
    hint = _VIDEO_PAGE_HINTS.get(matched_platform)
    if hint and hint.search(title):
        return matched_platform

    # For Facebook/Instagram/TikTok — always offer (videos autoplay)
    if matched_platform in ("Facebook", "Instagram", "TikTok"):
        return matched_platform

    return None


def get_platform_speech(platform: str) -> list[str]:
    """Get speech lines for a detected platform."""
    return _PLATFORM_SPEECH.get(platform, _PLATFORM_SPEECH["Video"])


class VideoURLDetector(QObject):
    """Monitors clipboard for video URLs and emits signals for pet to react."""

    video_url_detected = pyqtSignal(str, str)  # url, platform

    def __init__(self, check_interval_ms: int = 2000):
        super().__init__()
        self._last_url = ""
        self._last_detect_time = 0.0
        self._cooldown = 60.0  # Don't nag about same URL within 60 seconds
        self._offered_urls: set[str] = set()  # URLs we already offered
        self._enabled = True

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_clipboard)
        self._timer.start(check_interval_ms)

    def stop(self):
        self._timer.stop()

    def set_enabled(self, on: bool):
        self._enabled = on

    def _check_clipboard(self):
        if not self._enabled:
            return
        try:
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            if clipboard is None:
                return
            text = clipboard.text().strip()
            if not text:
                return

            now = time.time()
            # Same text cooldown
            if text == self._last_url and (now - self._last_detect_time) < self._cooldown:
                return

            url, platform = detect_video_url(text)
            if url and url not in self._offered_urls:
                self._last_url = text
                self._last_detect_time = now
                self._offered_urls.add(url)
                # Cap set size
                if len(self._offered_urls) > 100:
                    self._offered_urls = set(list(self._offered_urls)[-50:])
                self.video_url_detected.emit(url, platform)
        except Exception:
            pass

    def check_url_text(self, text: str) -> tuple[str | None, str | None]:
        """Manually check a text for video URL (e.g. from window title bar URL).

        Returns (url, platform) or (None, None).
        """
        return detect_video_url(text)
