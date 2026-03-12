from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
    QPushButton, QLineEdit, QScrollArea, QFrame, QLabel, QComboBox,
    QDateEdit,
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QFont
from datetime import date

from core.stats import PersistentStats

_PRIORITY_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢", "": ""}


class MiniTodoWidget(QWidget):
    """A small floating to-do list panel attached to the pet."""
    def __init__(self, stats: PersistentStats, parent=None):
        super().__init__(parent)
        self.stats = stats
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedWidth(280)
        self.setMaximumHeight(400)
        self.setStyleSheet(
            "QWidget { background: #F0F0F0; border: 2px solid #888;"
            "          border-radius: 8px; color: #222222; }"
            "QLabel { color: #222222; background: transparent; border: none; }"
            "QCheckBox { font-size: 11px; padding: 2px 0; color: #222222; }"
            "QLineEdit { border: 1px solid #ccc; border-radius: 4px;"
            "            padding: 3px; font-size: 11px;"
            "            background: white; color: #222222; }"
            "QPushButton { background: #5599ff; color: white; border: none;"
            "              border-radius: 4px; padding: 4px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #3377dd; }"
            "QComboBox { font-size: 10px; padding: 2px; background: white;"
            "            border: 1px solid #ccc; border-radius: 3px; color: #222; }"
            "QDateEdit { font-size: 10px; padding: 2px; background: white;"
            "            border: 1px solid #ccc; border-radius: 3px; color: #222; }"
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)

        # Header with overdue badge
        hdr = QHBoxLayout()
        title = QLabel("📋 To-Do List")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        hdr.addWidget(title)
        self._overdue_label = QLabel("")
        self._overdue_label.setStyleSheet("color: #cc0000; font-size: 10px; font-weight: bold;")
        hdr.addWidget(self._overdue_label)
        hdr.addStretch()
        self._layout.addLayout(hdr)

        # Scrollable area for items
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMaximumHeight(220)
        self._items_container = QWidget()
        self._items_layout = QVBoxLayout(self._items_container)
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(2)
        self._scroll.setWidget(self._items_container)
        self._layout.addWidget(self._scroll)

        # Add new item row
        row = QHBoxLayout()
        self._input = QLineEdit()
        self._input.setPlaceholderText("Add task...")
        self._input.returnPressed.connect(self._add_item)
        row.addWidget(self._input, stretch=1)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.clicked.connect(self._add_item)
        row.addWidget(add_btn)
        self._layout.addLayout(row)

        # Priority + due date row
        opts = QHBoxLayout()
        self._priority_combo = QComboBox()
        self._priority_combo.addItems(["Priority", "🔴 High", "🟡 Medium", "🟢 Low"])
        self._priority_combo.setFixedWidth(90)
        opts.addWidget(self._priority_combo)

        self._due_edit = QDateEdit()
        self._due_edit.setCalendarPopup(True)
        self._due_edit.setDate(QDate.currentDate())
        self._due_edit.setSpecialValueText("No due date")
        self._due_edit.setMinimumDate(QDate(2020, 1, 1))
        self._due_check = QCheckBox("Due:")
        self._due_check.setStyleSheet("QCheckBox { font-size: 10px; }")
        opts.addWidget(self._due_check)
        opts.addWidget(self._due_edit)
        opts.addStretch()
        self._layout.addLayout(opts)

        self._rebuild_items()

    def _add_item(self):
        text = self._input.text().strip()
        if not text:
            return
        pri_map = {0: "", 1: "high", 2: "medium", 3: "low"}
        priority = pri_map.get(self._priority_combo.currentIndex(), "")
        due = ""
        if self._due_check.isChecked():
            due = self._due_edit.date().toString("yyyy-MM-dd")
        self.stats.add_todo(text, priority=priority, due=due)
        self._input.clear()
        self._priority_combo.setCurrentIndex(0)
        self._due_check.setChecked(False)
        self._rebuild_items()

    def _rebuild_items(self):
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today_str = date.today().isoformat()
        overdue = self.stats.get_overdue_count()
        self._overdue_label.setText(f"⚠️ {overdue} overdue" if overdue else "")

        sorted_items = self.stats.get_todos_sorted()
        for real_idx, todo in sorted_items:
            row = QHBoxLayout()
            row.setSpacing(4)

            # Priority dot
            pri = todo.get("priority", "")
            pri_icon = _PRIORITY_ICONS.get(pri, "")
            if pri_icon:
                pri_lbl = QLabel(pri_icon)
                pri_lbl.setFixedWidth(16)
                row.addWidget(pri_lbl)

            # Checkbox
            label = todo["text"]
            due = todo.get("due", "")
            is_overdue = due and due < today_str and not todo.get("done")
            if due and not todo.get("done"):
                label += f"  📅{due[5:]}"  # show MM-DD

            cb = QCheckBox(label)
            cb.setChecked(todo.get("done", False))
            if todo.get("done"):
                cb.setStyleSheet("QCheckBox { color: #999999; text-decoration: line-through; }")
            elif is_overdue:
                cb.setStyleSheet("QCheckBox { color: #cc0000; font-weight: bold; }")
            else:
                cb.setStyleSheet("QCheckBox { color: #222222; }")
            idx = real_idx
            cb.toggled.connect(lambda checked, ii=idx: self._toggle(ii))
            row.addWidget(cb, stretch=1)

            del_btn = QPushButton("×")
            del_btn.setFixedSize(20, 20)
            del_btn.setStyleSheet(
                "QPushButton { background: #ff5555; padding: 0; font-size: 12px; }"
                "QPushButton:hover { background: #cc3333; }"
            )
            del_btn.clicked.connect(lambda _, ii=idx: self._delete(ii))
            row.addWidget(del_btn)

            container = QWidget()
            container.setLayout(row)
            self._items_layout.addWidget(container)

    def _toggle(self, index):
        self.stats.toggle_todo(index)
        self._rebuild_items()

    def _delete(self, index):
        self.stats.remove_todo(index)
        self._rebuild_items()

    def refresh(self):
        self._rebuild_items()
