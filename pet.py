import os
import math
import struct
import wave
from PIL import Image, ImageDraw, ImageFilter, ImageColor

# ----------------------------------------------------------------
#  PRO-GRADE CLAYMATION SHADING ENGINE
# ----------------------------------------------------------------

def get_rgba(hex_color, alpha=255):
    rgb = ImageColor.getrgb(hex_color)
    return (*rgb, alpha)

def draw_shiny_black_limb(draw, x, y, size_w=16, size_h=18):
    """Draws a glossy black arm or leg to match the clay/vinyl toy style."""
    bbox = [x, y, x + size_w, y + size_h]
    # Base black limb
    draw.ellipse(bbox, fill='#151515')
    
    # Tiny bright specular highlight for the plastic shine
    hl_w, hl_h = size_w * 0.3, size_h * 0.3
    hl_bbox = [x + size_w * 0.2, y + size_h * 0.15, x + size_w * 0.2 + hl_w, y + size_h * 0.15 + hl_h]
    draw.ellipse(hl_bbox, fill=(255, 255, 255, 180))

def draw_aaa_3d_body(draw, bbox, base_hex_color):
    """
    Matte 3D shading: Smooth radial gradients for a solid, clay-like feel.
    """
    base_rgb = ImageColor.getrgb(base_hex_color)
    steps = 40 
    
    x0, y0, x1, y1 = bbox
    w = x1 - x0
    h = y1 - y0
    
    light_cx = x0 + w * 0.35
    light_cy = y0 + h * 0.30
    
    for i in range(steps):
        t = i / steps
        # Softer color math for a matte look
        r = min(255, max(0, int(base_rgb[0] * (0.4 + 1.0 * t))))
        g = min(255, max(0, int(base_rgb[1] * (0.4 + 1.0 * t))))
        b = min(255, max(0, int(base_rgb[2] * (0.4 + 1.0 * t))))
        
        curr_x0 = x0 * (1 - t) + light_cx * t
        curr_y0 = y0 * (1 - t) + light_cy * t
        curr_x1 = x1 * (1 - t) + light_cx * t
        curr_y1 = y1 * (1 - t) + light_cy * t
        
        draw.ellipse([curr_x0, curr_y0, curr_x1, curr_y1], fill=(r, g, b, 255))

    # Soft Rim Light (bounce light from the ground)
    rim_bbox = [x0 + 4, y0 + 4, x1, y1]
    draw.arc(rim_bbox, 10, 80, fill=(255, 255, 255, 70), width=3)

# ----------------------------------------------------------------
#  FRAME GENERATOR
# ----------------------------------------------------------------

def make_frame(state, x_offset=0, y_offset=0):
    img = Image.new('RGBA', (120, 120), (0, 0, 0, 0)) # Expanded canvas slightly for limbs
    glow_layer = Image.new('RGBA', (120, 120), (0, 0, 0, 0))
    
    draw = ImageDraw.Draw(img)
    glow_draw = ImageDraw.Draw(glow_layer)
    
    # 1. --- STATE CONFIGURATION ---
    # Centered slightly differently to account for the 120x120 canvas
    body_color = '#2EBA54' # Slightly brighter, toy-like green
    glow_color = None
    body_bbox = [30 + x_offset, 40 + y_offset, 90 + x_offset, 100 + y_offset]
    
    # Hand and Foot default positions
    lx, ly = 35 + x_offset, 90 + y_offset   # Left foot
    rx, ry = 65 + x_offset, 90 + y_offset   # Right foot
    lhx, lhy = 15 + x_offset, 65 + y_offset # Left hand
    rhx, rhy = 85 + x_offset, 65 + y_offset # Right hand

    if 'sleep' in state or 'crawl' in state:
        body_bbox = [20 + x_offset, 65 + y_offset, 100 + x_offset, 100 + y_offset]
        ly, ry = 90 + y_offset, 90 + y_offset
        lhy, rhy = 80 + y_offset, 80 + y_offset
    elif 'run' in state:
        body_bbox = [25 + x_offset, 45 + y_offset, 95 + x_offset, 95 + y_offset]
        # Extreme arm/leg swing based on x_offset
        ly -= x_offset * 0.8
        ry += x_offset * 0.8
        lhy += x_offset * 1.0
        rhy -= x_offset * 1.0
    elif 'walk' in state:
        # Subtle arm/leg swing based on x_offset
        ly -= x_offset * 0.4
        ry += x_offset * 0.4
        lhy += x_offset * 0.5
        rhy -= x_offset * 0.5
    elif state in ['dance', 'excited', 'level_up', 'startup', 'notification']:
        # Hands thrown up in the air!
        lhy -= 20
        rhy -= 20
        lhx -= 5
        rhx += 5
    elif state in ['sad', 'shutdown']:
        body_color = '#5F9EA0'
        # Arms drooping down
        lhy += 15
        rhy += 15
        lhx += 5
        rhx -= 5
    elif state == 'pray':
        body_color = '#1A7A4C'
        glow_color = '#A8E6CF'
        # Hands together in front
        lhx, lhy = 48 + x_offset, 80 + y_offset
        rhx, rhy = 56 + x_offset, 80 + y_offset
    elif state == 'music_listen' or state == 'play_music':
        # One hand up holding headphones, one hand down
        lhy -= 10
        lhx += 5
        rhy += 10
        
    # --- Color overrides ---
    if state == 'dance' or state == 'level_up': body_color = '#FFD700'; glow_color = '#FFEA70'
    elif state == 'music_listen': body_color = '#9B59B6'
    elif state == 'excited': body_color = '#FF6347'
    elif state == 'screenshot': body_color = '#00BCD4'; glow_color = '#E0F7FA'
    elif state == 'notification': body_color = '#FF9800'; glow_color = '#FFE0B2'
    elif state == 'play_music': body_color = '#E91E63'; glow_color = '#F8BBD0'
    elif state == 'restart': body_color = '#2196F3'; glow_color = '#BBDEFB'
    elif state == 'startup': body_color = '#4CAF50'; glow_color = '#C8E6C9'
    elif state == 'run_app': body_color = '#3F51B5'; glow_color = '#C5CAE9'

    # 2. --- ADVANCED GROUND SHADOWS ---
    shadow_width = (body_bbox[2] - body_bbox[0]) * 0.9
    shadow_x_center = (body_bbox[0] + body_bbox[2]) / 2
    shadow_shrink = max(0, -y_offset * 0.5) 
    
    # Soft wide shadow
    wide_shadow_bbox = [
        shadow_x_center - (shadow_width / 2) + shadow_shrink,
        96, shadow_x_center + (shadow_width / 2) - shadow_shrink, 106
    ]
    draw.ellipse(wide_shadow_bbox, fill=(0, 0, 0, 35))

    # Ambient Occlusion
    if y_offset >= -2: 
        ao_width = shadow_width * 0.5
        ao_bbox = [shadow_x_center - (ao_width / 2), 98, shadow_x_center + (ao_width / 2), 103]
        draw.ellipse(ao_bbox, fill=(0, 0, 0, 80))

    # 3. --- GLOW EFFECTS ---
    if glow_color:
        gb_box = [body_bbox[0]-8, body_bbox[1]-8, body_bbox[2]+8, body_bbox[3]+8]
        glow_draw.ellipse(gb_box, fill=get_rgba(glow_color, 120))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=8))
        img.alpha_composite(glow_layer)

    # 4. --- DRAW LEGS (Behind body) ---
    draw_shiny_black_limb(draw, lx, ly)
    draw_shiny_black_limb(draw, rx, ry)

    # 5. --- DRAW CLAY BODY ---
    draw_aaa_3d_body(draw, body_bbox, body_color)
    
    # Soft Specular Highlight (The matte clay reflection)
    hl_width = (body_bbox[2] - body_bbox[0]) * 0.25
    hl_height = (body_bbox[3] - body_bbox[1]) * 0.15
    hl_bbox = [body_bbox[0] + 12, body_bbox[1] + 10, body_bbox[0] + 12 + hl_width, body_bbox[1] + 10 + hl_height]
    draw.ellipse(hl_bbox, fill=(255, 255, 255, 80))

    # 6. --- DRAW ARMS (In front of body) ---
    draw_shiny_black_limb(draw, lhx, lhy, size_w=14, size_h=16) # Arms slightly smaller than legs
    draw_shiny_black_limb(draw, rhx, rhy, size_w=14, size_h=16)


    # 7. --- DRAW FACIAL FEATURES ---
    
    # Permanent Toy Blush
    blush_y = 75 + y_offset
    draw.ellipse([42 + x_offset, blush_y, 50 + x_offset, blush_y + 6], fill='#D47C7C')
    draw.ellipse([70 + x_offset, blush_y, 78 + x_offset, blush_y + 6], fill='#D47C7C')

    # Eyes & Mouths
    if state in ['idle', 'walk_left', 'walk_right', 'run_left', 'run_right',
                 'crawl_left', 'crawl_right', 'yawn', 'stretch']:
        draw.ellipse([48 + x_offset, 60 + y_offset, 54 + x_offset, 72 + y_offset], fill='black')
        draw.ellipse([66 + x_offset, 60 + y_offset, 72 + x_offset, 72 + y_offset], fill='black')
        draw.arc([52 + x_offset, 72 + y_offset, 68 + x_offset, 82 + y_offset], 0, 180, fill='black', width=3)
        
        # Action lines for running
        if 'run' in state:
            draw.arc([15 + x_offset, 40 + y_offset, 35 + x_offset, 60 + y_offset], 90, 180, fill='black', width=2)
            draw.arc([85 + x_offset, 40 + y_offset, 105 + x_offset, 60 + y_offset], 0, 90, fill='black', width=2)

    elif state in ['smile', 'dance', 'excited', 'level_up', 'startup', 'play_music']:
        # Happy closed curve eyes
        draw.arc([46 + x_offset, 62 + y_offset, 54 + x_offset, 70 + y_offset], 180, 0, fill='black', width=3)
        draw.arc([66 + x_offset, 62 + y_offset, 74 + x_offset, 70 + y_offset], 180, 0, fill='black', width=3)
        # Big open mouth
        draw.chord([50 + x_offset, 70 + y_offset, 70 + x_offset, 88 + y_offset], 0, 180, fill='black')
        draw.chord([54 + x_offset, 78 + y_offset, 66 + x_offset, 88 + y_offset], 0, 180, fill='#D32F2F') # Tongue
        
        # Floating elements
        if state == 'dance' or state == 'play_music':
            draw.line([25 + x_offset, 30 + y_offset, 25 + x_offset, 40 + y_offset], fill='black', width=3)
            draw.ellipse([22 + x_offset, 38 + y_offset, 28 + x_offset, 44 + y_offset], fill='black')
            draw.line([95 + x_offset, 35 + y_offset, 95 + x_offset, 45 + y_offset], fill='black', width=3)
            draw.ellipse([92 + x_offset, 43 + y_offset, 98 + x_offset, 49 + y_offset], fill='black')

    elif state in ['sad', 'shutdown']:
        # Sad eyes
        draw.arc([46 + x_offset, 62 + y_offset, 54 + x_offset, 70 + y_offset], 0, 180, fill='black', width=3)
        draw.arc([66 + x_offset, 62 + y_offset, 74 + x_offset, 70 + y_offset], 0, 180, fill='black', width=3)
        # Sad mouth
        draw.arc([52 + x_offset, 78 + y_offset, 68 + x_offset, 86 + y_offset], 180, 0, fill='black', width=3)

    elif state == 'notification':
        # Wide alert eyes
        draw.ellipse([46 + x_offset, 58 + y_offset, 56 + x_offset, 72 + y_offset], fill='black')
        draw.ellipse([64 + x_offset, 58 + y_offset, 74 + x_offset, 72 + y_offset], fill='black')
        draw.ellipse([50 + x_offset, 60 + y_offset, 54 + x_offset, 64 + y_offset], fill='white')
        draw.ellipse([68 + x_offset, 60 + y_offset, 72 + x_offset, 64 + y_offset], fill='white')
        # Little 'o' mouth
        draw.ellipse([56 + x_offset, 76 + y_offset, 64 + x_offset, 84 + y_offset], fill='black')
        # Exclamation marks
        draw.line([85 + x_offset, 25 + y_offset, 85 + x_offset, 40 + y_offset], fill='#111', width=4)
        draw.ellipse([82 + x_offset, 45 + y_offset, 88 + x_offset, 51 + y_offset], fill='#111')

    elif state == 'restart':
        # Swirly dizzy eyes
        draw.arc([44 + x_offset, 60 + y_offset, 56 + x_offset, 72 + y_offset], 0, 300, fill='black', width=2)
        draw.arc([46 + x_offset, 62 + y_offset, 54 + x_offset, 70 + y_offset], 0, 300, fill='black', width=2)
        draw.arc([64 + x_offset, 60 + y_offset, 76 + x_offset, 72 + y_offset], 0, 300, fill='black', width=2)
        draw.arc([66 + x_offset, 62 + y_offset, 74 + x_offset, 70 + y_offset], 0, 300, fill='black', width=2)
        draw.ellipse([54 + x_offset, 76 + y_offset, 66 + x_offset, 86 + y_offset], fill='black')

    # [Note: I have kept the core structure tight to ensure it generates cleanly without breaking the logic.]
    
    # Catch-all for simple closed eyes (Pray, sleep)
    elif state in ['pray', 'sleep']:
        draw.line([46 + x_offset, 68 + y_offset, 56 + x_offset, 68 + y_offset], fill='black', width=3)
        draw.line([64 + x_offset, 68 + y_offset, 74 + x_offset, 68 + y_offset], fill='black', width=3)
        if state == 'sleep':
            z_x, z_y = 85 + x_offset, 45 + y_offset - (x_offset * 2) 
            draw.line([z_x, z_y, z_x+10, z_y, z_x, z_y+10, z_x+10, z_y+10], fill='#111', width=2)

    return img

# ----------------------------------------------------------------
#  ANIMATION CURVES & EXPORT
# ----------------------------------------------------------------

def save_gif(filename, frames, duration=40):
    filepath = os.path.join('assets', filename)
    frames[0].save(filepath, save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, disposal=2, transparency=0)

def anim_breathe(state, frames=24, intensity=3):
    return [make_frame(state, x_offset=0, y_offset=int(-intensity * math.sin(math.pi * (i / frames)))) for i in range(frames)]

def anim_walk(state, frames=16, move_x=10, bounce_y=5):
    return [make_frame(state, x_offset=int(move_x * math.sin(2 * math.pi * (i / frames))), 
                       y_offset=int(-bounce_y * abs(math.sin(2 * math.pi * (i / frames))))) for i in range(frames)]

def anim_jump(state, frames=20, height=12):
    return [make_frame(state, x_offset=0, y_offset=int(-height * math.sin(math.pi * (i / frames)))) for i in range(frames)]

def anim_dance(state, frames=24, move_x=6, move_y=4):
    return [make_frame(state, x_offset=int(move_x * math.sin(2 * math.pi * (i / frames))), 
                       y_offset=int(-move_y * abs(math.cos(2 * math.pi * (i / frames))))) for i in range(frames)]

# ----------------------------------------------------------------
#  EXECUTION
# ----------------------------------------------------------------
if not os.path.exists('assets'):
    os.makedirs('assets')

# ── NEW: Generate sprite sheet and atlas (preferred pipeline) ──
print("Generating sprite sheet assets (skin-based)...")
from core.sprite_engine import generate_skin_assets, get_available_skins
skin_id = "default"
if generate_skin_assets(skin_id, force=True):
    print(f"  Sprite sheet generated for skin '{skin_id}'.")
else:
    print("  WARNING: sprite sheet generation failed, falling back to GIFs.")

# ── LEGACY: Generate GIFs (deprecated — kept for GIF-fallback mode) ──
print("Generating Claymation-Style GIFs (legacy fallback)...")

# --- CORE STATES ---
save_gif('idle.gif', anim_breathe('idle', frames=24, intensity=3), duration=40)
save_gif('smile.gif', anim_breathe('smile', frames=24, intensity=3), duration=40)
save_gif('work.gif', anim_breathe('work', frames=24, intensity=2), duration=40)
save_gif('sleep.gif', anim_breathe('sleep', frames=40, intensity=4), duration=50)

# --- IDLE VARIATIONS ---
save_gif('yawn.gif', anim_breathe('yawn', frames=30, intensity=5), duration=40)
save_gif('sad.gif', anim_breathe('sad', frames=24, intensity=1), duration=50)
save_gif('stretch.gif', anim_jump('stretch', frames=24, height=7), duration=40)

# --- LOCOMOTION ---
save_gif('walk_right.gif', anim_walk('walk_right', frames=16, move_x=8, bounce_y=5), duration=40)
save_gif('walk_left.gif',  anim_walk('walk_left', frames=16, move_x=-8, bounce_y=5), duration=40)
save_gif('run_right.gif',  anim_walk('run_right', frames=12, move_x=16, bounce_y=7), duration=30)
save_gif('run_left.gif',   anim_walk('run_left', frames=12, move_x=-16, bounce_y=7), duration=30)
save_gif('crawl_right.gif', anim_walk('crawl_right', frames=24, move_x=6, bounce_y=2), duration=40)
save_gif('crawl_left.gif',  anim_walk('crawl_left', frames=24, move_x=-6, bounce_y=2), duration=40)

# --- ACTIONS & EMOTIONS ---
save_gif('dance.gif', anim_dance('dance', frames=24, move_x=8, move_y=6), duration=30)
save_gif('excited.gif', anim_dance('excited', frames=16, move_x=5, move_y=8), duration=30)
save_gif('level_up.gif', anim_jump('level_up', frames=24, height=14), duration=35)
save_gif('music_listen.gif', anim_dance('music_listen', frames=30, move_x=4, move_y=3), duration=40)
save_gif('pray.gif', anim_breathe('pray', frames=40, intensity=2), duration=50)

# --- NEW ACTION GIFS (v6) ---
save_gif('screenshot.gif', anim_jump('screenshot', frames=12, height=6), duration=40)
save_gif('notification.gif', anim_dance('notification', frames=16, move_x=5, move_y=6), duration=35)
save_gif('play_music.gif', anim_dance('play_music', frames=24, move_x=7, move_y=5), duration=30)
save_gif('shutdown.gif', anim_breathe('shutdown', frames=30, intensity=6), duration=60)
save_gif('restart.gif', anim_dance('restart', frames=20, move_x=8, move_y=4), duration=35)
save_gif('startup.gif', anim_jump('startup', frames=20, height=14), duration=40)
save_gif('run_app.gif', anim_jump('run_app', frames=16, height=10), duration=35)

# ----------------------------------------------------------------
#  GENERATE TASBEH / PRAYER ALERT SOUND (.wav)
# ----------------------------------------------------------------
def generate_tasbeh_wav(filepath, sample_rate=44100):
    def sine_tone(freq, duration, volume=0.5, fade_out=True):
        n_samples = int(sample_rate * duration)
        samples = []
        for i in range(n_samples):
            t = i / sample_rate
            val = volume * (
                0.7 * math.sin(2 * math.pi * freq * t) +
                0.2 * math.sin(2 * math.pi * freq * 2 * t) +
                0.1 * math.sin(2 * math.pi * freq * 3 * t)
            )
            if fade_out:
                envelope = 1.0 - (i / n_samples) ** 0.5
                val *= envelope
            if i < n_samples * 0.05:
                val *= i / (n_samples * 0.05)
            samples.append(val)
        return samples

    all_samples = []
    chime_sets = [
        (523.25, 0.6), (659.25, 0.6), (783.99, 0.9), (0, 0.4),
        (783.99, 0.5), (659.25, 0.5), (523.25, 1.2), (0, 0.3),
        (587.33, 0.5), (698.46, 0.5), (880.00, 1.5),
    ]

    for freq, dur in chime_sets:
        if freq == 0:
            all_samples.extend([0.0] * int(sample_rate * dur))
        else:
            all_samples.extend(sine_tone(freq, dur, volume=0.45))

    if all_samples:
        max_val = max(abs(s) for s in all_samples) or 1
        all_samples = [s / max_val * 0.8 for s in all_samples]

    raw = b''.join(struct.pack('<h', int(s * 32767)) for s in all_samples)

    with wave.open(filepath, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)

tasbeh_path = os.path.join('assets', 'tasbeh_alert.wav')
if not os.path.exists(tasbeh_path):
    print("Generating tasbeh prayer alert sound...")
    generate_tasbeh_wav(tasbeh_path)
else:
    print("tasbeh_alert.wav already exists, skipping.")

print("Done! Sprite sheet is the primary renderer. GIFs are legacy fallback.")