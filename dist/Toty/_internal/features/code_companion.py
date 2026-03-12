"""
Code Companion — Git-aware and build-aware assistant.
Tracks edited files, uncommitted changes, build status, and coding patterns.
"""
import os
import subprocess
import time
from pathlib import Path
from PyQt6.QtCore import QTimer, pyqtSignal, QObject


class CodeCompanion(QObject):
    """Watches git repos and build processes for developer feedback."""
    alert = pyqtSignal(str, str)  # (alert_type, message)

    # Alert types: "uncommitted", "long_no_commit", "build_fail", "build_pass",
    #              "branch_info", "merge_conflict", "file_focus"

    def __init__(self, check_interval_ms: int = 60000):
        super().__init__()
        self._last_commit_check = 0.0
        self._last_commit_time = 0.0
        self._last_branch = ""
        self._last_uncommitted = 0
        self._watched_dirs: list[str] = []
        self._file_edit_times: dict[str, float] = {}  # path → last edit time
        self._alert_cooldown: dict[str, float] = {}
        self._cooldown_sec = 300.0  # 5 min between same alert

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(check_interval_ms)

    def stop(self):
        self._timer.stop()

    def add_watch_dir(self, path: str):
        """Add a directory to watch for git activity."""
        if path not in self._watched_dirs:
            self._watched_dirs.append(path)

    def detect_repo_from_window(self, window_title: str):
        """Try to detect git repo from window title (VS Code, PyCharm, etc.)."""
        # VS Code: "filename - foldername - Visual Studio Code"
        parts = window_title.split(" - ")
        if len(parts) >= 2:
            folder = parts[-2].strip() if "visual studio code" in window_title.lower() else parts[0].strip()
            # Check common dev directories
            for base in [os.path.expanduser("~"), "D:\\", "C:\\"]:
                candidate = os.path.join(base, folder)
                if os.path.isdir(os.path.join(candidate, ".git")):
                    self.add_watch_dir(candidate)
                    return candidate
        return None

    def _should_alert(self, key: str) -> bool:
        now = time.time()
        last = self._alert_cooldown.get(key, 0)
        if now - last < self._cooldown_sec:
            return False
        self._alert_cooldown[key] = now
        return True

    def _run_git(self, repo_dir: str, *args) -> str | None:
        try:
            result = subprocess.run(
                ["git"] + list(args),
                capture_output=True, text=True, timeout=5,
                cwd=repo_dir,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def _check(self):
        for repo_dir in self._watched_dirs:
            if not os.path.isdir(os.path.join(repo_dir, ".git")):
                continue
            self._check_repo(repo_dir)

    def _check_repo(self, repo_dir: str):
        repo_name = os.path.basename(repo_dir)

        # Branch check
        branch = self._run_git(repo_dir, "branch", "--show-current")
        if branch and branch != self._last_branch:
            if self._last_branch:
                self.alert.emit("branch_info", f"Switched to branch: {branch}")
            self._last_branch = branch

        # Uncommitted changes
        status = self._run_git(repo_dir, "status", "--porcelain")
        if status is not None:
            uncommitted = len([ln for ln in status.split("\n") if ln.strip()])
            if uncommitted > 5 and uncommitted != self._last_uncommitted:
                if self._should_alert("uncommitted"):
                    self.alert.emit(
                        "uncommitted",
                        f"You have {uncommitted} uncommitted changes in {repo_name}!"
                    )
            self._last_uncommitted = uncommitted

        # Time since last commit — commit nudge if >2h AND >5 files
        log = self._run_git(repo_dir, "log", "-1", "--format=%ct")
        if log:
            try:
                last_commit = float(log)
                hours = (time.time() - last_commit) / 3600
                if hours > 2 and uncommitted > 5:
                    if self._should_alert("commit_nudge"):
                        self.alert.emit(
                            "commit_nudge",
                            f"💾 {uncommitted} files changed over {hours:.0f}h in {repo_name} — time to commit!"
                        )
                elif hours > 3:
                    if self._should_alert("long_no_commit"):
                        self.alert.emit(
                            "long_no_commit",
                            f"Last commit was {hours:.0f}h ago. Time to commit?"
                        )
            except ValueError:
                pass

        # Merge conflicts
        if status and any(ln.startswith("UU") or ln.startswith("AA") for ln in status.split("\n")):
            if self._should_alert("merge_conflict"):
                self.alert.emit("merge_conflict", f"⚠️ Merge conflicts detected in {repo_name}!")

    def get_repo_summary(self) -> str:
        """Get a summary of all watched repos."""
        if not self._watched_dirs:
            return "No git repos being watched."
        lines = ["🔧 Code Companion:"]
        for repo_dir in self._watched_dirs:
            name = os.path.basename(repo_dir)
            branch = self._run_git(repo_dir, "branch", "--show-current") or "?"
            status = self._run_git(repo_dir, "status", "--porcelain")
            changes = len([ln for ln in (status or "").split("\n") if ln.strip()])
            lines.append(f"  {name} ({branch}): {changes} changes")
        return "\n".join(lines)
