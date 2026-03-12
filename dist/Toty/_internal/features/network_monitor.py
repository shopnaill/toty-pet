"""Network Monitor — Real-time bandwidth, ping, Wi-Fi signal, and speed test."""
import logging
import socket
import subprocess
import time
import re
from collections import deque

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QApplication, QFrame, QGridLayout, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QBrush

log = logging.getLogger("toty.network_monitor")

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"
_YELLOW = "#F9E2AF"
_MAUVE = "#CBA6F7"

_SS = f"""
QDialog {{ background: {_BG}; }}
QPushButton {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background: #45475A; border-color: {_BLUE}; }}
QPushButton:pressed {{ background: {_BLUE}; color: {_BG}; }}
QLabel {{ color: {_TEXT}; }}
QProgressBar {{
    background: {_SURFACE}; border: 1px solid #45475A; border-radius: 4px;
    text-align: center; color: {_TEXT}; font-size: 11px;
}}
QProgressBar::chunk {{ background: {_BLUE}; border-radius: 3px; }}
"""


def _fmt_speed(bps: float) -> str:
    """Format bytes/sec to human-readable."""
    if bps < 1024:
        return f"{bps:.0f} B/s"
    elif bps < 1024 ** 2:
        return f"{bps / 1024:.1f} KB/s"
    elif bps < 1024 ** 3:
        return f"{bps / 1024 ** 2:.1f} MB/s"
    return f"{bps / 1024 ** 3:.2f} GB/s"


def _get_network_bytes():
    """Get total bytes sent/received using psutil if available."""
    try:
        import psutil
        counters = psutil.net_io_counters()
        return counters.bytes_sent, counters.bytes_recv
    except ImportError:
        return None, None


def _ping(host: str = "8.8.8.8", timeout: int = 3) -> float | None:
    """Ping a host and return RTT in ms, or None on failure."""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", str(timeout * 1000), host],
            capture_output=True, text=True, timeout=timeout + 2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        m = re.search(r"time[=<](\d+)ms", result.stdout)
        if m:
            return float(m.group(1))
    except Exception:
        pass
    return None


def _get_wifi_signal() -> tuple[str, int] | None:
    """Get Wi-Fi SSID and signal strength %."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ssid = ""
        signal = 0
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("SSID") and "BSSID" not in line:
                ssid = line.split(":", 1)[-1].strip()
            elif line.startswith("Signal"):
                m = re.search(r"(\d+)%", line)
                if m:
                    signal = int(m.group(1))
        if ssid:
            return ssid, signal
    except Exception:
        pass
    return None


class _PingWorker(QThread):
    result = pyqtSignal(object)  # float | None

    def __init__(self, host: str = "8.8.8.8"):
        super().__init__()
        self._host = host

    def run(self):
        self.result.emit(_ping(self._host))


class _SpeedTestWorker(QThread):
    """Simple download speed test using a known file."""
    progress = pyqtSignal(str)
    result = pyqtSignal(float, float)  # download_mbps, upload_mbps (0)

    def run(self):
        try:
            import urllib.request
            url = "http://speedtest.tele2.net/1MB.zip"
            self.progress.emit("Downloading test file…")
            start = time.time()
            req = urllib.request.Request(url)
            # Set a timeout to prevent hanging
            resp = urllib.request.urlopen(req, timeout=15)
            data = resp.read()
            elapsed = time.time() - start
            size_mb = len(data) / (1024 * 1024)
            speed = size_mb / elapsed if elapsed > 0 else 0
            self.result.emit(speed, 0)
        except Exception as e:
            self.progress.emit(f"Speed test failed: {e}")
            self.result.emit(0, 0)


class _SparkLine(QFrame):
    """Tiny bar chart for bandwidth history."""

    def __init__(self, color: str = _BLUE, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setMinimumWidth(200)
        self._color = QColor(color)
        self._data: deque[float] = deque(maxlen=60)

    def add_value(self, v: float):
        self._data.append(v)
        self.update()

    def paintEvent(self, _):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        max_val = max(self._data) if self._data else 1
        if max_val == 0:
            max_val = 1
        n = len(self._data)
        bar_w = max(2, w / 60)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._color))
        for i, v in enumerate(self._data):
            bar_h = max(1, int(v / max_val * (h - 2)))
            x = int(i * bar_w)
            painter.drawRect(int(x), h - bar_h, int(bar_w - 1), bar_h)
        painter.end()


class NetworkMonitorDialog(QDialog):
    """Real-time network monitoring dashboard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🌐 Network Monitor")
        self.setMinimumSize(480, 420)
        self.resize(500, 460)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)
        self._prev_sent = 0
        self._prev_recv = 0
        self._ping_worker: _PingWorker | None = None
        self._speed_worker: _SpeedTestWorker | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        title = QLabel("🌐 Network Monitor")
        title.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_BLUE};")
        lay.addWidget(title)

        # Stats grid
        grid = QGridLayout()
        grid.setSpacing(8)

        # Wi-Fi
        grid.addWidget(self._card_label("📶 Wi-Fi"), 0, 0)
        self._lbl_wifi = QLabel("Scanning…")
        self._lbl_wifi.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
        grid.addWidget(self._lbl_wifi, 0, 1)

        # Ping
        grid.addWidget(self._card_label("🏓 Ping"), 1, 0)
        self._lbl_ping = QLabel("—")
        self._lbl_ping.setStyleSheet(f"color: {_TEXT}; font-size: 13px;")
        grid.addWidget(self._lbl_ping, 1, 1)

        # IP
        grid.addWidget(self._card_label("🖥️ Local IP"), 2, 0)
        self._lbl_ip = QLabel("—")
        self._lbl_ip.setStyleSheet(
            f"color: {_TEXT}; font-family: Consolas; font-size: 13px;")
        grid.addWidget(self._lbl_ip, 2, 1)

        # Download speed
        grid.addWidget(self._card_label("⬇️ Download"), 3, 0)
        self._lbl_down = QLabel("0 B/s")
        self._lbl_down.setStyleSheet(
            f"color: {_GREEN}; font-family: Consolas; font-size: 14px; "
            f"font-weight: bold;")
        grid.addWidget(self._lbl_down, 3, 1)

        # Upload speed
        grid.addWidget(self._card_label("⬆️ Upload"), 4, 0)
        self._lbl_up = QLabel("0 B/s")
        self._lbl_up.setStyleSheet(
            f"color: {_BLUE}; font-family: Consolas; font-size: 14px; "
            f"font-weight: bold;")
        grid.addWidget(self._lbl_up, 4, 1)

        lay.addLayout(grid)

        # Sparklines
        lay.addWidget(QLabel("⬇️ Download History:"))
        self._spark_down = _SparkLine(_GREEN)
        lay.addWidget(self._spark_down)

        lay.addWidget(QLabel("⬆️ Upload History:"))
        self._spark_up = _SparkLine(_BLUE)
        lay.addWidget(self._spark_up)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._btn_speed = QPushButton("🚀 Speed Test")
        self._btn_speed.clicked.connect(self._start_speed_test)
        self._btn_speed.setStyleSheet(
            f"QPushButton {{ background: {_BLUE}; color: {_BG}; border: none; "
            f"border-radius: 6px; padding: 8px 16px; font-weight: bold; }}")
        btn_row.addWidget(self._btn_speed)

        self._lbl_speed_result = QLabel("")
        self._lbl_speed_result.setStyleSheet(f"font-size: 12px;")
        btn_row.addWidget(self._lbl_speed_result)

        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Timer for real-time updates
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)
        self._timer.start(1000)
        self._update()
        self._do_ping()

    def _card_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color: #BAC2DE; font-size: 13px;")
        lbl.setFixedWidth(120)
        return lbl

    def _update(self):
        # Bandwidth
        sent, recv = _get_network_bytes()
        if sent is not None and recv is not None:
            if self._prev_sent > 0:
                ds = recv - self._prev_recv
                us = sent - self._prev_sent
                self._lbl_down.setText(_fmt_speed(ds))
                self._lbl_up.setText(_fmt_speed(us))
                self._spark_down.add_value(ds)
                self._spark_up.add_value(us)
            self._prev_sent = sent
            self._prev_recv = recv
        else:
            self._lbl_down.setText("psutil not installed")

        # Wi-Fi
        wifi = _get_wifi_signal()
        if wifi:
            ssid, signal = wifi
            self._lbl_wifi.setText(f"{ssid}  ({signal}%)")
        else:
            self._lbl_wifi.setText("Not connected / Ethernet")

        # Local IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            self._lbl_ip.setText(ip)
        except Exception:
            self._lbl_ip.setText("No connection")

    def _do_ping(self):
        if self._ping_worker and self._ping_worker.isRunning():
            return
        self._ping_worker = _PingWorker()
        self._ping_worker.result.connect(self._on_ping)
        self._ping_worker.start()

    def _on_ping(self, rtt):
        if rtt is not None:
            color = _GREEN if rtt < 50 else (_YELLOW if rtt < 100 else _RED)
            self._lbl_ping.setText(f"{rtt:.0f} ms")
            self._lbl_ping.setStyleSheet(
                f"color: {color}; font-size: 13px; font-weight: bold;")
        else:
            self._lbl_ping.setText("Timeout")
            self._lbl_ping.setStyleSheet(
                f"color: {_RED}; font-size: 13px;")
        # Ping every 5 seconds
        QTimer.singleShot(5000, self._do_ping)

    def _start_speed_test(self):
        if self._speed_worker and self._speed_worker.isRunning():
            return
        self._btn_speed.setEnabled(False)
        self._lbl_speed_result.setText("Testing…")
        self._lbl_speed_result.setStyleSheet(f"color: {_BLUE}; font-size: 12px;")
        self._speed_worker = _SpeedTestWorker()
        self._speed_worker.progress.connect(
            lambda msg: self._lbl_speed_result.setText(msg))
        self._speed_worker.result.connect(self._on_speed_result)
        self._speed_worker.start()

    def _on_speed_result(self, dl_mbps: float, _ul: float):
        self._btn_speed.setEnabled(True)
        if dl_mbps > 0:
            self._lbl_speed_result.setText(f"⬇️ {dl_mbps:.1f} MB/s")
            self._lbl_speed_result.setStyleSheet(
                f"color: {_GREEN}; font-size: 13px; font-weight: bold;")
        else:
            self._lbl_speed_result.setText("Test failed")
            self._lbl_speed_result.setStyleSheet(
                f"color: {_RED}; font-size: 12px;")

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
