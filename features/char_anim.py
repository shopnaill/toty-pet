"""
Character Animation Enhancements — breathing, blinks, head-tracking,
physical reactions, size growth, emotion overlays, focus vignette.
All driven by QTimers on the pet widget.
"""
import math
import random
from PyQt6.QtCore import QTimer, QPoint, Qt
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPixmap, QRadialGradient, QBrush
from PyQt6.QtWidgets import QLabel, QWidget


# ══════════════════════════════════════════════════════════════
#  BREATHING ANIMATION
# ══════════════════════════════════════════════════════════════
class BreathingAnimator:
    """Subtle sine-wave Y-offset on the pet label to simulate breathing."""

    def __init__(self, pet_label: QLabel, base_y: int = 100, amplitude: float = 2.5, period_ms: int = 2500):
        self._label = pet_label
        self._base_y = base_y
        self._amplitude = amplitude
        self._period = period_ms
        self._phase = 0.0
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._enabled = False
        self._paused = False

    def start(self):
        self._enabled = True
        self._timer.start(33)  # ~30fps

    def stop(self):
        self._enabled = False
        self._timer.stop()
        self._label.move(self._label.x(), self._base_y)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    @property
    def base_y(self):
        return self._base_y

    @base_y.setter
    def base_y(self, val: int):
        self._base_y = val

    def _tick(self):
        if self._paused or not self._enabled:
            return
        self._phase += 33
        if self._phase > self._period:
            self._phase -= self._period
        t = self._phase / self._period
        offset = self._amplitude * math.sin(2 * math.pi * t)
        self._label.move(self._label.x(), int(self._base_y + offset))


# ══════════════════════════════════════════════════════════════
#  EYE BLINK SYSTEM
# ══════════════════════════════════════════════════════════════
class BlinkOverlay(QLabel):
    """Transparent overlay that draws blink lines over the pet's eyes."""

    def __init__(self, parent: QWidget, size: int = 100):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self._blinking = False
        self._blink_frame = 0  # 0=open, 1=half, 2=closed, 3=half, 4=open
        self._size = size

        # Blink timer (random interval 3-8s)
        self._blink_interval_timer = QTimer()
        self._blink_interval_timer.timeout.connect(self._start_blink)

        # Animation timer (fast — drives blink frames)
        self._anim_timer = QTimer()
        self._anim_timer.timeout.connect(self._next_frame)
        self._enabled = False

    def start(self):
        self._enabled = True
        self._schedule_next()
        self.show()

    def stop(self):
        self._enabled = False
        self._blink_interval_timer.stop()
        self._anim_timer.stop()
        self._blinking = False
        self.hide()

    def _schedule_next(self):
        interval = random.randint(3000, 8000)
        self._blink_interval_timer.setSingleShot(True)
        self._blink_interval_timer.start(interval)

    def _start_blink(self):
        if not self._enabled:
            return
        self._blinking = True
        self._blink_frame = 0
        self._anim_timer.start(40)  # 40ms per frame

    def _next_frame(self):
        self._blink_frame += 1
        self.update()
        if self._blink_frame >= 5:
            self._anim_timer.stop()
            self._blinking = False
            self.update()
            if self._enabled:
                self._schedule_next()

    def paintEvent(self, event):
        if not self._blinking:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Eye positions (relative to 100x100 pet — adjust for actual size)
        s = self._size / 100
        left_eye = (int(35 * s), int(38 * s))
        right_eye = (int(65 * s), int(38 * s))
        eye_w = int(12 * s)

        # Blink closure amount (0=open → 2=fully closed → 4=open)
        if self._blink_frame <= 2:
            closure = self._blink_frame / 2.0
        else:
            closure = (4 - self._blink_frame) / 2.0

        if closure <= 0:
            return

        # Draw eyelid lines
        pen = QPen(QColor(60, 60, 80, int(200 * closure)))
        pen.setWidth(max(2, int(3 * s * closure)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        for ex, ey in (left_eye, right_eye):
            # Upper eyelid descends
            y_off = int(eye_w * 0.6 * closure)
            painter.drawLine(ex - eye_w // 2, ey - y_off // 2,
                             ex + eye_w // 2, ey - y_off // 2)

        painter.end()


# ══════════════════════════════════════════════════════════════
#  HEAD-TRACK CURSOR
# ══════════════════════════════════════════════════════════════
class HeadTracker:
    """Makes the pet label shift slightly toward the cursor direction."""

    def __init__(self, pet_widget: QWidget, pet_label: QLabel,
                 base_x: int = 75, max_offset: int = 4):
        self._widget = pet_widget
        self._label = pet_label
        self._base_x = base_x
        self._max_offset = max_offset
        self._current_offset_x = 0.0
        self._current_offset_y = 0.0
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._enabled = False

    def start(self):
        self._enabled = True
        self._timer.start(100)  # 10fps

    def stop(self):
        self._enabled = False
        self._timer.stop()

    def _tick(self):
        if not self._enabled:
            return
        from PyQt6.QtGui import QCursor
        cursor = QCursor.pos()
        pet_center = self._widget.mapToGlobal(
            QPoint(self._label.x() + self._label.width() // 2,
                   self._label.y() + self._label.height() // 2)
        )
        dx = cursor.x() - pet_center.x()
        dy = cursor.y() - pet_center.y()
        dist = max(1, math.sqrt(dx * dx + dy * dy))

        # Normalize and scale
        target_x = (dx / dist) * self._max_offset
        target_y = (dy / dist) * min(self._max_offset, 2)  # less vertical

        # Smooth lerp
        self._current_offset_x += (target_x - self._current_offset_x) * 0.2
        self._current_offset_y += (target_y - self._current_offset_y) * 0.2

        # Apply offset (breathing controls Y base, we only adjust X)
        new_x = self._base_x + int(self._current_offset_x)
        self._label.move(new_x, self._label.y())


# ══════════════════════════════════════════════════════════════
#  PHYSICAL REACTIONS (jump, sneeze, stomp, wave)
# ══════════════════════════════════════════════════════════════
class PhysicalReactions:
    """Short procedural animations applied as Y/X offsets on the pet label."""

    def __init__(self, pet_label: QLabel, base_y: int = 100):
        self._label = pet_label
        self._base_y = base_y
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._sequence: list[tuple[int, int]] = []  # (dx, dy) offsets per frame
        self._frame = 0
        self._callback = None

    @property
    def is_playing(self) -> bool:
        return self._timer.isActive()

    def jump(self, callback=None):
        """Quick upward spring — for startled or level-up."""
        self._sequence = []
        # Up phase (12 frames)
        for i in range(12):
            t = i / 12
            y = int(-20 * math.sin(t * math.pi))
            self._sequence.append((0, y))
        # Settle
        for i in range(4):
            self._sequence.append((0, int(-3 * (4 - i) / 4)))
        self._sequence.append((0, 0))
        self._play(callback)

    def victory_dance(self, callback=None):
        """Bouncy celebrate — for achievements and challenges."""
        self._sequence = []
        for cycle in range(3):
            for i in range(8):
                t = i / 8
                y = int(-12 * abs(math.sin(t * math.pi)))
                x = int(6 * math.sin(t * 2 * math.pi))
                self._sequence.append((x, y))
        self._sequence.append((0, 0))
        self._play(callback)

    def sneeze(self, callback=None):
        """Rapid micro-shake — for idle comedy."""
        self._sequence = []
        # Wind-up
        for i in range(4):
            self._sequence.append((0, int(-2 * i)))
        # Snap forward
        self._sequence.extend([(0, 4), (3, 6), (-3, 4), (2, 2), (-2, 1)])
        # Settle
        self._sequence.extend([(0, 0)] * 3)
        self._play(callback)

    def stomp(self, callback=None):
        """Alternating Y-offset rage — for backspace fury."""
        self._sequence = []
        for i in range(6):
            self._sequence.append((random.randint(-2, 2), -4 if i % 2 == 0 else 4))
        self._sequence.extend([(0, 0)] * 2)
        self._play(callback)

    def wave(self, callback=None):
        """Gentle side-to-side sway — for greetings."""
        self._sequence = []
        for i in range(16):
            t = i / 16
            x = int(8 * math.sin(t * 2 * math.pi))
            self._sequence.append((x, 0))
        self._sequence.append((0, 0))
        self._play(callback)

    def eating(self, callback=None):
        """Small rhythmic nods — for feeding/pomodoro complete."""
        self._sequence = []
        for _ in range(4):
            self._sequence.extend([(0, -3), (0, 0), (0, 3), (0, 0)])
        self._sequence.append((0, 0))
        self._play(callback)

    def _play(self, callback=None):
        self._frame = 0
        self._callback = callback
        self._timer.start(33)

    def _tick(self):
        if self._frame >= len(self._sequence):
            self._timer.stop()
            self._label.move(self._label.x(), self._base_y)
            if self._callback:
                self._callback()
            return
        dx, dy = self._sequence[self._frame]
        base_x = self._label.x()
        self._label.move(base_x + dx, self._base_y + dy)
        self._frame += 1


# ══════════════════════════════════════════════════════════════
#  EMOTION FACE OVERLAY
# ══════════════════════════════════════════════════════════════
class EmotionOverlay(QLabel):
    """Draws dynamic face expressions over the pet based on mood."""

    # Mood thresholds for expressions
    EXPRESSIONS = {
        "ecstatic":   {"mood_min": 90, "eyes": "star",   "mouth": "grin"},
        "happy":      {"mood_min": 70, "eyes": "normal", "mouth": "smile"},
        "content":    {"mood_min": 50, "eyes": "normal", "mouth": "neutral"},
        "tired":      {"mood_min": 30, "eyes": "half",   "mouth": "frown"},
        "sad":        {"mood_min": 0,  "eyes": "droopy", "mouth": "sad"},
    }

    def __init__(self, parent: QWidget, size: int = 100):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self._size = size
        self._mood = 70.0
        self._energy = 80.0
        self._expression = "happy"
        self._enabled = False

    def start(self):
        self._enabled = True
        self.show()

    def stop(self):
        self._enabled = False
        self.hide()

    def update_mood(self, mood: float, energy: float):
        self._mood = mood
        self._energy = energy
        # Determine expression
        for name, cfg in self.EXPRESSIONS.items():
            if mood >= cfg["mood_min"]:
                self._expression = name
                break
        if self._enabled:
            self.update()

    def paintEvent(self, event):
        if not self._enabled:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        s = self._size / 100

        expr = self.EXPRESSIONS.get(self._expression, self.EXPRESSIONS["content"])

        # ── Eyes ──
        eye_color = QColor(50, 50, 70)
        left_x, right_x = int(35 * s), int(65 * s)
        eye_y = int(38 * s)
        eye_r = int(5 * s)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(eye_color)

        if expr["eyes"] == "star":
            # Star eyes ★
            painter.setPen(QPen(QColor(255, 200, 50), int(2 * s)))
            painter.setBrush(QColor(255, 220, 80))
            for ex in (left_x, right_x):
                self._draw_star(painter, ex, eye_y, eye_r, s)
        elif expr["eyes"] == "half":
            # Half-closed
            painter.setBrush(eye_color)
            for ex in (left_x, right_x):
                painter.drawEllipse(QPoint(ex, eye_y + int(2 * s)), eye_r, int(eye_r * 0.5))
        elif expr["eyes"] == "droopy":
            # Droopy eyes
            painter.setBrush(eye_color)
            for ex in (left_x, right_x):
                painter.drawEllipse(QPoint(ex, eye_y + int(3 * s)), eye_r, int(eye_r * 0.6))
        else:
            # Normal round eyes
            for ex in (left_x, right_x):
                painter.drawEllipse(QPoint(ex, eye_y), eye_r, eye_r)

        # ── Mouth ──
        mouth_y = int(58 * s)
        mouth_w = int(16 * s)
        pen = QPen(QColor(60, 60, 80), max(1, int(2 * s)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = int(50 * s)
        if expr["mouth"] == "grin":
            from PyQt6.QtCore import QRectF
            rect = QRectF(cx - mouth_w // 2, mouth_y - int(4 * s), mouth_w, int(10 * s))
            painter.drawArc(rect, 0, -180 * 16)
        elif expr["mouth"] == "smile":
            from PyQt6.QtCore import QRectF
            rect = QRectF(cx - mouth_w // 2, mouth_y - int(3 * s), mouth_w, int(8 * s))
            painter.drawArc(rect, 0, -180 * 16)
        elif expr["mouth"] == "frown":
            from PyQt6.QtCore import QRectF
            rect = QRectF(cx - mouth_w // 2, mouth_y, mouth_w, int(8 * s))
            painter.drawArc(rect, 0, 180 * 16)
        elif expr["mouth"] == "sad":
            from PyQt6.QtCore import QRectF
            rect = QRectF(cx - mouth_w // 2, mouth_y + int(2 * s), mouth_w, int(10 * s))
            painter.drawArc(rect, 0, 180 * 16)
        else:
            painter.drawLine(cx - mouth_w // 3, mouth_y, cx + mouth_w // 3, mouth_y)

        painter.end()

    def _draw_star(self, painter: QPainter, cx: int, cy: int, r: int, s: float):
        """Draw a 5-point star."""
        from PyQt6.QtGui import QPolygonF
        from PyQt6.QtCore import QPointF
        points = []
        for i in range(10):
            angle = math.pi / 2 + i * math.pi / 5
            radius = r if i % 2 == 0 else r * 0.4
            points.append(QPointF(cx + radius * math.cos(angle),
                                  cy - radius * math.sin(angle)))
        painter.drawPolygon(QPolygonF(points))


# ══════════════════════════════════════════════════════════════
#  SIZE GROWTH WITH EVOLUTION
# ══════════════════════════════════════════════════════════════
# Maps evolution level thresholds to pet size multipliers
GROWTH_SIZES = {
    1:  0.85,   # Baby — smaller
    5:  0.92,   # Growing
    10: 1.0,    # Teen — normal
    20: 1.05,   # Adult — slightly bigger
    30: 1.10,   # Elder
    50: 1.15,   # Legendary
}

def get_size_multiplier(level: int) -> float:
    """Get the pet size multiplier for the given level."""
    result = 0.85
    for threshold, mult in sorted(GROWTH_SIZES.items()):
        if level >= threshold:
            result = mult
    return result


# ══════════════════════════════════════════════════════════════
#  SEASONAL / EVENT SKINS
# ══════════════════════════════════════════════════════════════
def get_seasonal_event() -> str | None:
    """Detect current season or Islamic event for skin suggestions."""
    from datetime import datetime
    now = datetime.now()
    month, day = now.month, now.day

    # Try Hijri detection for Ramadan / Eid
    try:
        from features.prayer import gregorian_to_hijri
        hijri = gregorian_to_hijri(now.year, month, day)
        h_month = hijri[1]
        h_day = hijri[2]
        if h_month == 9:  # Ramadan
            return "ramadan"
        if h_month == 10 and h_day <= 3:  # Eid al-Fitr
            return "eid_fitr"
        if h_month == 12 and 10 <= h_day <= 13:  # Eid al-Adha
            return "eid_adha"
    except Exception:
        pass

    # Seasonal fallbacks
    if month == 12 or month <= 2:
        return "winter"
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    return "autumn"


SEASONAL_ACCESSORIES = {
    "ramadan": {"emoji": "🌙", "color": "#1a1a3e", "name": "Ramadan Crescent"},
    "eid_fitr": {"emoji": "🎉", "color": "#4CAF50", "name": "Eid al-Fitr"},
    "eid_adha": {"emoji": "🐑", "color": "#8B4513", "name": "Eid al-Adha"},
    "winter": {"emoji": "❄️", "color": "#87CEEB", "name": "Winter"},
    "spring": {"emoji": "🌸", "color": "#FFB7C5", "name": "Spring Bloom"},
    "summer": {"emoji": "☀️", "color": "#FFD700", "name": "Summer"},
    "autumn": {"emoji": "🍂", "color": "#D2691E", "name": "Autumn Leaves"},
}


# ══════════════════════════════════════════════════════════════
#  FOCUS VIGNETTE OVERLAY
# ══════════════════════════════════════════════════════════════
class FocusVignette(QLabel):
    """Semi-transparent edge-darkening overlay when focus mode is active."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")
        self._active = False
        self._opacity = 0.0
        self._target_opacity = 0.0
        self._timer = QTimer()
        self._timer.timeout.connect(self._fade_tick)
        self.hide()

    def activate(self):
        self._active = True
        self._target_opacity = 0.35
        self.setFixedSize(self.parent().size())
        self.move(0, 0)
        self.show()
        self.raise_()
        if not self._timer.isActive():
            self._timer.start(33)

    def deactivate(self):
        self._active = False
        self._target_opacity = 0.0
        if not self._timer.isActive():
            self._timer.start(33)

    def _fade_tick(self):
        diff = self._target_opacity - self._opacity
        if abs(diff) < 0.01:
            self._opacity = self._target_opacity
            self._timer.stop()
            if self._opacity <= 0:
                self.hide()
        else:
            self._opacity += diff * 0.15
        self.update()

    def paintEvent(self, event):
        if self._opacity <= 0:
            return
        painter = QPainter(self)
        w, h = self.width(), self.height()

        # Radial gradient: transparent center → dark edges
        center_x, center_y = w // 2, h // 2
        gradient = QRadialGradient(center_x, center_y, max(w, h) * 0.6)
        gradient.setColorAt(0, QColor(0, 0, 0, 0))
        gradient.setColorAt(0.7, QColor(0, 0, 0, int(80 * self._opacity)))
        gradient.setColorAt(1.0, QColor(0, 0, 0, int(180 * self._opacity)))

        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 0, w, h)
        painter.end()
