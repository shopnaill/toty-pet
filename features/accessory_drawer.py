"""
Accessory Drawer — QPainter-based cosmetic accessory renderers.
Extracted from animals.py to reduce monolith size.
"""
import math
from PyQt6.QtCore import Qt, QPoint as QP, QRectF
from PyQt6.QtGui import QPainter, QColor, QPolygon, QPen


def draw_crown(p: QPainter, size: int):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 215, 0))
    pts = [QP(25, 28), QP(30, 6), QP(38, 20), QP(50, 2),
           QP(62, 20), QP(70, 6), QP(75, 28)]
    p.drawPolygon(QPolygon(pts))
    p.setBrush(QColor(200, 170, 0))
    p.drawRect(25, 24, 50, 6)
    p.setBrush(QColor(220, 30, 30)); p.drawEllipse(35, 25, 5, 4)
    p.setBrush(QColor(30, 120, 220)); p.drawEllipse(47, 25, 5, 4)
    p.setBrush(QColor(30, 200, 80)); p.drawEllipse(59, 25, 5, 4)


def draw_party_hat(p: QPainter, size: int):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(220, 60, 160))
    p.drawPolygon(QPolygon([QP(50, 0), QP(30, 30), QP(70, 30)]))
    p.setBrush(QColor(60, 200, 220, 120))
    p.drawPolygon(QPolygon([QP(50, 0), QP(38, 18), QP(44, 18)]))
    p.drawPolygon(QPolygon([QP(50, 0), QP(56, 18), QP(62, 18)]))
    p.setBrush(QColor(255, 230, 50))
    p.drawEllipse(45, -4, 10, 10)
    p.setBrush(QColor(200, 50, 140))
    p.drawRoundedRect(28, 28, 44, 5, 2, 2)


def draw_bow_tie(p: QPainter, size: int):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(200, 50, 50))
    p.drawPolygon(QPolygon([QP(50, 60), QP(30, 52), QP(30, 68)]))
    p.drawPolygon(QPolygon([QP(50, 60), QP(70, 52), QP(70, 68)]))
    p.setBrush(QColor(160, 30, 30))
    p.drawEllipse(46, 56, 8, 8)


def draw_wizard_hat(p: QPainter, size: int):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(50, 30, 120))
    p.drawPolygon(QPolygon([QP(50, -10), QP(28, 30), QP(72, 30)]))
    p.setBrush(QColor(40, 20, 100))
    p.drawEllipse(18, 24, 64, 12)
    p.setBrush(QColor(255, 230, 100))
    p.drawEllipse(40, 8, 5, 5)
    p.drawEllipse(55, 14, 4, 4)
    p.drawEllipse(45, 20, 3, 3)
    p.setBrush(QColor(255, 255, 200, 180))
    p.drawEllipse(47, -12, 6, 6)


def draw_cape(p: QPainter, size: int):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(180, 30, 30, 180))
    p.drawPolygon(QPolygon([
        QP(35, 36), QP(65, 36), QP(75, 95), QP(25, 95)
    ]))
    p.setBrush(QColor(100, 20, 20, 120))
    p.drawPolygon(QPolygon([
        QP(40, 42), QP(60, 42), QP(68, 90), QP(32, 90)
    ]))


def draw_flower(p: QPainter, size: int):
    p.setPen(Qt.PenStyle.NoPen)
    for angle in range(0, 360, 60):
        rad = math.radians(angle)
        cx = 25 + 10 * math.cos(rad)
        cy = 18 + 10 * math.sin(rad)
        p.setBrush(QColor(255, 140, 180))
        p.drawEllipse(int(cx) - 5, int(cy) - 5, 10, 10)
    p.setBrush(QColor(255, 220, 50))
    p.drawEllipse(20, 13, 10, 10)


def draw_star_badge(p: QPainter, size: int):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 215, 0))
    cx, cy, r_outer, r_inner = 75, 75, 12, 5
    pts = []
    for i in range(10):
        angle = math.radians(i * 36 - 90)
        r = r_outer if i % 2 == 0 else r_inner
        pts.append(QP(int(cx + r * math.cos(angle)),
                       int(cy + r * math.sin(angle))))
    p.drawPolygon(QPolygon(pts))


def draw_sunglasses(p: QPainter, size: int):
    pen = QPen(QColor(20, 20, 20), 3)
    p.setPen(pen)
    p.setBrush(QColor(30, 30, 30, 200))
    p.drawRoundedRect(22, 32, 22, 16, 4, 4)
    p.drawRoundedRect(56, 32, 22, 16, 4, 4)
    p.drawLine(44, 39, 56, 39)
    p.drawLine(22, 37, 12, 34)
    p.drawLine(78, 37, 88, 34)


def draw_halo(p: QPainter, size: int):
    pen = QPen(QColor(255, 230, 100, 200), 3)
    p.setPen(pen)
    p.setBrush(QColor(255, 240, 150, 80))
    p.drawEllipse(QRectF(28, -2, 44, 14))


def draw_pirate_hat(p: QPainter, size: int):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(30, 30, 30))
    p.drawEllipse(20, 8, 60, 20)
    p.setBrush(QColor(25, 25, 25))
    p.drawPolygon(QPolygon([QP(30, 12), QP(50, -4), QP(70, 12)]))
    p.setBrush(QColor(220, 220, 220))
    p.drawEllipse(43, 4, 14, 12)
    p.setBrush(QColor(30, 30, 30))
    p.drawEllipse(46, 8, 3, 3)
    p.drawEllipse(52, 8, 3, 3)
    p.setBrush(QColor(40, 40, 40))
    p.drawRoundedRect(18, 22, 64, 6, 3, 3)


# Registry mapping accessory name → draw function
COSMETIC_DRAWERS: dict[str, callable] = {
    "crown": draw_crown,
    "party_hat": draw_party_hat,
    "bow_tie": draw_bow_tie,
    "wizard_hat": draw_wizard_hat,
    "cape": draw_cape,
    "flower": draw_flower,
    "star_badge": draw_star_badge,
    "sunglasses": draw_sunglasses,
    "halo": draw_halo,
    "pirate_hat": draw_pirate_hat,
}
