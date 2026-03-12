# Toty Skin System

## Overview
Skins customize how Toty looks — body color, limb style, face features, and per-state color tinting.

Each skin lives in its own folder under `assets/skins/<skin_id>/` and contains a `skin.json` file.

## Creating a New Skin

1. Create a folder: `assets/skins/my_skin/`
2. Add a `skin.json` file using the schema below
3. The skin automatically appears in right-click → Skins menu

## skin.json Schema

```json
{
  "name": "Display Name",
  "author": "Your Name",
  "description": "Short description",

  "body": {
    "color": "#HEX",          // Main body color
    "width": 60,               // Body ellipse width (px)
    "height": 60,              // Body ellipse height (px)
    "shading_steps": 40,       // Gradient quality (10-60)
    "specular_alpha": 80,      // Highlight brightness (0-255)
    "rim_light": true           // Edge highlight on/off
  },

  "limbs": {
    "color": "#151515",        // Arm/leg color
    "highlight_alpha": 180,    // Limb specular (0-255)
    "arm_w": 14, "arm_h": 16, // Arm dimensions
    "leg_w": 16, "leg_h": 18  // Leg dimensions
  },

  "face": {
    "eye_color": "#000000",
    "eye_w": 7, "eye_h": 12,
    "eye_spacing": 18,         // Distance between eyes
    "mouth_width": 16,
    "blush_color": "#D47C7C",
    "blush_alpha": 200,
    "blush_size": 8
  },

  "effects": {
    "shadow_alpha": 35,
    "shadow_ao_alpha": 80,
    "glow_alpha": 120,
    "glow_blur": 8
  },

  "state_colors": {
    "idle":     { "body": "#2EBA54" },
    "dance":    { "body": "#FFD700", "glow": "#FFEA70" },
    "sad":      { "body": "#5F9EA0" },
    "pray":     { "body": "#1A7A4C", "glow": "#A8E6CF" }
  }
}
```

### State Colors
The `state_colors` dict maps animation state names to body tint colors.
At runtime, the body part is tinted toward the specified color (35% blend).

Available states: `idle`, `walk`, `run`, `work`, `happy`, `dance`, `excited`,
`sad`, `sleep`, `pray`, `music`, `screenshot`, `notification`, `level_up`,
`startup`, `shutdown`, `restart`, `run_app`, `yawn`, `stretch`.

## Included Skins

| ID | Name | Description |
|----|------|-------------|
| `default` | Toty Classic | Original claymation green toy |
| `ocean` | Ocean Wave | Deep-sea teal theme |
| `sunset` | Sunset Blaze | Warm orange-red glow |

## Caching
Sprite sheets are cached based on a SHA-256 hash of `skin.json`.
Editing the JSON will trigger automatic regeneration on next load.
To force regeneration, delete `assets/pet_sheet.png`.
