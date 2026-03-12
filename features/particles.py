"""
Particle System — lightweight QLabel-based particle emitter for visual effects.
Supports: confetti, hearts, sparkles, stars, snow, leaves.
"""
import math
import random
from PyQt6.QtCore import QTimer, QPoint, Qt
from PyQt6.QtWidgets import QLabel, QWidget, QGraphicsOpacityEffect
from PyQt6.QtGui import QFont

# ── Particle presets ──────────────────────────────────────────
PARTICLE_PRESETS = {
    "confetti":  {"chars": "🎊🎉✨🟡🔵🔴🟢🟣", "count": 18, "life": 1500, "speed": 4, "gravity": 0.15, "spread": 80},
    "hearts":    {"chars": "❤️💕💖💗💓💞",       "count": 10, "life": 1800, "speed": 2, "gravity": -0.08, "spread": 60},
    "sparkles":  {"chars": "✨⭐💫🌟",           "count": 12, "life": 1200, "speed": 3, "gravity": 0.0,  "spread": 70},
    "stars":     {"chars": "⭐🌙✨💫🌟",         "count": 10, "life": 2000, "speed": 1.5, "gravity": -0.05, "spread": 50},
    "snow":      {"chars": "❄️🌨️☃️",              "count": 15, "life": 3000, "speed": 1, "gravity": 0.1,  "spread": 100},
    "leaves":    {"chars": "🍂🍁🌿🍃",           "count": 10, "life": 2500, "speed": 1.5, "gravity": 0.08, "spread": 80},
    "fire":      {"chars": "🔥🧡❤️‍🔥💥",          "count": 10, "life": 1000, "speed": 3, "gravity": -0.2, "spread": 40},
    "bubbles":   {"chars": "🫧💭🔵⚪",           "count": 8,  "life": 2000, "speed": 1, "gravity": -0.1, "spread": 50},
    "prayer":    {"chars": "🤲📿🕌✨🌙",         "count": 8,  "life": 2000, "speed": 1, "gravity": -0.06, "spread": 40},
    "level_up":  {"chars": "🎉⬆️✨🏆💪🔥",       "count": 20, "life": 2000, "speed": 5, "gravity": 0.12, "spread": 90},
}


class _Particle:
    __slots__ = ("label", "vx", "vy", "life", "age", "gravity")

    def __init__(self, label: QLabel, vx: float, vy: float, life: int, gravity: float):
        self.label = label
        self.vx = vx
        self.vy = vy
        self.life = life
        self.age = 0
        self.gravity = gravity


class ParticleEmitter:
    """Attach to a QWidget parent. Call emit() to spawn particle bursts."""

    _POOL_SIZE = 30  # max concurrent particles

    def __init__(self, parent: QWidget):
        self._parent = parent
        self._pool: list[QLabel] = []
        self._active: list[_Particle] = []
        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._tick)
        self._tick_ms = 33  # ~30 fps

        # Pre-create label pool
        for _ in range(self._POOL_SIZE):
            lbl = QLabel(parent)
            lbl.setFont(QFont("Segoe UI Emoji", 14))
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setStyleSheet("background: transparent; border: none;")
            lbl.setFixedSize(28, 28)
            opacity_fx = QGraphicsOpacityEffect(lbl)
            opacity_fx.setOpacity(1.0)
            lbl.setGraphicsEffect(opacity_fx)
            lbl.hide()
            self._pool.append(lbl)

    def emit(self, preset: str = "confetti", origin: QPoint | None = None):
        """Spawn a burst of particles at origin (defaults to center of parent)."""
        cfg = PARTICLE_PRESETS.get(preset, PARTICLE_PRESETS["confetti"])
        if origin is None:
            origin = QPoint(self._parent.width() // 2, self._parent.height() // 2)

        chars = list(cfg["chars"].replace("\ufe0f", ""))  # strip variation selectors for random pick
        if not chars:
            chars = ["✨"]
        count = cfg["count"]
        spread = cfg["spread"]

        spawned = 0
        for lbl in self._pool:
            if spawned >= count:
                break
            if lbl.isVisible():
                continue
            ch = random.choice(chars)
            lbl.setText(ch)
            lbl.move(origin.x() + random.randint(-10, 10),
                     origin.y() + random.randint(-10, 10))
            lbl.show()
            lbl.raise_()
            angle = random.uniform(0, 2 * math.pi)
            speed = cfg["speed"] * random.uniform(0.5, 1.5)
            vx = math.cos(angle) * speed * (spread / 50)
            vy = math.sin(angle) * speed * (spread / 50) - cfg["speed"]
            p = _Particle(lbl, vx, vy, cfg["life"], cfg["gravity"])
            self._active.append(p)
            spawned += 1

        if self._active and not self._timer.isActive():
            self._timer.start(self._tick_ms)

    def _tick(self):
        dt = self._tick_ms
        still_alive = []
        for p in self._active:
            p.age += dt
            if p.age >= p.life:
                p.label.hide()
                continue
            p.vy += p.gravity
            nx = p.label.x() + p.vx
            ny = p.label.y() + p.vy
            p.label.move(int(nx), int(ny))
            # Fade out in last 30%
            ratio = p.age / p.life
            if ratio > 0.7:
                opacity = max(0.0, 1.0 - (ratio - 0.7) / 0.3)
                fx = p.label.graphicsEffect()
                if fx:
                    fx.setOpacity(opacity)
            still_alive.append(p)

        self._active = still_alive
        if not self._active:
            self._timer.stop()

    def stop(self):
        self._timer.stop()
        for p in self._active:
            p.label.hide()
            fx = p.label.graphicsEffect()
            if fx:
                fx.setOpacity(1.0)
        self._active.clear()
