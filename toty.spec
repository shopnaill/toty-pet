# -*- mode: python ; coding: utf-8 -*-
"""
Toty Desktop Pet — PyInstaller spec file.

Build with:
    pyinstaller toty.spec
"""

import os
import sys

block_cipher = None

# ── Paths ─────────────────────────────────────────────────────────
ROOT = os.path.abspath(".")

# Collect all data files that need to ship with the exe
datas = [
    ("assets", "assets"),
    ("core", "core"),
    ("features", "features"),
    ("input", "input"),
    ("media", "media"),
]

# Add server_bridge if it exists
if os.path.isfile(os.path.join(ROOT, "server_bridge.py")):
    datas.append(("server_bridge.py", "."))

# ── Hidden imports ────────────────────────────────────────────────
# Modules imported dynamically or inside functions
hiddenimports = [
    # Core + input + media
    "core", "core.sprite_engine", "core.settings", "core.stats",
    "core.achievements", "core.mood", "core.speech", "core.safe_json",
    "input", "input.keyboard", "input.combo",
    "media", "media.controller", "media.detector", "media.scheduler",

    # Third-party
    "PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
    "PyQt6.sip",
    "pynput", "pynput.keyboard", "pynput.mouse",
    "pygetwindow",
    "psutil",
    "PIL", "PIL.Image",
    "sounddevice",
    "numpy",
    "qrcode",
    "speech_recognition",
    "pystray",
    "winsound",
    "winreg",
    "ctypes",
    "sqlite3",
    "json",
    "xml.etree.ElementTree",
]

# ── Analysis ──────────────────────────────────────────────────────
a = Analysis(
    ["animals.py"],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy optional deps — not bundled (user installs separately)
        "torch", "torchaudio", "demucs",
        "onnxruntime",
        "tensorflow", "keras",
        "matplotlib", "scipy",
        "IPython", "notebook", "jupyter",
        "tkinter",
        # Not used by app — saves ~110 MB
        "numba", "llvmlite",
        "pandas",
        "lxml",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── Bundle ────────────────────────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Toty",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # GUI app — no console window
    disable_windowed_traceback=False,
    icon="assets/toty_archive.ico",
    version="version_info.py",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Toty",
)
