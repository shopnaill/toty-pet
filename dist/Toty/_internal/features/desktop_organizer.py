"""
Desktop Auto-Organizer — Monitors the desktop and organizes files into folders.

Extensible rule-based system:
  - Each rule has: name, extensions, folder_name, icon
  - Easy to add new rules for Documents, Videos, Music, etc.
"""

import os
import shutil
import time
import ctypes
import ctypes.wintypes
from datetime import datetime


# ══════════════════════════════════════════════════════════════
#  ORGANIZATION RULES — extend this list to add new categories
# ══════════════════════════════════════════════════════════════

ORGANIZE_RULES = [
    {
        "name": "Photos",
        "extensions": {
            ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp",
            ".tiff", ".tif", ".ico", ".svg", ".heic", ".heif",
            ".raw", ".cr2", ".nef", ".arw",
        },
        "folder": "Photos",
        "icon": "📸",
        "speech_key": "organize_photo",
    },
    {
        "name": "Documents",
        "extensions": {
            ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt",
            ".xlsx", ".xls", ".pptx", ".ppt", ".csv",
            ".md", ".xml", ".json", ".html", ".htm",
        },
        "folder": "Documents",
        "icon": "📄",
        "speech_key": "organize_document",
    },
    {
        "name": "Videos",
        "extensions": {
            ".mp4", ".mkv", ".avi", ".mov", ".wmv",
            ".flv", ".webm", ".m4v", ".mpg", ".mpeg",
            ".3gp", ".ts",
        },
        "folder": "Videos",
        "icon": "🎬",
        "speech_key": "organize_video",
    },
    {
        "name": "Music",
        "extensions": {
            ".mp3", ".wav", ".flac", ".aac", ".ogg",
            ".wma", ".m4a", ".opus", ".mid", ".midi",
        },
        "folder": "Music",
        "icon": "🎵",
        "speech_key": "organize_music",
    },
    {
        "name": "Archives",
        "extensions": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "folder": "Archives",
        "icon": "📦",
        "speech_key": "organize_archive",
    },
    # ── Add more rules here ──────────────────────────────
    # NOTE: .exe / .msi / .lnk are intentionally excluded (apps & shortcuts stay on desktop)
]


def _get_desktop_path() -> str:
    """Return the current user's Desktop path (handles OneDrive redirection)."""
    home = os.path.expanduser("~")

    # Try Windows shell folder registry / known folder first
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
        ) as key:
            raw, _ = winreg.QueryValueEx(key, "Desktop")
            desktop = os.path.expandvars(raw)
            if os.path.isdir(desktop):
                return desktop
    except (ImportError, OSError):
        pass

    # OneDrive-redirected desktop (common on Windows 10/11)
    onedrive_desktop = os.path.join(home, "OneDrive", "Desktop")
    if os.path.isdir(onedrive_desktop):
        return onedrive_desktop

    # Standard fallback
    return os.path.join(home, "Desktop")


# ══════════════════════════════════════════════════════════════
#  DESKTOP ICON POSITION DETECTION (Windows shell via ctypes)
# ══════════════════════════════════════════════════════════════

def _get_desktop_icon_positions() -> dict[str, tuple[int, int]]:
    """
    Return {filename: (screen_x, screen_y)} for every icon on the desktop.

    Uses the SysListView32 approach: find the desktop ListView window,
    allocate memory in explorer's process, and read icon positions via
    LVM_GETITEMCOUNT / LVM_GETITEMPOSITION / LVM_GETITEMTEXT.
    Falls back to an empty dict on any failure.
    """
    positions: dict[str, tuple[int, int]] = {}
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Constants
        LVM_FIRST = 0x1000
        LVM_GETITEMCOUNT = LVM_FIRST + 4
        LVM_GETITEMPOSITION = LVM_FIRST + 16
        LVM_GETITEMTEXTW = LVM_FIRST + 115

        PROCESS_VM_OPERATION = 0x0008
        PROCESS_VM_READ = 0x0010
        PROCESS_VM_WRITE = 0x0020
        MEM_COMMIT = 0x1000
        MEM_RELEASE = 0x8000
        PAGE_READWRITE = 0x04

        # Find SysListView32 inside the desktop
        progman = user32.FindWindowW("Progman", None)
        if not progman:
            return positions

        # Try SHELLDLL_DefView > SysListView32 under Progman first
        def_view = user32.FindWindowExW(progman, 0, "SHELLDLL_DefView", None)
        if not def_view:
            # Sometimes it's under a WorkerW window
            def _enum_cb(hwnd, _):
                dv = user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
                if dv:
                    _enum_cb.result = dv
                    return False
                return True
            _enum_cb.result = 0
            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
            def_view = _enum_cb.result

        if not def_view:
            return positions

        listview = user32.FindWindowExW(def_view, 0, "SysListView32", None)
        if not listview:
            return positions

        count = user32.SendMessageW(listview, LVM_GETITEMCOUNT, 0, 0)
        if count <= 0:
            return positions

        # Get explorer PID
        pid = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(listview, ctypes.byref(pid))
        hproc = kernel32.OpenProcess(
            PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE,
            False, pid.value,
        )
        if not hproc:
            return positions

        try:
            # Allocate memory in explorer for POINT struct (8 bytes)
            point_buf = kernel32.VirtualAllocEx(
                hproc, 0, 8, MEM_COMMIT, PAGE_READWRITE,
            )
            # Allocate for LVITEMW struct + text buffer
            LVITEM_SIZE = 60
            TEXT_BUF_SIZE = 520  # 260 * 2 for wide chars
            item_buf = kernel32.VirtualAllocEx(
                hproc, 0, LVITEM_SIZE + TEXT_BUF_SIZE, MEM_COMMIT, PAGE_READWRITE,
            )
            if not point_buf or not item_buf:
                return positions

            text_buf = item_buf + LVITEM_SIZE
            read = ctypes.c_size_t()

            for i in range(count):
                # --- Get position ---
                user32.SendMessageW(listview, LVM_GETITEMPOSITION, i, point_buf)
                point_data = (ctypes.c_byte * 8)()
                kernel32.ReadProcessMemory(hproc, point_buf, point_data, 8, ctypes.byref(read))
                x = int.from_bytes(bytes(point_data[0:4]), "little", signed=True)
                y = int.from_bytes(bytes(point_data[4:8]), "little", signed=True)

                # --- Get text ---
                # LVITEMW: mask=LVIF_TEXT(1), iItem=i, iSubItem=0, ..., pszText=text_buf, cchTextMax=260
                lvi = bytearray(LVITEM_SIZE)
                import struct as _struct
                _struct.pack_into("<I", lvi, 0, 1)        # mask = LVIF_TEXT
                _struct.pack_into("<i", lvi, 4, i)        # iItem
                _struct.pack_into("<i", lvi, 8, 0)        # iSubItem
                if ctypes.sizeof(ctypes.c_void_p) == 8:
                    _struct.pack_into("<Q", lvi, 24, text_buf)   # pszText (64-bit)
                    _struct.pack_into("<i", lvi, 32, 260)        # cchTextMax
                else:
                    _struct.pack_into("<I", lvi, 20, text_buf)   # pszText (32-bit)
                    _struct.pack_into("<i", lvi, 24, 260)        # cchTextMax

                written = ctypes.c_size_t()
                kernel32.WriteProcessMemory(hproc, item_buf, (ctypes.c_byte * LVITEM_SIZE)(*lvi),
                                            LVITEM_SIZE, ctypes.byref(written))
                user32.SendMessageW(listview, LVM_GETITEMTEXTW, i, item_buf)
                name_data = (ctypes.c_byte * TEXT_BUF_SIZE)()
                kernel32.ReadProcessMemory(hproc, text_buf, name_data, TEXT_BUF_SIZE, ctypes.byref(read))
                name = bytes(name_data).decode("utf-16-le").rstrip("\x00")

                if name:
                    # Convert ListView coords to screen coords
                    pt = ctypes.wintypes.POINT(x, y)
                    user32.ClientToScreen(listview, ctypes.byref(pt))
                    positions[name] = (pt.x, pt.y)

            kernel32.VirtualFreeEx(hproc, point_buf, 0, MEM_RELEASE)
            kernel32.VirtualFreeEx(hproc, item_buf, 0, MEM_RELEASE)
        finally:
            kernel32.CloseHandle(hproc)

    except Exception:
        pass  # Silently fail — animation will use fallback positions

    return positions


class DesktopOrganizer:
    """
    Watches the desktop for new files and moves them to organized sub-folders.

    Usage:
        organizer = DesktopOrganizer(settings)
        moved = organizer.scan_and_organize()
        # moved = [{"file": "screenshot_123.png", "rule": "Photos", ...}, ...]
    """

    def __init__(self, settings):
        self.settings = settings
        self.desktop_path = _get_desktop_path()
        # Track known files so we only act on NEW ones
        self._known_files: set[str] = set()
        self._initialized = False
        # File must be at least this old (seconds) before we move it
        # (avoids moving files still being written)
        self._min_age_sec = 5

    def initialize(self):
        """Snapshot the current desktop so we don't move old files."""
        self._known_files = self._scan_desktop_files()
        self._initialized = True

    def _scan_desktop_files(self) -> set[str]:
        """Return set of filenames currently on the desktop (not folders)."""
        try:
            return {
                f for f in os.listdir(self.desktop_path)
                if os.path.isfile(os.path.join(self.desktop_path, f))
            }
        except OSError:
            return set()

    def _find_matching_rule(self, filename: str) -> dict | None:
        """Find the first rule whose extensions match the file."""
        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            return None
        for rule in ORGANIZE_RULES:
            if ext in rule["extensions"]:
                return rule
        return None

    def _is_file_ready(self, filepath: str) -> bool:
        """Check if file is old enough and not being written."""
        try:
            mtime = os.path.getmtime(filepath)
            age = time.time() - mtime
            return age >= self._min_age_sec
        except OSError:
            return False

    def detect_files_to_organize(self, force_all: bool = False) -> list[dict]:
        """
        Scan desktop for files that match rules but DON'T move them yet.
        Returns list with file info + screen positions for animation.

        Each item: {"file", "filepath", "dest_folder", "dest_path",
                     "rule_name", "icon", "speech_key",
                     "file_pos": (x, y) | None, "folder_pos": (x, y) | None}
        """
        if not self._initialized:
            self.initialize()
            force_all = True

        current_files = self._scan_desktop_files()
        new_files = current_files if force_all else (current_files - self._known_files)

        # Get desktop icon positions for animation
        icon_positions = _get_desktop_icon_positions()

        items = []

        for filename in sorted(new_files):
            filepath = os.path.join(self.desktop_path, filename)

            if not self._is_file_ready(filepath):
                continue

            rule = self._find_matching_rule(filename)
            if not rule:
                self._known_files.add(filename)
                continue

            # Destination
            dest_folder = os.path.join(self.desktop_path, rule["folder"])
            os.makedirs(dest_folder, exist_ok=True)
            dest_path = os.path.join(dest_folder, filename)
            if os.path.exists(dest_path):
                name, ext = os.path.splitext(filename)
                ts = datetime.now().strftime("%H%M%S")
                dest_path = os.path.join(dest_folder, f"{name}_{ts}{ext}")

            # Icon name on desktop (without extension for some files)
            name_no_ext = os.path.splitext(filename)[0]
            file_pos = icon_positions.get(filename) or icon_positions.get(name_no_ext)
            folder_pos = icon_positions.get(rule["folder"])

            items.append({
                "file": filename,
                "filepath": filepath,
                "dest_folder": rule["folder"],
                "dest_path": dest_path,
                "rule_name": rule["name"],
                "icon": rule["icon"],
                "speech_key": rule["speech_key"],
                "file_pos": file_pos,
                "folder_pos": folder_pos,
            })

        return items

    def move_file(self, item: dict) -> bool:
        """Actually move a single file. Returns True on success."""
        try:
            os.makedirs(os.path.dirname(item["dest_path"]), exist_ok=True)
            shutil.move(item["filepath"], item["dest_path"])
            self._known_files.discard(item["file"])
            self._known_files = self._scan_desktop_files() | self._known_files
            return True
        except (OSError, shutil.Error):
            return False

    def scan_and_organize(self, force_all: bool = False) -> list[dict]:
        """
        Detect + move in one shot (used when animation is not needed).

        Returns list of dicts: [{"file", "dest_folder", "rule_name", "icon", "speech_key"}]
        """
        items = self.detect_files_to_organize(force_all=force_all)
        moved = []
        for item in items:
            if self.move_file(item):
                moved.append(item)
        return moved

    def get_stats(self) -> dict:
        """Return counts of organized folders on desktop."""
        stats = {}
        for rule in ORGANIZE_RULES:
            folder_path = os.path.join(self.desktop_path, rule["folder"])
            if os.path.isdir(folder_path):
                count = len([
                    f for f in os.listdir(folder_path)
                    if os.path.isfile(os.path.join(folder_path, f))
                ])
                stats[rule["name"]] = {"count": count, "icon": rule["icon"]}
        return stats

    def get_active_rules(self) -> list[dict]:
        """Return currently active rules."""
        return list(ORGANIZE_RULES)
