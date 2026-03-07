import re
import pygetwindow as gw


class MusicDetector:
    """Detects whether music/media is currently playing.

    Detection strategy:
    - Browsers (YouTube, Spotify web, etc.): ONLY trigger on ▶ play indicator in title
    - Desktop music apps (Spotify, VLC, foobar): Use title patterns (they show track names only when playing)
    """

    DEDICATED_MUSIC_APPS = [
        "spotify", "vlc", "mpv", "foobar", "winamp",
        "musicbee", "aimp", "media player",
    ]

    BROWSERS = {
        "google chrome", "mozilla firefox", "microsoft edge",
        "brave", "opera", "vivaldi", "chromium", "safari",
    }

    MUSIC_SITES = [
        "youtube", "soundcloud", "apple music", "deezer", "tidal",
        "pandora", "amazon music", "youtube music", "spotify",
    ]

    PLAYING_INDICATORS = [
        "\u25b6", "\u25ba", "\u23f5", "now playing",
    ]
    PAUSED_INDICATORS = [
        "\u23f8", "\u275a\u275a", "paused",
    ]

    def __init__(self):
        self.is_playing = False
        self.is_paused = False
        self.current_track = ""
        self.current_app = ""
        self._was_playing = False
        self._audio_check_available = True

    def _is_browser(self, title_lower: str) -> str | None:
        for b in self.BROWSERS:
            if b in title_lower:
                return b
        return None

    def _has_music_site(self, title_lower: str) -> str | None:
        for site in self.MUSIC_SITES:
            if site in title_lower:
                return site
        return None

    def _is_dedicated_app(self, title_lower: str) -> str | None:
        for app in self.DEDICATED_MUSIC_APPS:
            if app in title_lower:
                return app
        return None

    def detect_from_all_windows(self) -> dict:
        """Scan ALL open windows with smart detection."""
        try:
            all_windows = gw.getAllWindows()
        except Exception:
            return self._no_change_result()

        found_music_app = False
        best_playing = None

        for win in all_windows:
            title = win.title
            if not title or len(title) < 3:
                continue
            title_lower = title.lower()

            has_play = any(ind in title or ind in title_lower
                          for ind in self.PLAYING_INDICATORS)
            has_pause = any(ind in title or ind in title_lower
                           for ind in self.PAUSED_INDICATORS)

            # BROWSER WINDOWS
            browser = self._is_browser(title_lower)
            if browser:
                music_site = self._has_music_site(title_lower)
                if not music_site:
                    continue

                found_music_app = True

                if has_play and not has_pause:
                    best_playing = (title, True, False, 100)
                    break
                elif has_pause:
                    if best_playing is None or best_playing[3] < 50:
                        best_playing = (title, False, True, 50)
                continue

            # DEDICATED MUSIC APPS
            ded_app = self._is_dedicated_app(title_lower)
            if not ded_app:
                continue

            found_music_app = True

            if has_play and not has_pause:
                best_playing = (title, True, False, 100)
                break
            if has_pause:
                if best_playing is None or best_playing[3] < 50:
                    best_playing = (title, False, True, 50)
                continue

            if ded_app == "spotify":
                if not title_lower.startswith("spotify") and " - " in title:
                    confidence = 80
                    if best_playing is None or best_playing[3] < confidence:
                        best_playing = (title, True, False, confidence)
                continue

            if ded_app == "vlc":
                if re.search(r".+\s*-\s*vlc", title_lower):
                    confidence = 75
                    if best_playing is None or best_playing[3] < confidence:
                        best_playing = (title, True, False, confidence)
                continue

            if ded_app == "foobar":
                if re.search(r".+\[foobar", title_lower):
                    confidence = 75
                    if best_playing is None or best_playing[3] < confidence:
                        best_playing = (title, True, False, confidence)
                continue

        if best_playing is None:
            self._was_playing = self.is_playing
            if self.is_playing:
                self.is_playing = False
                self.is_paused = False
                return {
                    "is_music_app": found_music_app,
                    "is_playing": False,
                    "is_paused": False,
                    "track": self.current_track,
                    "app": self.current_app,
                    "just_started": False,
                    "just_stopped": True,
                }
            return self._no_change_result()

        title, playing, paused, confidence = best_playing
        self._was_playing = self.is_playing
        self.is_playing = playing
        self.is_paused = paused
        self.current_app = self._detect_app(title.lower())
        self.current_track = self._extract_track(title)

        just_started = self.is_playing and not self._was_playing
        just_stopped = not self.is_playing and self._was_playing

        return {
            "is_music_app": True,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "track": self.current_track,
            "app": self.current_app,
            "just_started": just_started,
            "just_stopped": just_stopped,
        }

    def _no_change_result(self):
        return {
            "is_music_app": False,
            "is_playing": self.is_playing,
            "is_paused": self.is_paused,
            "track": self.current_track,
            "app": self.current_app,
            "just_started": False,
            "just_stopped": False,
        }

    def _detect_app(self, title: str) -> str:
        for site in self.MUSIC_SITES:
            if site in title:
                return site
        for app in self.DEDICATED_MUSIC_APPS:
            if app in title:
                return app
        return ""

    def _extract_track(self, title: str) -> str:
        cleaned = title
        for ind in self.PLAYING_INDICATORS + self.PAUSED_INDICATORS:
            cleaned = cleaned.replace(ind, "")
        for suffix in [" - YouTube", " - YouTube Music", " | Spotify",
                       " - Spotify", " - SoundCloud", " - Google Chrome",
                       " - Mozilla Firefox", " - Microsoft Edge",
                       " - Brave", " - Opera", " - VLC media player",
                       " [foobar2000]"]:
            if cleaned.lower().endswith(suffix.lower()):
                cleaned = cleaned[:-len(suffix)]
        return cleaned.strip()
