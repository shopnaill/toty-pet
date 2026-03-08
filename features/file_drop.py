"""
File Drop Zone — allows dragging files onto the pet for quick actions.
Actions: compress images, run scripts, organize, summarize text with AI.
"""
import os
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtCore import pyqtSignal, QObject


class FileDropHandler(QObject):
    """Processes files dropped onto the pet widget."""
    action_done = pyqtSignal(str, str)  # (action_type, message)

    # Extension → category mapping
    _IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tiff"}
    _CODE_EXT = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".rb", ".php"}
    _TEXT_EXT = {".txt", ".md", ".log", ".csv", ".json", ".xml", ".yaml", ".yml", ".ini", ".cfg"}
    _ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz"}

    def handle_drop(self, file_paths: list[str]) -> list[dict]:
        """Analyze dropped files and return list of available actions."""
        results = []
        for fp in file_paths:
            p = Path(fp)
            if not p.exists():
                continue

            if p.is_dir():
                file_count = sum(1 for _ in p.iterdir() if _.is_file())
                results.append({
                    "path": fp,
                    "name": p.name,
                    "kind": "folder",
                    "detail": f"{file_count} files",
                    "actions": ["organize", "count"],
                })
            else:
                ext = p.suffix.lower()
                size = p.stat().st_size
                size_str = self._format_size(size)
                kind = self._categorize(ext)
                actions = self._get_actions(kind, ext)
                results.append({
                    "path": fp,
                    "name": p.name,
                    "kind": kind,
                    "detail": size_str,
                    "ext": ext,
                    "actions": actions,
                })
        return results

    def execute_action(self, file_info: dict, action: str) -> str:
        """Execute a specific action on a file. Returns result message."""
        path = file_info["path"]
        name = file_info["name"]

        if action == "run" and file_info.get("ext") == ".py":
            return self._run_python(path)
        elif action == "count":
            return self._count_lines(path)
        elif action == "info":
            return self._file_info(path)
        elif action == "copy_path":
            return path
        elif action == "open_folder":
            folder = os.path.dirname(path)
            os.startfile(folder)
            return f"Opened folder for {name}"
        elif action == "organize" and file_info["kind"] == "folder":
            return self._organize_folder(path)
        return f"Unknown action: {action}"

    def _categorize(self, ext: str) -> str:
        if ext in self._IMAGE_EXT:
            return "image"
        if ext in self._CODE_EXT:
            return "code"
        if ext in self._TEXT_EXT:
            return "text"
        if ext in self._ARCHIVE_EXT:
            return "archive"
        return "file"

    def _get_actions(self, kind: str, ext: str) -> list[str]:
        actions = ["info", "copy_path", "open_folder"]
        if kind == "code":
            actions.insert(0, "count")
            if ext == ".py":
                actions.insert(0, "run")
        elif kind == "text":
            actions.insert(0, "count")
        elif kind == "image":
            actions.insert(0, "info")
        return actions

    def _run_python(self, path: str) -> str:
        """Run a Python script and capture output (with timeout)."""
        try:
            result = subprocess.run(
                ["python", path],
                capture_output=True, text=True, timeout=10,
                cwd=os.path.dirname(path),
            )
            output = result.stdout.strip()
            if result.returncode != 0:
                err = result.stderr.strip()
                return f"❌ Error:\n{err[:200]}"
            return f"✅ Output:\n{output[:300]}" if output else "✅ Ran successfully (no output)"
        except subprocess.TimeoutExpired:
            return "⏱️ Script timed out (10s limit)"
        except Exception as e:
            return f"❌ Failed: {e}"

    def _count_lines(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            non_empty = sum(1 for ln in lines if ln.strip())
            return f"📄 {len(lines)} lines ({non_empty} non-empty)"
        except Exception:
            return "Could not count lines"

    def _file_info(self, path: str) -> str:
        p = Path(path)
        size = self._format_size(p.stat().st_size)
        ext = p.suffix
        return f"📁 {p.name}\nSize: {size} | Type: {ext or 'none'}"

    def _organize_folder(self, path: str) -> str:
        """Organize files in a folder by extension."""
        p = Path(path)
        moved = 0
        for f in p.iterdir():
            if f.is_file() and f.suffix:
                category = self._categorize(f.suffix.lower())
                dest = p / category
                dest.mkdir(exist_ok=True)
                shutil.move(str(f), str(dest / f.name))
                moved += 1
        return f"📂 Organized {moved} files into sub-folders"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
