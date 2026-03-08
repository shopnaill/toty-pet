"""File Compressor — pro compress/extract with levels, passwords, drag-drop."""
import os
import zipfile
import logging
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QProgressBar, QComboBox, QLineEdit, QMessageBox,
    QFrame,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QMimeData
from PyQt6.QtGui import QFont, QDragEnterEvent, QDropEvent

log = logging.getLogger("toty.file_compressor")


# ── Compression level mapping ────────────────────────────────────────
_LEVEL_MAP = {
    "Fastest (ZIP_STORED)": zipfile.ZIP_STORED,
    "Normal (ZIP_DEFLATED)": zipfile.ZIP_DEFLATED,
    "Best (ZIP_BZIP2)": zipfile.ZIP_BZIP2,
}


def _total_size(paths: list[str]) -> int:
    """Recursively sum file sizes."""
    total = 0
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for f in files:
                    total += os.path.getsize(os.path.join(root, f))
        elif os.path.isfile(p):
            total += os.path.getsize(p)
    return total


def _human_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


class _CompressWorker(QThread):
    """Background thread for compression."""
    progress = pyqtSignal(int)       # 0-100
    finished = pyqtSignal(str)       # output path
    error = pyqtSignal(str)

    def __init__(self, files: list[str], output: str,
                 method: int = zipfile.ZIP_DEFLATED, password: str = ""):
        super().__init__()
        self._files = files
        self._output = output
        self._method = method
        self._password = password

    def run(self):
        try:
            if self._password:
                self._compress_with_password()
            else:
                self._compress_native()
        except Exception as e:
            self.error.emit(str(e))

    def _compress_native(self):
        total = len(self._files)
        with zipfile.ZipFile(self._output, "w", self._method) as zf:
            for i, fpath in enumerate(self._files):
                if os.path.isdir(fpath):
                    base = os.path.dirname(fpath)
                    for root, _dirs, fnames in os.walk(fpath):
                        for fname in fnames:
                            full = os.path.join(root, fname)
                            arcname = os.path.relpath(full, base)
                            zf.write(full, arcname)
                else:
                    zf.write(fpath, os.path.basename(fpath))
                self.progress.emit(int((i + 1) / total * 100))
        self.finished.emit(self._output)

    def _compress_with_password(self):
        """Password-protected ZIP using 7z for AES-256 encryption."""
        import subprocess
        sz = shutil.which("7z") or shutil.which("7za")
        if not sz:
            self.error.emit("7-Zip required for password-protected archives.\nInstall 7-Zip to enable this feature.")
            return
        cmd = [sz, "a", "-tzip", f"-p{self._password}", "-mem=AES256", self._output]
        cmd.extend(self._files)
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            self.progress.emit(100)
            self.finished.emit(self._output)
        else:
            self.error.emit(result.stderr[:300] or "Compression failed")


class _ExtractWorker(QThread):
    """Background thread for extraction."""
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)       # output dir
    error = pyqtSignal(str)

    def __init__(self, archive: str, output_dir: str, password: str = ""):
        super().__init__()
        self._archive = archive
        self._output_dir = output_dir
        self._password = password

    def run(self):
        ext = os.path.splitext(self._archive)[1].lower()
        try:
            if ext == ".zip" and not self._password:
                self._extract_zip()
            else:
                self._extract_with_7z()
        except Exception as e:
            self.error.emit(str(e))

    def _extract_zip(self):
        with zipfile.ZipFile(self._archive, "r") as zf:
            members = zf.namelist()
            total = len(members)
            for i, member in enumerate(members):
                member_path = os.path.normpath(member)
                if member_path.startswith("..") or os.path.isabs(member_path):
                    continue
                zf.extract(member, self._output_dir)
                self.progress.emit(int((i + 1) / total * 100))
        self.finished.emit(self._output_dir)

    def _extract_with_7z(self):
        """Use 7z command if available for RAR/7z/tar/password support."""
        import subprocess
        sz = shutil.which("7z") or shutil.which("7za")
        if not sz:
            self.error.emit("7-Zip not found. Install 7-Zip to extract this format.")
            return
        cmd = [sz, "x", self._archive, f"-o{self._output_dir}", "-y"]
        if self._password:
            cmd.append(f"-p{self._password}")
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode == 0:
            self.progress.emit(100)
            self.finished.emit(self._output_dir)
        else:
            msg = result.stderr[:300] or "Extraction failed"
            if "Wrong password" in msg or "password" in msg.lower():
                msg = "Wrong password or encrypted archive."
            self.error.emit(msg)


# ── Drop zone widget ─────────────────────────────────────────────────
class _DropZone(QFrame):
    """Drag-and-drop area for files/folders."""
    files_dropped = pyqtSignal(list)  # list[str]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(60)
        self.setStyleSheet(
            "QFrame { background: #313244; border: 2px dashed #45475A;"
            "  border-radius: 10px; }"
        )
        lay = QVBoxLayout(self)
        self._lbl = QLabel("📥 Drop files or folders here")
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet("color: #6C7086; font-size: 12px; border: none;")
        lay.addWidget(self._lbl)

    def set_text(self, text: str):
        self._lbl.setText(text)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(
                "QFrame { background: #313244; border: 2px dashed #89B4FA;"
                "  border-radius: 10px; }")

    def dragLeaveEvent(self, event):
        self.setStyleSheet(
            "QFrame { background: #313244; border: 2px dashed #45475A;"
            "  border-radius: 10px; }")

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(
            "QFrame { background: #313244; border: 2px dashed #45475A;"
            "  border-radius: 10px; }")
        paths = []
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.exists(p):
                paths.append(p)
        if paths:
            self.files_dropped.emit(paths)


class FileCompressorDialog(QDialog):
    """Pro compress & extract dialog with drag-drop, levels, passwords."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📦 File Compressor & Extractor")
        self.setMinimumWidth(440)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet("QDialog { background: #1E1E2E; }")
        self._worker = None
        self._selected_files: list[str] = []
        self._original_size = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("📦 Compress & Extract")
        title.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #89B4FA;")
        layout.addWidget(title)

        lbl_css = "color: #CDD6F4; font-size: 12px;"
        input_css = ("QLineEdit { background: #313244; color: #CDD6F4;"
                     " border: 1px solid #45475A; border-radius: 6px; padding: 6px;"
                     " font-size: 12px; }"
                     "QLineEdit:focus { border-color: #89B4FA; }")
        combo_css = ("QComboBox { background: #313244; color: #CDD6F4;"
                     " border: 1px solid #45475A; border-radius: 6px; padding: 6px; }"
                     "QComboBox QAbstractItemView { background: #313244; color: #CDD6F4; }")
        btn_style = (
            "QPushButton { background: #89B4FA; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 10px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #B4BEFE; }"
            "QPushButton:disabled { background: #45475A; color: #6C7086; }"
        )
        green_style = (
            "QPushButton { background: #A6E3A1; color: #1E1E2E; border: none;"
            "  border-radius: 8px; padding: 10px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background: #94E2D5; }"
        )

        # ── Compress Section ──
        comp_lbl = QLabel("🗜️ Compress Files/Folders → ZIP")
        comp_lbl.setStyleSheet("color: #F9E2AF; font-weight: bold; font-size: 12px;")
        layout.addWidget(comp_lbl)

        # Drop zone
        self._drop = _DropZone()
        self._drop.files_dropped.connect(self._on_drop)
        layout.addWidget(self._drop)

        row_pick = QHBoxLayout()
        self._btn_pick_files = QPushButton("📄 Select Files")
        self._btn_pick_files.setStyleSheet(btn_style)
        self._btn_pick_files.clicked.connect(self._pick_files)
        row_pick.addWidget(self._btn_pick_files)

        self._btn_pick_folder = QPushButton("📁 Select Folder")
        self._btn_pick_folder.setStyleSheet(btn_style)
        self._btn_pick_folder.clicked.connect(self._pick_folder)
        row_pick.addWidget(self._btn_pick_folder)
        layout.addLayout(row_pick)

        # Options row: level + password
        opt_row = QHBoxLayout()
        lvl_lbl = QLabel("Level:")
        lvl_lbl.setStyleSheet(lbl_css)
        opt_row.addWidget(lvl_lbl)
        self._level = QComboBox()
        self._level.addItems(list(_LEVEL_MAP.keys()))
        self._level.setCurrentIndex(1)
        self._level.setStyleSheet(combo_css)
        opt_row.addWidget(self._level)
        layout.addLayout(opt_row)

        pw_row = QHBoxLayout()
        pw_lbl = QLabel("🔒 Password (optional):")
        pw_lbl.setStyleSheet(lbl_css)
        pw_row.addWidget(pw_lbl)
        self._pw_input = QLineEdit()
        self._pw_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._pw_input.setPlaceholderText("Leave empty for no password")
        self._pw_input.setStyleSheet(input_css)
        pw_row.addWidget(self._pw_input)
        layout.addLayout(pw_row)

        self._btn_compress = QPushButton("🗜️ Compress to ZIP")
        self._btn_compress.setStyleSheet(btn_style)
        self._btn_compress.clicked.connect(self._compress)
        self._btn_compress.setEnabled(False)
        layout.addWidget(self._btn_compress)

        # ── Separator ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #45475A;")
        layout.addWidget(sep)

        # ── Extract Section ──
        ext_lbl = QLabel("📂 Extract Archives (ZIP, RAR, 7z, TAR)")
        ext_lbl.setStyleSheet("color: #F9E2AF; font-weight: bold; font-size: 12px;")
        layout.addWidget(ext_lbl)

        ext_pw_row = QHBoxLayout()
        ext_pw_lbl = QLabel("🔒 Archive password:")
        ext_pw_lbl.setStyleSheet(lbl_css)
        ext_pw_row.addWidget(ext_pw_lbl)
        self._ext_pw = QLineEdit()
        self._ext_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._ext_pw.setPlaceholderText("If encrypted")
        self._ext_pw.setStyleSheet(input_css)
        ext_pw_row.addWidget(self._ext_pw)
        layout.addLayout(ext_pw_row)

        self._btn_extract = QPushButton("📂 Select Archive & Extract")
        self._btn_extract.setStyleSheet(green_style)
        self._btn_extract.clicked.connect(self._extract)
        layout.addWidget(self._btn_extract)

        # ── Progress ──
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { background: #313244; border: 1px solid #45475A;"
            "  border-radius: 6px; height: 18px; text-align: center; color: #CDD6F4; }"
            "QProgressBar::chunk { background: #89B4FA; border-radius: 5px; }"
        )
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # Open folder button (shown after operation)
        self._btn_open = QPushButton("📂 Open Output Folder")
        self._btn_open.setStyleSheet(green_style)
        self._btn_open.setVisible(False)
        layout.addWidget(self._btn_open)

        self._last_output = ""

    def _update_selection(self, files: list[str]):
        self._selected_files = files
        self._original_size = _total_size(files)
        names = ", ".join(os.path.basename(f) for f in files[:4])
        if len(files) > 4:
            names += f" (+{len(files)-4} more)"
        icon = "📁" if (len(files) == 1 and os.path.isdir(files[0])) else "📄"
        self._drop.set_text(f"{icon} {names}\n📐 {_human_size(self._original_size)}")
        self._btn_compress.setEnabled(True)

    def _on_drop(self, paths: list[str]):
        self._update_selection(paths)

    def _pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select files to compress")
        if files:
            self._update_selection(files)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder to compress")
        if folder:
            self._update_selection([folder])

    def _compress(self):
        if not self._selected_files:
            return
        default_name = os.path.basename(self._selected_files[0])
        if len(self._selected_files) > 1:
            default_name = "archive"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = os.path.join(
            os.path.dirname(self._selected_files[0]),
            f"{default_name}_{ts}.zip",
        )
        output, _ = QFileDialog.getSaveFileName(
            self, "Save ZIP as", default_path, "ZIP Files (*.zip)")
        if not output:
            return

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status.setText("Compressing...")
        self._status.setStyleSheet("color: #89B4FA; font-size: 12px;")
        self._btn_compress.setEnabled(False)
        self._btn_open.setVisible(False)

        method = _LEVEL_MAP[self._level.currentText()]
        pw = self._pw_input.text().strip()

        self._worker = _CompressWorker(self._selected_files, output, method, pw)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_compress_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _extract(self):
        archive, _ = QFileDialog.getOpenFileName(
            self, "Select archive to extract",
            "", "Archives (*.zip *.rar *.7z *.tar *.gz *.bz2 *.xz)")
        if not archive:
            return

        output_dir = QFileDialog.getExistingDirectory(
            self, "Extract to folder",
            os.path.dirname(archive))
        if not output_dir:
            return

        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status.setText("Extracting...")
        self._status.setStyleSheet("color: #89B4FA; font-size: 12px;")
        self._btn_open.setVisible(False)

        pw = self._ext_pw.text().strip()
        self._worker = _ExtractWorker(archive, output_dir, pw)
        self._worker.progress.connect(self._progress.setValue)
        self._worker.finished.connect(self._on_extract_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_compress_done(self, path: str):
        compressed_size = os.path.getsize(path)
        ratio = ((1 - compressed_size / self._original_size) * 100) if self._original_size else 0
        self._status.setText(
            f"✅ {os.path.basename(path)}\n"
            f"📐 {_human_size(self._original_size)} → {_human_size(compressed_size)}  "
            f"({ratio:.0f}% smaller)")
        self._status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._btn_compress.setEnabled(True)
        self._last_output = os.path.dirname(path)
        self._btn_open.setVisible(True)
        self._btn_open.clicked.disconnect() if self._btn_open.receivers(self._btn_open.clicked) else None
        self._btn_open.clicked.connect(lambda: os.startfile(self._last_output))
        self._worker = None

    def _on_extract_done(self, dir_path: str):
        self._status.setText(f"✅ Extracted to {dir_path}")
        self._status.setStyleSheet("color: #A6E3A1; font-size: 12px;")
        self._last_output = dir_path
        self._btn_open.setVisible(True)
        self._btn_open.clicked.disconnect() if self._btn_open.receivers(self._btn_open.clicked) else None
        self._btn_open.clicked.connect(lambda: os.startfile(dir_path))
        self._worker = None

    def _on_error(self, msg: str):
        self._status.setText(f"❌ {msg}")
        self._status.setStyleSheet("color: #F38BA8; font-size: 12px;")
        self._btn_compress.setEnabled(True)
        self._progress.setVisible(False)
        self._btn_open.setVisible(False)
        self._worker = None
