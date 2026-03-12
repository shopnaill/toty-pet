"""QR Code Generator — Generate QR codes from text/URL, and scan QR from screen."""
import io
import logging

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QApplication, QFileDialog, QMessageBox, QComboBox,
)
from PyQt6.QtCore import Qt, QBuffer
from PyQt6.QtGui import QFont, QPixmap, QImage, QGuiApplication

log = logging.getLogger("toty.qr_generator")

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"

_SS = f"""
QDialog {{ background: {_BG}; }}
QTextEdit {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px; font-size: 13px;
}}
QPushButton {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background: #45475A; border-color: {_BLUE}; }}
QPushButton:pressed {{ background: {_BLUE}; color: {_BG}; }}
QLabel {{ color: {_TEXT}; }}
QComboBox {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 6px 10px; font-size: 13px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {_SURFACE}; color: {_TEXT}; selection-background-color: #45475A;
}}
"""

# Try to import qrcode; it's pure-python, we'll auto-install if needed
_HAS_QRCODE = False
try:
    import qrcode
    from qrcode.image.pure import PyPNGImage
    _HAS_QRCODE = True
except ImportError:
    pass


def _ensure_qrcode():
    """Install qrcode if missing."""
    global _HAS_QRCODE, qrcode, PyPNGImage
    if _HAS_QRCODE:
        return True
    try:
        import subprocess, sys
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "qrcode[pil]"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        import qrcode
        _HAS_QRCODE = True
        return True
    except Exception as e:
        log.warning("Cannot install qrcode: %s", e)
        return False


def _make_qr_pixmap(text: str, size: int = 300,
                     fg: str = "#000000", bg: str = "#FFFFFF") -> QPixmap | None:
    """Generate a QR code as QPixmap."""
    if not _ensure_qrcode():
        return None
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(text)
        qr.make(fit=True)

        try:
            from PIL import Image as PILImage
            img = qr.make_image(fill_color=fg, back_color=bg)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            pix = QPixmap()
            pix.loadFromData(buf.read())
        except ImportError:
            # Fallback without PIL: use pure PNG
            img = qr.make_image(image_factory=PyPNGImage)
            buf = io.BytesIO()
            img.save(buf)
            buf.seek(0)
            pix = QPixmap()
            pix.loadFromData(buf.read())

        if not pix.isNull():
            return pix.scaled(size, size,
                              Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    except Exception as e:
        log.warning("QR generation failed: %s", e)
    return None


class QRGeneratorDialog(QDialog):
    """Generate and save QR codes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📱 QR Code Generator")
        self.setFixedSize(420, 560)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)
        self._pixmap: QPixmap | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        title = QLabel("📱 QR Code Generator")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE};")
        lay.addWidget(title)

        self._input = QTextEdit()
        self._input.setPlaceholderText(
            "Enter text or URL…\nhttps://example.com")
        self._input.setMaximumHeight(80)
        lay.addWidget(self._input)

        # Options row
        opt_row = QHBoxLayout()
        opt_row.setSpacing(6)
        opt_row.addWidget(QLabel("Size:"))
        self._size = QComboBox()
        self._size.addItems(["200", "300", "400", "500"])
        self._size.setCurrentText("300")
        opt_row.addWidget(self._size)
        opt_row.addStretch()

        btn_gen = QPushButton("▶ Generate")
        btn_gen.clicked.connect(self._generate)
        btn_gen.setStyleSheet(
            f"QPushButton {{ background: {_BLUE}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 8px 18px; font-weight: bold; }}")
        opt_row.addWidget(btn_gen)
        lay.addLayout(opt_row)

        # Preview
        self._preview = QLabel()
        self._preview.setFixedSize(320, 320)
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setStyleSheet(
            f"background: {_SURFACE}; border: 2px solid #45475A; "
            f"border-radius: 8px; color: {_TEXT};")
        self._preview.setText("QR code will appear here")
        lay.addWidget(self._preview, alignment=Qt.AlignmentFlag.AlignCenter)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_copy = QPushButton("📋 Copy to Clipboard")
        self._btn_copy.clicked.connect(self._copy)
        self._btn_copy.setEnabled(False)
        btn_row.addWidget(self._btn_copy)

        self._btn_save = QPushButton("💾 Save as PNG")
        self._btn_save.clicked.connect(self._save)
        self._btn_save.setEnabled(False)
        btn_row.addWidget(self._btn_save)

        lay.addLayout(btn_row)

    def _generate(self):
        text = self._input.toPlainText().strip()
        if not text:
            self._preview.setText("Enter text first")
            return
        size = int(self._size.currentText())
        self._preview.setText("Generating…")
        QApplication.processEvents()

        pix = _make_qr_pixmap(text, size)
        if pix and not pix.isNull():
            self._pixmap = pix
            self._preview.setPixmap(pix)
            self._btn_copy.setEnabled(True)
            self._btn_save.setEnabled(True)
        else:
            self._preview.setText(
                "Failed to generate QR.\n"
                "Installing 'qrcode' package…\nTry again.")
            self._pixmap = None
            self._btn_copy.setEnabled(False)
            self._btn_save.setEnabled(False)

    def _copy(self):
        if self._pixmap:
            QApplication.clipboard().setPixmap(self._pixmap)
            self._preview.setText("✅ Copied to clipboard!")
            # Restore after 1.5s
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(
                1500, lambda: (
                    self._preview.setPixmap(self._pixmap)
                    if self._pixmap else None))

    def _save(self):
        if not self._pixmap:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save QR Code", "qr_code.png",
            "PNG Image (*.png);;JPEG Image (*.jpg)")
        if path:
            self._pixmap.save(path)
            self._preview.setText(f"✅ Saved to {path}")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(
                1500, lambda: (
                    self._preview.setPixmap(self._pixmap)
                    if self._pixmap else None))
