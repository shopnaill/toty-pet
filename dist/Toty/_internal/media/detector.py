import logging
import re

import pygetwindow as gw

log = logging.getLogger("toty.music")

# Try to import pycaw for system-level audio detection
try:
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    _HAS_PYCAW = True
except ImportError:
    _HAS_PYCAW = False


class MusicDetector:
    """Detects whether music/media is currently playing.

    Detection strategy (layered):
    1. **System audio sessions** (pycaw / WASAPI): Detects ANY app producing audio
       on Windows — browsers, games, media players, anything.
    2. **Window title scanning** (fallback): Extract track names, play/pause state
       from window titles for richer info.
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

    # Process names to ignore (system sounds, not real media)
    _IGNORE_PROCESSES = {
        "systemsounds", "svchost.exe", "runtimebroker.exe",
        "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
        "audiodg.exe", "taskhostw.exe", "explorer.exe",
        # OEM audio control panels
        "hpaudiocontrol_19h1.exe", "hpaudiocontrol.exe",
        "realtek audio console.exe", "realtekserviceprocess.exe",
        "nahimic3.exe", "nahimicservice.exe",
        "dolbydam.exe", "maxoaudiopro.exe",
        # Communication apps (audio sessions exist but it's not media)
        "msedgewebview2.exe", "widgets.exe",
        "gamebar.exe", "gamebarftserver.exe",
    }

    def __init__(self):
        self.is_playing = False
        self.is_paused = False
        self.current_track = ""
        self.current_app = ""
        self._was_playing = False
        self._audio_sessions_cache: list[str] = []  # process names producing audio

    # ==================================================================
    #  SYSTEM-LEVEL AUDIO DETECTION  (pycaw / WASAPI)
    # ==================================================================
    def _get_active_audio_sessions(self) -> list[dict]:
        """Return list of processes currently producing audio.

        Uses both volume level check AND audio meter peak to confirm
        actual audio output (not just an open session).
        """
        if not _HAS_PYCAW:
            return []
        results = []
        try:
            sessions = AudioUtilities.GetAllSessions()
            for s in sessions:
                if s.Process is None:
                    continue
                proc_name = s.Process.name().lower()
                if proc_name in self._IGNORE_PROCESSES:
                    continue
                try:
                    vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                    muted = vol.GetMute()
                    level = vol.GetMasterVolume()
                except Exception:
                    muted = False
                    level = 1.0
                if muted or level < 0.01:
                    continue

                # Check actual audio meter peak — confirms sound is really playing
                actually_producing = False
                try:
                    from pycaw.pycaw import IAudioMeterInformation
                    meter = s._ctl.QueryInterface(IAudioMeterInformation)
                    peak = meter.GetPeakValue()
                    actually_producing = peak > 0.001
                except Exception:
                    # If meter check fails, fall back to volume-only check
                    actually_producing = True

                if actually_producing:
                    results.append({
                        "process": proc_name,
                        "pid": s.Process.pid,
                        "volume": level,
                    })
        except Exception as e:
            log.debug("pycaw session scan failed: %s", e)
        return results

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
        """Scan for audio using system audio sessions + window titles."""

        # Layer 1: System-level audio session detection
        audio_sessions = self._get_active_audio_sessions()
        audio_process_names = [s["process"] for s in audio_sessions]
        system_audio_playing = len(audio_sessions) > 0

        # Layer 2: Window title scanning for track name / richer info
        try:
            all_windows = gw.getAllWindows()
        except Exception:
            all_windows = []

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
                    # Check if browser is in audio sessions (playing any audio)
                    browser_procs = ("chrome.exe", "firefox.exe", "msedge.exe",
                                     "brave.exe", "opera.exe", "vivaldi.exe")
                    browser_has_audio = any(p in audio_process_names for p in browser_procs)
                    if browser_has_audio and not has_pause:
                        found_music_app = True
                        if best_playing is None or best_playing[3] < 60:
                            best_playing = (title, True, False, 60)
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

        # Layer 3: If window titles found nothing but system audio IS playing,
        # use system-level detection as fallback
        if best_playing is None and system_audio_playing:
            # Try to identify the app name from the audio session process
            app_name = self._process_to_app_name(audio_process_names)
            found_music_app = True
            best_playing = (app_name or "Audio playing", True, False, 55)

        # Cache active audio processes for external queries
        self._audio_sessions_cache = audio_process_names

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
        # Check against cached audio sessions
        for proc in self._audio_sessions_cache:
            friendly = self._process_to_app_name([proc])
            if friendly:
                return friendly
        return ""

    @staticmethod
    def _process_to_app_name(process_names: list[str]) -> str:
        """Convert process names to friendly app names."""
        _MAP = {
            "spotify.exe": "Spotify",
            "chrome.exe": "Chrome",
            "firefox.exe": "Firefox",
            "msedge.exe": "Edge",
            "brave.exe": "Brave",
            "opera.exe": "Opera",
            "vivaldi.exe": "Vivaldi",
            "vlc.exe": "VLC",
            "mpv.exe": "mpv",
            "foobar2000.exe": "foobar2000",
            "musicbee.exe": "MusicBee",
            "aimp.exe": "AIMP",
            "winamp.exe": "Winamp",
            "wmplayer.exe": "Windows Media Player",
            "music.ui.exe": "Groove Music",
            "microsoft.media.player.exe": "Media Player",
            "itunes.exe": "iTunes",
            "audiodg.exe": "",  # system audio device graph — skip
        }
        for proc in process_names:
            name = _MAP.get(proc, "")
            if name:
                return name
        # Return first non-empty process name as fallback
        for proc in process_names:
            if proc and proc not in ("audiodg.exe",):
                return proc.replace(".exe", "").capitalize()
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
