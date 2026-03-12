"""Auto-dependency installer — ensures external tools are available."""
import os
import sys
import shutil
import subprocess
import logging
import threading
from typing import Optional

log = logging.getLogger("toty.auto_deps")

# ── pip helper ───────────────────────────────────────────────────────
def _pip_install(package: str) -> bool:
    """Install a Python package via pip. Returns True on success."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", package],
            capture_output=True, text=True, timeout=120,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0:
            log.info("pip install %s: OK", package)
            return True
        log.warning("pip install %s failed: %s", package, r.stderr[:200])
        return False
    except Exception as e:
        log.warning("pip install %s error: %s", package, e)
        return False


def _pip_installed(module_name: str) -> bool:
    """Check if a Python module is importable."""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


# ── winget helper ────────────────────────────────────────────────────
def _has_winget() -> bool:
    return shutil.which("winget") is not None


def _winget_install(package_id: str) -> bool:
    """Install via winget silently. Returns True on success."""
    if not _has_winget():
        log.warning("winget not available")
        return False
    try:
        r = subprocess.run(
            ["winget", "install", "--id", package_id,
             "--accept-source-agreements", "--accept-package-agreements",
             "--silent"],
            capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        ok = r.returncode == 0 or "already installed" in r.stdout.lower()
        if ok:
            log.info("winget install %s: OK", package_id)
            _refresh_path()
        else:
            log.warning("winget install %s failed (code %d): %s",
                        package_id, r.returncode, r.stderr[:200])
        return ok
    except subprocess.TimeoutExpired:
        log.warning("winget install %s timed out", package_id)
        return False
    except Exception as e:
        log.warning("winget install %s error: %s", package_id, e)
        return False


def _refresh_path():
    """Re-read PATH from registry so newly-installed tools are found."""
    try:
        parts = []
        for root, sub in [
            (r"HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment", "Path"),
            (r"HKCU\Environment", "Path"),
        ]:
            r = subprocess.run(
                ["reg", "query", root, "/v", sub],
                capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if r.returncode == 0:
                for line in r.stdout.splitlines():
                    if "REG_" in line:
                        parts.append(line.split("    ")[-1].strip())
        if parts:
            os.environ["Path"] = ";".join(parts)
    except Exception:
        pass


# ═════════════════════════════════════════════════════════════════════
#  Specific dependency checkers / installers
# ═════════════════════════════════════════════════════════════════════

# ── ffmpeg ───────────────────────────────────────────────────────────
_FFMPEG_PATHS = [
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    os.path.expanduser(r"~\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe"),
    os.path.expanduser(r"~\scoop\shims\ffmpeg.exe"),
]

def find_ffmpeg() -> Optional[str]:
    """Find ffmpeg on PATH or well-known locations."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    _refresh_path()
    found = shutil.which("ffmpeg")
    if found:
        return found
    for p in _FFMPEG_PATHS:
        if os.path.isfile(p):
            return p
    return None


def ensure_ffmpeg(callback=None):
    """Find or auto-install ffmpeg. If callback provided, runs async.
    callback(path_or_None) called when done."""
    path = find_ffmpeg()
    if path:
        if callback:
            callback(path)
        return path

    log.info("ffmpeg not found, attempting auto-install via winget...")
    if callback:
        def _bg():
            _winget_install("Gyan.FFmpeg")
            result = find_ffmpeg()
            callback(result)
        threading.Thread(target=_bg, daemon=True).start()
        return None
    else:
        _winget_install("Gyan.FFmpeg")
        return find_ffmpeg()


# ── 7-Zip ────────────────────────────────────────────────────────────
_7Z_PATHS = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\7-Zip\7z.exe"),
]

def find_7z() -> Optional[str]:
    """Find 7z.exe on PATH or well-known locations."""
    found = shutil.which("7z") or shutil.which("7za")
    if found:
        return found
    for p in _7Z_PATHS:
        if os.path.isfile(p):
            return p
    return None


def ensure_7z(callback=None):
    """Find or auto-install 7-Zip."""
    path = find_7z()
    if path:
        if callback:
            callback(path)
        return path

    log.info("7-Zip not found, attempting auto-install via winget...")
    if callback:
        def _bg():
            _winget_install("7zip.7zip")
            result = find_7z()
            callback(result)
        threading.Thread(target=_bg, daemon=True).start()
        return None
    else:
        _winget_install("7zip.7zip")
        return find_7z()


# ── git ──────────────────────────────────────────────────────────────
def find_git() -> Optional[str]:
    found = shutil.which("git")
    if found:
        return found
    _refresh_path()
    return shutil.which("git")


def ensure_git(callback=None):
    """Find or auto-install git."""
    path = find_git()
    if path:
        if callback:
            callback(path)
        return path

    log.info("git not found, attempting auto-install via winget...")
    if callback:
        def _bg():
            _winget_install("Git.Git")
            result = find_git()
            callback(result)
        threading.Thread(target=_bg, daemon=True).start()
        return None
    else:
        _winget_install("Git.Git")
        return find_git()


# ── SpeechRecognition (pip) ──────────────────────────────────────────
def ensure_speech_recognition() -> bool:
    """Ensure speech_recognition is importable; pip-install if needed."""
    if _pip_installed("speech_recognition"):
        return True
    log.info("speech_recognition not found, installing via pip...")
    ok = _pip_install("SpeechRecognition")
    return ok and _pip_installed("speech_recognition")


# ── Ollama ───────────────────────────────────────────────────────────
def find_ollama() -> Optional[str]:
    found = shutil.which("ollama")
    if found:
        return found
    for p in [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
    ]:
        if os.path.isfile(p):
            return p
    return None


def ensure_ollama(callback=None):
    """Find or auto-install Ollama."""
    path = find_ollama()
    if path:
        if callback:
            callback(path)
        return path

    log.info("Ollama not found, attempting auto-install via winget...")
    if callback:
        def _bg():
            _winget_install("Ollama.Ollama")
            result = find_ollama()
            callback(result)
        threading.Thread(target=_bg, daemon=True).start()
        return None
    else:
        _winget_install("Ollama.Ollama")
        return find_ollama()


# ═════════════════════════════════════════════════════════════════════
#  Startup check — install all missing deps in background
# ═════════════════════════════════════════════════════════════════════
def ensure_all_async(callback=None):
    """Background thread: install all missing deps at once.
    callback(results_dict) when done."""
    def _work():
        results = {}

        # pip packages first (fast)
        results["speech_recognition"] = ensure_speech_recognition()

        # binaries via winget (slower)
        if not find_ffmpeg():
            ensure_ffmpeg()
        results["ffmpeg"] = find_ffmpeg()

        if not find_7z():
            ensure_7z()
        results["7z"] = find_7z()

        if not find_git():
            ensure_git()
        results["git"] = find_git()

        # Ollama is large (~800MB), only install if user opts in
        results["ollama"] = find_ollama()

        log.info("Auto-deps results: %s",
                 {k: bool(v) for k, v in results.items()})
        if callback:
            callback(results)

    threading.Thread(target=_work, daemon=True).start()
