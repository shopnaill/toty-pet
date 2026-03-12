"""
Pet Store — coin economy, shop UI, and expanded equipment system.
Coins are earned from productivity; spent on cosmetic items + effects.
"""
import json
import os
import random
import logging
from datetime import datetime, date
from core.safe_json import safe_json_save
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPixmap, QPainter, QPen, QBrush
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget, QGridLayout, QTabWidget,
    QMessageBox, QGroupBox,
)

log = logging.getLogger("toty.pet_store")
_FILE = "pet_store.json"

# ── Rarity tiers ───────────────────────────────────────────────
RARITY_COMMON    = "common"
RARITY_RARE      = "rare"
RARITY_EPIC      = "epic"
RARITY_LEGENDARY = "legendary"

_RARITY_COLORS = {
    RARITY_COMMON:    "#a6adc8",
    RARITY_RARE:      "#89b4fa",
    RARITY_EPIC:      "#cba6f7",
    RARITY_LEGENDARY: "#f9e2af",
}

_RARITY_ORDER = [RARITY_COMMON, RARITY_RARE, RARITY_EPIC, RARITY_LEGENDARY]

# ── Equipment slots ────────────────────────────────────────────
SLOT_HEAD   = "head"
SLOT_FACE   = "face"
SLOT_BODY   = "body"
SLOT_HAND   = "hand"
SLOT_BACK   = "back"
SLOT_EFFECT = "effect"

_SLOT_NAMES = {
    SLOT_HEAD:   "🎩 Head",
    SLOT_FACE:   "👓 Face",
    SLOT_BODY:   "👕 Body",
    SLOT_HAND:   "🖐️ Hand",
    SLOT_BACK:   "🎒 Back",
    SLOT_EFFECT: "✨ Effect",
}

# ── Store catalog ──────────────────────────────────────────────
# (id, name, emoji, slot, rarity, price, description)
STORE_ITEMS = [
    # Head
    ("crown",        "Crown",          "👑", SLOT_HEAD, RARITY_LEGENDARY, 1000, "Royalty vibes!"),
    ("wizard_hat",   "Wizard Hat",     "🧙", SLOT_HEAD, RARITY_EPIC,      500,  "Cast spells of productivity"),
    ("party_hat",    "Party Hat",      "🎉", SLOT_HEAD, RARITY_RARE,      200,  "Every day is a celebration"),
    ("beanie",       "Beanie",         "🧶", SLOT_HEAD, RARITY_COMMON,      0,  "Cozy and warm"),
    ("winter_hat",   "Winter Hat",     "🎿", SLOT_HEAD, RARITY_COMMON,     50,  "For snowy days"),
    ("headband",     "Headband",       "🎀", SLOT_HEAD, RARITY_COMMON,     30,  "Sporty look"),
    ("pirate_hat",   "Pirate Hat",     "🏴‍☠️", SLOT_HEAD, RARITY_RARE,      300,  "Arr matey!"),
    ("halo",         "Halo",           "😇", SLOT_HEAD, RARITY_EPIC,      600,  "Angelic glow"),
    ("top_hat",      "Top Hat",        "🎩", SLOT_HEAD, RARITY_RARE,      250,  "Classy gentleman"),
    ("flower_crown", "Flower Crown",   "🌸", SLOT_HEAD, RARITY_RARE,      200,  "Spring vibes"),

    # Face
    ("sunglasses",   "Sunglasses",     "😎", SLOT_FACE, RARITY_COMMON,      0,  "Cool as always"),
    ("monocle",      "Monocle",        "🧐", SLOT_FACE, RARITY_RARE,      150,  "Distinguished indeed"),
    ("mask",         "Ninja Mask",     "🥷", SLOT_FACE, RARITY_RARE,      200,  "Stealthy focus mode"),
    ("glasses",      "Glasses",        "👓", SLOT_FACE, RARITY_COMMON,     20,  "Scholarly look"),
    ("mustache",     "Mustache",       "🥸", SLOT_FACE, RARITY_COMMON,     40,  "Disguise activated"),
    ("blush",        "Blush Sticker",  "😊", SLOT_FACE, RARITY_COMMON,     25,  "Cute cheeks!"),

    # Body
    ("hoodie",       "Hoodie",         "🧥", SLOT_BODY, RARITY_COMMON,     60,  "Comfy coder gear"),
    ("suit",         "Suit",           "🤵", SLOT_BODY, RARITY_RARE,      300,  "Business mode"),
    ("cape",         "Superhero Cape", "🦸", SLOT_BODY, RARITY_EPIC,      500,  "Productivity superhero!"),
    ("lab_coat",     "Lab Coat",       "🥼", SLOT_BODY, RARITY_RARE,      250,  "Science!"),
    ("raincoat",     "Raincoat",       "🌧️", SLOT_BODY, RARITY_COMMON,     80,  "Ready for rain"),
    ("tuxedo",       "Tuxedo",         "🎭", SLOT_BODY, RARITY_EPIC,      450,  "Black tie event"),
    ("cloak",        "Mystery Cloak",  "🧛", SLOT_BODY, RARITY_LEGENDARY, 800,  "Shrouded in mystery"),
    ("blanket",      "Cozy Blanket",   "🛋️", SLOT_BODY, RARITY_COMMON,     40,  "Wrapped up warm"),

    # Hand
    ("coffee_mug",   "Coffee Mug",     "☕", SLOT_HAND, RARITY_COMMON,     30,  "Fuel for coding"),
    ("laptop",       "Mini Laptop",    "💻", SLOT_HAND, RARITY_RARE,      200,  "Always working"),
    ("magic_wand",   "Magic Wand",     "🪄", SLOT_HAND, RARITY_EPIC,      400,  "Abracadabra!"),
    ("book",         "Book",           "📖", SLOT_HAND, RARITY_COMMON,     50,  "Knowledge is power"),
    ("umbrella",     "Umbrella",       "☂️",  SLOT_HAND, RARITY_COMMON,     35,  "Rain protection"),
    ("sword",        "Pixel Sword",    "⚔️",  SLOT_HAND, RARITY_EPIC,      550,  "Bug slayer!"),
    ("smartphone",   "Smartphone",     "📱", SLOT_HAND, RARITY_COMMON,     40,  "Always connected"),

    # Back
    ("backpack",     "Backpack",       "🎒", SLOT_BACK, RARITY_COMMON,     50,  "Adventure ready"),
    ("wings",        "Angel Wings",    "🪽", SLOT_BACK, RARITY_LEGENDARY, 1200, "Transcend productivity"),
    ("jetpack",      "Jetpack",        "🚀", SLOT_BACK, RARITY_LEGENDARY, 1500, "To infinity!"),
    ("guitar",       "Guitar",         "🎸", SLOT_BACK, RARITY_RARE,      250,  "Rock on!"),

    # Effects
    ("sparkle",      "Sparkle Trail",  "✨", SLOT_EFFECT, RARITY_RARE,     200,  "Shimmering aura"),
    ("fire_aura",    "Fire Aura",      "🔥", SLOT_EFFECT, RARITY_EPIC,     500,  "On fire!"),
    ("rainbow",      "Rainbow Glow",   "🌈", SLOT_EFFECT, RARITY_EPIC,     600,  "Fabulous!"),
    ("hearts",       "Floating Hearts","💕", SLOT_EFFECT, RARITY_RARE,     180,  "Full of love"),
    ("pixel_dust",   "Pixel Dust",     "💫", SLOT_EFFECT, RARITY_COMMON,    80,  "Retro vibes"),
    ("snow_effect",  "Snow Effect",    "❄️",  SLOT_EFFECT, RARITY_RARE,     200,  "Winter wonderland"),
]

# Build lookup
_ITEM_MAP = {item[0]: item for item in STORE_ITEMS}

# ── Coin rewards ───────────────────────────────────────────────
COIN_REWARDS = {
    "pomodoro_complete":  25,
    "focus_30min":        15,
    "streak_day":         10,
    "level_up":           50,
    "achievement":        30,
    "daily_login":        5,
    "habit_complete":     8,
    "typing_game":        10,
    "journal_entry":      5,
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Persistence
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PetStoreData:
    """Manages coins, owned items, equipped items, and daily spin."""

    def __init__(self):
        self._data = {
            "coins": 50,  # start with welcome bonus
            "owned": ["sunglasses", "beanie"],  # free starter items
            "equipped": {},    # slot → item_id
            "outfit_presets": {},  # name → {slot: item_id}
            "last_daily_spin": "",
            "total_earned": 50,
            "total_spent": 0,
        }
        self._load()

    def _load(self):
        if os.path.exists(_FILE):
            try:
                with open(_FILE, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._data.update(stored)
                # Ensure owned is a list
                if isinstance(self._data["owned"], set):
                    self._data["owned"] = list(self._data["owned"])
            except Exception:
                pass

    def save(self):
        safe_json_save(self._data, _FILE)

    @property
    def coins(self) -> int:
        return self._data["coins"]

    def add_coins(self, amount: int, source: str = "") -> int:
        self._data["coins"] += amount
        self._data["total_earned"] += amount
        self.save()
        return self._data["coins"]

    def spend_coins(self, amount: int) -> bool:
        if self._data["coins"] >= amount:
            self._data["coins"] -= amount
            self._data["total_spent"] += amount
            self.save()
            return True
        return False

    def owns(self, item_id: str) -> bool:
        return item_id in self._data["owned"]

    def buy(self, item_id: str) -> bool:
        """Buy item if affordable. Returns True on success."""
        item = _ITEM_MAP.get(item_id)
        if not item or self.owns(item_id):
            return False
        price = item[5]
        if price == 0:
            # Free item
            self._data["owned"].append(item_id)
            self.save()
            return True
        if self.spend_coins(price):
            self._data["owned"].append(item_id)
            self.save()
            return True
        return False

    def equip(self, item_id: str) -> bool:
        if not self.owns(item_id):
            return False
        item = _ITEM_MAP.get(item_id)
        if not item:
            return False
        slot = item[3]
        self._data["equipped"][slot] = item_id
        self.save()
        return True

    def unequip_slot(self, slot: str):
        self._data["equipped"].pop(slot, None)
        self.save()

    def get_equipped(self) -> dict:
        """Returns {slot: item_id}."""
        return dict(self._data.get("equipped", {}))

    def get_equipped_items(self) -> list[str]:
        """Returns list of equipped item IDs."""
        return list(self._data.get("equipped", {}).values())

    def get_owned(self) -> list[str]:
        return list(self._data["owned"])

    # ── Outfit presets ──────────────────────────────────────
    def save_preset(self, name: str):
        self._data["outfit_presets"][name] = dict(self._data["equipped"])
        self.save()

    def load_preset(self, name: str) -> dict:
        preset = self._data["outfit_presets"].get(name, {})
        if preset:
            self._data["equipped"] = dict(preset)
            self.save()
        return preset

    def get_presets(self) -> dict:
        return dict(self._data.get("outfit_presets", {}))

    def delete_preset(self, name: str):
        self._data["outfit_presets"].pop(name, None)
        self.save()

    # ── Daily spin ──────────────────────────────────────────
    def can_daily_spin(self) -> bool:
        last = self._data.get("last_daily_spin", "")
        return last != str(date.today())

    def do_daily_spin(self) -> tuple[str, int]:
        """Returns (reward_type, amount_or_item)."""
        self._data["last_daily_spin"] = str(date.today())

        # 60% coins, 30% item, 10% bonus coins
        roll = random.random()
        if roll < 0.6:
            # Coins (10-50)
            amount = random.choice([10, 15, 20, 25, 30, 40, 50])
            self.add_coins(amount, "daily_spin")
            self.save()
            return "coins", amount
        elif roll < 0.9:
            # Random unowned common/rare item
            unowned = [
                item_id for item_id, *_ in STORE_ITEMS
                if not self.owns(item_id) and _[3] in (RARITY_COMMON, RARITY_RARE)
            ]
            if unowned:
                item_id = random.choice(unowned)
                self._data["owned"].append(item_id)
                self.save()
                return "item", item_id
            # Fallback to coins
            self.add_coins(30, "daily_spin")
            self.save()
            return "coins", 30
        else:
            # Bonus coins
            amount = random.choice([50, 75, 100])
            self.add_coins(amount, "daily_spin_bonus")
            self.save()
            return "bonus_coins", amount

    def get_stats_text(self) -> str:
        return (
            f"💰 Coins: {self.coins}\n"
            f"🛍️ Owned: {len(self._data['owned'])} / {len(STORE_ITEMS)} items\n"
            f"💵 Total earned: {self._data['total_earned']}\n"
            f"💸 Total spent: {self._data['total_spent']}"
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Store dialog
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PetStoreDialog(QDialog):
    """Shop UI with item grid, preview, purchase, and outfit management."""

    item_equipped = pyqtSignal(str)     # item_id to equip on pet
    item_unequipped = pyqtSignal(str)   # slot to unequip

    _BG = "#1e1e2e"
    _CARD = "#313244"
    _ACCENT = "#89b4fa"
    _TEXT = "#cdd6f4"
    _SUB = "#a6adc8"
    _BORDER = "#585b70"
    _GREEN = "#a6e3a1"

    def __init__(self, store_data: PetStoreData, parent=None):
        super().__init__(parent)
        self._store = store_data
        self.setWindowTitle("🛍️ Pet Store")
        self.setFixedSize(620, 560)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setStyleSheet(
            f"QDialog {{ background: {self._BG}; border: 2px solid {self._ACCENT};"
            f" border-radius: 14px; }}"
        )
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        # Header with coin display
        hdr_row = QHBoxLayout()
        title = QLabel("🛍️ Pet Store")
        title.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {self._ACCENT};")
        hdr_row.addWidget(title)
        hdr_row.addStretch()

        self._coin_label = QLabel(f"💰 {self._store.coins}")
        self._coin_label.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self._coin_label.setStyleSheet(f"color: #f9e2af;")
        hdr_row.addWidget(self._coin_label)
        lay.addLayout(hdr_row)

        # Daily spin button
        spin_row = QHBoxLayout()
        self._spin_btn = QPushButton("🎰 Daily Spin (Free!)")
        self._spin_btn.setStyleSheet(self._btn_style("#f9e2af", "#1e1e2e"))
        can_spin = self._store.can_daily_spin()
        self._spin_btn.setEnabled(can_spin)
        if not can_spin:
            self._spin_btn.setText("🎰 Already spun today!")
        self._spin_btn.clicked.connect(self._daily_spin)
        spin_row.addWidget(self._spin_btn)
        spin_row.addStretch()

        stats_btn = QPushButton("📊 Stats")
        stats_btn.setStyleSheet(self._btn_style(self._BORDER, self._TEXT))
        stats_btn.clicked.connect(
            lambda: QMessageBox.information(self, "Store Stats", self._store.get_stats_text()))
        spin_row.addWidget(stats_btn)
        lay.addLayout(spin_row)

        # Tabs: shop by slot + inventory + outfits
        tabs = QTabWidget()
        tabs.setStyleSheet(self._tab_style())

        for slot, slot_name in _SLOT_NAMES.items():
            tab = self._build_shop_tab(slot)
            tabs.addTab(tab, slot_name)

        tabs.addTab(self._build_equipped_tab(), "✅ Equipped")
        tabs.addTab(self._build_outfits_tab(), "👔 Outfits")
        lay.addWidget(tabs)

        self._tabs = tabs

    def _build_shop_tab(self, slot: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
            f"QScrollBar:vertical {{ width: 6px; background: {self._CARD}; }}"
            f"QScrollBar::handle:vertical {{ background: {self._BORDER}; border-radius: 3px; }}"
        )

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(8)
        grid.setContentsMargins(4, 4, 4, 4)

        items = [i for i in STORE_ITEMS if i[3] == slot]
        items.sort(key=lambda x: (_RARITY_ORDER.index(x[4]), x[5]))

        for idx, (item_id, name, emoji, _slot, rarity, price, desc) in enumerate(items):
            card = self._make_item_card(item_id, name, emoji, rarity, price, desc)
            grid.addWidget(card, idx // 3, idx % 3)

        grid.setRowStretch(grid.rowCount(), 1)
        scroll.setWidget(grid_widget)
        lay.addWidget(scroll)
        return w

    def _make_item_card(self, item_id, name, emoji, rarity, price, desc) -> QFrame:
        card = QFrame()
        owned = self._store.owns(item_id)
        equipped_items = self._store.get_equipped_items()
        is_equipped = item_id in equipped_items
        rarity_color = _RARITY_COLORS.get(rarity, self._SUB)

        border_color = self._GREEN if is_equipped else rarity_color if owned else self._BORDER
        card.setStyleSheet(
            f"QFrame {{ background: {self._CARD}; border: 2px solid {border_color};"
            f" border-radius: 10px; padding: 6px; }}"
        )
        card.setFixedSize(176, 130)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(3)

        # Emoji + name
        top = QLabel(f"{emoji} {name}")
        top.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        top.setStyleSheet(f"color: {self._TEXT}; border: none;")
        lay.addWidget(top)

        # Rarity tag
        tag = QLabel(rarity.upper())
        tag.setStyleSheet(
            f"color: {rarity_color}; font-size: 9px; font-weight: bold; border: none;")
        lay.addWidget(tag)

        # Description
        d = QLabel(desc)
        d.setStyleSheet(f"color: {self._SUB}; font-size: 10px; border: none;")
        d.setWordWrap(True)
        lay.addWidget(d)

        # Action button
        if is_equipped:
            btn = QPushButton("✅ Equipped")
            btn.setStyleSheet(self._small_btn(self._GREEN, "#1e1e2e"))
            btn.clicked.connect(lambda _, iid=item_id: self._unequip_item(iid))
        elif owned:
            btn = QPushButton("👕 Equip")
            btn.setStyleSheet(self._small_btn(self._ACCENT, "#1e1e2e"))
            btn.clicked.connect(lambda _, iid=item_id: self._equip_item(iid))
        else:
            label = "FREE" if price == 0 else f"💰 {price}"
            btn = QPushButton(f"🛒 {label}")
            btn.setStyleSheet(self._small_btn("#f9e2af", "#1e1e2e"))
            btn.clicked.connect(lambda _, iid=item_id, p=price: self._buy_item(iid, p))

        lay.addWidget(btn)
        return card

    def _build_equipped_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        equipped = self._store.get_equipped()
        if not equipped:
            empty = QLabel("Nothing equipped yet!\nBrowse the shop tabs to buy and equip items.")
            empty.setStyleSheet(f"color: {self._SUB}; font-size: 12px;")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(empty)
        else:
            for slot, item_id in equipped.items():
                item = _ITEM_MAP.get(item_id)
                if not item:
                    continue
                row = QHBoxLayout()
                slot_lbl = QLabel(f"{_SLOT_NAMES.get(slot, slot)}:")
                slot_lbl.setStyleSheet(f"color: {self._SUB}; font-size: 12px; min-width: 80px;")
                row.addWidget(slot_lbl)

                item_lbl = QLabel(f"{item[2]} {item[1]}")
                item_lbl.setStyleSheet(f"color: {self._TEXT}; font-size: 12px; font-weight: bold;")
                row.addWidget(item_lbl)
                row.addStretch()

                unequip = QPushButton("❌")
                unequip.setStyleSheet(self._small_btn("#f38ba8", "#1e1e2e"))
                unequip.setFixedWidth(36)
                unequip.clicked.connect(
                    lambda _, s=slot: self._unequip_slot(s))
                row.addWidget(unequip)

                lay.addLayout(row)

        lay.addStretch()

        # Unequip all
        unequip_all = QPushButton("🗑️ Unequip All")
        unequip_all.setStyleSheet(self._btn_style("#f38ba8", "#1e1e2e"))
        unequip_all.clicked.connect(self._unequip_all)
        lay.addWidget(unequip_all)
        return w

    def _build_outfits_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(8)

        info = QLabel("Save your current outfit as a preset to quickly switch later.")
        info.setStyleSheet(f"color: {self._SUB}; font-size: 11px;")
        info.setWordWrap(True)
        lay.addWidget(info)

        # Save button
        save_row = QHBoxLayout()
        from PyQt6.QtWidgets import QLineEdit
        self._preset_name = QLineEdit()
        self._preset_name.setPlaceholderText("Outfit name...")
        self._preset_name.setStyleSheet(
            f"QLineEdit {{ background: {self._CARD}; color: {self._TEXT};"
            f" border: 1px solid {self._BORDER}; border-radius: 6px;"
            f" padding: 6px; font-size: 12px; }}"
        )
        save_row.addWidget(self._preset_name)

        save_btn = QPushButton("💾 Save")
        save_btn.setStyleSheet(self._btn_style(self._ACCENT, "#1e1e2e"))
        save_btn.clicked.connect(self._save_preset)
        save_row.addWidget(save_btn)
        lay.addLayout(save_row)

        # List presets
        presets = self._store.get_presets()
        if presets:
            for name, slots in presets.items():
                row = QHBoxLayout()
                items_text = ", ".join(
                    _ITEM_MAP[iid][2] + _ITEM_MAP[iid][1]
                    for iid in slots.values() if iid in _ITEM_MAP
                ) or "(empty)"
                lbl = QLabel(f"👔 {name}: {items_text}")
                lbl.setStyleSheet(f"color: {self._TEXT}; font-size: 11px;")
                lbl.setWordWrap(True)
                row.addWidget(lbl)

                load_btn = QPushButton("👕")
                load_btn.setToolTip(f"Load {name}")
                load_btn.setStyleSheet(self._small_btn(self._ACCENT, "#1e1e2e"))
                load_btn.setFixedWidth(36)
                load_btn.clicked.connect(lambda _, n=name: self._load_preset(n))
                row.addWidget(load_btn)

                del_btn = QPushButton("🗑️")
                del_btn.setToolTip(f"Delete {name}")
                del_btn.setStyleSheet(self._small_btn("#f38ba8", "#1e1e2e"))
                del_btn.setFixedWidth(36)
                del_btn.clicked.connect(lambda _, n=name: self._delete_preset(n))
                row.addWidget(del_btn)

                lay.addLayout(row)
        else:
            empty = QLabel("No outfit presets saved yet.")
            empty.setStyleSheet(f"color: {self._SUB}; font-size: 11px;")
            lay.addWidget(empty)

        lay.addStretch()
        return w

    # ── Actions ─────────────────────────────────────────────
    def _buy_item(self, item_id: str, price: int):
        if self._store.owns(item_id):
            QMessageBox.information(self, "Already Owned", "You already own this item!")
            return
        if price > 0 and self._store.coins < price:
            QMessageBox.warning(self, "Not Enough Coins",
                                f"You need {price} coins but only have {self._store.coins}.")
            return
        if self._store.buy(item_id):
            item = _ITEM_MAP[item_id]
            self._refresh_coins()
            QMessageBox.information(self, "Purchased!",
                                    f"{item[2]} {item[1]} is now yours!")
            self._rebuild_tabs()

    def _equip_item(self, item_id: str):
        if self._store.equip(item_id):
            self.item_equipped.emit(item_id)
            self._rebuild_tabs()

    def _unequip_item(self, item_id: str):
        item = _ITEM_MAP.get(item_id)
        if item:
            self._store.unequip_slot(item[3])
            self.item_unequipped.emit(item[3])
            self._rebuild_tabs()

    def _unequip_slot(self, slot: str):
        self._store.unequip_slot(slot)
        self.item_unequipped.emit(slot)
        self._rebuild_tabs()

    def _unequip_all(self):
        for slot in list(self._store.get_equipped().keys()):
            self._store.unequip_slot(slot)
            self.item_unequipped.emit(slot)
        self._rebuild_tabs()

    def _daily_spin(self):
        if not self._store.can_daily_spin():
            return
        reward_type, value = self._store.do_daily_spin()
        if reward_type == "coins":
            QMessageBox.information(self, "🎰 Daily Spin!", f"You won 💰 {value} coins!")
        elif reward_type == "bonus_coins":
            QMessageBox.information(self, "🎰 BONUS!", f"Lucky! 💰 {value} bonus coins!")
        elif reward_type == "item":
            item = _ITEM_MAP.get(value)
            name = f"{item[2]} {item[1]}" if item else value
            QMessageBox.information(self, "🎰 Item Won!", f"You won {name}!")
        self._spin_btn.setEnabled(False)
        self._spin_btn.setText("🎰 Already spun today!")
        self._refresh_coins()
        self._rebuild_tabs()

    def _save_preset(self):
        name = self._preset_name.text().strip()
        if not name:
            return
        self._store.save_preset(name)
        self._preset_name.clear()
        self._rebuild_tabs()

    def _load_preset(self, name: str):
        equipped = self._store.load_preset(name)
        for item_id in equipped.values():
            self.item_equipped.emit(item_id)
        self._rebuild_tabs()

    def _delete_preset(self, name: str):
        self._store.delete_preset(name)
        self._rebuild_tabs()

    def _refresh_coins(self):
        self._coin_label.setText(f"💰 {self._store.coins}")

    def _rebuild_tabs(self):
        """Rebuild all tabs to reflect updated state."""
        current = self._tabs.currentIndex()
        self._tabs.clear()
        for slot, slot_name in _SLOT_NAMES.items():
            self._tabs.addTab(self._build_shop_tab(slot), slot_name)
        self._tabs.addTab(self._build_equipped_tab(), "✅ Equipped")
        self._tabs.addTab(self._build_outfits_tab(), "👔 Outfits")
        if current < self._tabs.count():
            self._tabs.setCurrentIndex(current)

    # ── Styles ──────────────────────────────────────────────
    def _btn_style(self, bg: str, fg: str) -> str:
        return (
            f"QPushButton {{ background: {bg}; color: {fg}; border: none;"
            f" border-radius: 8px; padding: 8px 16px; font-size: 12px; }}"
            f"QPushButton:hover {{ opacity: 0.85; }}"
            f"QPushButton:disabled {{ background: {self._BORDER}; color: {self._SUB}; }}"
        )

    def _small_btn(self, bg: str, fg: str) -> str:
        return (
            f"QPushButton {{ background: {bg}; color: {fg}; border: none;"
            f" border-radius: 6px; padding: 4px 10px; font-size: 11px; }}"
            f"QPushButton:hover {{ opacity: 0.85; }}"
        )

    def _tab_style(self) -> str:
        return (
            f"QTabWidget::pane {{ border: 1px solid {self._BORDER};"
            f" border-radius: 8px; background: {self._BG}; }}"
            f"QTabBar::tab {{ background: {self._CARD}; color: {self._SUB};"
            f" padding: 6px 10px; border-top-left-radius: 6px;"
            f" border-top-right-radius: 6px; margin-right: 2px; font-size: 10px; }}"
            f"QTabBar::tab:selected {{ background: {self._ACCENT}; color: #1e1e2e;"
            f" font-weight: bold; }}"
            f"QTabBar::tab:hover {{ background: #45475a; color: {self._TEXT}; }}"
        )
