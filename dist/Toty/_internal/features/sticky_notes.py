"""
Quick Sticky Notes — floating color-coded notes.
Persistent to JSON, always-on-top optional.
Auto-archive on close with restore capability.
"""
import json
import os
import logging
from datetime import datetime
from core.safe_json import safe_json_save
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel,
    QDialog, QListWidget, QListWidgetItem,
)
from PyQt6.QtCore import Qt, QPoint, pyqtSignal, QObject, QTimer
from PyQt6.QtGui import QFont, QColor

log = logging.getLogger("toty")
_FILE = "sticky_notes.json"

COLORS = [
    ("#FFF9C4", "#F9A825"),  # yellow
    ("#C8E6C9", "#388E3C"),  # green
    ("#BBDEFB", "#1565C0"),  # blue
    ("#F8BBD0", "#C2185B"),  # pink
    ("#E1BEE7", "#7B1FA2"),  # purple
    ("#FFE0B2", "#E65100"),  # orange
]


class StickyNote(QWidget):
    """Single floating sticky note."""
    closed = pyqtSignal(int)  # note id
    changed = pyqtSignal()

    def __init__(self, nid: int, text: str = "", color_idx: int = 0,
                 pos: tuple = (200, 200)):
        super().__init__(None)
        self.nid = nid
        self._color_idx = color_idx % len(COLORS)
        self._dragging = False
        self._drag_offset = QPoint()

        bg, accent = COLORS[self._color_idx]
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(240, 200)
        self.move(pos[0], pos[1])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        title = QLabel(f"📝 Note #{nid}")
        title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {accent};")
        header.addWidget(title)
        header.addStretch()

        # Color cycle button
        color_btn = QPushButton("🎨")
        color_btn.setFixedSize(24, 24)
        color_btn.setStyleSheet("border: none; font-size: 14px;")
        color_btn.clicked.connect(self._cycle_color)
        header.addWidget(color_btn)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet(
            f"border: none; font-size: 14px; font-weight: bold; color: {accent};"
        )
        close_btn.clicked.connect(lambda: self.closed.emit(self.nid))
        header.addWidget(close_btn)
        layout.addLayout(header)

        # Text area
        self._editor = QTextEdit()
        self._editor.setPlainText(text)
        self._editor.setFont(QFont("Segoe UI", 10))
        self._editor.setStyleSheet(
            f"background: {bg}; border: 1px solid {accent}; border-radius: 4px; "
            f"color: #333; padding: 4px;"
        )
        self._editor.textChanged.connect(self.changed.emit)
        layout.addWidget(self._editor)

        self.setStyleSheet(
            f"QWidget {{ background: {bg}; border: 2px solid {accent}; "
            f"border-radius: 8px; }}"
        )

    def _cycle_color(self):
        self._color_idx = (self._color_idx + 1) % len(COLORS)
        bg, accent = COLORS[self._color_idx]
        self.setStyleSheet(
            f"QWidget {{ background: {bg}; border: 2px solid {accent}; "
            f"border-radius: 8px; }}"
        )
        self._editor.setStyleSheet(
            f"background: {bg}; border: 1px solid {accent}; "
            f"border-radius: 4px; color: #333; padding: 4px;"
        )
        self.changed.emit()

    def get_text(self) -> str:
        return self._editor.toPlainText()

    def get_data(self) -> dict:
        return {
            "nid": self.nid,
            "text": self.get_text(),
            "color_idx": self._color_idx,
            "pos": [self.x(), self.y()],
            "created": getattr(self, "_created", datetime.now().isoformat()),
        }

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self.changed.emit()
        super().mouseReleaseEvent(event)


class StickyNotesManager(QObject):
    """Manages creation, persistence, and display of sticky notes."""
    note_created = pyqtSignal(int)
    note_closed = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self._notes: dict[int, StickyNote] = {}
        self._archive: list[dict] = []  # archived note dicts
        self._next_id = 1
        # Debounce saves: collect rapid changes into one disk write
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._do_save)
        self._load()

    def create_note(self, text: str = "", pos: tuple = (200, 200),
                    color_idx: int = 0) -> StickyNote:
        nid = self._next_id
        self._next_id += 1
        note = StickyNote(nid, text, color_idx, pos)
        note._created = datetime.now().isoformat()
        note.closed.connect(self.close_note)
        note.changed.connect(self._save)
        self._notes[nid] = note
        note.show()
        self._save()
        self.note_created.emit(nid)
        return note

    def close_note(self, nid: int):
        note = self._notes.pop(nid, None)
        if note:
            # Archive the note before closing
            data = note.get_data()
            data["archived_at"] = datetime.now().isoformat()
            self._archive.append(data)
            # Keep last 50 archived notes
            self._archive = self._archive[-50:]
            note.close()
            note.deleteLater()
            self._save()
            self.note_closed.emit(nid)

    def restore_note(self, archive_idx: int):
        """Restore a note from the archive."""
        if 0 <= archive_idx < len(self._archive):
            item = self._archive.pop(archive_idx)
            self.create_note(
                text=item.get("text", ""),
                pos=tuple(item.get("pos", [200, 200])),
                color_idx=item.get("color_idx", 0),
            )

    def get_archive(self) -> list[dict]:
        return list(self._archive)

    def clear_archive(self):
        self._archive.clear()
        self._save()

    def toggle_all(self):
        """Show/hide all notes."""
        if self._notes:
            any_visible = any(n.isVisible() for n in self._notes.values())
            for n in self._notes.values():
                n.setVisible(not any_visible)
        else:
            self.create_note()

    def get_count(self) -> int:
        return len(self._notes)

    def _save(self):
        """Schedule a debounced save (coalesces rapid edits)."""
        if not self._save_timer.isActive():
            self._save_timer.start()

    def _do_save(self):
        """Actually write notes to disk."""
        data = {
            "next_id": self._next_id,
            "notes": [n.get_data() for n in self._notes.values()],
            "archive": self._archive,
        }
        try:
            safe_json_save(data, _FILE)
        except OSError as e:
            log.warning("StickyNotes: save failed: %s", e)

    def _load(self):
        if not os.path.exists(_FILE):
            return
        try:
            with open(_FILE, encoding="utf-8") as f:
                data = json.load(f)
            self._next_id = data.get("next_id", 1)
            self._archive = data.get("archive", [])
            for nd in data.get("notes", []):
                nid = nd["nid"]
                note = StickyNote(nid, nd.get("text", ""),
                                  nd.get("color_idx", 0),
                                  tuple(nd.get("pos", [200, 200])))
                note.closed.connect(self.close_note)
                note.changed.connect(self._save)
                self._notes[nid] = note
                # Don't auto-show on load — user toggles them
        except (json.JSONDecodeError, IOError, KeyError):
            pass

    def show_all(self):
        for n in self._notes.values():
            n.show()

    def hide_all(self):
        for n in self._notes.values():
            n.hide()

    def stop(self):
        self._save_timer.stop()
        self._do_save()  # flush pending save immediately
        for n in list(self._notes.values()):
            n.close()
        self._notes.clear()


class StickyArchiveDialog(QDialog):
    """Dialog to browse and restore archived sticky notes."""

    def __init__(self, manager: StickyNotesManager, parent=None):
        super().__init__(parent)
        self._mgr = manager
        self.setWindowTitle("📦 Archived Notes")
        self.setFixedSize(360, 400)
        self.setStyleSheet(
            "QDialog { background: #2b2b2b; }"
            "QLabel { color: #ddd; }"
            "QListWidget { background: #1e1e1e; color: #ccc; border: 1px solid #555; "
            "  border-radius: 4px; font-size: 12px; }"
            "QListWidget::item { padding: 6px; }"
            "QListWidget::item:selected { background: #3a6ea5; }"
            "QPushButton { background: #3a6ea5; color: white; border: none; "
            "  border-radius: 4px; padding: 6px 14px; font-weight: bold; }"
            "QPushButton:hover { background: #4a8ed4; }"
        )
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Closed notes are archived here. Select to restore:"))
        self._list = QListWidget()
        lay.addWidget(self._list)

        btn_row = QHBoxLayout()
        restore_btn = QPushButton("♻️ Restore Selected")
        restore_btn.clicked.connect(self._restore)
        btn_row.addWidget(restore_btn)
        clear_btn = QPushButton("🗑️ Clear Archive")
        clear_btn.setStyleSheet(
            "QPushButton { background: #8b2222; }"
            "QPushButton:hover { background: #a03030; }"
        )
        clear_btn.clicked.connect(self._clear)
        btn_row.addWidget(clear_btn)
        lay.addLayout(btn_row)

        self._refresh()

    def _refresh(self):
        self._list.clear()
        for i, item in enumerate(reversed(self._mgr.get_archive())):
            preview = (item.get("text", "")[:60] or "(empty)").replace("\n", " ")
            archived = item.get("archived_at", "?")[:16]
            display = f"[{archived}]  {preview}"
            li = QListWidgetItem(display)
            li.setData(Qt.ItemDataRole.UserRole, len(self._mgr.get_archive()) - 1 - i)
            self._list.addItem(li)

    def _restore(self):
        sel = self._list.currentItem()
        if sel:
            idx = sel.data(Qt.ItemDataRole.UserRole)
            self._mgr.restore_note(idx)
            self._refresh()

    def _clear(self):
        self._mgr.clear_archive()
        self._refresh()
