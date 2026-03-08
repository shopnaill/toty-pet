"""
Settings Export/Import & Backup — one-click export all pet data
to a ZIP file. Import from ZIP on a new machine.
"""
import json
import os
import shutil
import tempfile
import logging
from datetime import datetime
from zipfile import ZipFile
from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger("toty")

# Files to include in backup
BACKUP_FILES = [
    "settings.json",
    "stats.json",
    "habits.json",
    "journal.json",
    "sticky_notes.json",
    "reminders_v2.json",
    "social_data.json",
    "tasbeeh_data.json",
    "launcher_pins.json",
    "pet_memory.json",
    "todo_items.json",
    "web_tracker.json",
    "achievements.json",
]

BACKUP_DIRS = [
    "screenshots",
]


class BackupManager(QObject):
    """Handles export/import of all pet data."""
    export_done = pyqtSignal(str)     # zip path
    import_done = pyqtSignal(int)     # number of files restored
    error = pyqtSignal(str)

    def __init__(self, base_dir: str = "."):
        super().__init__()
        self._base = base_dir

    def export_backup(self, dest_path: str | None = None) -> str | None:
        """Create a ZIP backup of all pet data."""
        if not dest_path:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_path = os.path.join(self._base, f"toty_backup_{ts}.zip")
        try:
            with ZipFile(dest_path, "w") as zf:
                count = 0
                for fname in BACKUP_FILES:
                    fpath = os.path.join(self._base, fname)
                    if os.path.exists(fpath):
                        zf.write(fpath, fname)
                        count += 1
                for dname in BACKUP_DIRS:
                    dpath = os.path.join(self._base, dname)
                    if os.path.isdir(dpath):
                        for root, _, files in os.walk(dpath):
                            for f in files:
                                full = os.path.join(root, f)
                                arc = os.path.relpath(full, self._base)
                                zf.write(full, arc)
                                count += 1
            log.info("Backup exported: %s (%d files)", dest_path, count)
            self.export_done.emit(dest_path)
            return dest_path
        except Exception as exc:
            self.error.emit(f"Export failed: {exc}")
            return None

    def import_backup(self, zip_path: str) -> int:
        """Restore pet data from a ZIP backup."""
        if not os.path.exists(zip_path):
            self.error.emit("Backup file not found")
            return 0
        try:
            allowed = set(BACKUP_FILES)
            for d in BACKUP_DIRS:
                allowed.add(d + "/")
            count = 0
            with ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    name = info.filename
                    # Security: only extract known files, no path traversal
                    if ".." in name or name.startswith("/"):
                        continue
                    base_name = name.split("/")[0] if "/" in name else name
                    if base_name in BACKUP_FILES or base_name in BACKUP_DIRS:
                        zf.extract(info, self._base)
                        count += 1
            log.info("Backup imported: %d files from %s", count, zip_path)
            self.import_done.emit(count)
            return count
        except Exception as exc:
            self.error.emit(f"Import failed: {exc}")
            return 0

    def list_backups(self) -> list[str]:
        """List existing backup ZIP files."""
        backups = []
        for f in os.listdir(self._base):
            if f.startswith("toty_backup_") and f.endswith(".zip"):
                backups.append(f)
        return sorted(backups, reverse=True)

    def get_backup_info(self, zip_path: str) -> dict:
        """Get info about a backup file."""
        try:
            with ZipFile(zip_path, "r") as zf:
                return {
                    "file_count": len(zf.namelist()),
                    "files": zf.namelist(),
                    "size_bytes": os.path.getsize(zip_path),
                }
        except Exception:
            return {}
