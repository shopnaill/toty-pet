"""
Sprite Sheet Animation Engine for PyQt6.

Replaces the GIF-based animation system with a segmented sprite sheet pipeline:
  1. A single PNG sprite sheet with all body parts
  2. A JSON atlas defining part regions + pivot points
  3. A JSON animation file with keyframed transforms per part per state

Supports:
  - Per-part position, rotation, scale, opacity keyframes
  - Linear and ease-in-out interpolation
  - Horizontal flip (no duplicate left/right assets)
  - Runtime slot overrides (swap hats, held items, expressions)
  - GIF fallback if sprite assets are not present
"""

from __future__ import annotations
import json
import logging
import math
import os
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPixmap, QPainter, QTransform, QColor, QImage
from PyQt6.QtWidgets import QWidget

log = logging.getLogger("toty.sprite_engine")


# ══════════════════════════════════════════════════════════════
#  DATA STRUCTURES
# ══════════════════════════════════════════════════════════════

class PartRegion:
    """A rectangular region on the sprite sheet for one body part."""
    __slots__ = ("name", "x", "y", "w", "h", "pivot_x", "pivot_y", "z_order",
                 "draw_x", "draw_y")

    def __init__(self, name: str, x: int, y: int, w: int, h: int,
                 pivot_x: float = 0.5, pivot_y: float = 0.5, z_order: int = 0,
                 draw_x: float = 0.0, draw_y: float = 0.0):
        self.name = name
        self.x = x          # region x on sheet (for cutting)
        self.y = y          # region y on sheet (for cutting)
        self.w = w           # width
        self.h = h           # height
        self.pivot_x = pivot_x  # 0..1 relative pivot
        self.pivot_y = pivot_y
        self.z_order = z_order  # draw order (higher = on top)
        self.draw_x = draw_x    # rest-pose X offset from character center
        self.draw_y = draw_y    # rest-pose Y offset from character center


class Keyframe:
    """A single keyframe for one part at a given normalized time."""
    __slots__ = ("t", "x", "y", "rot", "scale_x", "scale_y", "opacity", "easing")

    def __init__(self, t: float, x: float = 0, y: float = 0, rot: float = 0,
                 scale_x: float = 1.0, scale_y: float = 1.0,
                 opacity: float = 1.0, easing: str = "linear"):
        self.t = t           # 0.0 .. 1.0 (normalized time in animation cycle)
        self.x = x           # offset from base position
        self.y = y
        self.rot = rot       # degrees
        self.scale_x = scale_x
        self.scale_y = scale_y
        self.opacity = opacity
        self.easing = easing  # "linear" or "ease"


class AnimationDef:
    """Definition of one animation state (e.g., 'idle', 'walk')."""
    __slots__ = ("name", "fps", "loop", "parts")

    def __init__(self, name: str, fps: int = 12, loop: bool = True,
                 parts: dict[str, list[Keyframe]] | None = None):
        self.name = name
        self.fps = fps
        self.loop = loop
        # {part_name: [Keyframe, ...]} sorted by t
        self.parts: dict[str, list[Keyframe]] = parts or {}


# ══════════════════════════════════════════════════════════════
#  INTERPOLATION
# ══════════════════════════════════════════════════════════════

def _ease_in_out(t: float) -> float:
    """Smooth ease-in-out (cubic)."""
    if t < 0.5:
        return 4 * t * t * t
    return 1 - (-2 * t + 2) ** 3 / 2


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _interpolate_keyframes(keyframes: list[Keyframe], t: float) -> dict:
    """Interpolate between keyframes at normalized time t (0..1)."""
    if not keyframes:
        return {"x": 0, "y": 0, "rot": 0, "scale_x": 1, "scale_y": 1, "opacity": 1}

    t = t % 1.0 if t >= 1.0 else t

    # Find surrounding keyframes
    prev = keyframes[0]
    nxt = keyframes[-1]
    for i, kf in enumerate(keyframes):
        if kf.t >= t:
            nxt = kf
            prev = keyframes[max(0, i - 1)]
            break
    else:
        prev = nxt = keyframes[-1]

    if prev is nxt or abs(nxt.t - prev.t) < 1e-6:
        kf = prev
        return {
            "x": kf.x, "y": kf.y, "rot": kf.rot,
            "scale_x": kf.scale_x, "scale_y": kf.scale_y, "opacity": kf.opacity,
        }

    # Compute local t
    local_t = (t - prev.t) / (nxt.t - prev.t)
    if nxt.easing == "ease":
        local_t = _ease_in_out(local_t)

    return {
        "x":       _lerp(prev.x, nxt.x, local_t),
        "y":       _lerp(prev.y, nxt.y, local_t),
        "rot":     _lerp(prev.rot, nxt.rot, local_t),
        "scale_x": _lerp(prev.scale_x, nxt.scale_x, local_t),
        "scale_y": _lerp(prev.scale_y, nxt.scale_y, local_t),
        "opacity": _lerp(prev.opacity, nxt.opacity, local_t),
    }


# ══════════════════════════════════════════════════════════════
#  ATLAS + ANIMATION LOADERS
# ══════════════════════════════════════════════════════════════

def load_atlas(atlas_path: str) -> dict[str, PartRegion]:
    """Load pet_atlas.json → {part_name: PartRegion}."""
    with open(atlas_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    parts = {}
    for name, info in data["parts"].items():
        parts[name] = PartRegion(
            name=name,
            x=info["x"], y=info["y"], w=info["w"], h=info["h"],
            pivot_x=info.get("pivot_x", 0.5),
            pivot_y=info.get("pivot_y", 0.5),
            z_order=info.get("z_order", 0),
            draw_x=info.get("draw_x", 0.0),
            draw_y=info.get("draw_y", 0.0),
        )
    return parts


def load_animations(anim_path: str) -> dict[str, AnimationDef]:
    """Load pet_animations.json → {state_name: AnimationDef}."""
    with open(anim_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    anims = {}
    for state_name, adef in data.items():
        parts_kf: dict[str, list[Keyframe]] = {}
        for part_name, kf_list in adef.get("keyframes", {}).items():
            keyframes = []
            for kf in kf_list:
                keyframes.append(Keyframe(
                    t=kf["t"],
                    x=kf.get("x", 0), y=kf.get("y", 0),
                    rot=kf.get("rot", 0),
                    scale_x=kf.get("scale_x", 1.0),
                    scale_y=kf.get("scale_y", 1.0),
                    opacity=kf.get("opacity", 1.0),
                    easing=kf.get("easing", "linear"),
                ))
            keyframes.sort(key=lambda k: k.t)
            parts_kf[part_name] = keyframes
        anims[state_name] = AnimationDef(
            name=state_name,
            fps=adef.get("fps", 12),
            loop=adef.get("loop", True),
            parts=parts_kf,
        )
    return anims


# ══════════════════════════════════════════════════════════════
#  STATE NAME MAPPING (old GIF names → sprite animation names)
# ══════════════════════════════════════════════════════════════

# Maps old set_state() names to (animation_name, facing_right)
# So "walk_left" → play "walk" animation, flipped left
STATE_MAP: dict[str, tuple[str, bool | None]] = {
    # Movement (direction handled by flip)
    "walk_left":    ("walk", False),
    "walk_right":   ("walk", True),
    "run_left":     ("run",  False),
    "run_right":    ("run",  True),
    "crawl_left":   ("crawl", False),
    "crawl_right":  ("crawl", True),
    "carry_left":   ("carry", False),
    "carry_right":  ("carry", True),
    # Non-directional (keep current facing)
    "idle":         ("idle", None),
    "work":         ("work", None),
    "sleep":        ("sleep", None),
    "dance":        ("dance", None),
    "smile":        ("happy", None),
    "excited":      ("excited", None),
    "sad":          ("sad", None),
    "yawn":         ("yawn", None),
    "stretch":      ("stretch", None),
    "pray":         ("pray", None),
    "screenshot":   ("screenshot", None),
    "notification": ("notification", None),
    "music_listen": ("music", None),
    "play_music":   ("music", None),
    "level_up":     ("level_up", None),
    "startup":      ("startup", None),
    "shutdown":     ("shutdown", None),
    "restart":      ("restart", None),
    "run_app":      ("run_app", None),
}


# ══════════════════════════════════════════════════════════════
#  SPRITE RENDERER WIDGET
# ══════════════════════════════════════════════════════════════

class SpriteRenderer(QWidget):
    """
    Renders segmented sprite-sheet animations using QPainter.

    Drop-in replacement for pet_label + QMovie system.
    Call play(state) instead of set_state() — or use set_state() which delegates.
    """

    def __init__(self, parent: QWidget | None = None, size: int = 100):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._size = size
        self._sheet: QPixmap | None = None
        self._parts: dict[str, PartRegion] = {}
        self._animations: dict[str, AnimationDef] = {}
        self._part_pixmaps: dict[str, QPixmap] = {}  # pre-cut part images

        # Runtime state
        self._current_anim: AnimationDef | None = None
        self._anim_name: str = ""
        self._frame_time: float = 0.0   # accumulated time in seconds
        self._facing_right: bool = True

        # Slot overrides: {slot_name: alternative_part_name or None to hide}
        self._slot_overrides: dict[str, str | None] = {}

        # State color tinting: {anim_name: QColor}
        self._state_colors: dict[str, QColor] = {}
        self._tint_strength: float = 0.35  # blend factor for body tint

        # Render timer
        self._fps = 30
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000 // self._fps)

        # Whether sprite assets are loaded
        self._loaded = False

    @property
    def loaded(self) -> bool:
        return self._loaded

    def load(self, assets_folder: str = "assets") -> bool:
        """
        Load sprite sheet + atlas + animations from assets folder.
        Returns True if loaded successfully, False if files not found (use GIF fallback).
        """
        sheet_path = os.path.join(assets_folder, "pet_sheet.png")
        atlas_path = os.path.join(assets_folder, "pet_atlas.json")
        anim_path = os.path.join(assets_folder, "pet_animations.json")

        if not all(os.path.exists(p) for p in (sheet_path, atlas_path, anim_path)):
            return False

        try:
            self._sheet = QPixmap(sheet_path)
            if self._sheet.isNull():
                return False

            self._parts = load_atlas(atlas_path)
            self._animations = load_animations(anim_path)

            # Pre-cut part pixmaps from the sheet
            self._part_pixmaps.clear()
            for name, region in self._parts.items():
                self._part_pixmaps[name] = self._sheet.copy(
                    region.x, region.y, region.w, region.h,
                )

            self._loaded = True

            # Load state colors from the skin config
            self._state_colors.clear()
            try:
                with open(atlas_path, "r", encoding="utf-8") as f:
                    atlas_data = json.load(f)
                skin_id = atlas_data.get("skin", "default")
                skin_dir = os.path.join("assets", "skins", skin_id)
                if os.path.isdir(skin_dir):
                    skin_data = load_skin(skin_dir)
                    for state, val in skin_data.get("state_colors", {}).items():
                        # val can be {"body": "#hex", ...} or plain "#hex"
                        hex_color = val.get("body", val) if isinstance(val, dict) else val
                        self._state_colors[state] = QColor(hex_color)
            except (OSError, json.JSONDecodeError, KeyError):
                pass

            return True
        except Exception as e:
            log.warning("Failed to load sprite assets: %s", e)
            return False

    def switch_skin(self, skin_id: str,
                    skins_root: str = "assets/skins",
                    assets_folder: str = "assets") -> bool:
        """
        Generate assets from the given skin and reload them.
        Returns True on success.
        """
        current_anim = self._anim_name
        ok = generate_skin_assets(skin_id, skins_root, assets_folder, force=True)
        if not ok:
            return False
        loaded = self.load(assets_folder)
        if loaded and current_anim:
            self.play(current_anim)
        return loaded

    def get_animation_names(self) -> list[str]:
        """Return list of available sprite animation names."""
        return list(self._animations.keys())

    def has_animation(self, name: str) -> bool:
        """Check if a sprite animation exists (mapped or direct)."""
        if name in self._animations:
            return True
        mapped = STATE_MAP.get(name)
        if mapped and mapped[0] in self._animations:
            return True
        return False

    def play(self, state_name: str):
        """
        Play an animation by name. Handles STATE_MAP translation.
        Compatible with old set_state() names like 'walk_left'.
        """
        mapped = STATE_MAP.get(state_name)
        if mapped:
            anim_name, facing = mapped
            if facing is not None:
                self._facing_right = facing
        else:
            anim_name = state_name

        if anim_name == self._anim_name and self._current_anim is not None:
            return  # already playing

        anim = self._animations.get(anim_name)
        if not anim:
            # Try fallback to idle
            anim = self._animations.get("idle")
        if not anim:
            return

        self._current_anim = anim
        self._anim_name = anim_name
        self._frame_time = 0.0
        self.update()

    def set_facing(self, right: bool):
        """Set horizontal facing direction."""
        self._facing_right = right

    def set_slot(self, slot_name: str, part_name: str | None):
        """
        Override a slot to show a different part (or None to hide it).
        E.g., set_slot("held_item", "folder_icon") to show carrying.
        """
        if part_name is None:
            self._slot_overrides[slot_name] = None  # explicitly hidden
        elif part_name in self._part_pixmaps:
            self._slot_overrides[slot_name] = part_name
        else:
            # Part not in atlas — ignore silently
            self._slot_overrides.pop(slot_name, None)

    def clear_slot(self, slot_name: str):
        """Remove a slot override, returning to the default part."""
        self._slot_overrides.pop(slot_name, None)

    def clear_all_slots(self):
        """Remove all slot overrides."""
        self._slot_overrides.clear()

    def _tick(self):
        """Advance animation time and repaint."""
        if not self._current_anim:
            return
        dt = 1.0 / self._fps
        self._frame_time += dt
        self.update()

    def paintEvent(self, event):
        """Render all parts with current keyframe transforms."""
        if not self._loaded or not self._current_anim:
            return

        anim = self._current_anim
        # Compute normalized time (0..1) within animation cycle
        cycle_duration = max(len(next(iter(anim.parts.values()), [])), 1) / max(anim.fps, 1)
        # More robust: use the max 't' in keyframes to derive cycle length
        # Each cycle = 1.0 in normalized time, played over (1/fps * num_conceptual_frames)
        anim_speed = anim.fps
        t_normalized = (self._frame_time * anim_speed) % 1.0 if anim.loop else min(self._frame_time * anim_speed, 0.999)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Collect parts to draw, sorted by z_order
        draw_list: list[tuple[int, str, PartRegion, dict]] = []

        for part_name, region in self._parts.items():
            # Check slot overrides
            if part_name in self._slot_overrides:
                override = self._slot_overrides[part_name]
                if override is None:
                    continue  # slot hidden
                # Use override pixmap but original region's position/z
                actual_pix_name = override
            else:
                actual_pix_name = part_name

            pix = self._part_pixmaps.get(actual_pix_name)
            if pix is None or pix.isNull():
                continue

            # Get interpolated transform for this part
            kf_data = anim.parts.get(part_name, [])
            # Skip parts with no keyframes and no slot override (e.g. hat, held_item)
            if not kf_data and part_name not in self._slot_overrides:
                continue
            transforms = _interpolate_keyframes(kf_data, t_normalized)

            draw_list.append((region.z_order, actual_pix_name, region, transforms))

        # Sort by z_order
        draw_list.sort(key=lambda item: item[0])

        # Center of widget
        cx = self._size / 2
        cy = self._size / 2

        for _, pix_name, region, tf in draw_list:
            pix = self._part_pixmaps[pix_name]
            opacity = tf["opacity"]
            if opacity <= 0:
                continue

            painter.save()
            painter.setOpacity(opacity)

            # Rest-pose position from atlas (relative to character center)
            base_x = cx + region.draw_x
            base_y = cy + region.draw_y

            # Apply animation offsets
            anim_x = tf["x"]
            anim_y = tf["y"]
            rot = tf["rot"]
            sx = tf["scale_x"]
            sy = tf["scale_y"]

            draw_x = base_x + anim_x
            draw_y = base_y + anim_y

            # Flip horizontally if facing left
            if not self._facing_right:
                draw_x = self._size - draw_x
                rot = -rot

            # Pivot point (in part-local space)
            pivot_x = region.w * region.pivot_x
            pivot_y = region.h * region.pivot_y

            # Build transform
            transform = QTransform()
            transform.translate(draw_x, draw_y)
            transform.rotate(rot)
            transform.scale(sx if self._facing_right else -sx, sy)
            transform.translate(-pivot_x, -pivot_y)

            painter.setTransform(transform)
            painter.drawPixmap(0, 0, region.w, region.h, pix)

            # Apply state-color tint to body part
            if pix_name == "body" and self._anim_name in self._state_colors:
                tint = self._state_colors[self._anim_name]
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                tint.setAlphaF(self._tint_strength)
                painter.fillRect(0, 0, region.w, region.h, tint)

            painter.restore()

        painter.end()


# ══════════════════════════════════════════════════════════════
#  SKIN SYSTEM
# ══════════════════════════════════════════════════════════════

def get_available_skins(skins_root: str = "assets/skins") -> list[dict]:
    """Return list of {name, id, path} for all installed skins."""
    skins = []
    if not os.path.isdir(skins_root):
        return skins
    for entry in sorted(os.listdir(skins_root)):
        skin_dir = os.path.join(skins_root, entry)
        skin_json = os.path.join(skin_dir, "skin.json")
        if os.path.isfile(skin_json):
            with open(skin_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            skins.append({
                "id": entry,
                "name": data.get("name", entry),
                "description": data.get("description", ""),
                "path": skin_dir,
            })
    return skins


def load_skin(skin_path: str) -> dict:
    """Load a skin.json and return its data dict."""
    with open(os.path.join(skin_path, "skin.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def generate_skin_thumbnail(skin_id: str,
                            skins_root: str = "assets/skins",
                            size: int = 32) -> str | None:
    """
    Generate a small PNG thumbnail for a skin and return its file path.
    Returns None on failure.  Caches to assets/skins/<skin_id>/thumb.png.
    """
    from PIL import Image, ImageDraw

    skin_path = os.path.join(skins_root, skin_id)
    skin_json = os.path.join(skin_path, "skin.json")
    thumb_path = os.path.join(skin_path, "thumb.png")

    if not os.path.isfile(skin_json):
        return None

    # Cache check: thumb newer than skin.json
    if os.path.isfile(thumb_path):
        if os.path.getmtime(thumb_path) >= os.path.getmtime(skin_json):
            return thumb_path

    try:
        skin = load_skin(skin_path)
        body_color = skin["body"]["color"]
        limb_color = skin["limbs"]["color"]

        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Simple clay body
        margin = size // 8
        _draw_clay_ellipse(draw,
                           [margin, margin, size - margin, size - margin],
                           body_color, steps=20, specular_alpha=60, rim_light=True)

        # Eyes
        eye_sz = max(2, size // 10)
        cx = size // 2
        ey = size // 3
        sep = size // 6
        draw.ellipse([cx - sep - eye_sz, ey, cx - sep + eye_sz, ey + eye_sz * 2],
                     fill=skin["face"].get("eye_color", "#000"))
        draw.ellipse([cx + sep - eye_sz, ey, cx + sep + eye_sz, ey + eye_sz * 2],
                     fill=skin["face"].get("eye_color", "#000"))

        # Mouth
        mw = size // 5
        my = int(size * 0.55)
        draw.arc([cx - mw, my, cx + mw, my + mw // 2], 0, 180, fill="#000000", width=1)

        img.save(thumb_path)
        return thumb_path
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
#  CLAYMATION SPRITE SHEET GENERATOR  (PIL-based, matches pet.py style)
# ══════════════════════════════════════════════════════════════

def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    from PIL import ImageColor as IC
    rgb = IC.getrgb(hex_color)
    return (*rgb, alpha)


def _draw_clay_ellipse(draw, bbox, base_hex: str, steps: int = 40,
                       specular_alpha: int = 80, rim_light: bool = True):
    """
    Matte 3D clay shading — radial gradient exactly like pet.py's draw_aaa_3d_body.
    """
    from PIL import ImageColor as IC
    base_rgb = IC.getrgb(base_hex)
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    light_cx = x0 + w * 0.35
    light_cy = y0 + h * 0.30

    for i in range(steps):
        t = i / steps
        r = min(255, max(0, int(base_rgb[0] * (0.4 + 1.0 * t))))
        g = min(255, max(0, int(base_rgb[1] * (0.4 + 1.0 * t))))
        b = min(255, max(0, int(base_rgb[2] * (0.4 + 1.0 * t))))
        cx0 = x0 * (1 - t) + light_cx * t
        cy0 = y0 * (1 - t) + light_cy * t
        cx1 = x1 * (1 - t) + light_cx * t
        cy1 = y1 * (1 - t) + light_cy * t
        draw.ellipse([cx0, cy0, cx1, cy1], fill=(r, g, b, 255))

    # Rim light
    if rim_light:
        draw.arc([x0 + 2, y0 + 2, x1, y1], 10, 80, fill=(255, 255, 255, 70), width=2)

    # Specular highlight
    hl_w = w * 0.25
    hl_h = h * 0.15
    draw.ellipse([x0 + w * 0.2, y0 + h * 0.12,
                  x0 + w * 0.2 + hl_w, y0 + h * 0.12 + hl_h],
                 fill=(255, 255, 255, specular_alpha))


def _draw_shiny_limb(draw, x, y, w, h, limb_hex: str, hl_alpha: int = 180):
    """Glossy black (or colored) limb with specular dot — matches pet.py."""
    draw.ellipse([x, y, x + w, y + h], fill=limb_hex)
    # Specular highlight
    hl_w, hl_h = w * 0.3, h * 0.3
    draw.ellipse([x + w * 0.2, y + h * 0.15,
                  x + w * 0.2 + hl_w, y + h * 0.15 + hl_h],
                 fill=(255, 255, 255, hl_alpha))


def _skin_hash(skin_json_path: str) -> str:
    """Return SHA-256 hex digest of the skin.json file contents."""
    import hashlib
    with open(skin_json_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def generate_skin_assets(skin_id: str = "default",
                         skins_root: str = "assets/skins",
                         assets_folder: str = "assets",
                         force: bool = False) -> bool:
    """
    Generate pet_sheet.png + pet_atlas.json from a skin config.
    Uses PIL to draw claymation-quality parts matching the GIF style.
    Also writes pet_animations.json (shared across skins).
    Skips regeneration when the skin.json hash matches the cached atlas.
    Pass force=True to bypass caching.
    Returns True on success.
    """
    from PIL import Image, ImageDraw, ImageFilter

    skin_path = os.path.join(skins_root, skin_id)
    skin_json = os.path.join(skin_path, "skin.json")
    if not os.path.isfile(skin_json):
        log.warning("Skin not found: %s", skin_json)
        return False

    # ── Cache check: skip if atlas already matches this skin config ──
    current_hash = _skin_hash(skin_json)
    atlas_path = os.path.join(assets_folder, "pet_atlas.json")
    sheet_path = os.path.join(assets_folder, "pet_sheet.png")
    if not force and os.path.isfile(atlas_path) and os.path.isfile(sheet_path):
        try:
            with open(atlas_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("skin_hash") == current_hash and cached.get("skin") == skin_id:
                # Ensure animations file exists
                anim_path = os.path.join(assets_folder, "pet_animations.json")
                if not os.path.isfile(anim_path):
                    _write_default_animations(anim_path)
                return True
        except (json.JSONDecodeError, OSError):
            pass  # corrupted cache — regenerate

    skin = load_skin(skin_path)
    body_cfg = skin["body"]
    limb_cfg = skin["limbs"]
    face_cfg = skin["face"]

    body_color = body_cfg["color"]
    limb_color = limb_cfg["color"]
    steps = body_cfg.get("shading_steps", 40)
    spec_a = body_cfg.get("specular_alpha", 80)
    rim = body_cfg.get("rim_light", True)
    hl_a = limb_cfg.get("highlight_alpha", 180)

    arm_w, arm_h = limb_cfg["arm_w"], limb_cfg["arm_h"]
    leg_w, leg_h = limb_cfg["leg_w"], limb_cfg["leg_h"]
    eye_w, eye_h = face_cfg["eye_w"], face_cfg["eye_h"]
    mouth_w = face_cfg["mouth_width"]
    blush_hex = face_cfg["blush_color"]
    blush_a = face_cfg.get("blush_alpha", 200)
    blush_sz = face_cfg.get("blush_size", 8)

    # Sheet layout — generous sizing, 512x256 to fit quality parts
    sheet_w, sheet_h = 512, 256
    img = Image.new("RGBA", (sheet_w, sheet_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Part dimensions and positions on the sheet (packing)
    body_w, body_h = body_cfg["width"], body_cfg["height"]
    # We'll place each part with padding
    pad = 4

    # ── BODY (big clay ellipse) ──
    bx, by = pad, pad
    _draw_clay_ellipse(draw, [bx, by, bx + body_w, by + body_h],
                       body_color, steps, spec_a, rim)
    # Blush marks on body (like cheeks)
    blush_y_off = int(body_h * 0.55)
    blush_x_left = bx + int(body_w * 0.18)
    blush_x_right = bx + int(body_w * 0.68)
    draw.ellipse([blush_x_left, by + blush_y_off,
                  blush_x_left + blush_sz, by + blush_y_off + blush_sz // 2],
                 fill=_hex_to_rgba(blush_hex, blush_a))
    draw.ellipse([blush_x_right, by + blush_y_off,
                  blush_x_right + blush_sz, by + blush_y_off + blush_sz // 2],
                 fill=_hex_to_rgba(blush_hex, blush_a))

    # ── LEFT ARM ──
    lax = bx + body_w + pad
    lay = pad
    _draw_shiny_limb(draw, lax, lay, arm_w, arm_h, limb_color, hl_a)

    # ── RIGHT ARM ──
    rax = lax + arm_w + pad
    ray = pad
    _draw_shiny_limb(draw, rax, ray, arm_w, arm_h, limb_color, hl_a)

    # ── LEFT LEG ──
    llx = rax + arm_w + pad
    lly = pad
    _draw_shiny_limb(draw, llx, lly, leg_w, leg_h, limb_color, hl_a)

    # ── RIGHT LEG ──
    rlx = llx + leg_w + pad
    rly = pad
    _draw_shiny_limb(draw, rlx, rly, leg_w, leg_h, limb_color, hl_a)

    # ── TAIL (small clay ellipse) ──
    tail_w, tail_h = 14, 18
    tx = rlx + leg_w + pad
    ty = pad
    _draw_clay_ellipse(draw, [tx, ty, tx + tail_w, ty + tail_h],
                       body_color, 20, 60, rim)

    # ── LEFT EYE ──
    lex = pad
    ley = body_h + pad * 2
    eye_color = face_cfg.get("eye_color", "#000000")
    draw.ellipse([lex, ley, lex + eye_w, ley + eye_h], fill=eye_color)

    # ── RIGHT EYE ──
    rex = lex + eye_w + pad
    rey = ley
    draw.ellipse([rex, rey, rex + eye_w, rey + eye_h], fill=eye_color)

    # ── MOUTH (smile arc) ──
    mouth_h = 8
    mx = rex + eye_w + pad
    my = ley
    draw.arc([mx, my, mx + mouth_w, my + mouth_h], 0, 180, fill="#000000", width=2)

    # ── SLEEPY LEFT EYE (closed line) ──
    sleepy_h = 4
    slx = mx + mouth_w + pad
    sly = ley
    draw.line([slx, sly + sleepy_h // 2, slx + eye_w, sly + sleepy_h // 2],
              fill="#000000", width=2)

    # ── SLEEPY RIGHT EYE ──
    srx = slx + eye_w + pad
    sry = ley
    draw.line([srx, sry + sleepy_h // 2, srx + eye_w, sry + sleepy_h // 2],
              fill="#000000", width=2)

    # ── HELD ITEM (folder icon) ──
    hi_w, hi_h = 22, 18
    hix = srx + eye_w + pad
    hiy = ley
    draw.rectangle([hix, hiy, hix + hi_w, hiy + hi_h], fill="#FFD700",
                   outline="#C8A000", width=2)
    draw.rectangle([hix, hiy, hix + hi_w // 2, hiy + 4], fill="#E6BE00")
    # Inner file
    draw.rectangle([hix + 4, hiy + 5, hix + hi_w - 4, hiy + hi_h - 3],
                   fill="#FFFFFF", outline="#AAAAAA", width=1)

    # ── HAT (party hat, colored from body accent) ──
    hat_w, hat_h = 28, 14
    hatx = hix + hi_w + pad
    haty = ley
    draw.rectangle([hatx, haty + 4, hatx + hat_w, haty + hat_h],
                   fill="#E53935", outline="#B71C1C", width=2)
    draw.rectangle([hatx + 4, haty, hatx + hat_w - 4, haty + 6],
                   fill="#E53935", outline="#B71C1C", width=1)

    # ── SHADOW (ground shadow ellipse) ──
    sh_w, sh_h = body_w, 10
    shx = hatx + hat_w + pad
    shy = ley
    draw.ellipse([shx, shy, shx + sh_w, shy + sh_h], fill=(0, 0, 0, 40))

    # Save sheet
    os.makedirs(assets_folder, exist_ok=True)
    img.save(os.path.join(assets_folder, "pet_sheet.png"))

    # ── ATLAS ──
    atlas = {
        "sheet": "pet_sheet.png",
        "skin": skin_id,
        "skin_hash": current_hash,
        "parts": {
            "body":    {"x": bx, "y": by, "w": body_w, "h": body_h,
                        "pivot_x": 0.5, "pivot_y": 0.75, "z_order": 2,
                        "draw_x": 0, "draw_y": 5},
            "left_arm": {"x": lax, "y": lay, "w": arm_w, "h": arm_h,
                         "pivot_x": 0.5, "pivot_y": 0.15, "z_order": 1,
                         "draw_x": -(body_w // 2 + arm_w // 2 - 2), "draw_y": -2},
            "right_arm":{"x": rax, "y": ray, "w": arm_w, "h": arm_h,
                         "pivot_x": 0.5, "pivot_y": 0.15, "z_order": 3,
                         "draw_x": (body_w // 2 + arm_w // 2 - 2), "draw_y": -2},
            "left_leg": {"x": llx, "y": lly, "w": leg_w, "h": leg_h,
                         "pivot_x": 0.5, "pivot_y": 0.1, "z_order": 1,
                         "draw_x": -(body_w // 4), "draw_y": body_h // 2 + 2},
            "right_leg":{"x": rlx, "y": rly, "w": leg_w, "h": leg_h,
                         "pivot_x": 0.5, "pivot_y": 0.1, "z_order": 1,
                         "draw_x": (body_w // 4), "draw_y": body_h // 2 + 2},
            "tail":     {"x": tx, "y": ty, "w": tail_w, "h": tail_h,
                         "pivot_x": 0.3, "pivot_y": 0.5, "z_order": 0,
                         "draw_x": -(body_w // 2 + 4), "draw_y": body_h // 4},
            "left_eye": {"x": lex, "y": ley, "w": eye_w, "h": eye_h,
                         "pivot_x": 0.5, "pivot_y": 0.5, "z_order": 6,
                         "draw_x": -(face_cfg["eye_spacing"] // 2), "draw_y": -(body_h // 4)},
            "right_eye":{"x": rex, "y": rey, "w": eye_w, "h": eye_h,
                         "pivot_x": 0.5, "pivot_y": 0.5, "z_order": 6,
                         "draw_x": (face_cfg["eye_spacing"] // 2), "draw_y": -(body_h // 4)},
            "mouth":    {"x": mx, "y": my, "w": mouth_w, "h": mouth_h,
                         "pivot_x": 0.5, "pivot_y": 0.5, "z_order": 6,
                         "draw_x": 0, "draw_y": -(body_h // 8)},
            "sleepy_left_eye": {"x": slx, "y": sly, "w": eye_w, "h": sleepy_h,
                                "pivot_x": 0.5, "pivot_y": 0.5, "z_order": 6,
                                "draw_x": -(face_cfg["eye_spacing"] // 2), "draw_y": -(body_h // 4)},
            "sleepy_right_eye":{"x": srx, "y": sry, "w": eye_w, "h": sleepy_h,
                                "pivot_x": 0.5, "pivot_y": 0.5, "z_order": 6,
                                "draw_x": (face_cfg["eye_spacing"] // 2), "draw_y": -(body_h // 4)},
            "held_item":{"x": hix, "y": hiy, "w": hi_w, "h": hi_h,
                         "pivot_x": 0.5, "pivot_y": 0.5, "z_order": 7,
                         "draw_x": body_w // 2 + 4, "draw_y": -(body_h // 4)},
            "hat":      {"x": hatx, "y": haty, "w": hat_w, "h": hat_h,
                         "pivot_x": 0.5, "pivot_y": 1.0, "z_order": 8,
                         "draw_x": 0, "draw_y": -(body_h // 2 + 5)},
            "shadow":   {"x": shx, "y": shy, "w": sh_w, "h": sh_h,
                         "pivot_x": 0.5, "pivot_y": 0.5, "z_order": -1,
                         "draw_x": 0, "draw_y": body_h // 2 + 10},
        }
    }
    with open(os.path.join(assets_folder, "pet_atlas.json"), "w", encoding="utf-8") as f:
        json.dump(atlas, f, indent=2)

    # ── ANIMATIONS (shared — only write if missing) ──
    anim_path = os.path.join(assets_folder, "pet_animations.json")
    if not os.path.isfile(anim_path):
        _write_default_animations(anim_path)

    log.info("Generated assets for skin '%s' – sheet %dx%d, %d parts",
             skin.get('name', skin_id), sheet_w, sheet_h, len(atlas['parts']))
    return True


def _write_default_animations(anim_path: str):
    """Write the default pet_animations.json (shared by all skins)."""
    animations = {
        "idle": {
            "fps": 2, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.5, "y": -2, "easing": "ease"}, {"t": 1.0, "y": 0}],
                "head":     [{"t": 0, "y": 0, "rot": 0}, {"t": 0.5, "y": -3, "rot": 2, "easing": "ease"}, {"t": 1.0, "y": 0, "rot": 0}],
                "left_arm": [{"t": 0, "rot": 0}, {"t": 0.5, "rot": -3, "easing": "ease"}, {"t": 1.0, "rot": 0}],
                "right_arm":[{"t": 0, "rot": 0}, {"t": 0.5, "rot": 3, "easing": "ease"}, {"t": 1.0, "rot": 0}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 0.25, "rot": 10}, {"t": 0.75, "rot": -10}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.5, "scale_x": 0.95}, {"t": 1.0}],
            }
        },
        "walk": {
            "fps": 4, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.25, "y": -3}, {"t": 0.5, "y": 0}, {"t": 0.75, "y": -3}, {"t": 1.0, "y": 0}],
                "left_arm": [{"t": 0, "rot": -15}, {"t": 0.5, "rot": 15}, {"t": 1.0, "rot": -15}],
                "right_arm":[{"t": 0, "rot": 15}, {"t": 0.5, "rot": -15}, {"t": 1.0, "rot": 15}],
                "left_leg": [{"t": 0, "rot": -20}, {"t": 0.5, "rot": 20}, {"t": 1.0, "rot": -20}],
                "right_leg":[{"t": 0, "rot": 20}, {"t": 0.5, "rot": -20}, {"t": 1.0, "rot": 20}],
                "tail":     [{"t": 0, "rot": -15}, {"t": 0.5, "rot": 15}, {"t": 1.0, "rot": -15}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.25, "scale_x": 0.9}, {"t": 0.5}, {"t": 0.75, "scale_x": 0.9}, {"t": 1.0}],
            }
        },
        "run": {
            "fps": 6, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.25, "y": -5}, {"t": 0.5, "y": 0}, {"t": 0.75, "y": -5}, {"t": 1.0, "y": 0}],
                "left_arm": [{"t": 0, "rot": -30}, {"t": 0.5, "rot": 30}, {"t": 1.0, "rot": -30}],
                "right_arm":[{"t": 0, "rot": 30}, {"t": 0.5, "rot": -30}, {"t": 1.0, "rot": 30}],
                "left_leg": [{"t": 0, "rot": -35}, {"t": 0.5, "rot": 35}, {"t": 1.0, "rot": -35}],
                "right_leg":[{"t": 0, "rot": 35}, {"t": 0.5, "rot": -35}, {"t": 1.0, "rot": 35}],
                "tail":     [{"t": 0, "rot": -25}, {"t": 0.5, "rot": 25}, {"t": 1.0, "rot": -25}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.25, "scale_x": 0.85}, {"t": 0.5}, {"t": 0.75, "scale_x": 0.85}, {"t": 1.0}],
            }
        },
        "crawl": {
            "fps": 2, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 4}, {"t": 0.5, "y": 3}, {"t": 1.0, "y": 4}],
                "left_arm": [{"t": 0, "rot": -10, "y": 4}, {"t": 0.5, "rot": 10, "y": 4}, {"t": 1.0, "rot": -10, "y": 4}],
                "right_arm":[{"t": 0, "rot": 10, "y": 4}, {"t": 0.5, "rot": -10, "y": 4}, {"t": 1.0, "rot": 10, "y": 4}],
                "left_leg": [{"t": 0, "rot": -10}, {"t": 0.5, "rot": 10}, {"t": 1.0, "rot": -10}],
                "right_leg":[{"t": 0, "rot": 10}, {"t": 0.5, "rot": -10}, {"t": 1.0, "rot": 10}],
                "tail":     [{"t": 0, "rot": 5}, {"t": 1.0, "rot": 5}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0, "scale_x": 1.1}, {"t": 1.0, "scale_x": 1.1}],
            }
        },
        "carry": {
            "fps": 4, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.25, "y": -2}, {"t": 0.5, "y": 0}, {"t": 0.75, "y": -2}, {"t": 1.0, "y": 0}],
                "left_arm": [{"t": 0, "rot": -10}, {"t": 0.5, "rot": 10}, {"t": 1.0, "rot": -10}],
                "right_arm":[{"t": 0, "rot": -40}, {"t": 1.0, "rot": -40}],
                "left_leg": [{"t": 0, "rot": -15}, {"t": 0.5, "rot": 15}, {"t": 1.0, "rot": -15}],
                "right_leg":[{"t": 0, "rot": 15}, {"t": 0.5, "rot": -15}, {"t": 1.0, "rot": 15}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 1.0, "rot": 0}],
                "held_item":[{"t": 0, "y": -8, "x": 12}, {"t": 0.25, "y": -10, "x": 12}, {"t": 0.5, "y": -8, "x": 12}, {"t": 0.75, "y": -10, "x": 12}, {"t": 1.0, "y": -8, "x": 12}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 1.0}],
            }
        },
        "happy": {
            "fps": 3, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.3, "y": -6, "easing": "ease"}, {"t": 0.6, "y": 0}, {"t": 1.0, "y": 0}],
                "left_arm": [{"t": 0, "rot": 0}, {"t": 0.3, "rot": -30}, {"t": 1.0, "rot": 0}],
                "right_arm":[{"t": 0, "rot": 0}, {"t": 0.3, "rot": 30}, {"t": 1.0, "rot": 0}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 0.2, "rot": 20}, {"t": 0.4, "rot": -20}, {"t": 0.6, "rot": 20}, {"t": 0.8, "rot": -20}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0, "scale_y": 1.0}, {"t": 0.3, "scale_y": 1.3}, {"t": 1.0, "scale_y": 1.0}],
                "right_eye":[{"t": 0, "scale_y": 1.0}, {"t": 0.3, "scale_y": 1.3}, {"t": 1.0, "scale_y": 1.0}],
                "mouth":    [{"t": 0, "scale_x": 1.0}, {"t": 0.3, "scale_x": 1.4, "scale_y": 1.3}, {"t": 1.0, "scale_x": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.3, "scale_x": 0.85}, {"t": 1.0}],
            }
        },
        "sad": {
            "fps": 1, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 2}, {"t": 1.0, "y": 2}],
                "left_arm": [{"t": 0, "rot": 5}, {"t": 1.0, "rot": 5}],
                "right_arm":[{"t": 0, "rot": -5}, {"t": 1.0, "rot": -5}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": -5, "y": 3}, {"t": 1.0, "rot": -5, "y": 3}],
                "left_eye": [{"t": 0, "y": 1}, {"t": 1.0, "y": 1}],
                "right_eye":[{"t": 0, "y": 1}, {"t": 1.0, "y": 1}],
                "mouth":    [{"t": 0, "rot": 180}, {"t": 1.0, "rot": 180}],
                "shadow":   [{"t": 0, "scale_x": 1.05}, {"t": 1.0, "scale_x": 1.05}],
            }
        },
        "sleep": {
            "fps": 1, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 4}, {"t": 0.5, "y": 5, "easing": "ease"}, {"t": 1.0, "y": 4}],
                "left_arm": [{"t": 0, "rot": 8, "y": 4}, {"t": 1.0, "rot": 8, "y": 4}],
                "right_arm":[{"t": 0, "rot": -8, "y": 4}, {"t": 1.0, "rot": -8, "y": 4}],
                "left_leg": [{"t": 0, "y": 2}, {"t": 1.0, "y": 2}],
                "right_leg":[{"t": 0, "y": 2}, {"t": 1.0, "y": 2}],
                "tail":     [{"t": 0, "rot": 0, "y": 4}, {"t": 1.0, "rot": 0, "y": 4}],
                "left_eye": [{"t": 0, "opacity": 0}, {"t": 1.0, "opacity": 0}],
                "right_eye":[{"t": 0, "opacity": 0}, {"t": 1.0, "opacity": 0}],
                "mouth":    [{"t": 0, "scale_x": 0.6}, {"t": 0.5, "scale_x": 1.0}, {"t": 1.0, "scale_x": 0.6}],
                "shadow":   [{"t": 0, "scale_x": 1.1}, {"t": 1.0, "scale_x": 1.1}],
            }
        },
        "work": {
            "fps": 3, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 1.0, "y": 0}],
                "left_arm": [{"t": 0, "rot": -25, "y": -4}, {"t": 0.3, "rot": -15, "y": -2}, {"t": 0.6, "rot": -25, "y": -4}, {"t": 1.0, "rot": -25, "y": -4}],
                "right_arm":[{"t": 0, "rot": 25, "y": -4}, {"t": 0.4, "rot": 15, "y": -2}, {"t": 0.7, "rot": 25, "y": -4}, {"t": 1.0, "rot": 25, "y": -4}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 1.0}],
            }
        },
        "dance": {
            "fps": 5, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0, "rot": 0}, {"t": 0.25, "y": -5, "rot": 8}, {"t": 0.5, "y": 0, "rot": 0}, {"t": 0.75, "y": -5, "rot": -8}, {"t": 1.0, "y": 0, "rot": 0}],
                "left_arm": [{"t": 0, "rot": -45}, {"t": 0.25, "rot": 30}, {"t": 0.5, "rot": -45}, {"t": 0.75, "rot": 30}, {"t": 1.0, "rot": -45}],
                "right_arm":[{"t": 0, "rot": 45}, {"t": 0.25, "rot": -30}, {"t": 0.5, "rot": 45}, {"t": 0.75, "rot": -30}, {"t": 1.0, "rot": 45}],
                "left_leg": [{"t": 0, "rot": 0}, {"t": 0.25, "rot": 20}, {"t": 0.5, "rot": 0}, {"t": 0.75, "rot": -20}, {"t": 1.0, "rot": 0}],
                "right_leg":[{"t": 0, "rot": 0}, {"t": 0.25, "rot": -20}, {"t": 0.5, "rot": 0}, {"t": 0.75, "rot": 20}, {"t": 1.0, "rot": 0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 0.15, "rot": 25}, {"t": 0.35, "rot": -25}, {"t": 0.5, "rot": 25}, {"t": 0.65, "rot": -25}, {"t": 0.85, "rot": 25}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0, "scale_x": 1.2}, {"t": 1.0, "scale_x": 1.2}],
                "shadow":   [{"t": 0}, {"t": 0.25, "scale_x": 0.85}, {"t": 0.5}, {"t": 0.75, "scale_x": 0.85}, {"t": 1.0}],
            }
        },
        "excited": {
            "fps": 6, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.2, "y": -8}, {"t": 0.4, "y": 0}, {"t": 0.6, "y": -8}, {"t": 0.8, "y": 0}, {"t": 1.0, "y": 0}],
                "left_arm": [{"t": 0, "rot": -60}, {"t": 0.3, "rot": 20}, {"t": 0.6, "rot": -60}, {"t": 1.0, "rot": -60}],
                "right_arm":[{"t": 0, "rot": 60}, {"t": 0.3, "rot": -20}, {"t": 0.6, "rot": 60}, {"t": 1.0, "rot": 60}],
                "left_leg": [{"t": 0, "rot": -10}, {"t": 0.3, "rot": 10}, {"t": 0.6, "rot": -10}, {"t": 1.0, "rot": -10}],
                "right_leg":[{"t": 0, "rot": 10}, {"t": 0.3, "rot": -10}, {"t": 0.6, "rot": 10}, {"t": 1.0, "rot": 10}],
                "tail":     [{"t": 0, "rot": -20}, {"t": 0.15, "rot": 20}, {"t": 0.3, "rot": -20}, {"t": 0.45, "rot": 20}, {"t": 0.6, "rot": -20}, {"t": 0.75, "rot": 20}, {"t": 0.9, "rot": -20}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0, "scale_x": 1.2, "scale_y": 1.2}, {"t": 1.0, "scale_x": 1.2, "scale_y": 1.2}],
                "right_eye":[{"t": 0, "scale_x": 1.2, "scale_y": 1.2}, {"t": 1.0, "scale_x": 1.2, "scale_y": 1.2}],
                "mouth":    [{"t": 0, "scale_x": 1.3, "scale_y": 1.4}, {"t": 1.0, "scale_x": 1.3, "scale_y": 1.4}],
                "shadow":   [{"t": 0}, {"t": 0.2, "scale_x": 0.8}, {"t": 0.4}, {"t": 0.6, "scale_x": 0.8}, {"t": 1.0}],
            }
        },
        "yawn": {
            "fps": 2, "loop": False,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.5, "y": 2}, {"t": 1.0, "y": 0}],
                "left_arm": [{"t": 0, "rot": 0}, {"t": 0.3, "rot": -50}, {"t": 0.7, "rot": -50}, {"t": 1.0, "rot": 0}],
                "right_arm":[{"t": 0, "rot": 0}, {"t": 0.3, "rot": 50}, {"t": 0.7, "rot": 50}, {"t": 1.0, "rot": 0}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 0.5, "rot": -5}, {"t": 1.0, "rot": 0}],
                "mouth":    [{"t": 0, "scale_x": 1.0, "scale_y": 1.0}, {"t": 0.3, "scale_x": 1.8, "scale_y": 2.0}, {"t": 0.7, "scale_x": 1.8, "scale_y": 2.0}, {"t": 1.0, "scale_x": 1.0, "scale_y": 1.0}],
                "left_eye": [{"t": 0}, {"t": 0.2, "scale_y": 0.3}, {"t": 0.8, "scale_y": 0.3}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 0.2, "scale_y": 0.3}, {"t": 0.8, "scale_y": 0.3}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 1.0}],
            }
        },
        "stretch": {
            "fps": 2, "loop": False,
            "keyframes": {
                "body":     [{"t": 0, "y": 0, "scale_y": 1.0}, {"t": 0.5, "y": -4, "scale_y": 1.1}, {"t": 1.0, "y": 0, "scale_y": 1.0}],
                "left_arm": [{"t": 0, "rot": 0}, {"t": 0.3, "rot": -80}, {"t": 0.7, "rot": -80}, {"t": 1.0, "rot": 0}],
                "right_arm":[{"t": 0, "rot": 0}, {"t": 0.3, "rot": 80}, {"t": 0.7, "rot": 80}, {"t": 1.0, "rot": 0}],
                "left_leg": [{"t": 0}, {"t": 0.5, "y": 2}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 0.5, "y": 2}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 0.5, "rot": 15}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.5, "scale_x": 0.9}, {"t": 1.0}],
            }
        },
        "pray": {
            "fps": 2, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 2}, {"t": 0.5, "y": 4, "easing": "ease"}, {"t": 1.0, "y": 2}],
                "left_arm": [{"t": 0, "rot": 15, "x": 4}, {"t": 1.0, "rot": 15, "x": 4}],
                "right_arm":[{"t": 0, "rot": -15, "x": -4}, {"t": 1.0, "rot": -15, "x": -4}],
                "left_leg": [{"t": 0, "y": 2}, {"t": 1.0, "y": 2}],
                "right_leg":[{"t": 0, "y": 2}, {"t": 1.0, "y": 2}],
                "tail":     [{"t": 0}, {"t": 1.0}],
                "left_eye": [{"t": 0, "opacity": 0}, {"t": 1.0, "opacity": 0}],
                "right_eye":[{"t": 0, "opacity": 0}, {"t": 1.0, "opacity": 0}],
                "mouth":    [{"t": 0, "scale_x": 0.5}, {"t": 1.0, "scale_x": 0.5}],
                "shadow":   [{"t": 0}, {"t": 1.0}],
            }
        },
        "screenshot": {
            "fps": 4, "loop": False,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.3, "y": -3}, {"t": 0.5, "y": 0, "scale_x": 1.1, "scale_y": 0.9}, {"t": 0.7, "scale_x": 1.0, "scale_y": 1.0}, {"t": 1.0}],
                "left_arm": [{"t": 0, "rot": 0}, {"t": 0.2, "rot": -40}, {"t": 0.5, "rot": -20}, {"t": 1.0, "rot": 0}],
                "right_arm":[{"t": 0, "rot": 0}, {"t": 0.2, "rot": 40}, {"t": 0.5, "rot": 20}, {"t": 1.0, "rot": 0}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 0.3, "rot": 30}, {"t": 0.6, "rot": -10}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0, "scale_x": 1.0}, {"t": 0.3, "scale_x": 1.5, "scale_y": 1.5}, {"t": 0.6, "scale_x": 1.0, "scale_y": 1.0}, {"t": 1.0}],
                "right_eye":[{"t": 0, "scale_x": 1.0}, {"t": 0.3, "scale_x": 1.5, "scale_y": 1.5}, {"t": 0.6, "scale_x": 1.0, "scale_y": 1.0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 0.3, "scale_x": 1.5, "scale_y": 1.5}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.3, "scale_x": 0.9}, {"t": 1.0}],
            }
        },
        "notification": {
            "fps": 4, "loop": False,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.2, "y": -4}, {"t": 0.5, "y": 0}, {"t": 1.0}],
                "left_arm": [{"t": 0, "rot": 0}, {"t": 0.2, "rot": -25}, {"t": 0.5, "rot": 0}, {"t": 1.0}],
                "right_arm":[{"t": 0, "rot": 0}, {"t": 0.2, "rot": 25}, {"t": 0.5, "rot": 0}, {"t": 1.0}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 0.2, "rot": 20}, {"t": 0.5, "rot": -5}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0}, {"t": 0.1, "scale_y": 1.4}, {"t": 0.5, "scale_y": 1.0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 0.1, "scale_y": 1.4}, {"t": 0.5, "scale_y": 1.0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 0.1, "scale_x": 1.3}, {"t": 0.5}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.2, "scale_x": 0.88}, {"t": 1.0}],
            }
        },
        "music": {
            "fps": 4, "loop": True,
            "keyframes": {
                "body":     [{"t": 0, "y": 0, "rot": 0}, {"t": 0.25, "y": -3, "rot": 5}, {"t": 0.5, "y": 0, "rot": 0}, {"t": 0.75, "y": -3, "rot": -5}, {"t": 1.0, "y": 0, "rot": 0}],
                "left_arm": [{"t": 0, "rot": -20}, {"t": 0.25, "rot": 10}, {"t": 0.5, "rot": -20}, {"t": 0.75, "rot": 10}, {"t": 1.0, "rot": -20}],
                "right_arm":[{"t": 0, "rot": 20}, {"t": 0.25, "rot": -10}, {"t": 0.5, "rot": 20}, {"t": 0.75, "rot": -10}, {"t": 1.0, "rot": 20}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0, "rot": -15}, {"t": 0.25, "rot": 15}, {"t": 0.5, "rot": -15}, {"t": 0.75, "rot": 15}, {"t": 1.0, "rot": -15}],
                "left_eye": [{"t": 0, "scale_y": 0.7}, {"t": 1.0, "scale_y": 0.7}],
                "right_eye":[{"t": 0, "scale_y": 0.7}, {"t": 1.0, "scale_y": 0.7}],
                "mouth":    [{"t": 0, "scale_x": 1.1}, {"t": 1.0, "scale_x": 1.1}],
                "shadow":   [{"t": 0}, {"t": 0.25, "scale_x": 0.9}, {"t": 0.5}, {"t": 0.75, "scale_x": 0.9}, {"t": 1.0}],
            }
        },
        "level_up": {
            "fps": 5, "loop": False,
            "keyframes": {
                "body":     [{"t": 0, "y": 0}, {"t": 0.2, "y": -10}, {"t": 0.4, "y": -2}, {"t": 0.6, "y": -8}, {"t": 0.8, "y": 0}, {"t": 1.0}],
                "left_arm": [{"t": 0, "rot": 0}, {"t": 0.15, "rot": -90}, {"t": 0.5, "rot": -90}, {"t": 0.7, "rot": -30}, {"t": 1.0, "rot": 0}],
                "right_arm":[{"t": 0, "rot": 0}, {"t": 0.15, "rot": 90}, {"t": 0.5, "rot": 90}, {"t": 0.7, "rot": 30}, {"t": 1.0, "rot": 0}],
                "left_leg": [{"t": 0, "rot": 0}, {"t": 0.2, "rot": -15}, {"t": 0.5, "rot": 15}, {"t": 1.0, "rot": 0}],
                "right_leg":[{"t": 0, "rot": 0}, {"t": 0.2, "rot": 15}, {"t": 0.5, "rot": -15}, {"t": 1.0, "rot": 0}],
                "tail":     [{"t": 0, "rot": 0}, {"t": 0.2, "rot": 30}, {"t": 0.5, "rot": -30}, {"t": 0.8, "rot": 15}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0}, {"t": 0.2, "scale_x": 1.4, "scale_y": 1.4}, {"t": 0.6, "scale_x": 1.4, "scale_y": 1.4}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 0.2, "scale_x": 1.4, "scale_y": 1.4}, {"t": 0.6, "scale_x": 1.4, "scale_y": 1.4}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 0.2, "scale_x": 1.5, "scale_y": 1.5}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.2, "scale_x": 0.75}, {"t": 0.6, "scale_x": 0.8}, {"t": 1.0}],
            }
        },
        "startup": {
            "fps": 3, "loop": False,
            "keyframes": {
                "body":     [{"t": 0, "y": 10, "opacity": 0}, {"t": 0.3, "y": 0, "opacity": 1.0, "easing": "ease"}, {"t": 0.6, "y": -5}, {"t": 1.0, "y": 0}],
                "left_arm": [{"t": 0, "rot": 0, "opacity": 0}, {"t": 0.4, "rot": -30, "opacity": 1.0}, {"t": 0.7, "rot": 0}, {"t": 1.0}],
                "right_arm":[{"t": 0, "rot": 0, "opacity": 0}, {"t": 0.4, "rot": 30, "opacity": 1.0}, {"t": 0.7, "rot": 0}, {"t": 1.0}],
                "left_leg": [{"t": 0, "opacity": 0}, {"t": 0.3, "opacity": 1.0}, {"t": 1.0}],
                "right_leg":[{"t": 0, "opacity": 0}, {"t": 0.3, "opacity": 1.0}, {"t": 1.0}],
                "tail":     [{"t": 0, "opacity": 0}, {"t": 0.3, "opacity": 1.0}, {"t": 0.5, "rot": 15}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0, "opacity": 0}, {"t": 0.4, "opacity": 1.0}, {"t": 1.0}],
                "right_eye":[{"t": 0, "opacity": 0}, {"t": 0.4, "opacity": 1.0}, {"t": 1.0}],
                "mouth":    [{"t": 0, "opacity": 0}, {"t": 0.4, "opacity": 1.0}, {"t": 1.0}],
                "shadow":   [{"t": 0, "opacity": 0}, {"t": 0.3, "opacity": 1.0}, {"t": 1.0}],
            }
        },
        "shutdown": {
            "fps": 2, "loop": False,
            "keyframes": {
                "body":     [{"t": 0}, {"t": 0.5, "y": 5}, {"t": 1.0, "y": 10, "opacity": 0, "easing": "ease"}],
                "left_arm": [{"t": 0}, {"t": 0.5, "rot": 10}, {"t": 1.0, "opacity": 0}],
                "right_arm":[{"t": 0}, {"t": 0.5, "rot": -10}, {"t": 1.0, "opacity": 0}],
                "left_leg": [{"t": 0}, {"t": 1.0, "opacity": 0}],
                "right_leg":[{"t": 0}, {"t": 1.0, "opacity": 0}],
                "tail":     [{"t": 0}, {"t": 1.0, "opacity": 0}],
                "left_eye": [{"t": 0}, {"t": 0.3, "scale_y": 0.1}, {"t": 1.0, "opacity": 0}],
                "right_eye":[{"t": 0}, {"t": 0.3, "scale_y": 0.1}, {"t": 1.0, "opacity": 0}],
                "mouth":    [{"t": 0}, {"t": 1.0, "opacity": 0}],
                "shadow":   [{"t": 0}, {"t": 1.0, "opacity": 0}],
            }
        },
        "restart": {
            "fps": 4, "loop": False,
            "keyframes": {
                "body":     [{"t": 0}, {"t": 0.3, "rot": 360}, {"t": 0.6, "rot": 720}, {"t": 1.0, "rot": 0}],
                "left_arm": [{"t": 0}, {"t": 0.3, "rot": -45}, {"t": 0.6, "rot": 0}, {"t": 1.0}],
                "right_arm":[{"t": 0}, {"t": 0.3, "rot": 45}, {"t": 0.6, "rot": 0}, {"t": 1.0}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0}, {"t": 0.5, "rot": 20}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 1.0}],
            }
        },
        "run_app": {
            "fps": 4, "loop": False,
            "keyframes": {
                "body":     [{"t": 0}, {"t": 0.3, "y": -4}, {"t": 0.6, "y": 0}, {"t": 1.0}],
                "left_arm": [{"t": 0, "rot": 0}, {"t": 0.2, "rot": -60}, {"t": 0.5, "rot": 0}, {"t": 1.0}],
                "right_arm":[{"t": 0, "rot": 0}, {"t": 0.2, "rot": 60}, {"t": 0.5, "rot": 0}, {"t": 1.0}],
                "left_leg": [{"t": 0}, {"t": 1.0}],
                "right_leg":[{"t": 0}, {"t": 1.0}],
                "tail":     [{"t": 0}, {"t": 0.3, "rot": 15}, {"t": 1.0, "rot": 0}],
                "left_eye": [{"t": 0}, {"t": 1.0}],
                "right_eye":[{"t": 0}, {"t": 1.0}],
                "mouth":    [{"t": 0}, {"t": 1.0}],
                "shadow":   [{"t": 0}, {"t": 0.3, "scale_x": 0.9}, {"t": 1.0}],
            }
        },
    }
    with open(anim_path, "w", encoding="utf-8") as f:
        json.dump(animations, f, indent=2)
    log.info("Wrote pet_animations.json (%d animations)", len(animations))
