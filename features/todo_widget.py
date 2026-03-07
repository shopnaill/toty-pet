from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QCheckBox,
    QPushButton, QLineEdit, QScrollArea, QFrame, QLabel,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.stats import PersistentStats


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
        self.setFixedWidth(240)
        self.setMaximumHeight(320)
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
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(4)

        title = QLabel("To-Do List")
        title.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(title)

        # Scrollable area for items
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setMaximumHeight(200)
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
        row.addWidget(self._input)
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(30)
        add_btn.clicked.connect(self._add_item)
        row.addWidget(add_btn)
        self._layout.addLayout(row)

        self._rebuild_items()

    def _add_item(self):
        text = self._input.text().strip()
        if text:
            self.stats.add_todo(text)
            self._input.clear()
            self._rebuild_items()

    def _rebuild_items(self):
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        todos = self.stats.get_todos()
        for i, todo in enumerate(todos):
            row = QHBoxLayout()
            cb = QCheckBox(todo["text"])
            cb.setChecked(todo.get("done", False))
            if todo.get("done"):
                cb.setStyleSheet("QCheckBox { color: #999999; text-decoration: line-through; }")
            else:
                cb.setStyleSheet("QCheckBox { color: #222222; }")
            idx = i
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
