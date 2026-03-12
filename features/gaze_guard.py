"""Gaze Guard — AI-powered haram/NSFW content blocker & Islamic browsing protection.

Features:
  1. Haram website blocker (title-based detection)
  2. Screen content guard (optional AI via nudenet)
  3. Instant blur hotkey (Ctrl+Shift+G)
  4. Clean browsing streak tracker
  5. Islamic reminders on detection
  6. Safe search enforcer (Google/YouTube/Bing)
  7. Customizable block list
  8. Pet reaction signals

All AI processing is LOCAL — zero data sent anywhere.
"""
import os
import re
import sys
import json
import time
import random
import logging
import subprocess
import tempfile
import ctypes
import hashlib
from datetime import date, datetime
from collections import deque

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QWidget, QListWidget, QListWidgetItem, QLineEdit, QComboBox,
    QCheckBox, QTabWidget, QFrame, QMessageBox, QInputDialog,
    QApplication, QTextEdit, QSlider, QGroupBox, QSpinBox,
    QFileDialog, QProgressBar,
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QPropertyAnimation,
    QRect, QPoint,
)
from PyQt6.QtGui import (
    QFont, QColor, QPainter, QBrush, QPen, QScreen,
    QGuiApplication, QPixmap, QCursor, QImage,
    QRadialGradient, QLinearGradient,
)

log = logging.getLogger("toty.gaze_guard")

# ── Paths & constants ─────────────────────────────────────────────────
_CONFIG_PATH = "gaze_guard_config.json"

_BG = "#1E1E2E"
_SURFACE = "#313244"
_TEXT = "#CDD6F4"
_BLUE = "#89B4FA"
_GREEN = "#A6E3A1"
_RED = "#F38BA8"
_YELLOW = "#F9E2AF"
_TEAL = "#94E2D5"

_SS = f"""
QDialog {{ background: {_BG}; }}
QLabel {{ color: {_TEXT}; }}
QLineEdit {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px; font-size: 13px;
}}
QLineEdit:focus {{ border-color: {_BLUE}; }}
QPushButton {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 8px 16px; font-size: 13px;
}}
QPushButton:hover {{ background: #45475A; border-color: {_BLUE}; }}
QPushButton:pressed {{ background: {_BLUE}; color: {_BG}; }}
QCheckBox {{ color: {_TEXT}; font-size: 13px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border: 2px solid #45475A;
    border-radius: 4px; background: {_SURFACE};
}}
QCheckBox::indicator:checked {{
    background: {_GREEN}; border-color: {_GREEN};
}}
QListWidget {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 4px; font-size: 13px;
}}
QListWidget::item {{ padding: 4px 8px; border-radius: 4px; }}
QListWidget::item:selected {{ background: #45475A; }}
QTabWidget::pane {{ border: 1px solid #45475A; border-radius: 6px; background: {_BG}; }}
QTabBar::tab {{
    background: {_SURFACE}; color: {_TEXT}; padding: 8px 16px;
    border: 1px solid #45475A; border-bottom: none; border-radius: 6px 6px 0 0;
    margin-right: 2px;
}}
QTabBar::tab:selected {{ background: {_BG}; border-color: {_BLUE}; color: {_BLUE}; }}
QGroupBox {{
    color: {_TEXT}; border: 1px solid #45475A; border-radius: 6px;
    margin-top: 12px; padding-top: 16px; font-weight: bold;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}
QComboBox {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 6px 10px; font-size: 13px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background: {_SURFACE}; color: {_TEXT}; selection-background-color: #45475A;
}}
QTextEdit {{
    background: {_SURFACE}; color: {_TEXT}; border: 1px solid #45475A;
    border-radius: 6px; padding: 6px; font-size: 13px;
}}
"""

# ── Islamic reminders (Quran & Hadith) ────────────────────────────────
GAZE_REMINDERS = [
    "قُل لِّلْمُؤْمِنِينَ يَغُضُّوا مِنْ أَبْصَارِهِمْ\n"
    "\"Tell the believing men to lower their gaze\"\n— Surah An-Nur 24:30",

    "وَيَحْفَظُوا فُرُوجَهُمْ ۚ ذَٰلِكَ أَزْكَىٰ لَهُمْ\n"
    "\"…and guard their modesty. That is purer for them.\"\n— Surah An-Nur 24:30",

    "إِنَّ السَّمْعَ وَالْبَصَرَ وَالْفُؤَادَ كُلُّ أُولَٰئِكَ كَانَ عَنْهُ مَسْئُولًا\n"
    "\"Indeed, hearing, sight, and the heart — each will be questioned.\"\n— Surah Al-Isra 17:36",

    "\"The glance is a poisoned arrow from the arrows of Iblis.\n"
    "Whoever lowers his gaze for Allah, He will grant him a\n"
    "sweetness of faith in his heart.\"\n— Hadith (Tabarani)",

    "\"O Ali, do not follow a glance with another,\n"
    "for you will be forgiven for the first,\n"
    "but not for the second.\"\n— Hadith (Abu Dawud, Tirmidhi)",

    "يَعْلَمُ خَائِنَةَ الْأَعْيُنِ وَمَا تُخْفِي الصُّدُورُ\n"
    "\"He knows the treachery of the eyes\n"
    "and what the hearts conceal.\"\n— Surah Ghafir 40:19",

    "\"Whoever guarantees me (the chastity of) what is between\n"
    "his jaws and what is between his legs,\n"
    "I guarantee him Paradise.\"\n— Hadith (Bukhari)",

    "وَلَا تَقْرَبُوا الزِّنَا ۖ إِنَّهُ كَانَ فَاحِشَةً وَسَاءَ سَبِيلًا\n"
    "\"And do not approach unlawful sexual intercourse.\n"
    "Indeed, it is ever an immorality and evil as a way.\"\n— Surah Al-Isra 17:32",

    "\"The adultery of the eyes is the gaze.\"\n— Hadith (Bukhari & Muslim)",

    "وَقُل لِّلْمُؤْمِنَاتِ يَغْضُضْنَ مِنْ أَبْصَارِهِنَّ\n"
    "\"And tell the believing women to lower their gaze\n"
    "and guard their modesty.\"\n— Surah An-Nur 24:31",
]

# ── Default blocked title keywords ────────────────────────────────────
# Three strictness levels: low, medium, high
_BLOCKED_KEYWORDS_LOW = {
    "pornhub", "xvideos", "xnxx", "xhamster", "redtube", "youporn",
    "brazzers", "bangbros", "realitykings", "naughtyamerica",
    "chaturbate", "stripchat", "cam4", "bongacams", "livejasmin",
    "rule34", "e621", "gelbooru", "danbooru",
    "nhentai", "hanime", "hentaihaven",
}

_BLOCKED_KEYWORDS_MEDIUM = _BLOCKED_KEYWORDS_LOW | {
    "onlyfans", "fansly", "manyvids",
    "nsfw", "xxx", "18+", "porn", "hentai",
    "nude", "naked", "sex video",
    "erotic", "adult content",
    "hookup", "escort", "backpage",
}

_BLOCKED_KEYWORDS_HIGH = _BLOCKED_KEYWORDS_MEDIUM | {
    "bikini", "lingerie", "swimsuit model",
    "dating", "tinder", "bumble", "hinge",
    "sugardaddy", "sugarbaby", "seeking arrangement",
    "gambling", "casino", "betway", "bet365", "poker",
    "alcohol", "liquor store", "beer", "wine",
}

_STRICTNESS_MAP = {
    "low": _BLOCKED_KEYWORDS_LOW,
    "medium": _BLOCKED_KEYWORDS_MEDIUM,
    "high": _BLOCKED_KEYWORDS_HIGH,
}

# Pet speech when blocking
_PET_BLOCK_SPEECH = [
    "🛡️ Astaghfirullah! I blocked harmful content for you.",
    "👁️ Lowering your gaze... I've got your back!",
    "🤲 May Allah protect you. Harmful site blocked!",
    "🛡️ Remember: your eyes will be questioned. Blocked!",
    "🐾 *covers eyes* Not on my watch! Site blocked.",
    "📿 SubhanAllah — I caught that in time. Stay pure!",
]

_PET_SCREEN_SPEECH = [
    "🛡️ Inappropriate content detected on screen! Blurring...",
    "👁️ I spotted something haram — activating shield!",
    "🤲 Lowering your gaze... screen protected!",
]

_PET_BLUR_SPEECH = [
    "🕶️ Screen blurred! Take a breath.",
    "👁️ Gaze lowered. Press the hotkey again to unblur.",
]

# ── nudenet label categories (gender-aware) ───────────────────────────
_FEMALE_LABELS = {
    "FACE_FEMALE",
    "FEMALE_BREAST_EXPOSED", "FEMALE_BREAST_COVERED",
    "FEMALE_GENITALIA_EXPOSED", "FEMALE_GENITALIA_COVERED",
}
_MALE_LABELS = {
    "FACE_MALE",
    "MALE_BREAST_EXPOSED", "MALE_BREAST_COVERED",
    "MALE_GENITALIA_EXPOSED", "MALE_GENITALIA_COVERED",
}
_NSFW_EXPOSED = {
    "FEMALE_BREAST_EXPOSED", "FEMALE_GENITALIA_EXPOSED",
    "MALE_BREAST_EXPOSED", "MALE_GENITALIA_EXPOSED",
    "BUTTOCKS_EXPOSED", "ANUS_EXPOSED",
}
_NEUTRAL_BODY = {
    "BUTTOCKS_EXPOSED", "BUTTOCKS_COVERED",
    "ANUS_EXPOSED", "ANUS_COVERED",
    "BELLY_EXPOSED", "BELLY_COVERED",
    "ARMPITS_EXPOSED", "ARMPITS_COVERED",
    "FEET_EXPOSED", "FEET_COVERED",
}

# Map blur_target → which nudenet labels to react to
_BLUR_TARGET_LABELS = {
    "women":     _FEMALE_LABELS | {"BUTTOCKS_EXPOSED", "ANUS_EXPOSED", "BELLY_EXPOSED"},
    "men":       _MALE_LABELS | {"BUTTOCKS_EXPOSED", "ANUS_EXPOSED", "BELLY_EXPOSED"},
    "both":      _FEMALE_LABELS | _MALE_LABELS | _NEUTRAL_BODY,
    "nsfw_only": _NSFW_EXPOSED,
}

# Min confidence threshold per detection strictness
_DETECTION_THRESHOLDS = {
    "low": 0.70,
    "medium": 0.50,
    "high": 0.30,
}

# Blur rendering modes (inspired by HaramBlur)
_BLUR_MODES = ("blur", "gray", "solid")


def _merge_overlapping_rects(detections: list[dict], iou_thresh: float = 0.30) -> list[dict]:
    """Merge overlapping bounding boxes (like HaramBlur's rect merger).

    Prevents multiple overlapping blur patches from stacking and
    flickering.  Uses simple IoU-based greedy merge.
    """
    if len(detections) <= 1:
        return detections

    def _iou(a: QRect, b: QRect) -> float:
        ix = max(a.left(), b.left())
        iy = max(a.top(), b.top())
        ix2 = min(a.right(), b.right())
        iy2 = min(a.bottom(), b.bottom())
        if ix2 <= ix or iy2 <= iy:
            return 0.0
        inter = (ix2 - ix) * (iy2 - iy)
        area_a = a.width() * a.height()
        area_b = b.width() * b.height()
        if area_a + area_b - inter <= 0:
            return 0.0
        return inter / (area_a + area_b - inter)

    merged: list[dict] = []
    used = [False] * len(detections)
    for i, d in enumerate(detections):
        if used[i]:
            continue
        box = QRect(d["box"])
        best_score = d.get("score", 0.0)
        best_class = d.get("class", "")
        best_extra = {k: v for k, v in d.items() if k not in ("box", "score", "class")}
        # Absorb all overlapping boxes
        for j in range(i + 1, len(detections)):
            if used[j]:
                continue
            if _iou(box, detections[j]["box"]) >= iou_thresh:
                used[j] = True
                other = detections[j]["box"]
                box = box.united(other)  # union rect
                if detections[j].get("score", 0) > best_score:
                    best_score = detections[j]["score"]
                    best_class = detections[j].get("class", best_class)
                    best_extra = {k: v for k, v in detections[j].items()
                                  if k not in ("box", "score", "class")}
        result = {"class": best_class, "score": best_score, "box": box}
        result.update(best_extra)
        merged.append(result)
    return merged


# ══════════════════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════════════════

def _default_config() -> dict:
    return {
        "enabled": True,
        "strictness": "medium",        # low / medium / high
        "custom_blocked": [],           # user-added keywords
        "custom_allowed": [],           # whitelisted keywords
        "screen_guard_enabled": False,  # AI screen analysis
        "screen_guard_interval_sec": 2,
        "safe_search_enforced": False,
        "blur_hotkey_enabled": True,
        "auto_close_tab": True,         # send Ctrl+W on block
        "show_overlay": True,           # show blocking overlay
        # ── HaramBlur-like detection settings ──
        "blur_target": "both",          # women / men / both / nsfw_only
        "blur_intensity": 85,           # 0-100 opacity of blur patches
        "detection_strictness": "medium",  # low (>0.7) / medium (>0.5) / high (>0.3)
        "targeted_blur": True,          # True=blur regions, False=full screen
        "hover_to_reveal": False,       # hover over patch to glimpse (not recommended)
        "blur_mode": "blur",            # blur / gray / solid  (like HaramBlur)
        "solid_color": "#808080",       # solid color for solid mode
        # ── New features ──
        "body_coverage": "face_body",   # face_only / face_neck / face_body
        "adaptive_blur": True,          # scale blur strength by detection score
        "edge_feathering": True,        # gradient alpha on blur edges
        "adaptive_interval": True,      # speed up tracking when screen changes fast
        "multi_monitor": True,          # scan all monitors
        "whitelist_rects": [],          # [{"x": int, "y": int, "w": int, "h": int}]
        "toast_on_detect": True,        # show toast on first detection
        "skin_tone_tint": False,        # tint solid blur with skin color
        # ── Statistics ──
        "session_faces_detected": 0,
        "session_start_time": "",
        "total_faces_detected": 0,
        "total_screen_time_sec": 0,
        "daily_stats": {},              # {"2025-01-15": {"blocks": 3, "faces": 12}}
        # ── Streak ──
        "streak_current": 0,
        "streak_longest": 0,
        "streak_start_date": "",
        "last_clean_date": "",
        "total_blocks": 0,
        "incidents": [],                # last 20 incident dates
    }


def _load_config() -> dict:
    cfg = _default_config()
    if os.path.exists(_CONFIG_PATH):
        try:
            with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception:
            pass
    # Migrate old slow interval to fast default
    if cfg.get("screen_guard_interval_sec", 2) > 5:
        cfg["screen_guard_interval_sec"] = 2
    return cfg


def _save_config(cfg: dict):
    from core.safe_json import safe_json_save
    safe_json_save(cfg, _CONFIG_PATH, indent=2)


# ══════════════════════════════════════════════════════════════════════
#  AI DETECTORS — init on MAIN thread (onnxruntime DLL workaround)
# ══════════════════════════════════════════════════════════════════════

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
_FACE_MODEL = os.path.join(_MODELS_DIR, "face_detection_yunet.onnx")
_GENDER_MODEL = os.path.join(_MODELS_DIR, "gender_googlenet.onnx")

_FACE_MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)
_GENDER_MODEL_URL = (
    "https://github.com/onnx/models/raw/main/validated/vision/"
    "body_analysis/age_gender/models/gender_googlenet.onnx"
)


class _DetectorBundle:
    """Holds references to face detector, gender net, and nudenet."""
    __slots__ = ("face_detector", "gender_net", "nude_detector")

    def __init__(self):
        self.face_detector = None  # cv2.FaceDetectorYN
        self.gender_net = None     # cv2.dnn.Net
        self.nude_detector = None  # nudenet.NudeDetector


_shared_bundle: _DetectorBundle | None = None


def _ensure_model(path: str, url: str) -> bool:
    """Download model file if missing. Returns True if file exists."""
    if os.path.exists(path):
        return True
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        log.info("Downloading model: %s", os.path.basename(path))
        import urllib.request
        urllib.request.urlretrieve(url, path)
        log.info("Model downloaded: %s (%d bytes)",
                 os.path.basename(path), os.path.getsize(path))
        return True
    except Exception as e:
        log.warning("Failed to download model %s: %s", os.path.basename(path), e)
        return False


def _init_detectors() -> _DetectorBundle:
    """Initialise ALL detectors on the MAIN thread.

    Must be called before QThread.start() so onnxruntime DLLs are
    loaded while the DLL search path is still intact (before Qt
    modifies it on Windows).
    """
    global _shared_bundle
    if _shared_bundle is not None:
        return _shared_bundle

    import cv2
    bundle = _DetectorBundle()

    # 1. YuNet face detector (OpenCV, ~230KB, very fast)
    if _ensure_model(_FACE_MODEL, _FACE_MODEL_URL):
        try:
            bundle.face_detector = cv2.FaceDetectorYN.create(
                _FACE_MODEL, "", (320, 320), 0.5, 0.3, 5000)
            log.info("Face detector (YuNet) loaded")
        except Exception as e:
            log.warning("Face detector failed: %s", e)

    # 2. Gender classifier (GoogLeNet ONNX, ~24MB)
    if _ensure_model(_GENDER_MODEL, _GENDER_MODEL_URL):
        try:
            bundle.gender_net = cv2.dnn.readNetFromONNX(_GENDER_MODEL)
            log.info("Gender classifier loaded")
        except Exception as e:
            log.warning("Gender classifier failed: %s", e)

    # 3. nudenet for NSFW body detection (optional)
    try:
        from nudenet import NudeDetector
        bundle.nude_detector = NudeDetector()
        log.info("nudenet NSFW detector loaded")
    except Exception as e:
        log.info("nudenet not available (optional): %s", e)

    _shared_bundle = bundle
    ok_parts = []
    if bundle.face_detector:
        ok_parts.append("face")
    if bundle.gender_net:
        ok_parts.append("gender")
    if bundle.nude_detector:
        ok_parts.append("nsfw")
    log.info("Detector bundle: %s", "+".join(ok_parts) or "none")
    return bundle


# ══════════════════════════════════════════════════════════════════════
#  SCREEN ANALYZER — dual AI (face+gender AND nudenet NSFW)
# ══════════════════════════════════════════════════════════════════════

class _ScreenAnalyzer(QThread):
    """Real-time screen scanner with dual detection pipeline.

    Pipeline 1 — Face + Gender (OpenCV YuNet + GoogLeNet):
        Detects faces, classifies gender, applies blur based on target.
        Very fast (~40ms), runs every cycle.

    Pipeline 2 — NSFW Body (nudenet):
        Detects exposed body parts. Slower (~200ms), runs every Nth cycle.

    All detectors are pre-initialised on the main thread and shared.
    """
    detections_found = pyqtSignal(list, object)  # [{class, score, box}], QPixmap
    unsafe_detected = pyqtSignal(float)           # max NSFW score

    # Fast face tracking interval in seconds.  Face detection is cheap
    # (~30 ms) so we can afford to run it frequently for smooth tracking.
    _TRACK_INTERVAL = 0.4

    def __init__(self, bundle: _DetectorBundle, interval_sec: int = 2,
                 blur_target: str = "both", min_confidence: float = 0.50,
                 multi_monitor: bool = True, adaptive_interval: bool = True,
                 body_coverage: str = "face_body",
                 whitelist_rects: list | None = None):
        super().__init__()
        self._bundle = bundle
        self._full_interval = interval_sec   # gender + nudenet
        self._running = False
        self._blur_target = blur_target
        self._min_confidence = min_confidence
        self._multi_monitor = multi_monitor
        self._adaptive_interval = adaptive_interval
        self._body_coverage = body_coverage
        self._whitelist_rects = [QRect(r["x"], r["y"], r["w"], r["h"])
                                 for r in (whitelist_rects or [])
                                 if all(k in r for k in ("x", "y", "w", "h"))]
        # nudenet runs in a background thread to avoid blocking face detect
        self._nsfw_every_n = max(1, 15 // max(1, interval_sec))  # ~15s
        self._cycle = 0
        self._nsfw_results: list[dict] = []  # latest nudenet results
        self._nsfw_lock = __import__("threading").Lock()
        # Screen change detection — checked EVERY cycle for scroll/tab responsiveness
        self._prev_hash: int | None = None
        self._screen_changed = False  # True when hash changed this cycle
        # Change rate tracking for adaptive intervals
        self._change_history: deque = deque(maxlen=10)  # last 10 hash comparisons
        self._current_track_interval = self._TRACK_INTERVAL
        # Gender cache: remembers gender per-face across fast-track cycles
        self._gender_cache: list[dict] = []  # [{"box": QRect, "gender": str}]
        # Miss counter: consecutive cycles with no detections.
        # After several misses we know faces truly left and can clear.
        self._miss_count = 0
        # Sticky detections: last known good detections + screenshot,
        # re-emitted when the face detector fails (e.g. overlay captured
        # over the face making it unrecognisable).
        self._last_detections: list[dict] = []
        self._last_pix: object = None  # QPixmap
        # EMA-smoothed positions keyed by face index for jitter reduction
        self._smooth_positions: list[dict] = []  # [{"box": QRect, ...}]
        self._ema_alpha = 0.7  # higher = more responsive, lower = smoother

    def set_blur_target(self, target: str):
        self._blur_target = target

    def set_min_confidence(self, val: float):
        self._min_confidence = val

    def set_body_coverage(self, mode: str):
        self._body_coverage = mode

    def set_whitelist_rects(self, rects: list):
        self._whitelist_rects = [QRect(r["x"], r["y"], r["w"], r["h"])
                                 for r in rects
                                 if all(k in r for k in ("x", "y", "w", "h"))]

    def run(self):
        self._running = True
        if not self._bundle or (
            not self._bundle.face_detector and not self._bundle.nude_detector
        ):
            log.warning("Screen guard: no detectors available")
            self._running = False
            return

        log.info("Screen guard: running (full=%ds, track=%.1fs, target=%s, thresh=%.2f)",
                 self._full_interval, self._TRACK_INTERVAL,
                 self._blur_target, self._min_confidence)

        last_full = 0.0
        while self._running:
            now = time.time()
            do_full = (now - last_full) >= self._full_interval
            try:
                self._analyze_screen(full_analysis=do_full)
            except Exception as e:
                log.debug("Screen analysis error: %s", e)
            if do_full:
                last_full = now
                self._cycle += 1
            # Sleep in ~100 ms increments for responsiveness
            interval = self._current_track_interval
            ticks = max(1, int(interval * 10))
            for _ in range(ticks):
                if not self._running:
                    break
                self.msleep(100)

    def stop(self):
        self._running = False

    def _capture_screen(self):
        """Grab screen(s) and return list of (numpy_rgb, full_pixmap, geo, actual_w, actual_h).

        When multi_monitor is True, captures all screens; otherwise just primary.
        Returns RGB directly — YuNet and GoogLeNet work fine on RGB.
        """
        import numpy as np
        screens = QGuiApplication.screens() if self._multi_monitor else []
        if not screens:
            screen = QGuiApplication.primaryScreen()
            screens = [screen] if screen else []
        if not screens:
            return []

        cap_w, cap_h = 640, 360

        results = []
        for screen in screens:
            geo = screen.geometry()
            pix = screen.grabWindow(0)
            if pix.isNull():
                continue
            pix_small = pix.scaled(
                cap_w, cap_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            actual_w = pix_small.width()
            actual_h = pix_small.height()
            qimg = pix_small.toImage().convertToFormat(QImage.Format.Format_RGB888)
            ptr = qimg.bits()
            ptr.setsize(qimg.sizeInBytes())
            bpl = qimg.bytesPerLine()
            _h, _w = qimg.height(), qimg.width()
            _raw = np.frombuffer(ptr, dtype=np.uint8).reshape((_h, bpl))
            img = _raw[:, :_w * 3].reshape((_h, _w, 3)).copy()
            results.append((img, pix, geo, actual_w, actual_h))
        return results

    def _analyze_screen(self, full_analysis: bool = False):
        """Two-tier detection with multi-monitor, adaptive intervals,
        configurable body coverage, and whitelist support.
        """
        import cv2
        import numpy as np
        t_start = time.perf_counter()
        captures = self._capture_screen()
        if not captures:
            return

        all_detections: list[dict] = []
        max_nsfw = 0.0
        target = self._blur_target
        threshold = self._min_confidence
        combined_pix = None  # use first screen's pixmap for overlay

        for cap_idx, (img, full_pix, geo, actual_w, actual_h) in enumerate(captures):
            if cap_idx == 0:
                combined_pix = full_pix

            # ── Screen change detection (EVERY cycle for scroll/tab responsiveness) ──
            tiny = cv2.resize(img, (32, 18), interpolation=cv2.INTER_AREA)
            cur_hash = hash(tiny.tobytes())
            changed = self._prev_hash is None or cur_hash != self._prev_hash
            self._screen_changed = changed
            self._change_history.append(changed)
            self._prev_hash = cur_hash

            if full_analysis and not changed and cap_idx == 0:
                full_analysis = False

            # When screen changed: reset EMA positions so blur
            # jumps to new locations instantly (no drag during scroll)
            if changed:
                self._smooth_positions = []

            # ── Adaptive interval: speed up for video/scroll ─────
            if self._adaptive_interval and len(self._change_history) >= 3:
                recent = list(self._change_history)[-5:]
                change_rate = sum(recent) / len(recent)
                if change_rate > 0.7:
                    self._current_track_interval = 0.15  # video/scroll: 150ms
                elif change_rate < 0.3:
                    self._current_track_interval = 0.5  # static: 500ms
                else:
                    self._current_track_interval = self._TRACK_INTERVAL

            sx = geo.width() / actual_w
            sy = geo.height() / actual_h

            # ── Pipeline 1: Face detection (ALWAYS) + gender (full) ──
            new_gender_cache: list[dict] = []
            if self._bundle.face_detector and target != "nsfw_only":
                fd = self._bundle.face_detector
                h, w = img.shape[:2]
                fd.setInputSize((w, h))
                _, faces = fd.detect(img)
                if faces is not None:
                    for face in faces:
                        x, y, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                        conf = float(face[14])
                        if conf < threshold:
                            continue

                        # ── Face rect: anatomically-aware padding ────
                        pad_top = int(fh * 0.55)
                        pad_bottom = int(fh * 0.45)
                        pad_side = int(fw * 0.30)
                        fx1 = int(max(0, x - pad_side) * sx) + geo.x()
                        fy1 = int(max(0, y - pad_top) * sy) + geo.y()
                        fx2 = int(min(actual_w, x + fw + pad_side) * sx) + geo.x()
                        fy2 = int(min(actual_h, y + fh + pad_bottom) * sy) + geo.y()
                        face_rect = QRect(fx1, fy1, fx2 - fx1, fy2 - fy1)

                        # ── Extract 5 YuNet landmarks (screen coords) ─
                        landmarks = []
                        try:
                            for li in range(5):
                                lx = int(float(face[4 + li * 2]) * sx) + geo.x()
                                ly = int(float(face[5 + li * 2]) * sy) + geo.y()
                                landmarks.append((lx, ly))
                        except (IndexError, ValueError):
                            landmarks = []

                        # ── Whitelist check ──────────────────────────
                        if self._is_whitelisted(face_rect):
                            continue

                        # ── Body rect based on coverage setting ──────
                        body_rect = None
                        coverage = self._body_coverage
                        if coverage != "face_only":
                            face_cx = x + fw // 2
                            if coverage == "face_neck":
                                body_w = int(fw * 1.8)
                                body_h = int(fh * 1.2)
                            else:  # face_body
                                body_w = int(fw * 3.0)
                                body_h = int(fh * 3.0)
                            body_x = int(max(0, face_cx - body_w // 2) * sx) + geo.x()
                            body_y = fy2
                            body_bx = int(min(actual_w, face_cx + body_w // 2) * sx) + geo.x()
                            body_by = int(min(actual_h, y + fh + pad_bottom + body_h) * sy) + geo.y()
                            body_rect = QRect(body_x, body_y,
                                              body_bx - body_x, body_by - body_y)

                        # ── Gender ───────────────────────────────────
                        gender = "unknown"
                        if full_analysis and self._bundle.gender_net:
                            ex, ey = int(fw * 0.3), int(fh * 0.3)
                            cx, cy = max(0, x - ex), max(0, y - ey)
                            cw = min(w, x + fw + ex) - cx
                            ch = min(h, y + fh + ey) - cy
                            crop = img[cy:cy+ch, cx:cx+cw]
                            if crop.size > 0:
                                blob = cv2.dnn.blobFromImage(
                                    crop, 1.0, (227, 227),
                                    (114.9, 87.8, 78.4), swapRB=True)
                                self._bundle.gender_net.setInput(blob)
                                preds = self._bundle.gender_net.forward()
                                m = float(preds[0][0])
                                f = float(preds[0][1])
                                if abs(m - f) < 0.25:
                                    gender = "unknown"
                                elif m > f:
                                    gender = "male"
                                else:
                                    gender = "female"
                        else:
                            gender = self._match_gender_cache(face_rect)

                        new_gender_cache.append(
                            {"box": face_rect, "gender": gender})

                        # ── Filter by target ─────────────────────────
                        if full_analysis:
                            if target == "women" and gender != "female":
                                continue
                            if target == "men" and gender != "male":
                                continue
                        else:
                            if target == "women" and gender == "male":
                                continue
                            if target == "men" and gender == "female":
                                continue

                        label = f"FACE_{gender.upper()}"
                        # ── Skin-tone sampling ───────────────────────
                        skin_color = None
                        try:
                            # Sample center of face crop for dominant skin tone
                            fc_x = max(0, x + fw // 4)
                            fc_y = max(0, y + fh // 4)
                            fc_w = max(1, fw // 2)
                            fc_h = max(1, fh // 2)
                            face_crop = img[fc_y:fc_y+fc_h, fc_x:fc_x+fc_w]
                            if face_crop.size > 0:
                                avg = face_crop.mean(axis=(0, 1)).astype(int)
                                skin_color = f"#{avg[0]:02x}{avg[1]:02x}{avg[2]:02x}"
                        except Exception:
                            pass

                        all_detections.append({
                            "class": label,
                            "score": conf,
                            "box": face_rect,
                            "skin_color": skin_color,
                            "landmarks": landmarks,
                        })
                        if body_rect and body_rect.height() > 10 and body_rect.width() > 10:
                            all_detections.append({
                                "class": f"BODY_{gender.upper()}",
                                "score": conf * 0.8,
                                "box": body_rect,
                                "skin_color": skin_color,
                                "body_mask": None,
                            })

                # Update gender cache
                if full_analysis:
                    self._gender_cache = new_gender_cache
                elif new_gender_cache:
                    self._gender_cache = new_gender_cache

        t_face = time.perf_counter()

        # ── Pipeline 2: NSFW body detection (full analysis only) ─────
        with self._nsfw_lock:
            for det in self._nsfw_results:
                if not self._is_whitelisted(det["box"]):
                    all_detections.append(det)
                    score = det.get("score", 0.0)
                    if score > max_nsfw:
                        max_nsfw = score

        if (full_analysis and self._bundle.nude_detector
                and captures
                and self._cycle > 0
                and (self._cycle % max(1, self._nsfw_every_n) == 0)):
            img0, _, geo0, _, _ = captures[0]
            import threading
            threading.Thread(
                target=self._run_nudenet_async,
                args=(img0, geo0.width() / max(1, img0.shape[1]),
                      geo0.height() / max(1, img0.shape[0]),
                      geo0, target, threshold),
                daemon=True,
            ).start()

        t_end = time.perf_counter()

        # ── Emit results ─────────────────────────────────────────────
        if all_detections:
            self._miss_count = 0
            all_detections = _merge_overlapping_rects(all_detections)
            # EMA smooth positions to reduce jitter
            all_detections = self._smooth_detections(all_detections)
            if full_analysis:
                log.info("Screen guard [full]: %d detections "
                         "(face=%.0fms nsfw=%.0fms target=%s)",
                         len(all_detections),
                         (t_face - t_start) * 1000,
                         (t_end - t_face) * 1000, target)
            self._last_detections = all_detections
            self._last_pix = combined_pix
            self.detections_found.emit(all_detections, combined_pix)
            if max_nsfw > 0:
                self.unsafe_detected.emit(max_nsfw)
        else:
            self._miss_count += 1
            # If screen changed (scroll/tab), clear immediately — stale blur
            # at wrong positions is worse than a brief flash of content.
            if self._screen_changed:
                self._last_detections = []
                self._last_pix = None
                self._smooth_positions = []
                self.detections_found.emit([], None)
            elif self._miss_count <= 4 and self._last_detections:
                self.detections_found.emit(
                    self._last_detections, self._last_pix)
            elif self._miss_count > 4:
                self._last_detections = []
                self._last_pix = None
                self.detections_found.emit([], None)

    def _is_whitelisted(self, rect: QRect) -> bool:
        """Check if a detection falls entirely within a whitelisted region."""
        for wr in self._whitelist_rects:
            if wr.contains(rect):
                return True
        return False

    def _smooth_detections(self, detections: list[dict]) -> list[dict]:
        """EMA smooth detection positions to reduce frame-to-frame jitter.

        Matches current detections to previous smoothed positions by IoU,
        then blends the new box toward the old one.
        """
        if not self._smooth_positions:
            self._smooth_positions = detections
            return detections

        alpha = self._ema_alpha
        smoothed = []
        used_prev = [False] * len(self._smooth_positions)

        for det in detections:
            box = det["box"]
            best_idx = -1
            best_iou = 0.3  # min IoU to consider a match
            for pi, prev in enumerate(self._smooth_positions):
                if used_prev[pi]:
                    continue
                iou = self._calc_iou(box, prev["box"])
                if iou > best_iou:
                    best_iou = iou
                    best_idx = pi

            if best_idx >= 0:
                used_prev[best_idx] = True
                prev_box = self._smooth_positions[best_idx]["box"]
                # Blend: new = alpha * current + (1-alpha) * previous
                sx = int(alpha * box.x() + (1 - alpha) * prev_box.x())
                sy = int(alpha * box.y() + (1 - alpha) * prev_box.y())
                sw = int(alpha * box.width() + (1 - alpha) * prev_box.width())
                sh = int(alpha * box.height() + (1 - alpha) * prev_box.height())
                new_det = dict(det)
                new_det["box"] = QRect(sx, sy, max(4, sw), max(4, sh))
                smoothed.append(new_det)
            else:
                smoothed.append(det)

        self._smooth_positions = smoothed
        return smoothed

    # ── Gender cache helpers ─────────────────────────────────────────

    def _match_gender_cache(self, rect: QRect) -> str:
        """Find best matching gender from the cache using IoU overlap."""
        best_iou = 0.0
        best_gender = "unknown"
        for cached in self._gender_cache:
            iou = self._calc_iou(rect, cached["box"])
            if iou > best_iou:
                best_iou = iou
                best_gender = cached["gender"]
        return best_gender if best_iou > 0.15 else "unknown"

    @staticmethod
    def _calc_iou(a: QRect, b: QRect) -> float:
        ix = max(a.left(), b.left())
        iy = max(a.top(), b.top())
        ix2 = min(a.right(), b.right())
        iy2 = min(a.bottom(), b.bottom())
        if ix2 <= ix or iy2 <= iy:
            return 0.0
        inter = (ix2 - ix) * (iy2 - iy)
        area_a = a.width() * a.height()
        area_b = b.width() * b.height()
        denom = area_a + area_b - inter
        return inter / denom if denom > 0 else 0.0

    def _run_nudenet_async(self, img, sx, sy, geo, target, threshold):
        """Run nudenet in a separate thread so face detection isn't blocked."""
        import cv2
        tmp = os.path.join(tempfile.gettempdir(), "_toty_nsfw.jpg")
        # img is RGB; cv2.imwrite expects BGR
        bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        cv2.imwrite(tmp, bgr, [cv2.IMWRITE_JPEG_QUALITY, 60])
        try:
            results = self._bundle.nude_detector.detect(tmp)
            target_labels = _BLUR_TARGET_LABELS.get(target,
                                                     _BLUR_TARGET_LABELS["both"])
            new_results = []
            for det in results:
                label = det.get("class", "")
                score = det.get("score", 0.0)
                if label not in target_labels or score < threshold:
                    continue
                box = det.get("box", [0, 0, 0, 0])
                rx = int(box[0] * sx) + geo.x()
                ry = int(box[1] * sy) + geo.y()
                rw = int(box[2] * sx)
                rh = int(box[3] * sy)
                pad_x = int(rw * 0.2)
                pad_y = int(rh * 0.2)
                screen_rect = QRect(
                    max(rx - pad_x, geo.x()),
                    max(ry - pad_y, geo.y()),
                    min(rw + pad_x * 2, geo.width()),
                    min(rh + pad_y * 2, geo.height()),
                )
                new_results.append({
                    "class": label,
                    "score": score,
                    "box": screen_rect,
                })
            with self._nsfw_lock:
                self._nsfw_results = new_results
            if new_results:
                log.info("nudenet async: %d NSFW detections", len(new_results))
        except Exception as e:
            log.warning("nudenet async error: %s", e)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass


# ══════════════════════════════════════════════════════════════════════
#  OVERLAY WIDGETS
# ══════════════════════════════════════════════════════════════════════


class _RegionBlurOverlay(QWidget):
    """Full-screen click-through overlay that paints blur patches at detected
    screen regions — similar to how HaramBlur blurs faces/bodies in-browser.

    Each detected region gets a tinted rectangle with an Islamic geometric
    pattern and a shield icon, hiding the underlying content.
    """

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput   # click-through
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self._regions: list[dict] = []   # [{"box": QRect, "class": str, "score": float}]
        self._intensity = 85             # 0-100 blur opacity
        self._hover_reveal = False
        self._hover_pos = QPoint()
        self._visible = False
        self._cached_screenshot: QPixmap | None = None  # captured once per update
        self._precomputed: list[tuple] = []  # [(QRect, QPixmap|None, is_face, ...)]
        self._prev_precomputed: list[tuple] = []  # previous cycle for caching
        self._blur_mode = "blur"         # blur / gray / solid
        self._solid_color = QColor("#808080")
        self._adaptive_blur = True       # scale blur by detection score
        self._edge_feathering = True     # gradient alpha at edges
        self._skin_tone_tint = False     # tint solid with skin color

        # Auto-hide timer: if no refresh within 2× interval, fade out
        self._expire_timer = QTimer(self)
        self._expire_timer.setSingleShot(True)
        self._expire_timer.timeout.connect(self._on_expired)

        # Make click-through on Windows via ctypes
        self._apply_click_through()

    def _apply_click_through(self):
        """Set WS_EX_TRANSPARENT | WS_EX_LAYERED so mouse events pass through,
        and WDA_EXCLUDEFROMCAPTURE so screen capture APIs don't see us.
        """
        try:
            import ctypes
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32

            # Click-through
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x00080000
            WS_EX_TRANSPARENT = 0x00000020
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TRANSPARENT)

            # Exclude from screen capture (Win10 2004+).
            # This is THE critical fix: without it, grabWindow() captures
            # our blur overlay, the face detector sees a blurred blob
            # instead of a face, detection fails, overlay clears, face
            # reappears, detected again → flicker cycle.
            WDA_EXCLUDEFROMCAPTURE = 0x00000011
            user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass  # fallback: WindowTransparentForInput flag handles click-through

    def set_intensity(self, value: int):
        self._intensity = max(0, min(100, value))
        self.update()

    def set_hover_reveal(self, on: bool):
        self._hover_reveal = on
        if on:
            self.setMouseTracking(True)

    def set_blur_mode(self, mode: str):
        if mode in _BLUR_MODES:
            self._blur_mode = mode
            self.update()

    def set_solid_color(self, color: str):
        self._solid_color = QColor(color)
        self.update()

    def set_adaptive_blur(self, on: bool):
        self._adaptive_blur = on

    def set_edge_feathering(self, on: bool):
        self._edge_feathering = on

    def set_skin_tone_tint(self, on: bool):
        self._skin_tone_tint = on

    def update_regions(self, detections: list[dict],
                       screenshot: QPixmap | None = None,
                       expire_sec: int = 25):
        """Update the overlay with new detection regions.

        Args:
            detections: list of {"box": QRect, "class": str, "score": float}
            screenshot: full-res screenshot captured by the analyzer.
                        Passed directly so we never need to hide/show
                        the overlay to get a clean capture (flicker fix).
            expire_sec: auto-hide after this many seconds if not refreshed
        """
        self._regions = detections
        if not detections:
            return  # keep current state; expire timer handles cleanup

        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

        # Use the screenshot from the analyzer (captured while the overlay
        # was still showing the PREVIOUS cycle's blur, which is fine —
        # re-blurring already-blurred content just makes it MORE hidden).
        if screenshot is not None and not screenshot.isNull():
            self._cached_screenshot = screenshot
        elif self._cached_screenshot is None and screen:
            # Fallback: first time only, capture directly
            self._cached_screenshot = screen.grabWindow(0)

        if not self._visible:
            self.show()
            self.raise_()
            self._visible = True
            self._apply_click_through()  # re-apply after show

        # Pre-compute blurred / gray / solid patches so paintEvent
        # just blits them (fast, no per-frame scaling).
        self._precompute_patches()
        self.update()
        self._expire_timer.start(expire_sec * 1000)

    def _precompute_patches(self):
        """Build ready-to-paint pixmaps for each region.

        Uses cv2.GaussianBlur for high-quality blur (vs pixelate hack).
        Caches patches when a detection barely moved (IoU > 0.85).
        Carries landmarks and body_mask for contour-aware painting.
        """
        prev = {id(p[0]): p for p in self._prev_precomputed}
        self._prev_precomputed = self._precomputed
        self._precomputed = []
        ss = self._cached_screenshot
        if ss is None:
            return
        mode = self._blur_mode
        base_intensity = self._intensity
        for det in self._regions:
            rect = det["box"]
            if rect.width() < 4 or rect.height() < 4:
                continue
            is_face = det.get("class", "").startswith("FACE_")
            score = det.get("score", 0.7)
            skin_color = det.get("skin_color")
            landmarks = det.get("landmarks", [])
            body_mask = det.get("body_mask")  # QImage or None

            # Adaptive blur: higher confidence → heavier blur
            if self._adaptive_blur:
                intensity = int(base_intensity * min(1.0, 0.5 + score * 0.6))
            else:
                intensity = base_intensity

            # ── Patch caching: reuse if position barely changed ──
            cached_patch = self._find_cached_patch(rect, self._prev_precomputed)
            if cached_patch is not None:
                # Update metadata but reuse pixmap
                self._precomputed.append(
                    (rect, cached_patch, is_face, score, skin_color,
                     landmarks, body_mask))
                continue

            if mode == "solid":
                self._precomputed.append(
                    (rect, None, is_face, score, skin_color,
                     landmarks, body_mask))
            elif mode == "gray":
                cropped = ss.copy(rect)
                if cropped.isNull():
                    continue
                gray_img = cropped.toImage().convertToFormat(
                    QImage.Format.Format_Grayscale8)
                self._precomputed.append(
                    (rect, QPixmap.fromImage(gray_img), is_face, score,
                     skin_color, landmarks, body_mask))
            else:
                # cv2 GaussianBlur for much better visual quality
                blur_pix = self._cv2_gaussian_blur(ss, rect, intensity)
                if blur_pix is None:
                    continue
                self._precomputed.append(
                    (rect, blur_pix, is_face, score, skin_color,
                     landmarks, body_mask))

    @staticmethod
    def _find_cached_patch(rect: QRect, prev_patches: list) -> 'QPixmap | None':
        """Return cached patch pixmap if a previous patch overlaps > 85%."""
        for prev_rect, prev_pix, *_ in prev_patches:
            if prev_pix is None:
                continue
            # Quick overlap check
            ix = max(rect.left(), prev_rect.left())
            iy = max(rect.top(), prev_rect.top())
            ix2 = min(rect.right(), prev_rect.right())
            iy2 = min(rect.bottom(), prev_rect.bottom())
            if ix2 <= ix or iy2 <= iy:
                continue
            inter = (ix2 - ix) * (iy2 - iy)
            area_cur = rect.width() * rect.height()
            area_prev = prev_rect.width() * prev_rect.height()
            denom = area_cur + area_prev - inter
            if denom > 0 and inter / denom > 0.85:
                return prev_pix
        return None

    @staticmethod
    def _cv2_gaussian_blur(screenshot: QPixmap, rect: QRect,
                           intensity: int) -> 'QPixmap | None':
        """High-quality Gaussian blur via cv2 instead of pixelate+upscale."""
        import cv2
        import numpy as np
        cropped = screenshot.copy(rect)
        if cropped.isNull():
            return None
        qimg = cropped.toImage().convertToFormat(QImage.Format.Format_RGB888)
        ptr = qimg.bits()
        ptr.setsize(qimg.sizeInBytes())
        bpl = qimg.bytesPerLine()
        h, w = qimg.height(), qimg.width()
        raw = np.frombuffer(ptr, dtype=np.uint8).reshape((h, bpl))
        arr = raw[:, :w * 3].reshape((h, w, 3)).copy()
        # Kernel size scales with intensity (must be odd)
        ksize = max(3, int(intensity / 2)) | 1  # ensure odd
        # Multiple passes for very heavy blur
        passes = max(1, intensity // 25)
        for _ in range(passes):
            arr = cv2.GaussianBlur(arr, (ksize, ksize), 0)
        # Convert back to QPixmap
        h, w, ch = arr.shape
        result_img = QImage(arr.data, w, h, w * ch,
                           QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(result_img)

    def clear(self):
        """Remove all blur patches and hide."""
        self._regions.clear()
        self._cached_screenshot = None
        self._prev_precomputed = []
        if self._visible:
            self.hide()
            self._visible = False
        self._expire_timer.stop()

    def _on_expired(self):
        """Auto-clear if screen analyzer hasn't refreshed."""
        self.clear()

    def paintEvent(self, e):
        """Contour-aware rendering: landmark polygon for faces, GrabCut
        silhouette for bodies, with edge feathering.
        """
        if not self._precomputed:
            return

        from PyQt6.QtGui import QPainterPath, QPolygonF
        from PyQt6.QtCore import QPointF

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        intensity = self._intensity
        mode = self._blur_mode

        for item in self._precomputed:
            rect, patch_pix, is_face, score, skin_color = item[:5]
            landmarks = item[5] if len(item) > 5 else []
            body_mask = item[6] if len(item) > 6 else None

            # Skip if hover-reveal active
            if self._hover_reveal and rect.contains(self._hover_pos):
                continue

            # ── Build clip path ──────────────────────────────────
            if is_face:
                clip = QPainterPath()
                clip.addEllipse(rect.toRectF())
                p.setClipPath(clip)
            else:
                clip = self._body_shape_path(rect)
                p.setClipPath(clip)

            # ── Draw blur content ────────────────────────────────
            if mode == "solid":
                if self._skin_tone_tint and skin_color:
                    c = QColor(skin_color)
                    c.setAlpha(int(255 * intensity / 100))
                else:
                    c = QColor(self._solid_color)
                    c.setAlpha(int(255 * intensity / 100))
                p.setBrush(QBrush(c))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(rect)

            elif mode == "gray" and patch_pix is not None:
                p.drawPixmap(rect, patch_pix)
                overlay_c = QColor(0, 0, 0, int(180 * intensity / 100))
                p.setBrush(QBrush(overlay_c))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(rect)

            elif patch_pix is not None:
                p.drawPixmap(rect, patch_pix)

            p.setClipping(False)

            # ── Edge feathering ──────────────────────────────────
            if self._edge_feathering and rect.width() > 20 and rect.height() > 20:
                feather = min(16, rect.width() // 6, rect.height() // 6)
                if is_face:
                    cx = rect.center().x()
                    cy = rect.center().y()
                    rx = rect.width() / 2.0
                    ry = rect.height() / 2.0
                    grad = QRadialGradient(cx, cy, max(rx, ry))
                    grad.setColorAt(0.0, QColor(0, 0, 0, 0))
                    grad.setColorAt(max(0.0, 1.0 - feather / max(rx, ry, 1)),
                                    QColor(0, 0, 0, 0))
                    grad.setColorAt(1.0, QColor(0, 0, 0, 60))
                    p.setBrush(QBrush(grad))
                    p.setPen(Qt.PenStyle.NoPen)
                    p.drawEllipse(rect)
                else:
                    for side_rect, grad in self._edge_feather_gradients(rect, feather):
                        p.setBrush(QBrush(grad))
                        p.setPen(Qt.PenStyle.NoPen)
                        p.drawRect(side_rect)

        p.end()

    @staticmethod
    def _body_shape_path(rect: QRect) -> 'QPainterPath':
        """Body/torso-shaped clip path using bezier curves.

        Creates a natural human torso silhouette: wide shoulders,
        narrower waist, slightly wider hips.  Much faster than
        GrabCut and produces a consistent, flicker-free shape.
        """
        from PyQt6.QtGui import QPainterPath
        x, y = float(rect.x()), float(rect.y())
        w, h = float(rect.width()), float(rect.height())
        path = QPainterPath()
        # Start top-left (shoulder)
        path.moveTo(x + w * 0.05, y)
        # Top edge (shoulders)
        path.lineTo(x + w * 0.95, y)
        # Right side: shoulder → waist → hip → bottom
        path.cubicTo(x + w * 1.02, y + h * 0.10,
                     x + w * 0.75, y + h * 0.40,
                     x + w * 0.80, y + h * 0.55)
        path.cubicTo(x + w * 0.85, y + h * 0.70,
                     x + w * 0.82, y + h * 0.88,
                     x + w * 0.75, y + h)
        # Bottom edge
        path.lineTo(x + w * 0.25, y + h)
        # Left side: bottom → hip → waist → shoulder
        path.cubicTo(x + w * 0.18, y + h * 0.88,
                     x + w * 0.15, y + h * 0.70,
                     x + w * 0.20, y + h * 0.55)
        path.cubicTo(x + w * 0.25, y + h * 0.40,
                     x + w * -0.02, y + h * 0.10,
                     x + w * 0.05, y)
        path.closeSubpath()
        return path

    @staticmethod
    def _edge_feather_gradients(rect: QRect, feather: int):
        """Generate (QRect, QLinearGradient) for each edge of a rectangle."""
        transparent = QColor(0, 0, 0, 0)
        edge_color = QColor(0, 0, 0, 40)
        # Top edge
        r = QRect(rect.x(), rect.y(), rect.width(), feather)
        g = QLinearGradient(r.x(), r.y(), r.x(), r.bottom())
        g.setColorAt(0, edge_color)
        g.setColorAt(1, transparent)
        yield r, g
        # Bottom edge
        r = QRect(rect.x(), rect.bottom() - feather, rect.width(), feather)
        g = QLinearGradient(r.x(), r.bottom(), r.x(), r.y())
        g.setColorAt(0, edge_color)
        g.setColorAt(1, transparent)
        yield r, g
        # Left edge
        r = QRect(rect.x(), rect.y(), feather, rect.height())
        g = QLinearGradient(r.x(), r.y(), r.right(), r.y())
        g.setColorAt(0, edge_color)
        g.setColorAt(1, transparent)
        yield r, g
        # Right edge
        r = QRect(rect.right() - feather, rect.y(), feather, rect.height())
        g = QLinearGradient(r.right(), r.y(), r.x(), r.y())
        g.setColorAt(0, edge_color)
        g.setColorAt(1, transparent)
        yield r, g

    def mouseMoveEvent(self, e):
        if self._hover_reveal:
            self._hover_pos = e.globalPosition().toPoint()
            self.update()
        super().mouseMoveEvent(e)


class _ToastNotification(QWidget):
    """Subtle auto-fading toast shown when Gaze Guard first detects content."""

    def __init__(self, message: str = "🛡️ Gaze Guard — Content detected & blurred"):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(360, 56)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 8)
        lbl = QLabel(message)
        lbl.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_TEAL}; background: transparent;")
        lay.addWidget(lbl)

        # Position: top-right of primary screen
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.right() - self.width() - 20, geo.top() + 20)

        # Auto-fade timer
        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._start_fade)
        self._opacity = 1.0

    def show_toast(self, duration_ms: int = 3000):
        self.setWindowOpacity(0.95)
        self._opacity = 0.95
        self.show()
        self.raise_()
        self._fade_timer.start(duration_ms)

    def _start_fade(self):
        self._fade_step = QTimer(self)
        self._fade_step.setInterval(50)
        self._fade_step.timeout.connect(self._do_fade)
        self._fade_step.start()

    def _do_fade(self):
        self._opacity -= 0.05
        if self._opacity <= 0:
            self._fade_step.stop()
            self.hide()
            self.deleteLater()
        else:
            self.setWindowOpacity(self._opacity)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(49, 50, 68, 230))  # _SURFACE with alpha
        p.setPen(QPen(QColor(_TEAL), 1))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 10, 10)
        p.end()


class _BlockOverlay(QWidget):
    """Full-screen overlay shown when haram content is detected."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setStyleSheet(f"background: {_BG};")

        # Fill all screens
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            self.setGeometry(geo)

        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, 40, 40, 40)
        lay.addStretch(2)

        # Shield icon
        shield = QLabel("🛡️")
        shield.setFont(QFont("Segoe UI Emoji", 64))
        shield.setAlignment(Qt.AlignmentFlag.AlignCenter)
        shield.setStyleSheet("background: transparent;")
        lay.addWidget(shield)

        # Title
        title = QLabel("Content Blocked")
        title.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(f"color: {_RED}; background: transparent;")
        lay.addWidget(title)

        sub = QLabel("Toty Gaze Guard has blocked potentially harmful content")
        sub.setFont(QFont("Arial", 14))
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet(f"color: {_TEXT}; background: transparent;")
        lay.addWidget(sub)

        lay.addSpacing(20)

        # Islamic reminder
        self._reminder_label = QLabel()
        self._reminder_label.setFont(QFont("Arial", 13))
        self._reminder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._reminder_label.setWordWrap(True)
        self._reminder_label.setStyleSheet(
            f"color: {_TEAL}; background: {_SURFACE};"
            f" border: 1px solid #45475A; border-radius: 12px;"
            f" padding: 20px; margin: 20px 80px;")
        self._reminder_label.setMaximumWidth(700)
        lay.addWidget(self._reminder_label, alignment=Qt.AlignmentFlag.AlignCenter)
        self.set_random_reminder()

        lay.addSpacing(20)

        # Dismiss button
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn = QPushButton("🤲 I seek refuge in Allah — Close")
        btn.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        btn.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_BG}; border: none;"
            f" border-radius: 10px; padding: 14px 32px; font-size: 14px; }}"
            f"QPushButton:hover {{ background: #C6F3C1; }}")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._dismiss)
        btn_row.addWidget(btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        lay.addStretch(2)

    def set_random_reminder(self):
        self._reminder_label.setText(random.choice(GAZE_REMINDERS))

    def _dismiss(self):
        self.hide()

    def show_blocking(self):
        """Show the overlay on all screens."""
        self.set_random_reminder()
        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._dismiss()
        super().keyPressEvent(e)


class _BlurOverlay(QWidget):
    """Full-screen dark overlay for instant 'lower your gaze' blur."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")
        self._opacity = 0.88

        screen = QGuiApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.addStretch()

        icon = QLabel("👁️")
        icon.setFont(QFont("Segoe UI Emoji", 48))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("background: transparent;")
        lay.addWidget(icon)

        hint = QLabel("Screen Hidden — Lower Your Gaze\nPress Ctrl+Shift+G to unblur")
        hint.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {_TEAL}; background: transparent;")
        lay.addWidget(hint)

        # Show a reminder
        reminder = QLabel(random.choice(GAZE_REMINDERS))
        reminder.setFont(QFont("Arial", 12))
        reminder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reminder.setWordWrap(True)
        reminder.setMaximumWidth(600)
        reminder.setStyleSheet(f"color: {_TEXT}; background: transparent; margin: 20px;")
        lay.addWidget(reminder, alignment=Qt.AlignmentFlag.AlignCenter)

        lay.addStretch()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(20, 20, 30, int(255 * self._opacity)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRect(self.rect())
        # Geometric pattern
        pen = QPen(QColor(148, 226, 213, 30))
        pen.setWidth(1)
        p.setPen(pen)
        w, h = self.width(), self.height()
        step = 60
        for i in range(0, max(w, h) + step, step):
            p.drawLine(i, 0, 0, i)
            p.drawLine(w - i, 0, w, i)
        p.end()

    def toggle(self):
        if self.isVisible():
            self.hide()
        else:
            screen = QGuiApplication.primaryScreen()
            if screen:
                self.setGeometry(screen.geometry())
            self.showFullScreen()
            self.raise_()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(e)


# ══════════════════════════════════════════════════════════════════════
#  MAIN ENGINE
# ══════════════════════════════════════════════════════════════════════

class GazeGuard:
    """Core engine: monitors window titles, manages blocking, streaks,
    and HaramBlur-like screen guard with gender-aware detection."""

    def __init__(self, on_blocked=None, on_screen_alert=None, on_blur_toggle=None,
                 on_detections=None):
        self.cfg = _load_config()
        self._on_blocked = on_blocked          # callback(keyword)
        self._on_screen_alert = on_screen_alert  # callback(confidence)
        self._on_blur_toggle = on_blur_toggle    # callback(is_visible)
        self._on_detections = on_detections      # callback(count: int)  — NEW

        # Overlays (created lazily to avoid issues before QApp exists)
        self._block_overlay: _BlockOverlay | None = None
        self._blur_overlay: _BlurOverlay | None = None
        self._region_overlay: _RegionBlurOverlay | None = None   # targeted blur

        # Screen analyzer
        self._screen_analyzer: _ScreenAnalyzer | None = None

        # Cooldown to avoid spamming
        self._last_block_time = 0.0
        self._last_blocked_title = ""

        # Session statistics
        self._session_start = time.time()
        self._session_faces = 0
        self._toast_shown = False  # only show toast once per session

        # Init streak from config
        self._update_streak_on_start()

    # ── Title checking ────────────────────────────────────────────────

    def check_title(self, title: str) -> bool:
        """Check a window title for blocked content.

        Returns True if content was blocked.
        """
        if not self.cfg.get("enabled", True):
            return False
        if not title:
            return False

        title_lower = title.lower()

        # Check whitelist first
        for allowed in self.cfg.get("custom_allowed", []):
            if allowed.lower() in title_lower:
                return False

        # Build keyword set based on strictness
        strictness = self.cfg.get("strictness", "medium")
        keywords = _STRICTNESS_MAP.get(strictness, _BLOCKED_KEYWORDS_MEDIUM)

        # Add custom blocked keywords
        custom = {k.lower() for k in self.cfg.get("custom_blocked", [])}
        all_keywords = keywords | custom

        # Check each keyword
        matched = None
        for kw in all_keywords:
            if kw in title_lower:
                matched = kw
                break

        if not matched:
            return False

        # Cooldown: don't re-trigger for same title within 5 seconds
        now = time.time()
        if title_lower == self._last_blocked_title and now - self._last_block_time < 5:
            return True  # Already blocked, don't re-show
        self._last_block_time = now
        self._last_blocked_title = title_lower

        log.info("Gaze Guard: blocked '%s' (keyword: %s)", title[:60], matched)
        self._record_block()

        # Show overlay
        if self.cfg.get("show_overlay", True):
            self._show_block_overlay()

        # Auto-close tab
        if self.cfg.get("auto_close_tab", True):
            self._close_tab()

        # Callback
        if self._on_blocked:
            self._on_blocked(matched)

        return True

    def _show_block_overlay(self):
        if self._block_overlay is None:
            self._block_overlay = _BlockOverlay()
        self._block_overlay.show_blocking()

    def _close_tab(self):
        """Send Ctrl+W to close the current browser tab."""
        try:
            import ctypes
            VK_CONTROL = 0x11
            VK_W = 0x57
            KEYEVENTF_KEYUP = 0x0002
            user32 = ctypes.windll.user32
            user32.keybd_event(VK_CONTROL, 0, 0, 0)
            user32.keybd_event(VK_W, 0, 0, 0)
            user32.keybd_event(VK_W, 0, KEYEVENTF_KEYUP, 0)
            user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)
        except Exception as e:
            log.debug("Failed to send Ctrl+W: %s", e)

    # ── Instant blur ─────────────────────────────────────────────────

    def toggle_blur(self):
        """Toggle the full-screen blur overlay."""
        if self._blur_overlay is None:
            self._blur_overlay = _BlurOverlay()
        self._blur_overlay.toggle()
        if self._on_blur_toggle:
            self._on_blur_toggle(self._blur_overlay.isVisible())

    def is_blur_active(self) -> bool:
        return self._blur_overlay is not None and self._blur_overlay.isVisible()

    # ── Screen guard (AI — HaramBlur-like) ─────────────────────────────

    def start_screen_guard(self):
        """Start the AI screen analyzer with dual pipeline.

        All detectors are initialised HERE (main thread) so
        onnxruntime DLLs load correctly, then shared with the worker.
        """
        if self._screen_analyzer and self._screen_analyzer.isRunning():
            return

        # Init all detectors on main thread — critical for Windows DLLs
        bundle = _init_detectors()
        if not bundle.face_detector and not bundle.nude_detector:
            log.warning("Screen guard: cannot start — no detectors available")
            return

        interval = self.cfg.get("screen_guard_interval_sec", 2)
        target = self.cfg.get("blur_target", "both")
        strictness = self.cfg.get("detection_strictness", "medium")
        threshold = _DETECTION_THRESHOLDS.get(strictness, 0.50)

        self._screen_analyzer = _ScreenAnalyzer(
            bundle=bundle,
            interval_sec=interval,
            blur_target=target,
            min_confidence=threshold,
            multi_monitor=self.cfg.get("multi_monitor", True),
            adaptive_interval=self.cfg.get("adaptive_interval", True),
            body_coverage=self.cfg.get("body_coverage", "face_body"),
            whitelist_rects=self.cfg.get("whitelist_rects", []),
        )
        self._screen_analyzer.detections_found.connect(
            self._on_detections_found)  # (list, QPixmap)
        self._screen_analyzer.unsafe_detected.connect(self._on_screen_unsafe)
        self._screen_analyzer.start()
        self.cfg["screen_guard_enabled"] = True
        _save_config(self.cfg)
        log.info("Screen guard started (full=%ds, track=%.1fs, target=%s, strictness=%s)",
                 interval, self._screen_analyzer._TRACK_INTERVAL, target, strictness)

    def stop_screen_guard(self):
        """Stop the AI screen analyzer and clear overlays."""
        if self._screen_analyzer:
            self._screen_analyzer.stop()
            self._screen_analyzer.wait(3000)
            self._screen_analyzer = None
        if self._region_overlay:
            self._region_overlay.clear()
        self.cfg["screen_guard_enabled"] = False
        _save_config(self.cfg)
        log.info("Screen guard stopped")

    def is_screen_guard_running(self) -> bool:
        return self._screen_analyzer is not None and self._screen_analyzer.isRunning()

    def update_screen_guard_settings(self):
        """Apply current cfg to the running analyzer (live update)."""
        if self._screen_analyzer and self._screen_analyzer.isRunning():
            target = self.cfg.get("blur_target", "both")
            strictness = self.cfg.get("detection_strictness", "medium")
            threshold = _DETECTION_THRESHOLDS.get(strictness, 0.50)
            self._screen_analyzer.set_blur_target(target)
            self._screen_analyzer.set_min_confidence(threshold)
            self._screen_analyzer.set_body_coverage(
                self.cfg.get("body_coverage", "face_body"))
            self._screen_analyzer.set_whitelist_rects(
                self.cfg.get("whitelist_rects", []))
        if self._region_overlay:
            self._region_overlay.set_intensity(self.cfg.get("blur_intensity", 85))
            self._region_overlay.set_hover_reveal(self.cfg.get("hover_to_reveal", False))
            self._region_overlay.set_blur_mode(self.cfg.get("blur_mode", "blur"))
            self._region_overlay.set_solid_color(self.cfg.get("solid_color", "#808080"))
            self._region_overlay.set_adaptive_blur(self.cfg.get("adaptive_blur", True))
            self._region_overlay.set_edge_feathering(self.cfg.get("edge_feathering", True))
            self._region_overlay.set_skin_tone_tint(self.cfg.get("skin_tone_tint", False))

    def _on_detections_found(self, detections: list, screenshot=None):
        """Handle targeted detections — place blur patches on detected regions."""
        if not detections:
            if self._region_overlay:
                self._region_overlay.clear()
            return

        # ── Session statistics ───────────────────────────────────────
        face_count = sum(1 for d in detections if d.get("class", "").startswith("FACE_"))
        self._session_faces += face_count
        self.cfg["total_faces_detected"] = self.cfg.get("total_faces_detected", 0) + face_count
        today = date.today().isoformat()
        daily = self.cfg.get("daily_stats", {})
        if today not in daily:
            daily[today] = {"blocks": 0, "faces": 0}
        daily[today]["faces"] = daily[today].get("faces", 0) + face_count
        self.cfg["daily_stats"] = daily

        # ── Toast notification (once per session) ────────────────────
        if not self._toast_shown and self.cfg.get("toast_on_detect", True):
            self._toast_shown = True
            toast = _ToastNotification()
            toast.show_toast(3000)

        if self.cfg.get("targeted_blur", True):
            if self._region_overlay is None:
                self._region_overlay = _RegionBlurOverlay()
                self._region_overlay.set_intensity(self.cfg.get("blur_intensity", 85))
                self._region_overlay.set_hover_reveal(self.cfg.get("hover_to_reveal", False))
                self._region_overlay.set_blur_mode(self.cfg.get("blur_mode", "blur"))
                self._region_overlay.set_solid_color(self.cfg.get("solid_color", "#808080"))
                self._region_overlay.set_adaptive_blur(self.cfg.get("adaptive_blur", True))
                self._region_overlay.set_edge_feathering(self.cfg.get("edge_feathering", True))
                self._region_overlay.set_skin_tone_tint(self.cfg.get("skin_tone_tint", False))
            self._region_overlay.update_regions(
                detections, screenshot=screenshot, expire_sec=2)
        else:
            if self._blur_overlay is None:
                self._blur_overlay = _BlurOverlay()
            if not self._blur_overlay.isVisible():
                self._blur_overlay.toggle()

        # Notify pet
        if self._on_detections:
            self._on_detections(len(detections))

    def _on_screen_unsafe(self, confidence: float):
        log.info("Screen guard: unsafe content detected (%.1f%%)", confidence * 100)
        self._record_block()
        if self._on_screen_alert:
            self._on_screen_alert(confidence)

    # ── Streak tracking ──────────────────────────────────────────────

    def _update_streak_on_start(self):
        """Update streak based on date — called on init."""
        today = date.today().isoformat()
        last_clean = self.cfg.get("last_clean_date", "")

        if not last_clean:
            # First time — start fresh
            self.cfg["streak_start_date"] = today
            self.cfg["last_clean_date"] = today
            self.cfg["streak_current"] = 0
            _save_config(self.cfg)
            return

        if last_clean == today:
            return  # Already updated today

        # Calculate days since last clean date
        try:
            last_dt = date.fromisoformat(last_clean)
            delta = (date.today() - last_dt).days
            if delta == 1:
                # Consecutive day — increment streak
                self.cfg["streak_current"] = self.cfg.get("streak_current", 0) + 1
                self.cfg["last_clean_date"] = today
                if self.cfg["streak_current"] > self.cfg.get("streak_longest", 0):
                    self.cfg["streak_longest"] = self.cfg["streak_current"]
            elif delta > 1:
                # Gap — but if no incidents, streak continues
                # We only break streak on actual blocks, not missed days
                self.cfg["streak_current"] = self.cfg.get("streak_current", 0) + delta
                self.cfg["last_clean_date"] = today
                if self.cfg["streak_current"] > self.cfg.get("streak_longest", 0):
                    self.cfg["streak_longest"] = self.cfg["streak_current"]
        except (ValueError, TypeError):
            self.cfg["streak_start_date"] = today
            self.cfg["last_clean_date"] = today
            self.cfg["streak_current"] = 0

        _save_config(self.cfg)

    def _record_block(self):
        """Record a blocking incident — resets streak."""
        today = date.today().isoformat()
        self.cfg["total_blocks"] = self.cfg.get("total_blocks", 0) + 1

        # Daily stats
        daily = self.cfg.get("daily_stats", {})
        if today not in daily:
            daily[today] = {"blocks": 0, "faces": 0}
        daily[today]["blocks"] = daily[today].get("blocks", 0) + 1
        self.cfg["daily_stats"] = daily

        # Break streak
        if self.cfg.get("streak_current", 0) > self.cfg.get("streak_longest", 0):
            self.cfg["streak_longest"] = self.cfg["streak_current"]
        self.cfg["streak_current"] = 0
        self.cfg["streak_start_date"] = today

        # Record incident
        incidents = self.cfg.get("incidents", [])
        incidents.append(today)
        self.cfg["incidents"] = incidents[-20:]

        _save_config(self.cfg)

    def get_streak_info(self) -> dict:
        return {
            "current": self.cfg.get("streak_current", 0),
            "longest": self.cfg.get("streak_longest", 0),
            "total_blocks": self.cfg.get("total_blocks", 0),
            "start_date": self.cfg.get("streak_start_date", ""),
        }

    def get_session_stats(self) -> dict:
        """Return current session statistics."""
        elapsed = time.time() - self._session_start
        return {
            "session_faces": self._session_faces,
            "session_time_sec": int(elapsed),
            "total_faces": self.cfg.get("total_faces_detected", 0),
            "total_blocks": self.cfg.get("total_blocks", 0),
            "daily_stats": self.cfg.get("daily_stats", {}),
        }

    # ── SafeSearch enforcer ──────────────────────────────────────────

    @staticmethod
    def enforce_safe_search() -> tuple[bool, str]:
        """Add hosts file entries to force SafeSearch on Google & YouTube.

        Requires admin privileges. Returns (success, message).
        """
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
        marker = "# Toty Gaze Guard SafeSearch"

        entries = [
            marker,
            "216.239.38.120 www.google.com        # Force SafeSearch",
            "216.239.38.120 google.com             # Force SafeSearch",
            "216.239.38.119 www.youtube.com        # Force YouTube Restricted",
            "216.239.38.119 m.youtube.com          # Force YouTube Restricted",
            "216.239.38.119 youtubei.googleapis.com # Force YouTube Restricted",
            "216.239.38.119 youtube.googleapis.com # Force YouTube Restricted",
            "216.239.38.119 www.youtube-nocookie.com # Force YouTube Restricted",
            "strict.bing.com www.bing.com          # Force Bing SafeSearch",
            marker + " END",
        ]

        try:
            # Check if already enforced
            with open(hosts_path, "r", encoding="utf-8") as f:
                content = f.read()
            if marker in content:
                return True, "SafeSearch is already enforced."

            # Need admin — write via elevated PowerShell
            lines_str = "\\n".join(entries)
            cmd = (
                f'Add-Content -Path "{hosts_path}" '
                f'-Value "`n{lines_str}" -Encoding UTF8'
            )

            r = subprocess.run(
                ["powershell", "-Command",
                 f"Start-Process powershell -ArgumentList '-Command','{cmd}' -Verb RunAs -Wait"],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            # Flush DNS
            subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            return True, "SafeSearch enforced! Google & YouTube now use safe mode."
        except Exception as e:
            return False, f"Failed: {e}"

    @staticmethod
    def remove_safe_search() -> tuple[bool, str]:
        """Remove Toty's SafeSearch entries from hosts file."""
        hosts_path = r"C:\Windows\System32\drivers\etc\hosts"
        marker = "# Toty Gaze Guard SafeSearch"

        try:
            with open(hosts_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Filter out our lines
            new_lines = []
            inside_block = False
            for line in lines:
                if marker in line and "END" not in line:
                    inside_block = True
                    continue
                if marker + " END" in line:
                    inside_block = False
                    continue
                if inside_block:
                    continue
                new_lines.append(line)

            content = "".join(new_lines)
            # Write via elevated PowerShell
            content_escaped = content.replace("'", "''").replace("`", "``")
            cmd = f"Set-Content -Path '{hosts_path}' -Value '{content_escaped}' -Encoding UTF8"

            subprocess.run(
                ["powershell", "-Command",
                 f"Start-Process powershell -ArgumentList '-Command','{cmd}' -Verb RunAs -Wait"],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            subprocess.run(
                ["ipconfig", "/flushdns"],
                capture_output=True, timeout=10,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            return True, "SafeSearch entries removed."
        except Exception as e:
            return False, f"Failed: {e}"

    # ── Config management ────────────────────────────────────────────

    def set_enabled(self, on: bool):
        self.cfg["enabled"] = on
        _save_config(self.cfg)

    def set_strictness(self, level: str):
        if level in _STRICTNESS_MAP:
            self.cfg["strictness"] = level
            _save_config(self.cfg)

    def add_blocked_keyword(self, kw: str):
        lst = self.cfg.get("custom_blocked", [])
        if kw.lower() not in [x.lower() for x in lst]:
            lst.append(kw)
            self.cfg["custom_blocked"] = lst
            _save_config(self.cfg)

    def remove_blocked_keyword(self, kw: str):
        lst = self.cfg.get("custom_blocked", [])
        self.cfg["custom_blocked"] = [x for x in lst if x.lower() != kw.lower()]
        _save_config(self.cfg)

    def add_allowed_keyword(self, kw: str):
        lst = self.cfg.get("custom_allowed", [])
        if kw.lower() not in [x.lower() for x in lst]:
            lst.append(kw)
            self.cfg["custom_allowed"] = lst
            _save_config(self.cfg)

    def remove_allowed_keyword(self, kw: str):
        lst = self.cfg.get("custom_allowed", [])
        self.cfg["custom_allowed"] = [x for x in lst if x.lower() != kw.lower()]
        _save_config(self.cfg)

    def save(self):
        _save_config(self.cfg)

    def cleanup(self):
        """Stop all background processes and save session stats."""
        # Save session screen time
        elapsed = int(time.time() - self._session_start)
        self.cfg["total_screen_time_sec"] = self.cfg.get("total_screen_time_sec", 0) + elapsed
        _save_config(self.cfg)

        if self._screen_analyzer:
            self._screen_analyzer.stop()
            self._screen_analyzer.wait(2000)
        if self._block_overlay:
            self._block_overlay.close()
        if self._blur_overlay:
            self._blur_overlay.close()
        if self._region_overlay:
            self._region_overlay.clear()
            self._region_overlay.close()


            self._blur_overlay.close()
        if self._region_overlay:
            self._region_overlay.clear()
            self._region_overlay.close()


# ══════════════════════════════════════════════════════════════════════
#  VIDEO BLUR PROCESSOR — bake blur into video files for sharing
# ══════════════════════════════════════════════════════════════════════

class _VideoBlurProcessor(QThread):
    """Process a video file frame-by-frame, applying face/body blur.

    Creates its OWN face detector and gender net instances to avoid
    thread-safety issues with the live screen guard's shared detectors.
    """
    progress = pyqtSignal(int)       # 0-100
    status = pyqtSignal(str)         # status text
    finished_ok = pyqtSignal(str)    # output path
    finished_err = pyqtSignal(str)   # error message

    def __init__(self, input_path: str, output_path: str,
                 bundle: _DetectorBundle,
                 blur_target: str = "both",
                 min_confidence: float = 0.50,
                 blur_intensity: int = 85,
                 body_coverage: str = "face_body",
                 blur_mode: str = "blur"):
        super().__init__()
        self._input = input_path
        self._output = output_path
        # Only keep nudenet from the shared bundle (it has internal locks).
        # Face detector and gender net are NOT thread-safe — create fresh
        # instances in run() on the worker thread.
        self._nude_detector = bundle.nude_detector if bundle else None
        self._blur_target = blur_target
        self._min_conf = min_confidence
        self._intensity = blur_intensity
        self._body_coverage = body_coverage
        self._blur_mode = blur_mode
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import cv2
        import numpy as np

        # ── Create DEDICATED detectors for this thread ────────────
        # cv2.FaceDetectorYN and cv2.dnn.Net are NOT thread-safe.
        # We must create fresh instances here, not share with screen guard.
        fd = None
        gender_net = None
        try:
            if os.path.exists(_FACE_MODEL):
                fd = cv2.FaceDetectorYN.create(
                    _FACE_MODEL, "", (320, 320), 0.35, 0.3, 5000)
        except Exception:
            pass
        try:
            if os.path.exists(_GENDER_MODEL):
                gender_net = cv2.dnn.readNetFromONNX(_GENDER_MODEL)
        except Exception:
            pass
        nude_det = self._nude_detector

        cap = cv2.VideoCapture(self._input)
        if not cap.isOpened():
            self.finished_err.emit(f"Cannot open video: {self._input}")
            return

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if total_frames <= 0 or w <= 0 or h <= 0:
            cap.release()
            self.finished_err.emit("Invalid video file or cannot read properties.")
            return

        self.status.emit(f"Processing {total_frames} frames at {w}x{h} ({fps:.1f} fps)...")

        # ── Write blurred frames via ffmpeg pipe (H.264 + copy audio) ─
        # This produces a properly encoded mp4 that plays everywhere.
        # Falls back to cv2.VideoWriter if ffmpeg is unavailable.
        use_ffmpeg = self._has_ffmpeg()
        tmp_raw = None

        if use_ffmpeg:
            # Pipe raw frames to ffmpeg which encodes H.264 to a temp file,
            # then mux with audio from original.
            tmp_raw = os.path.join(tempfile.gettempdir(), "_toty_vid_noaudio.mp4")
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-s", f"{w}x{h}",
                "-pix_fmt", "bgr24",
                "-r", str(fps),
                "-i", "-",           # stdin
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                tmp_raw,
            ]
            try:
                ff_proc = subprocess.Popen(
                    ffmpeg_cmd, stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                use_ffmpeg = False

        if not use_ffmpeg:
            # Fallback: cv2 writer with XVID (more compatible than mp4v)
            fourcc = cv2.VideoWriter_fourcc(*"XVID")
            writer = cv2.VideoWriter(self._output, fourcc, fps, (w, h))
            if not writer.isOpened():
                cap.release()
                self.finished_err.emit("Cannot create output video file.")
                return

        target = self._blur_target
        threshold = self._min_conf
        target_labels = _BLUR_TARGET_LABELS.get(target, _BLUR_TARGET_LABELS["both"])

        # Process at detection resolution, preserving aspect ratio
        DET_MAX_DIM = 854  # max dimension for detection
        MAX_REGIONS = 20  # safety cap to prevent memory blowup

        frame_idx = 0
        last_pct = -1
        # Run nudenet every N frames
        nsfw_interval = max(1, int(fps))  # every ~1 second
        nsfw_results: list[dict] = []

        # ── Tracking state ───────────────────────────────────
        # Each tracked region:
        #   [x, y, w, h, is_face, last_seen, miss_count, vx, vy, hit_count]
        #   Coordinates in full-res space.
        tracked: list[list] = []  # active tracked objects
        T_X, T_Y, T_W, T_H = 0, 1, 2, 3
        T_FACE, T_SEEN, T_MISS, T_VX, T_VY, T_HITS = 4, 5, 6, 7, 8, 9
        EMA_ALPHA = 0.6   # position smoothing (lower = smoother)
        MAX_MISS = max(6, int(fps / 3))  # carry-over frames (~10 at 30fps)
        IOU_MATCH = 0.15  # min IoU to associate detection with track

        def _box_iou(a, b):
            """IoU between two (x, y, w, h) tuples."""
            ax1, ay1, ax2, ay2 = a[0], a[1], a[0]+a[2], a[1]+a[3]
            bx1, by1, bx2, by2 = b[0], b[1], b[0]+b[2], b[1]+b[3]
            ix1, iy1 = max(ax1, bx1), max(ay1, by1)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            if ix2 <= ix1 or iy2 <= iy1:
                return 0.0
            inter = (ix2 - ix1) * (iy2 - iy1)
            aa = a[2] * a[3]
            ab = b[2] * b[3]
            denom = aa + ab - inter
            return inter / denom if denom > 0 else 0.0

        while True:
            if self._cancelled:
                cap.release()
                if use_ffmpeg:
                    ff_proc.stdin.close()
                    ff_proc.wait()
                    try:
                        os.remove(tmp_raw)
                    except OSError:
                        pass
                else:
                    writer.release()
                try:
                    os.remove(self._output)
                except OSError:
                    pass
                self.finished_err.emit("Cancelled by user.")
                return

            ret, frame = cap.read()
            if not ret:
                break

            # Detect on downscaled frame — PRESERVE ASPECT RATIO
            scale = min(DET_MAX_DIM / w, DET_MAX_DIM / h, 1.0)
            det_w = int(w * scale)
            det_h = int(h * scale)
            # Ensure even dimensions for codec compatibility
            det_w = max(det_w, 2)
            det_h = max(det_h, 2)
            det_frame = cv2.resize(frame, (det_w, det_h),
                                   interpolation=cv2.INTER_AREA)
            sx = w / det_w
            sy = h / det_h
            new_dets = []  # list of (x, y, w, h, is_face) in full-res coords

            # ── Face detection ──────────────────────────────────
            if fd and target != "nsfw_only":
                fd.setInputSize((det_w, det_h))
                _, faces = fd.detect(det_frame)
                if faces is not None:
                    for face in faces:
                        fx, fy, fw, fh = int(face[0]), int(face[1]), int(face[2]), int(face[3])
                        conf = float(face[14])
                        if conf < threshold:
                            continue

                        # Gender classification
                        gender = "unknown"
                        if gender_net:
                            ex, ey = int(fw * 0.3), int(fh * 0.3)
                            cx, cy = max(0, fx - ex), max(0, fy - ey)
                            cw = min(det_w, fx + fw + ex) - cx
                            ch = min(det_h, fy + fh + ey) - cy
                            crop = det_frame[cy:cy+ch, cx:cx+cw]
                            if crop.size > 0:
                                blob = cv2.dnn.blobFromImage(
                                    crop, 1.0, (227, 227),
                                    (114.9, 87.8, 78.4), swapRB=True)
                                gender_net.setInput(blob)
                                preds = gender_net.forward()
                                m_score = float(preds[0][0])
                                f_score = float(preds[0][1])
                                if abs(m_score - f_score) < 0.25:
                                    gender = "unknown"
                                elif m_score > f_score:
                                    gender = "male"
                                else:
                                    gender = "female"

                        # Filter by target
                        if target == "women" and gender == "male":
                            continue
                        if target == "men" and gender == "female":
                            continue

                        # Face region (full-res coords, with padding)
                        pad_top = int(fh * 0.55)
                        pad_bottom = int(fh * 0.45)
                        pad_side = int(fw * 0.30)
                        r_x = int(max(0, fx - pad_side) * sx)
                        r_y = int(max(0, fy - pad_top) * sy)
                        r_x2 = int(min(det_w, fx + fw + pad_side) * sx)
                        r_y2 = int(min(det_h, fy + fh + pad_bottom) * sy)
                        new_dets.append((r_x, r_y, r_x2 - r_x, r_y2 - r_y, True))

                        # Body region
                        if self._body_coverage != "face_only":
                            face_cx = fx + fw // 2
                            if self._body_coverage == "face_neck":
                                bw = int(fw * 1.8)
                                bh_ext = int(fh * 1.2)
                            else:
                                bw = int(fw * 3.0)
                                bh_ext = int(fh * 3.0)
                            b_x = int(max(0, face_cx - bw // 2) * sx)
                            b_y = r_y2
                            b_x2 = int(min(det_w, face_cx + bw // 2) * sx)
                            b_y2 = int(min(det_h, fy + fh + pad_bottom + bh_ext) * sy)
                            if b_y2 > b_y + 10 and b_x2 > b_x + 10:
                                new_dets.append((b_x, b_y, b_x2 - b_x, b_y2 - b_y, False))

            # ── NSFW body detection (every N frames) ────────────
            if nude_det and frame_idx % nsfw_interval == 0:
                tmp = os.path.join(tempfile.gettempdir(), "_toty_vid_nsfw.jpg")
                cv2.imwrite(tmp, det_frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                try:
                    results = nude_det.detect(tmp)
                    nsfw_results = []
                    for det in results:
                        label = det.get("class", "")
                        score = det.get("score", 0.0)
                        if label not in target_labels or score < threshold:
                            continue
                        box = det.get("box", [0, 0, 0, 0])
                        rx = int(box[0] * sx)
                        ry = int(box[1] * sy)
                        rw = int(box[2] * sx)
                        rh = int(box[3] * sy)
                        pad = int(max(rw, rh) * 0.2)
                        nsfw_results.append((
                            max(0, rx - pad), max(0, ry - pad),
                            min(w, rw + pad * 2), min(h, rh + pad * 2), False))
                except Exception:
                    pass

            # Add cached NSFW results
            new_dets.extend(nsfw_results)

            # ── IoU-based tracking: match new detections to tracks ──
            matched_track = [False] * len(tracked)
            matched_det = [False] * len(new_dets)

            # Match detections to existing tracks by best IoU
            for di, d in enumerate(new_dets):
                best_idx, best_iou = -1, IOU_MATCH
                for ti, t in enumerate(tracked):
                    if matched_track[ti]:
                        continue
                    # Compare against predicted position (track + velocity)
                    pred_box = (t[T_X] + t[T_VX], t[T_Y] + t[T_VY],
                                t[T_W], t[T_H])
                    iou = _box_iou(d[:4], pred_box)
                    # Also try raw position for static objects
                    iou = max(iou, _box_iou(d[:4], (t[T_X], t[T_Y],
                                                     t[T_W], t[T_H])))
                    if iou > best_iou:
                        best_iou = iou
                        best_idx = ti
                if best_idx >= 0:
                    matched_track[best_idx] = True
                    matched_det[di] = True
                    t = tracked[best_idx]
                    # Compute velocity from position change
                    t[T_VX] = d[0] - t[T_X]
                    t[T_VY] = d[1] - t[T_Y]
                    # EMA smooth position
                    t[T_X] = int(EMA_ALPHA * d[0] + (1 - EMA_ALPHA) * t[T_X])
                    t[T_Y] = int(EMA_ALPHA * d[1] + (1 - EMA_ALPHA) * t[T_Y])
                    t[T_W] = int(EMA_ALPHA * d[2] + (1 - EMA_ALPHA) * t[T_W])
                    t[T_H] = int(EMA_ALPHA * d[3] + (1 - EMA_ALPHA) * t[T_H])
                    t[T_FACE] = d[4]
                    t[T_SEEN] = frame_idx
                    t[T_MISS] = 0
                    t[T_HITS] = min(t[T_HITS] + 1, 100)

            # Create new tracks for unmatched detections
            for di, d in enumerate(new_dets):
                if not matched_det[di]:
                    tracked.append([d[0], d[1], d[2], d[3], d[4],
                                    frame_idx, 0, 0.0, 0.0, 1])

            # Update unmatched tracks: apply velocity, increment miss
            for ti in range(len(matched_track)):
                if not matched_track[ti] and tracked[ti][T_SEEN] < frame_idx:
                    t = tracked[ti]
                    t[T_MISS] += 1
                    # Drift prediction: nudge position by velocity
                    t[T_X] = int(t[T_X] + t[T_VX] * 0.5)
                    t[T_Y] = int(t[T_Y] + t[T_VY] * 0.5)
                    # Decay velocity
                    t[T_VX] *= 0.7
                    t[T_VY] *= 0.7

            # Remove dead tracks
            tracked = [t for t in tracked if t[T_MISS] <= MAX_MISS]

            # Build final regions from all active tracks
            # Tracks need at least 2 hits OR be fresh (hit_count >= 1
            # and miss_count == 0) to be rendered — filters noise
            regions = []
            for t in tracked:
                if t[T_HITS] >= 2 or (t[T_HITS] >= 1 and t[T_MISS] == 0):
                    regions.append((t[T_X], t[T_Y], t[T_W], t[T_H],
                                    t[T_FACE]))

            # Safety cap: limit regions per frame to avoid memory blowup
            if len(regions) > MAX_REGIONS:
                regions.sort(key=lambda r: r[2] * r[3], reverse=True)
                regions = regions[:MAX_REGIONS]

            # ── Apply blur to frame ─────────────────────────────
            for rx, ry, rw, rh, is_face in regions:
                rx = max(0, rx)
                ry = max(0, ry)
                rw = min(rw, w - rx)
                rh = min(rh, h - ry)
                if rw < 4 or rh < 4:
                    continue

                if self._blur_mode == "solid":
                    cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh),
                                  (128, 128, 128), -1)
                elif self._blur_mode == "gray":
                    roi = frame[ry:ry+rh, rx:rx+rw]
                    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                    frame[ry:ry+rh, rx:rx+rw] = cv2.merge([gray, gray, gray])
                else:
                    # Gaussian blur
                    roi = frame[ry:ry+rh, rx:rx+rw]
                    ksize = max(3, int(self._intensity / 2)) | 1
                    passes = max(1, self._intensity // 25)
                    for _ in range(passes):
                        roi = cv2.GaussianBlur(roi, (ksize, ksize), 0)

                    # Ellipse mask for face, rounded for body
                    if is_face:
                        mask = np.zeros((rh, rw), dtype=np.uint8)
                        cv2.ellipse(mask, (rw // 2, rh // 2),
                                    (rw // 2, rh // 2), 0, 0, 360, 255, -1)
                        mask_3ch = cv2.merge([mask, mask, mask])
                        inv_mask = cv2.bitwise_not(mask_3ch)
                        original = frame[ry:ry+rh, rx:rx+rw]
                        blended = ((roi.astype(np.float32) * mask_3ch / 255) +
                                   (original.astype(np.float32) * inv_mask / 255)
                                   ).astype(np.uint8)
                        frame[ry:ry+rh, rx:rx+rw] = blended
                    else:
                        frame[ry:ry+rh, rx:rx+rw] = roi

            if use_ffmpeg:
                ff_proc.stdin.write(frame.tobytes())
            else:
                writer.write(frame)
            frame_idx += 1

            pct = int(frame_idx * 100 / total_frames)
            if pct != last_pct:
                last_pct = pct
                self.progress.emit(pct)
                if pct % 10 == 0:
                    self.status.emit(
                        f"Frame {frame_idx}/{total_frames} "
                        f"({len(regions)} tracked, "
                        f"{len(tracked)} total tracks)")

        cap.release()

        if use_ffmpeg:
            ff_proc.stdin.close()
            ff_proc.wait()
            self.status.emit("Encoding final video with audio...")
            self.progress.emit(98)

            # Mux: combine blurred video + audio from original
            mux_cmd = [
                "ffmpeg", "-y",
                "-i", tmp_raw,         # blurred video (no audio)
                "-i", self._input,     # original (for audio)
                "-c:v", "copy",        # keep H.264 as-is
                "-c:a", "aac",         # re-encode audio to AAC
                "-map", "0:v:0",       # video from blurred
                "-map", "1:a?",        # audio from original (if exists)
                "-shortest",
                "-movflags", "+faststart",  # web-friendly
                self._output,
            ]
            try:
                result = subprocess.run(
                    mux_cmd, capture_output=True, timeout=300)
                if result.returncode != 0:
                    # If mux fails (e.g. no audio), just use video-only
                    import shutil
                    shutil.move(tmp_raw, self._output)
                else:
                    try:
                        os.remove(tmp_raw)
                    except OSError:
                        pass
            except Exception:
                import shutil
                shutil.move(tmp_raw, self._output)
        else:
            writer.release()

        self.progress.emit(100)
        self.status.emit(f"Done! {frame_idx} frames processed.")
        self.finished_ok.emit(self._output)

    @staticmethod
    def _has_ffmpeg() -> bool:
        try:
            subprocess.run(["ffmpeg", "-version"],
                          capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


# ══════════════════════════════════════════════════════════════════════
#  SETTINGS DIALOG
# ══════════════════════════════════════════════════════════════════════

class GazeGuardDialog(QDialog):
    """Settings & management dialog for Gaze Guard."""

    def __init__(self, guard: GazeGuard, parent=None):
        super().__init__(parent)
        self._guard = guard
        self.setWindowTitle("🛡️ Gaze Guard — Islamic Content Protection")
        self.setFixedSize(600, 720)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setStyleSheet(_SS)
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("🛡️ Gaze Guard")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_TEAL};")
        hdr.addWidget(title)
        hdr.addStretch()

        self._toggle_btn = QPushButton()
        self._update_toggle_btn()
        self._toggle_btn.clicked.connect(self._toggle_enabled)
        hdr.addWidget(self._toggle_btn)
        lay.addLayout(hdr)

        sub = QLabel("AI-powered protection to help lower your gaze — all processing is local & private")
        sub.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self._build_streak_tab(), "📊 Streak")
        tabs.addTab(self._build_detection_tab(), "👁️ AI Detection")
        tabs.addTab(self._build_protection_tab(), "🛡️ Protection")
        tabs.addTab(self._build_blocklist_tab(), "🚫 Block List")
        tabs.addTab(self._build_stats_tab(), "📈 Statistics")
        tabs.addTab(self._build_video_tab(), "🎬 Video Blur")
        tabs.addTab(self._build_advanced_tab(), "⚙️ Advanced")
        lay.addWidget(tabs, 1)

    # ── Streak tab ────────────────────────────────────────────────────

    def _build_streak_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(12)

        info = self._guard.get_streak_info()

        # Big streak number
        streak_box = QFrame()
        streak_box.setStyleSheet(
            f"background: {_SURFACE}; border: 2px solid {_TEAL};"
            f" border-radius: 12px; padding: 20px;")
        slay = QVBoxLayout(streak_box)

        days = info["current"]
        streak_num = QLabel(f"🔥 {days}")
        streak_num.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        streak_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        streak_num.setStyleSheet(f"color: {_TEAL}; background: transparent;")
        slay.addWidget(streak_num)

        streak_sub = QLabel("Clean Browsing Days")
        streak_sub.setFont(QFont("Arial", 14))
        streak_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        streak_sub.setStyleSheet(f"color: {_TEXT}; background: transparent;")
        slay.addWidget(streak_sub)

        lay.addWidget(streak_box)

        # Stats
        stats_row = QHBoxLayout()
        for label_text, value in [
            ("🏆 Longest Streak", f"{info['longest']} days"),
            ("🛡️ Total Blocks", str(info["total_blocks"])),
        ]:
            box = QFrame()
            box.setStyleSheet(
                f"background: {_SURFACE}; border: 1px solid #45475A;"
                f" border-radius: 8px; padding: 12px;")
            blay = QVBoxLayout(box)
            lbl_v = QLabel(value)
            lbl_v.setFont(QFont("Arial", 20, QFont.Weight.Bold))
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_v.setStyleSheet(f"color: {_BLUE}; background: transparent;")
            blay.addWidget(lbl_v)
            lbl_t = QLabel(label_text)
            lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_t.setStyleSheet(f"color: {_TEXT}; font-size: 12px; background: transparent;")
            blay.addWidget(lbl_t)
            stats_row.addWidget(box)
        lay.addLayout(stats_row)

        # Motivational reminder
        reminder = QLabel(random.choice(GAZE_REMINDERS))
        reminder.setWordWrap(True)
        reminder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        reminder.setStyleSheet(
            f"color: {_TEAL}; font-size: 12px; padding: 10px;"
            f" background: {_SURFACE}; border-radius: 8px;")
        lay.addWidget(reminder)

        lay.addStretch()
        return w

    # ── Protection tab ────────────────────────────────────────────────

    # ── AI Detection tab (HaramBlur-like settings) ────────────────────

    def _build_detection_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        # Header
        hdr = QLabel("🤖 AI Screen Guard — Like HaramBlur")
        hdr.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {_TEAL};")
        lay.addWidget(hdr)

        desc = QLabel(
            "Uses dual AI: YuNet face detection + gender classification\n"
            "+ nudenet NSFW body detection — blurs faces & bodies\n"
            "in real-time like HaramBlur. All LOCAL, zero data sent.")
        desc.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        # ── Start / Stop button
        screen_row = QHBoxLayout()
        self._btn_screen = QPushButton()
        self._update_screen_btn()
        self._btn_screen.clicked.connect(self._toggle_screen_guard)
        screen_row.addWidget(self._btn_screen)
        screen_row.addStretch()
        lay.addLayout(screen_row)

        # ── Blur Target (like HaramBlur gender filter)
        grp_target = QGroupBox("👤 Blur Target (Who to blur)")
        tl = QVBoxLayout(grp_target)

        self._target_combo = QComboBox()
        self._target_combo.addItem("Women — Blur female faces & bodies", "women")
        self._target_combo.addItem("Men — Blur male faces & bodies", "men")
        self._target_combo.addItem("Both — Blur all detected faces & bodies", "both")
        self._target_combo.addItem("NSFW Only — Blur only explicit content", "nsfw_only")
        current_target = self._guard.cfg.get("blur_target", "both")
        for i in range(self._target_combo.count()):
            if self._target_combo.itemData(i) == current_target:
                self._target_combo.setCurrentIndex(i)
                break
        self._target_combo.currentIndexChanged.connect(self._on_target_changed)
        tl.addWidget(self._target_combo)

        target_info = QLabel(
            "• Women: detects female faces, head coverings, bodies\n"
            "• Men: detects male faces and bodies\n"
            "• Both: all human content detected and blurred\n"
            "• NSFW Only: only explicit/exposed content")
        target_info.setStyleSheet("color: #A6ADC8; font-size: 10px;")
        tl.addWidget(target_info)
        lay.addWidget(grp_target)

        # ── Detection Sensitivity
        grp_sens = QGroupBox("🎯 Detection Sensitivity")
        sensl = QVBoxLayout(grp_sens)

        self._det_strict_combo = QComboBox()
        self._det_strict_combo.addItem("Low — Only high-confidence detections (>70%)", "low")
        self._det_strict_combo.addItem("Medium — Balanced accuracy (>50%)", "medium")
        self._det_strict_combo.addItem("High — Aggressive, catch more (>30%)", "high")
        current_det = self._guard.cfg.get("detection_strictness", "medium")
        for i in range(self._det_strict_combo.count()):
            if self._det_strict_combo.itemData(i) == current_det:
                self._det_strict_combo.setCurrentIndex(i)
                break
        self._det_strict_combo.currentIndexChanged.connect(self._on_det_strictness_changed)
        sensl.addWidget(self._det_strict_combo)
        lay.addWidget(grp_sens)

        # ── Blur Intensity slider
        grp_blur = QGroupBox("🌫️ Blur Intensity")
        bl = QVBoxLayout(grp_blur)

        self._intensity_slider = QSlider(Qt.Orientation.Horizontal)
        self._intensity_slider.setRange(30, 100)
        self._intensity_slider.setValue(self._guard.cfg.get("blur_intensity", 85))
        self._intensity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._intensity_slider.setTickInterval(10)
        self._intensity_slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ background: {_SURFACE}; height: 8px;"
            f" border-radius: 4px; }}"
            f"QSlider::handle:horizontal {{ background: {_TEAL}; width: 18px;"
            f" margin: -5px 0; border-radius: 9px; }}"
            f"QSlider::sub-page:horizontal {{ background: {_TEAL}; border-radius: 4px; }}")
        self._intensity_label = QLabel(f"{self._intensity_slider.value()}%")
        self._intensity_label.setStyleSheet(f"color: {_TEAL}; font-weight: bold;")
        self._intensity_slider.valueChanged.connect(self._on_intensity_changed)

        irow = QHBoxLayout()
        irow.addWidget(QLabel("Light"))
        irow.addWidget(self._intensity_slider, 1)
        irow.addWidget(QLabel("Opaque"))
        irow.addWidget(self._intensity_label)
        bl.addLayout(irow)
        lay.addWidget(grp_blur)

        # ── Options
        self._chk_targeted = QCheckBox("Targeted blur (blur specific regions like HaramBlur)")
        self._chk_targeted.setChecked(self._guard.cfg.get("targeted_blur", True))
        self._chk_targeted.toggled.connect(lambda v: self._set_cfg_and_update("targeted_blur", v))
        lay.addWidget(self._chk_targeted)

        self._chk_hover = QCheckBox("Hover to temporarily reveal (not recommended)")
        self._chk_hover.setChecked(self._guard.cfg.get("hover_to_reveal", False))
        self._chk_hover.toggled.connect(lambda v: self._set_cfg_and_update("hover_to_reveal", v))
        lay.addWidget(self._chk_hover)

        # ── Blur Mode (like HaramBlur: blur / gray / solid)
        grp_mode = QGroupBox("🎨 Blur Mode (like HaramBlur)")
        ml = QHBoxLayout(grp_mode)
        ml.addWidget(QLabel("Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Blur — Pixelated blur over regions", "blur")
        self._mode_combo.addItem("Gray — Grayscale + darken", "gray")
        self._mode_combo.addItem("Solid — Opaque color block", "solid")
        current_mode = self._guard.cfg.get("blur_mode", "blur")
        for i in range(self._mode_combo.count()):
            if self._mode_combo.itemData(i) == current_mode:
                self._mode_combo.setCurrentIndex(i)
                break
        self._mode_combo.currentIndexChanged.connect(self._on_blur_mode_changed)
        ml.addWidget(self._mode_combo, 1)
        lay.addWidget(grp_mode)

        # ── Body Coverage
        grp_body = QGroupBox("🦴 Body Coverage")
        bcl = QHBoxLayout(grp_body)
        bcl.addWidget(QLabel("Coverage:"))
        self._body_combo = QComboBox()
        self._body_combo.addItem("Face Only — blur face region only", "face_only")
        self._body_combo.addItem("Face + Neck — face and neck area", "face_neck")
        self._body_combo.addItem("Face + Body — face and estimated body", "face_body")
        current_body = self._guard.cfg.get("body_coverage", "face_body")
        for i in range(self._body_combo.count()):
            if self._body_combo.itemData(i) == current_body:
                self._body_combo.setCurrentIndex(i)
                break
        self._body_combo.currentIndexChanged.connect(self._on_body_coverage_changed)
        bcl.addWidget(self._body_combo, 1)
        lay.addWidget(grp_body)

        # ── Enhancement Options
        grp_enhancements = QGroupBox("✨ Enhancements")
        el = QVBoxLayout(grp_enhancements)

        self._chk_adaptive_blur = QCheckBox("Adaptive blur strength (stronger for high confidence)")
        self._chk_adaptive_blur.setChecked(self._guard.cfg.get("adaptive_blur", True))
        self._chk_adaptive_blur.toggled.connect(lambda v: self._set_cfg_and_update("adaptive_blur", v))
        el.addWidget(self._chk_adaptive_blur)

        self._chk_feathering = QCheckBox("Edge feathering (smooth blur edges)")
        self._chk_feathering.setChecked(self._guard.cfg.get("edge_feathering", True))
        self._chk_feathering.toggled.connect(lambda v: self._set_cfg_and_update("edge_feathering", v))
        el.addWidget(self._chk_feathering)

        self._chk_adaptive_interval = QCheckBox("Video-aware adaptive intervals (faster for video)")
        self._chk_adaptive_interval.setChecked(self._guard.cfg.get("adaptive_interval", True))
        self._chk_adaptive_interval.toggled.connect(lambda v: self._set_cfg_and_update("adaptive_interval", v))
        el.addWidget(self._chk_adaptive_interval)

        self._chk_multi_monitor = QCheckBox("Multi-monitor support (scan all screens)")
        self._chk_multi_monitor.setChecked(self._guard.cfg.get("multi_monitor", True))
        self._chk_multi_monitor.toggled.connect(lambda v: self._set_cfg_and_update("multi_monitor", v))
        el.addWidget(self._chk_multi_monitor)

        self._chk_toast = QCheckBox("Toast notification on first detection")
        self._chk_toast.setChecked(self._guard.cfg.get("toast_on_detect", True))
        self._chk_toast.toggled.connect(lambda v: self._set_cfg_and_update("toast_on_detect", v))
        el.addWidget(self._chk_toast)

        self._chk_skin_tint = QCheckBox("Skin-tone tint (solid mode uses detected skin color)")
        self._chk_skin_tint.setChecked(self._guard.cfg.get("skin_tone_tint", False))
        self._chk_skin_tint.toggled.connect(lambda v: self._set_cfg_and_update("skin_tone_tint", v))
        el.addWidget(self._chk_skin_tint)

        lay.addWidget(grp_enhancements)

        # ── Scan Interval
        grp_interval = QGroupBox("⏱️ Scan Interval (seconds)")
        il = QHBoxLayout(grp_interval)
        il.addWidget(QLabel("Scan every:"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 30)
        self._interval_spin.setValue(self._guard.cfg.get("screen_guard_interval_sec", 2))
        self._interval_spin.setSuffix(" sec")
        self._interval_spin.setStyleSheet(
            f"QSpinBox {{ background: {_SURFACE}; color: {_TEXT};"
            f" border: 1px solid #45475A; padding: 4px; }}")
        self._interval_spin.valueChanged.connect(self._on_interval_changed)
        il.addWidget(self._interval_spin)
        il.addWidget(QLabel("(1-2s = real-time, restart guard to apply)"))
        il.addStretch()
        lay.addWidget(grp_interval)

        lay.addStretch()
        return w

    def _on_target_changed(self, idx: int):
        target = self._target_combo.itemData(idx)
        if target:
            self._guard.cfg["blur_target"] = target
            self._guard.save()
            self._guard.update_screen_guard_settings()

    def _on_det_strictness_changed(self, idx: int):
        level = self._det_strict_combo.itemData(idx)
        if level:
            self._guard.cfg["detection_strictness"] = level
            self._guard.save()
            self._guard.update_screen_guard_settings()

    def _on_intensity_changed(self, value: int):
        self._intensity_label.setText(f"{value}%")
        self._guard.cfg["blur_intensity"] = value
        self._guard.save()
        self._guard.update_screen_guard_settings()

    def _on_blur_mode_changed(self, idx: int):
        mode = self._mode_combo.itemData(idx)
        if mode:
            self._guard.cfg["blur_mode"] = mode
            self._guard.save()
            self._guard.update_screen_guard_settings()

    def _on_body_coverage_changed(self, idx: int):
        cov = self._body_combo.itemData(idx)
        if cov:
            self._guard.cfg["body_coverage"] = cov
            self._guard.save()
            self._guard.update_screen_guard_settings()

    def _on_interval_changed(self, value: int):
        self._guard.cfg["screen_guard_interval_sec"] = value
        self._guard.save()

    def _set_cfg_and_update(self, key: str, value):
        self._guard.cfg[key] = value
        self._guard.save()
        self._guard.update_screen_guard_settings()

    # ── Statistics tab ──────────────────────────────────────────────

    def _build_stats_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        hdr = QLabel("📈 Detection Statistics")
        hdr.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {_TEAL};")
        lay.addWidget(hdr)

        stats = self._guard.get_session_stats()

        # Session stats row
        sess_row = QHBoxLayout()
        for label_text, value in [
            ("👤 Session Faces", str(stats["session_faces"])),
            ("⏱️ Session Time", self._format_time(stats["session_time_sec"])),
        ]:
            box = QFrame()
            box.setStyleSheet(
                f"background: {_SURFACE}; border: 1px solid #45475A;"
                f" border-radius: 8px; padding: 10px;")
            blay = QVBoxLayout(box)
            lbl_v = QLabel(value)
            lbl_v.setFont(QFont("Arial", 18, QFont.Weight.Bold))
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_v.setStyleSheet(f"color: {_TEAL}; background: transparent;")
            blay.addWidget(lbl_v)
            lbl_t = QLabel(label_text)
            lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_t.setStyleSheet(f"color: {_TEXT}; font-size: 11px; background: transparent;")
            blay.addWidget(lbl_t)
            sess_row.addWidget(box)
        lay.addLayout(sess_row)

        # Lifetime stats row
        life_row = QHBoxLayout()
        total_time = self._guard.cfg.get("total_screen_time_sec", 0) + stats["session_time_sec"]
        for label_text, value in [
            ("👤 Total Faces", str(stats["total_faces"])),
            ("🛡️ Total Blocks", str(stats["total_blocks"])),
            ("⏱️ Protected Time", self._format_time(total_time)),
        ]:
            box = QFrame()
            box.setStyleSheet(
                f"background: {_SURFACE}; border: 1px solid #45475A;"
                f" border-radius: 8px; padding: 10px;")
            blay = QVBoxLayout(box)
            lbl_v = QLabel(value)
            lbl_v.setFont(QFont("Arial", 16, QFont.Weight.Bold))
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_v.setStyleSheet(f"color: {_BLUE}; background: transparent;")
            blay.addWidget(lbl_v)
            lbl_t = QLabel(label_text)
            lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_t.setStyleSheet(f"color: {_TEXT}; font-size: 11px; background: transparent;")
            blay.addWidget(lbl_t)
            life_row.addWidget(box)
        lay.addLayout(life_row)

        # Daily history (last 7 days)
        grp_daily = QGroupBox("📅 Last 7 Days")
        dl = QVBoxLayout(grp_daily)
        daily = stats.get("daily_stats", {})
        # Sort by date descending, take last 7
        sorted_days = sorted(daily.keys(), reverse=True)[:7]
        if sorted_days:
            for day_str in sorted_days:
                d = daily[day_str]
                row = QHBoxLayout()
                lbl_date = QLabel(day_str)
                lbl_date.setStyleSheet(f"color: {_TEXT};")
                row.addWidget(lbl_date)
                row.addStretch()
                lbl_info = QLabel(
                    f"👤 {d.get('faces', 0)} faces  •  "
                    f"🛡️ {d.get('blocks', 0)} blocks")
                lbl_info.setStyleSheet(f"color: {_TEAL};")
                row.addWidget(lbl_info)
                dl.addLayout(row)
        else:
            no_data = QLabel("No data yet — start Screen Guard to begin tracking!")
            no_data.setStyleSheet(f"color: #A6ADC8; font-style: italic;")
            dl.addWidget(no_data)
        lay.addWidget(grp_daily)

        lay.addStretch()
        return w

    @staticmethod
    def _format_time(seconds: int) -> str:
        if seconds < 60:
            return f"{seconds}s"
        if seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"

    # ── Protection tab ────────────────────────────────────────────────

    def _build_protection_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        # Site blocking strictness
        grp_strict = QGroupBox("🚫 Website Blocking Strictness")
        sl = QVBoxLayout(grp_strict)

        self._strict_combo = QComboBox()
        self._strict_combo.addItems(["low", "medium", "high"])
        self._strict_combo.setCurrentText(self._guard.cfg.get("strictness", "medium"))
        self._strict_combo.currentTextChanged.connect(self._on_strictness_changed)
        sl.addWidget(self._strict_combo)

        strict_desc = QLabel(
            "• Low: blocks only known explicit sites\n"
            "• Medium: + NSFW keywords & adult platforms\n"
            "• High: + dating, gambling, alcohol, revealing content")
        strict_desc.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        sl.addWidget(strict_desc)
        lay.addWidget(grp_strict)

        # Options
        self._chk_overlay = QCheckBox("Show blocking overlay with Islamic reminder")
        self._chk_overlay.setChecked(self._guard.cfg.get("show_overlay", True))
        self._chk_overlay.toggled.connect(lambda v: self._set_cfg("show_overlay", v))
        lay.addWidget(self._chk_overlay)

        self._chk_close = QCheckBox("Auto-close browser tab (Ctrl+W)")
        self._chk_close.setChecked(self._guard.cfg.get("auto_close_tab", True))
        self._chk_close.toggled.connect(lambda v: self._set_cfg("auto_close_tab", v))
        lay.addWidget(self._chk_close)

        self._chk_blur = QCheckBox("Enable blur hotkey (Ctrl+Shift+G)")
        self._chk_blur.setChecked(self._guard.cfg.get("blur_hotkey_enabled", True))
        self._chk_blur.toggled.connect(lambda v: self._set_cfg("blur_hotkey_enabled", v))
        lay.addWidget(self._chk_blur)

        lay.addStretch()
        return w

    # ── Block list tab ────────────────────────────────────────────────

    def _build_blocklist_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)

        # Custom blocked
        lay.addWidget(QLabel("🚫 Custom Blocked Keywords:"))

        self._blocked_list = QListWidget()
        for kw in self._guard.cfg.get("custom_blocked", []):
            self._blocked_list.addItem(kw)
        lay.addWidget(self._blocked_list, 1)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ Add")
        btn_add.clicked.connect(self._add_blocked)
        btn_row.addWidget(btn_add)
        btn_rm = QPushButton("– Remove")
        btn_rm.clicked.connect(self._remove_blocked)
        btn_row.addWidget(btn_rm)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Whitelist
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background: #45475A;")
        lay.addWidget(sep)

        lay.addWidget(QLabel("✅ Whitelisted Keywords (never block):"))

        self._allowed_list = QListWidget()
        for kw in self._guard.cfg.get("custom_allowed", []):
            self._allowed_list.addItem(kw)
        lay.addWidget(self._allowed_list, 1)

        btn_row2 = QHBoxLayout()
        btn_add2 = QPushButton("+ Add")
        btn_add2.clicked.connect(self._add_allowed)
        btn_row2.addWidget(btn_add2)
        btn_rm2 = QPushButton("– Remove")
        btn_rm2.clicked.connect(self._remove_allowed)
        btn_row2.addWidget(btn_rm2)
        btn_row2.addStretch()
        lay.addLayout(btn_row2)

        return w

    # ── Video Blur tab ────────────────────────────────────────────────

    def _build_video_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        hdr = QLabel("🎬 Video Blur — Download with HaramBlur")
        hdr.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {_TEAL};")
        lay.addWidget(hdr)

        desc = QLabel(
            "Process a video file and bake blur into detected faces & bodies.\n"
            "The output video has blur permanently applied so it can be\n"
            "safely shared. Uses the same AI pipeline as live screen guard.")
        desc.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        desc.setWordWrap(True)
        lay.addWidget(desc)

        # File selection
        grp_file = QGroupBox("📂 Video File")
        fl = QVBoxLayout(grp_file)

        file_row = QHBoxLayout()
        self._vid_path_label = QLabel("No file selected")
        self._vid_path_label.setStyleSheet(
            f"color: {_TEXT}; background: {_SURFACE}; padding: 8px;"
            f" border-radius: 6px; border: 1px solid #45475A;")
        self._vid_path_label.setWordWrap(True)
        file_row.addWidget(self._vid_path_label, 1)

        btn_browse = QPushButton("📁 Browse")
        btn_browse.clicked.connect(self._browse_video)
        file_row.addWidget(btn_browse)
        fl.addLayout(file_row)

        # File info
        self._vid_info_label = QLabel("")
        self._vid_info_label.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        fl.addWidget(self._vid_info_label)
        lay.addWidget(grp_file)

        # Settings (inherits from main detection settings)
        grp_set = QGroupBox("⚙️ Blur Settings (uses AI Detection settings)")
        sl = QVBoxLayout(grp_set)
        current_target = self._guard.cfg.get("blur_target", "both")
        current_mode = self._guard.cfg.get("blur_mode", "blur")
        current_int = self._guard.cfg.get("blur_intensity", 85)
        current_body = self._guard.cfg.get("body_coverage", "face_body")
        sl.addWidget(QLabel(
            f"  Target: {current_target}  •  Mode: {current_mode}\n"
            f"  Intensity: {current_int}%  •  Coverage: {current_body}\n"
            f"  (Change these in the AI Detection tab)"))
        lay.addWidget(grp_set)

        # Progress
        grp_prog = QGroupBox("📊 Progress")
        pl = QVBoxLayout(grp_prog)

        self._vid_progress = QProgressBar()
        self._vid_progress.setRange(0, 100)
        self._vid_progress.setValue(0)
        self._vid_progress.setStyleSheet(
            f"QProgressBar {{ background: {_SURFACE}; border: 1px solid #45475A;"
            f" border-radius: 6px; height: 22px; text-align: center;"
            f" color: {_TEXT}; font-weight: bold; }}"
            f"QProgressBar::chunk {{ background: {_TEAL}; border-radius: 5px; }}")
        pl.addWidget(self._vid_progress)

        self._vid_status = QLabel("Ready")
        self._vid_status.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        pl.addWidget(self._vid_status)
        lay.addWidget(grp_prog)

        # Action buttons
        btn_row = QHBoxLayout()
        self._btn_process = QPushButton("🚀 Process Video")
        self._btn_process.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_BG}; border: none;"
            f" border-radius: 6px; padding: 10px 20px; font-weight: bold;"
            f" font-size: 14px; }}"
            f"QPushButton:hover {{ background: #C6F3C1; }}"
            f"QPushButton:disabled {{ background: #45475A; color: #6C7086; }}")
        self._btn_process.clicked.connect(self._start_video_process)
        self._btn_process.setEnabled(False)
        btn_row.addWidget(self._btn_process)

        self._btn_cancel_vid = QPushButton("⏹ Cancel")
        self._btn_cancel_vid.setStyleSheet(
            f"QPushButton {{ background: {_RED}; color: {_BG}; border: none;"
            f" border-radius: 6px; padding: 10px 20px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #F5A0B5; }}"
            f"QPushButton:disabled {{ background: #45475A; color: #6C7086; }}")
        self._btn_cancel_vid.clicked.connect(self._cancel_video_process)
        self._btn_cancel_vid.setEnabled(False)
        btn_row.addWidget(self._btn_cancel_vid)

        btn_row.addStretch()
        lay.addLayout(btn_row)

        # Output info
        self._vid_output_label = QLabel("")
        self._vid_output_label.setStyleSheet(f"color: {_GREEN}; font-size: 12px;")
        self._vid_output_label.setWordWrap(True)
        lay.addWidget(self._vid_output_label)

        lay.addStretch()

        self._vid_input_path: str = ""
        self._vid_processor: _VideoBlurProcessor | None = None
        return w

    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.webm *.flv *.wmv);;All Files (*)")
        if not path:
            return
        self._vid_input_path = path
        self._vid_path_label.setText(os.path.basename(path))
        self._vid_output_label.setText("")
        self._vid_progress.setValue(0)
        self._vid_status.setText("Ready")
        self._btn_process.setEnabled(True)

        # Show video info
        import cv2
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            dur = frames / fps if fps > 0 else 0
            cap.release()
            self._vid_info_label.setText(
                f"{w}x{h}  •  {fps:.1f} fps  •  {frames} frames  •  "
                f"{dur:.1f}s duration")
        else:
            self._vid_info_label.setText("Could not read video info")

    def _start_video_process(self):
        if not self._vid_input_path:
            return

        # Generate output path
        base, ext = os.path.splitext(self._vid_input_path)
        output_path = f"{base}_blurred.mp4"

        # Check if output exists
        if os.path.exists(output_path):
            reply = QMessageBox.question(
                self, "File Exists",
                f"Output file already exists:\n{os.path.basename(output_path)}\n\nOverwrite?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Ensure detectors are loaded
        bundle = _init_detectors()

        cfg = self._guard.cfg
        det_level = cfg.get("detection_strictness", "medium")
        threshold = _DETECTION_THRESHOLDS.get(det_level, 0.50)

        self._vid_processor = _VideoBlurProcessor(
            input_path=self._vid_input_path,
            output_path=output_path,
            bundle=bundle,
            blur_target=cfg.get("blur_target", "both"),
            min_confidence=threshold,
            blur_intensity=cfg.get("blur_intensity", 85),
            body_coverage=cfg.get("body_coverage", "face_body"),
            blur_mode=cfg.get("blur_mode", "blur"),
        )
        self._vid_processor.progress.connect(self._vid_progress.setValue)
        self._vid_processor.status.connect(self._vid_status.setText)
        self._vid_processor.finished_ok.connect(self._on_video_done)
        self._vid_processor.finished_err.connect(self._on_video_error)
        self._vid_processor.finished.connect(self._on_video_thread_done)
        self._vid_processor.start()

        self._btn_process.setEnabled(False)
        self._btn_cancel_vid.setEnabled(True)
        self._vid_status.setText("Starting...")
        self._vid_output_label.setText("")

    def _cancel_video_process(self):
        if self._vid_processor:
            self._vid_processor.cancel()
            self._vid_status.setText("Cancelling...")

    def _on_video_done(self, output_path: str):
        self._vid_output_label.setText(f"✅ Saved: {output_path}")
        QMessageBox.information(
            self, "Video Processed",
            f"Blurred video saved to:\n{output_path}\n\nSafe to share!")

    def _on_video_error(self, error: str):
        self._vid_output_label.setText(f"❌ {error}")
        if "Cancelled" not in error:
            QMessageBox.warning(self, "Video Error", error)

    def _on_video_thread_done(self):
        self._btn_process.setEnabled(bool(self._vid_input_path))
        self._btn_cancel_vid.setEnabled(False)
        self._vid_processor = None

    # ── Advanced tab ──────────────────────────────────────────────────

    def _build_advanced_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)

        # Whitelist screen regions
        grp_wl = QGroupBox("📍 Whitelist Screen Regions")
        wl_lay = QVBoxLayout(grp_wl)
        wl_desc = QLabel(
            "Skip detections in these screen areas (e.g. taskbar, clock).\n"
            "Format: x, y, width, height in pixels.")
        wl_desc.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        wl_lay.addWidget(wl_desc)

        self._wl_list = QListWidget()
        self._wl_list.setMaximumHeight(80)
        for r in self._guard.cfg.get("whitelist_rects", []):
            self._wl_list.addItem(f"{r['x']}, {r['y']}, {r['w']}, {r['h']}")
        wl_lay.addWidget(self._wl_list)

        wl_btns = QHBoxLayout()
        btn_add_wl = QPushButton("+ Add Region")
        btn_add_wl.clicked.connect(self._add_whitelist_region)
        wl_btns.addWidget(btn_add_wl)
        btn_rm_wl = QPushButton("– Remove")
        btn_rm_wl.clicked.connect(self._remove_whitelist_region)
        wl_btns.addWidget(btn_rm_wl)
        wl_btns.addStretch()
        wl_lay.addLayout(wl_btns)
        lay.addWidget(grp_wl)

        # SafeSearch enforcer
        grp_safe = QGroupBox("🔒 SafeSearch Enforcer")
        sf_lay = QVBoxLayout(grp_safe)

        sf_desc = QLabel(
            "Force SafeSearch on Google, YouTube Restricted Mode,\n"
            "and Bing SafeSearch by modifying the system hosts file.\n"
            "Requires administrator privileges.")
        sf_desc.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        sf_lay.addWidget(sf_desc)

        sf_row = QHBoxLayout()
        btn_enforce = QPushButton("🔒 Enforce SafeSearch")
        btn_enforce.setStyleSheet(
            f"QPushButton {{ background: {_GREEN}; color: {_BG}; border: none;"
            f" border-radius: 6px; padding: 8px 16px; font-weight: bold; }}"
            f"QPushButton:hover {{ background: #C6F3C1; }}")
        btn_enforce.clicked.connect(self._enforce_safe_search)
        sf_row.addWidget(btn_enforce)

        btn_remove = QPushButton("🔓 Remove")
        btn_remove.clicked.connect(self._remove_safe_search)
        sf_row.addWidget(btn_remove)
        sf_row.addStretch()
        sf_lay.addLayout(sf_row)
        lay.addWidget(grp_safe)

        # Reset streak
        grp_streak = QGroupBox("📊 Streak Management")
        sk_lay = QVBoxLayout(grp_streak)
        btn_reset = QPushButton("🔄 Reset Streak Counter")
        btn_reset.clicked.connect(self._reset_streak)
        sk_lay.addWidget(btn_reset)
        lay.addWidget(grp_streak)

        # Info
        info = QLabel(
            "ℹ️ Gaze Guard is integrated into Toty's window monitoring.\n"
            "It checks every active window title against the block list.\n\n"
            "🤖 AI Screen Guard uses YuNet face detection + gender\n"
            "classification + nudenet NSFW — like HaramBlur but\n"
            "for your entire screen. All processing is 100% local.\n\n"
            "⌨️ Blur Hotkey: Ctrl+Shift+G to instantly hide the screen.\n\n"
            "👁️ Blur Targets:\n"
            "  • Women — blurs female faces & bodies\n"
            "  • Men — blurs male faces & bodies\n"
            "  • Both — blurs all human content\n"
            "  • NSFW Only — only explicit content")
        info.setStyleSheet("color: #A6ADC8; font-size: 11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        lay.addStretch()
        return w

    # ── Handlers ──────────────────────────────────────────────────────

    def _update_toggle_btn(self):
        on = self._guard.cfg.get("enabled", True)
        if on:
            self._toggle_btn.setText("✅ Enabled")
            self._toggle_btn.setStyleSheet(
                f"QPushButton {{ background: {_GREEN}; color: {_BG}; border: none;"
                f" border-radius: 6px; padding: 8px 16px; font-weight: bold; }}")
        else:
            self._toggle_btn.setText("❌ Disabled")
            self._toggle_btn.setStyleSheet(
                f"QPushButton {{ background: {_RED}; color: {_BG}; border: none;"
                f" border-radius: 6px; padding: 8px 16px; font-weight: bold; }}")

    def _toggle_enabled(self):
        on = not self._guard.cfg.get("enabled", True)
        self._guard.set_enabled(on)
        self._update_toggle_btn()

    def _on_strictness_changed(self, level: str):
        self._guard.set_strictness(level)

    def _set_cfg(self, key: str, value):
        self._guard.cfg[key] = value
        self._guard.save()

    def _update_screen_btn(self):
        running = self._guard.is_screen_guard_running()
        if running:
            self._btn_screen.setText("⏹ Stop Screen Guard")
            self._btn_screen.setStyleSheet(
                f"QPushButton {{ background: {_RED}; color: {_BG}; border: none;"
                f" border-radius: 6px; padding: 8px 16px; font-weight: bold; }}")
        else:
            self._btn_screen.setText("▶ Start Screen Guard")
            self._btn_screen.setStyleSheet(
                f"QPushButton {{ background: {_BLUE}; color: {_BG}; border: none;"
                f" border-radius: 6px; padding: 8px 16px; font-weight: bold; }}")

    def _toggle_screen_guard(self):
        if self._guard.is_screen_guard_running():
            self._guard.stop_screen_guard()
        else:
            self._guard.start_screen_guard()
        self._update_screen_btn()

    def _add_blocked(self):
        text, ok = QInputDialog.getText(self, "Add Blocked Keyword",
                                        "Keyword to block (matches window titles):")
        if ok and text.strip():
            self._guard.add_blocked_keyword(text.strip())
            self._blocked_list.addItem(text.strip())

    def _remove_blocked(self):
        item = self._blocked_list.currentItem()
        if item:
            self._guard.remove_blocked_keyword(item.text())
            self._blocked_list.takeItem(self._blocked_list.row(item))

    def _add_allowed(self):
        text, ok = QInputDialog.getText(self, "Add Whitelist Keyword",
                                        "Keyword to never block:")
        if ok and text.strip():
            self._guard.add_allowed_keyword(text.strip())
            self._allowed_list.addItem(text.strip())

    def _remove_allowed(self):
        item = self._allowed_list.currentItem()
        if item:
            self._guard.remove_allowed_keyword(item.text())
            self._allowed_list.takeItem(self._allowed_list.row(item))

    def _enforce_safe_search(self):
        ok, msg = GazeGuard.enforce_safe_search()
        if ok:
            self._guard.cfg["safe_search_enforced"] = True
            self._guard.save()
        QMessageBox.information(self, "SafeSearch", msg)

    def _remove_safe_search(self):
        ok, msg = GazeGuard.remove_safe_search()
        if ok:
            self._guard.cfg["safe_search_enforced"] = False
            self._guard.save()
        QMessageBox.information(self, "SafeSearch", msg)

    def _reset_streak(self):
        reply = QMessageBox.question(
            self, "Reset Streak",
            "Are you sure you want to reset your clean browsing streak?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self._guard.cfg["streak_current"] = 0
            self._guard.cfg["streak_start_date"] = date.today().isoformat()
            self._guard.save()
            QMessageBox.information(self, "Reset", "Streak has been reset. Fresh start! 💪")

    def _add_whitelist_region(self):
        text, ok = QInputDialog.getText(
            self, "Add Whitelist Region",
            "Enter region as: x, y, width, height\n"
            "Example: 0, 1040, 1920, 40 (taskbar)")
        if ok and text.strip():
            parts = [p.strip() for p in text.split(",")]
            if len(parts) == 4:
                try:
                    x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])
                    rects = self._guard.cfg.get("whitelist_rects", [])
                    rects.append({"x": x, "y": y, "w": w, "h": h})
                    self._guard.cfg["whitelist_rects"] = rects
                    self._guard.save()
                    self._guard.update_screen_guard_settings()
                    self._wl_list.addItem(f"{x}, {y}, {w}, {h}")
                except ValueError:
                    QMessageBox.warning(self, "Error", "Invalid numbers. Use: x, y, width, height")
            else:
                QMessageBox.warning(self, "Error", "Need exactly 4 values: x, y, width, height")

    def _remove_whitelist_region(self):
        item = self._wl_list.currentItem()
        if item:
            idx = self._wl_list.row(item)
            rects = self._guard.cfg.get("whitelist_rects", [])
            if 0 <= idx < len(rects):
                rects.pop(idx)
                self._guard.cfg["whitelist_rects"] = rects
                self._guard.save()
                self._guard.update_screen_guard_settings()
            self._wl_list.takeItem(idx)
