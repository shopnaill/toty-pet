"""Folder Locker — pro folder protection with rename obfuscation & brute-force guard."""
import os
import json
import hashlib
import logging
import re
import time
import uuid
import subprocess
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QProgressBar, QWidget,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor
from core.safe_json import safe_json_save

log = logging.getLogger("toty.folder_locker")
_FILE = "locked_folders.json"
_MAX_ATTEMPTS = 3
_LOCKOUT_SECS = 30


def _hash_pw(pw: str, salt: str = "") -> str:
    return hashlib.sha256((salt + pw).encode("utf-8")).hexdigest()


def _hide_folder(path: str):
    """Set hidden + system attributes on Windows."""
    try:
        subprocess.run(
            ["attrib", "+H", "+S", path],
            check=True, capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        log.error("Failed to hide folder: %s", e)


def _unhide_folder(path: str):
    """Remove hidden + system attributes on Windows."""
    try:
        subprocess.run(
            ["attrib", "-H", "-S", path],
            check=True, capture_output=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception as e:
        log.error("Failed to unhide folder: %s", e)


def _pw_strength(pw: str) -> tuple[int, str, str]:
    """Return (score 0-4, label, color)."""
    score = 0
    if len(pw) >= 8:
        score += 1
    if len(pw) >= 12:
        score += 1
    if re.search(r"[A-Z]", pw) and re.search(r"[a-z]", pw):
        score += 1
    if re.search(r"\d", pw):
        score += 1
    if re.search(r"[^A-Za-z0-9]", pw):
        score += 1
    labels = [
        (0, "Very Weak", "#F38BA8"),
        (1, "Weak", "#FAB387"),
        (2, "Fair", "#F9E2AF"),
        (3, "Strong", "#A6E3A1"),
        (4, "Very Strong", "#94E2D5"),
    ]
    score = min(score, 4)
    return labels[score]


class FolderLocker:
    """Manages locked folders with rename obfuscation & brute-force protection."""

    def __init__(self):
        self._locked: list[dict] = []
        # {path, original_name, obfuscated_name, hash, salt, locked, failed_attempts, lockout_until}
        self._load()

    def lock(self, folder_path: str, password: str) -> bool:
        """Lock a folder: rename to UUID, hide it, store salted hash."""
        if not os.path.isdir(folder_path):
            return False
        norm = os.path.normpath(folder_path)
        for entry in self._locked:
            if os.path.normpath(entry["path"]) == norm:
                if not entry["locked"]:
                    return self._relock(entry, password)
                return False

        salt = uuid.uuid4().hex[:16]
        original_name = os.path.basename(norm)
        obf_name = f".toty_{uuid.uuid4().hex[:12]}"
        parent = os.path.dirname(norm)
        obf_path = os.path.join(parent, obf_name)

        try:
            os.rename(norm, obf_path)
        except OSError as e:
            log.error("Failed to rename folder: %s", e)
            return False

        _hide_folder(obf_path)
        self._locked.append({
            "path": parent,
            "original_name": original_name,
            "obfuscated_name": obf_name,
            "hash": _hash_pw(password, salt),
            "salt": salt,
            "locked": True,
            "failed_attempts": 0,
            "lockout_until": 0,
        })
        self._save()
        log.info("Folder locked: %s → %s", original_name, obf_name)
        return True

    def _relock(self, entry: dict, password: str) -> bool:
        """Re-lock a previously unlocked folder."""
        parent = entry["path"]
        orig = os.path.join(parent, entry["original_name"])
        if not os.path.isdir(orig):
            return False
        obf_name = f".toty_{uuid.uuid4().hex[:12]}"
        obf_path = os.path.join(parent, obf_name)
        try:
            os.rename(orig, obf_path)
        except OSError:
            return False
        _hide_folder(obf_path)
        salt = uuid.uuid4().hex[:16]
        entry["obfuscated_name"] = obf_name
        entry["hash"] = _hash_pw(password, salt)
        entry["salt"] = salt
        entry["locked"] = True
        entry["failed_attempts"] = 0
        entry["lockout_until"] = 0
        self._save()
        return True

    def unlock(self, entry_index: int, password: str) -> tuple[bool, str]:
        """Unlock by index. Returns (success, message)."""
        if entry_index < 0 or entry_index >= len(self._locked):
            return False, "Invalid entry."
        entry = self._locked[entry_index]
        if not entry["locked"]:
            return False, "Already unlocked."

        # Brute-force protection
        now = time.time()
        if entry.get("lockout_until", 0) > now:
            remaining = int(entry["lockout_until"] - now)
            return False, f"Too many attempts. Try again in {remaining}s."

        if _hash_pw(password, entry.get("salt", "")) != entry["hash"]:
            entry["failed_attempts"] = entry.get("failed_attempts", 0) + 1
            if entry["failed_attempts"] >= _MAX_ATTEMPTS:
                entry["lockout_until"] = now + _LOCKOUT_SECS
                entry["failed_attempts"] = 0
                self._save()
                return False, f"Wrong password! Locked out for {_LOCKOUT_SECS}s."
            left = _MAX_ATTEMPTS - entry["failed_attempts"]
            self._save()
            return False, f"Wrong password! {left} attempt(s) left."

        # Correct password — restore
        parent = entry["path"]
        obf_path = os.path.join(parent, entry["obfuscated_name"])
        orig_path = os.path.join(parent, entry["original_name"])
        _unhide_folder(obf_path)
        try:
            os.rename(obf_path, orig_path)
        except OSError as e:
            log.error("Failed to restore folder name: %s", e)
            return False, f"Rename error: {e}"

        entry["locked"] = False
        entry["failed_attempts"] = 0
        entry["lockout_until"] = 0
        self._save()
        log.info("Folder unlocked: %s", entry["original_name"])
        return True, "Unlocked successfully!"

    def change_password(self, entry_index: int, old_pw: str, new_pw: str) -> tuple[bool, str]:
        """Change password for a locked folder."""
        if entry_index < 0 or entry_index >= len(self._locked):
            return False, "Invalid entry."
        entry = self._locked[entry_index]
        if _hash_pw(old_pw, entry.get("salt", "")) != entry["hash"]:
            return False, "Current password is incorrect."
        salt = uuid.uuid4().hex[:16]
        entry["hash"] = _hash_pw(new_pw, salt)
        entry["salt"] = salt
        self._save()
        return True, "Password changed!"

    def get_locked(self) -> list[dict]:
        return [e for e in self._locked if e["locked"]]

    def get_all(self) -> list[dict]:
        return list(self._locked)

    def remove(self, entry_index: int):
        """Remove folder from tracking (auto-unlocks if locked)."""
        if entry_index < 0 or entry_index >= len(self._locked):
            return
        entry = self._locked[entry_index]
        if entry["locked"]:
            parent = entry["path"]
            obf_path = os.path.join(parent, entry["obfuscated_name"])
            orig_path = os.path.join(parent, entry["original_name"])
            _unhide_folder(obf_path)
            try:
                os.rename(obf_path, orig_path)
            except OSError:
                pass
        self._locked.pop(entry_index)
        self._save()

    def _save(self):
        try:
            safe_json_save({"folders": self._locked}, _FILE)
        except IOError:
            pass

    def _load(self):
        if os.path.exists(_FILE):
            try:
                with open(_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._locked = data.get("folders", [])
                # Migrate old entries that lack new fields
                for e in self._locked:
                    e.setdefault("salt", "")
                    e.setdefault("original_name", os.path.basename(e.get("path", "")))
                    e.setdefault("obfuscated_name", "")
                    e.setdefault("failed_attempts", 0)
                    e.setdefault("lockout_until", 0)
            except (json.JSONDecodeError, IOError):
                pass


# ── Password strength widget ─────────────────────────────────────────
class _PasswordStrengthBar(QWidget):
    """Inline password strength indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._bar = QProgressBar()
        self._bar.setRange(0, 4)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        self._bar.setStyleSheet(
            "QProgressBar { background: #313244; border-radius: 4px; }"
            "QProgressBar::chunk { background: #6C7086; border-radius: 4px; }")
        lay.addWidget(self._bar)
        self._lbl = QLabel("")
        self._lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        self._lbl.setFixedWidth(80)
        lay.addWidget(self._lbl)

    def update_strength(self, password: str):
        score, label, color = _pw_strength(password)
        self._bar.setValue(score)
        self._lbl.setText(label)
        self._lbl.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: bold;")
        self._bar.setStyleSheet(
            f"QProgressBar {{ background: #313244; border-radius: 4px; }}"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 4px; }}")


# ── Main dialog ──────────────────────────────────────────────────────
class FolderLockerDialog(QDialog):
    """Pro UI for locking/unlocking/managing folders."""

    def __init__(self, locker: FolderLocker, parent=None):
        super().__init__(parent)
        self._locker = locker
        self.setWindowTitle("🔒 Folder Locker")
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("🔒 Folder Locker")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #F9E2AF;")
        layout.addWidget(title)

        desc = QLabel("Lock folders with password. Folders are renamed & hidden for extra security.")
        desc.setStyleSheet("color: #6C7086; font-size: 11px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Folder list
        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget { background: #313244; color: #CDD6F4; border: 1px solid #45475A;"
            "  border-radius: 8px; padding: 4px; font-size: 12px; }"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background: #45475A; }"
        )
        layout.addWidget(self._list)

        btn_style = (
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #B4BEFE; }"
        )
        green_style = (
            "QPushButton { background: #A6E3A1; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #94E2D5; }"
        )
        warn_style = (
            "QPushButton { background: #FAB387; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #F9E2AF; }"
        )
        red_style = (
            "QPushButton { background: #F38BA8; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 8px 14px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #EBA0AC; }"
        )

        row1 = QHBoxLayout()
        self._btn_lock = QPushButton("🔒 Lock Folder...")
        self._btn_lock.setStyleSheet(btn_style)
        self._btn_lock.clicked.connect(self._lock_folder)
        row1.addWidget(self._btn_lock)

        self._btn_unlock = QPushButton("🔓 Unlock")
        self._btn_unlock.setStyleSheet(green_style)
        self._btn_unlock.clicked.connect(self._unlock_selected)
        row1.addWidget(self._btn_unlock)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        self._btn_chpw = QPushButton("🔑 Change Password")
        self._btn_chpw.setStyleSheet(warn_style)
        self._btn_chpw.clicked.connect(self._change_password)
        row2.addWidget(self._btn_chpw)

        self._btn_remove = QPushButton("🗑️ Remove")
        self._btn_remove.setStyleSheet(red_style)
        self._btn_remove.clicked.connect(self._remove_selected)
        row2.addWidget(self._btn_remove)
        layout.addLayout(row2)

        self._refresh()

    def _refresh(self):
        self._list.clear()
        for i, entry in enumerate(self._locker.get_all()):
            icon = "🔒" if entry["locked"] else "🔓"
            name = entry.get("original_name", os.path.basename(entry.get("path", "?")))
            loc = entry.get("path", "")
            item = QListWidgetItem(f"{icon} {name}   📁 {loc}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self._list.addItem(item)

    def _get_selected_index(self) -> int:
        item = self._list.currentItem()
        if not item:
            return -1
        return item.data(Qt.ItemDataRole.UserRole)

    def _lock_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder to lock")
        if not folder:
            return
        dlg = _SetPasswordDialog(self)
        if dlg.exec() and dlg.password:
            if self._locker.lock(folder, dlg.password):
                self._refresh()
            else:
                QMessageBox.warning(self, "Error", "Folder already locked or not found.")

    def _unlock_selected(self):
        idx = self._get_selected_index()
        if idx < 0:
            return
        entry = self._locker.get_all()[idx]
        name = entry.get("original_name", "folder")
        pw, ok = QInputDialog.getText(
            self, "🔓 Enter Password",
            f"Password for \"{name}\":",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not pw:
            return
        success, msg = self._locker.unlock(idx, pw)
        if success:
            self._refresh()
            QMessageBox.information(self, "Success", msg)
        else:
            QMessageBox.warning(self, "Error", msg)

    def _change_password(self):
        idx = self._get_selected_index()
        if idx < 0:
            return
        entry = self._locker.get_all()[idx]
        if not entry["locked"]:
            QMessageBox.information(self, "Info", "Folder is not locked.")
            return
        old_pw, ok = QInputDialog.getText(
            self, "🔑 Current Password", "Enter current password:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not old_pw:
            return
        dlg = _SetPasswordDialog(self, title="Set New Password")
        if dlg.exec() and dlg.password:
            success, msg = self._locker.change_password(idx, old_pw, dlg.password)
            if success:
                QMessageBox.information(self, "Success", msg)
            else:
                QMessageBox.warning(self, "Error", msg)

    def _remove_selected(self):
        idx = self._get_selected_index()
        if idx < 0:
            return
        entry = self._locker.get_all()[idx]
        name = entry.get("original_name", "folder")
        r = QMessageBox.question(
            self, "Remove",
            f"Remove \"{name}\" from tracking?\n"
            + ("(This will also unlock and restore the folder.)" if entry["locked"] else ""),
        )
        if r == QMessageBox.StandardButton.Yes:
            self._locker.remove(idx)
            self._refresh()


class _SetPasswordDialog(QDialog):
    """Password dialog with strength meter and confirmation."""

    def __init__(self, parent=None, title: str = "Set Password"):
        super().__init__(parent)
        self.setWindowTitle(f"🔒 {title}")
        self.setMinimumWidth(340)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")
        self.password = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        lbl_css = "color: #CDD6F4; font-size: 12px;"
        input_css = ("QLineEdit { background: #313244; color: #CDD6F4;"
                     " border: 1px solid #45475A; border-radius: 6px; padding: 8px;"
                     " font-size: 12px; }"
                     "QLineEdit:focus { border-color: #89B4FA; }")

        lbl1 = QLabel("Password:")
        lbl1.setStyleSheet(lbl_css)
        layout.addWidget(lbl1)

        self._pw1 = QLineEdit()
        self._pw1.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw1.setStyleSheet(input_css)
        self._pw1.setPlaceholderText("Enter password...")
        layout.addWidget(self._pw1)

        self._strength = _PasswordStrengthBar()
        layout.addWidget(self._strength)
        self._pw1.textChanged.connect(self._strength.update_strength)

        lbl2 = QLabel("Confirm:")
        lbl2.setStyleSheet(lbl_css)
        layout.addWidget(lbl2)

        self._pw2 = QLineEdit()
        self._pw2.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw2.setStyleSheet(input_css)
        self._pw2.setPlaceholderText("Confirm password...")
        layout.addWidget(self._pw2)

        self._match_lbl = QLabel("")
        self._match_lbl.setStyleSheet("color: #6C7086; font-size: 10px;")
        layout.addWidget(self._match_lbl)
        self._pw2.textChanged.connect(self._check_match)

        btn_style = (
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 10px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #B4BEFE; }"
            "QPushButton:disabled { background: #45475A; color: #6C7086; }"
        )
        self._btn_ok = QPushButton("✅ Set Password")
        self._btn_ok.setStyleSheet(btn_style)
        self._btn_ok.setEnabled(False)
        self._btn_ok.clicked.connect(self._accept)
        layout.addWidget(self._btn_ok)

    def _check_match(self):
        pw1, pw2 = self._pw1.text(), self._pw2.text()
        if not pw2:
            self._match_lbl.setText("")
            self._btn_ok.setEnabled(False)
        elif pw1 == pw2:
            self._match_lbl.setText("✅ Passwords match")
            self._match_lbl.setStyleSheet("color: #A6E3A1; font-size: 10px;")
            self._btn_ok.setEnabled(len(pw1) >= 4)
        else:
            self._match_lbl.setText("❌ Passwords don't match")
            self._match_lbl.setStyleSheet("color: #F38BA8; font-size: 10px;")
            self._btn_ok.setEnabled(False)

    def _accept(self):
        self.password = self._pw1.text()
        self.accept()
