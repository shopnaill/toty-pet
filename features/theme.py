"""
Toty Pro Dark Theme — centralised design system.

Matches the Toty website aesthetic: deep dark backgrounds, green (#4ADE80)
primary accent, modern rounded corners, subtle glow effects.

Usage
─────
  from features.theme import THEME_QSS, C
  app.setStyleSheet(THEME_QSS)          # once at startup
  label.setStyleSheet(f"color: {C.ACCENT};")  # ad-hoc override
"""


# ── Colour palette (mirrors website CSS variables) ─────────────────
class C:
    """Toty colour constants."""
    BG_DEEP     = "#070B09"
    BG_DARK     = "#0D1411"
    BG_CARD     = "#131C17"
    BG_HOVER    = "#192520"
    SURFACE     = "#1E2B23"
    BORDER      = "#1C3A2A"
    BORDER_HI   = "#2D5E42"

    ACCENT      = "#4ADE80"      # primary green
    ACCENT_DIM  = "#1A4D32"
    ACCENT_GLOW = "rgba(74,222,128,0.25)"
    ACCENT_PRESS = "#38B866"

    AMBER       = "#FBBF24"
    RED         = "#F87171"
    BLUE        = "#34D399"
    PURPLE      = "#A78BFA"

    TEXT        = "#D1D5DB"
    TEXT_DIM    = "#6B7280"
    TEXT_BRIGHT = "#FFFFFF"

    RADIUS      = "10px"
    RADIUS_SM   = "6px"
    RADIUS_XS   = "4px"


# ── Global QSS ────────────────────────────────────────────────────
THEME_QSS = f"""
/* ─── Base ─────────────────────────────── */
QDialog, QMainWindow, QWidget#central {{
    background: {C.BG_DEEP};
    color: {C.TEXT};
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 13px;
}}

/* ─── Labels ───────────────────────────── */
QLabel {{
    color: {C.TEXT};
    background: transparent;
}}

/* ─── Buttons ──────────────────────────── */
QPushButton {{
    background: {C.SURFACE};
    color: {C.TEXT};
    border: 1px solid {C.BORDER};
    border-radius: {C.RADIUS_SM};
    padding: 7px 18px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {C.BG_HOVER};
    border-color: {C.ACCENT};
    color: {C.ACCENT};
}}
QPushButton:pressed {{
    background: {C.ACCENT_DIM};
    border-color: {C.ACCENT};
    color: {C.ACCENT};
}}
QPushButton:disabled {{
    background: {C.BG_CARD};
    color: {C.TEXT_DIM};
    border-color: {C.BORDER};
}}

/* ── Primary button (objectName = "primary") */
QPushButton#primary {{
    background: {C.ACCENT};
    color: {C.BG_DEEP};
    border: none;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: {C.ACCENT_PRESS};
    color: {C.BG_DEEP};
}}
QPushButton#primary:pressed {{
    background: #2EA55A;
    color: {C.BG_DEEP};
}}

/* ── Danger button (objectName = "danger") */
QPushButton#danger {{
    background: transparent;
    color: {C.RED};
    border: 1px solid {C.RED};
}}
QPushButton#danger:hover {{
    background: rgba(248,113,113,0.12);
}}

/* ─── Inputs ───────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background: {C.BG_CARD};
    color: {C.TEXT};
    border: 1px solid {C.BORDER};
    border-radius: {C.RADIUS_SM};
    padding: 6px 10px;
    selection-background-color: {C.ACCENT_DIM};
    selection-color: {C.ACCENT};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border-color: {C.ACCENT};
}}

/* ─── Spin boxes ───────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background: {C.BG_CARD};
    color: {C.TEXT};
    border: 1px solid {C.BORDER};
    border-radius: {C.RADIUS_SM};
    padding: 4px 8px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {C.ACCENT};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: {C.SURFACE};
    border: none;
    width: 18px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {C.BG_HOVER};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {C.TEXT_DIM};
    width: 0; height: 0;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {C.TEXT_DIM};
    width: 0; height: 0;
}}

/* ─── Combo boxes ──────────────────────── */
QComboBox {{
    background: {C.BG_CARD};
    color: {C.TEXT};
    border: 1px solid {C.BORDER};
    border-radius: {C.RADIUS_SM};
    padding: 5px 10px;
    min-width: 100px;
}}
QComboBox:hover {{
    border-color: {C.ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {C.TEXT_DIM};
    width: 0; height: 0;
}}
QComboBox QAbstractItemView {{
    background: {C.BG_CARD};
    color: {C.TEXT};
    border: 1px solid {C.BORDER_HI};
    selection-background-color: {C.ACCENT_DIM};
    selection-color: {C.ACCENT};
    outline: none;
}}

/* ─── Check boxes ──────────────────────── */
QCheckBox {{
    color: {C.TEXT};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border: 2px solid {C.BORDER_HI};
    border-radius: {C.RADIUS_XS};
    background: {C.BG_CARD};
}}
QCheckBox::indicator:hover {{
    border-color: {C.ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {C.ACCENT};
    border-color: {C.ACCENT};
    image: none;
}}

/* ─── Tab widget ───────────────────────── */
QTabWidget::pane {{
    background: {C.BG_DARK};
    border: 1px solid {C.BORDER};
    border-radius: {C.RADIUS_SM};
    top: -1px;
}}
QTabBar::tab {{
    background: {C.BG_CARD};
    color: {C.TEXT_DIM};
    border: 1px solid {C.BORDER};
    border-bottom: none;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: {C.RADIUS_SM};
    border-top-right-radius: {C.RADIUS_SM};
    font-size: 12px;
}}
QTabBar::tab:selected {{
    background: {C.BG_DARK};
    color: {C.ACCENT};
    border-bottom: 2px solid {C.ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    background: {C.SURFACE};
    color: {C.TEXT};
}}

/* ─── Group boxes ──────────────────────── */
QGroupBox {{
    background: {C.BG_CARD};
    border: 1px solid {C.BORDER};
    border-radius: {C.RADIUS_SM};
    margin-top: 14px;
    padding-top: 18px;
    font-weight: 600;
    color: {C.TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {C.ACCENT};
}}

/* ─── Scroll areas ─────────────────────── */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: {C.BG_DARK};
    width: 8px;
    margin: 0;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {C.SURFACE};
    min-height: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C.BORDER_HI};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {C.BG_DARK};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {C.SURFACE};
    min-width: 30px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {C.BORDER_HI};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ─── Progress bars ────────────────────── */
QProgressBar {{
    background: {C.BG_CARD};
    border: 1px solid {C.BORDER};
    border-radius: {C.RADIUS_XS};
    text-align: center;
    color: {C.TEXT};
    height: 18px;
    font-size: 11px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C.ACCENT_DIM}, stop:1 {C.ACCENT});
    border-radius: {C.RADIUS_XS};
}}

/* ─── Menus ────────────────────────────── */
QMenu {{
    background: {C.BG_CARD};
    border: 1px solid {C.BORDER_HI};
    border-radius: {C.RADIUS_SM};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 7px 28px 7px 16px;
    color: {C.TEXT};
}}
QMenu::item:selected {{
    background: {C.ACCENT_DIM};
    color: {C.ACCENT};
}}
QMenu::item:disabled {{
    color: {C.TEXT_DIM};
}}
QMenu::separator {{
    height: 1px;
    background: {C.BORDER};
    margin: 4px 10px;
}}

/* ─── Tooltips ─────────────────────────── */
QToolTip {{
    background: {C.BG_CARD};
    color: {C.TEXT};
    border: 1px solid {C.BORDER_HI};
    border-radius: {C.RADIUS_XS};
    padding: 5px 8px;
    font-size: 12px;
}}

/* ─── Form layout labels ──────────────── */
QFormLayout {{
    /* Not a real QSS selector, just a note:
       Form labels are QLabel — styled above. */
}}

/* ─── Slider ───────────────────────────── */
QSlider::groove:horizontal {{
    background: {C.BG_CARD};
    height: 6px;
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {C.ACCENT};
    width: 16px; height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {C.ACCENT_DIM};
    border-radius: 3px;
}}

/* ─── Message box ──────────────────────── */
QMessageBox {{
    background: {C.BG_DEEP};
}}
QMessageBox QLabel {{
    color: {C.TEXT};
    font-size: 13px;
}}
"""


# ── Menu stylesheet (for context menus applied via setStyleSheet) ──
MENU_QSS = (
    f"QMenu {{ background: {C.BG_CARD}; border: 1px solid {C.BORDER_HI}; "
    f"border-radius: {C.RADIUS_SM}; padding: 4px 0; }}"
    f"QMenu::item {{ padding: 7px 28px 7px 16px; color: {C.TEXT}; }}"
    f"QMenu::item:selected {{ background: {C.ACCENT_DIM}; color: {C.ACCENT}; }}"
    f"QMenu::item:disabled {{ color: {C.TEXT_DIM}; }}"
    f"QMenu::separator {{ height: 1px; background: {C.BORDER}; margin: 4px 10px; }}"
)
