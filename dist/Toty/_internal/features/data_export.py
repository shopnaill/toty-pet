"""
Data Export — export pet stats, mood history, diary, habits, and keyboard
heatmap to CSV or JSON for external analysis.
"""
import csv
import io
import json
import os
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QCheckBox, QFileDialog, QMessageBox, QGroupBox,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt


class DataExportDialog(QDialog):
    """Dialog to choose which data to export and the output format."""

    def __init__(self, pet, parent=None):
        super().__init__(parent)
        self._pet = pet
        self.setWindowTitle("📊 Export Toty Data")
        self.setFixedSize(380, 420)
        self.setStyleSheet(
            "QDialog { background: #1e1e2e; }"
            "QLabel { color: #cdd6f4; }"
            "QGroupBox { color: #89b4fa; border: 1px solid rgba(100,100,140,80);"
            " border-radius: 8px; margin-top: 10px; padding-top: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; }"
            "QCheckBox { color: #cdd6f4; spacing: 8px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        btn_style = (
            "QPushButton { background: #89b4fa; color: #1e1e2e; border: none;"
            " border-radius: 8px; padding: 8px 16px; font-weight: bold; }"
            "QPushButton:hover { background: #b4d0fb; }"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel("📊 Export Toty Data")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: #cdd6f4;")
        layout.addWidget(title)

        # Data selection checkboxes
        group = QGroupBox("Select data to export")
        group_layout = QVBoxLayout(group)

        self._cb_stats = QCheckBox("📈 Lifetime Stats (XP, level, session time)")
        self._cb_stats.setChecked(True)
        group_layout.addWidget(self._cb_stats)

        self._cb_mood = QCheckBox("😊 Mood History")
        self._cb_mood.setChecked(True)
        group_layout.addWidget(self._cb_mood)

        self._cb_diary = QCheckBox("📔 Pet Diary Entries")
        self._cb_diary.setChecked(True)
        group_layout.addWidget(self._cb_diary)

        self._cb_habits = QCheckBox("✅ Habit Tracker Data")
        self._cb_habits.setChecked(True)
        group_layout.addWidget(self._cb_habits)

        self._cb_heatmap = QCheckBox("⌨️ Keyboard Heatmap")
        group_layout.addWidget(self._cb_heatmap)

        self._cb_app_time = QCheckBox("⏱️ App Time Tracking")
        group_layout.addWidget(self._cb_app_time)

        layout.addWidget(group)

        # Format buttons
        btn_row = QHBoxLayout()
        btn_json = QPushButton("Export as JSON")
        btn_json.setStyleSheet(btn_style)
        btn_json.clicked.connect(lambda: self._export("json"))
        btn_row.addWidget(btn_json)

        btn_csv = QPushButton("Export as CSV")
        btn_csv.setStyleSheet(btn_style)
        btn_csv.clicked.connect(lambda: self._export("csv"))
        btn_row.addWidget(btn_csv)

        layout.addLayout(btn_row)
        layout.addStretch()

    def _gather_data(self) -> dict:
        data = {}
        data["export_date"] = datetime.now().isoformat()
        data["version"] = getattr(self._pet, '__version__', '15.0.0')

        if self._cb_stats.isChecked():
            stats = self._pet.stats
            data["stats"] = {
                "total_xp": stats.data.get("xp", 0),
                "level": stats.data.get("level", 1),
                "total_keys": stats.data.get("total_keys", 0),
                "total_pets": stats.data.get("total_pets", 0),
                "total_sessions": stats.data.get("total_sessions", 0),
                "focus_minutes": stats.data.get("focus_minutes", 0),
                "achievements": stats.data.get("achievements", []),
            }

        if self._cb_mood.isChecked():
            mood = self._pet.mood_engine
            data["mood"] = {
                "current_mood": mood.mood,
                "current_energy": mood.energy,
                "history": getattr(mood, '_history', []),
            }

        if self._cb_diary.isChecked():
            diary = self._pet._pet_diary
            data["diary"] = diary._entries

        if self._cb_habits.isChecked():
            habits = self._pet.habit_tracker
            data["habits"] = habits.data if hasattr(habits, 'data') else {}

        if self._cb_heatmap.isChecked():
            heatmap = self._pet._kb_heatmap
            data["keyboard_heatmap"] = heatmap.data if hasattr(heatmap, 'data') else {}

        if self._cb_app_time.isChecked():
            tracker = self._pet._app_time_tracker
            data["app_time"] = tracker.data if hasattr(tracker, 'data') else {}

        return data

    def _export(self, fmt: str):
        data = self._gather_data()

        if fmt == "json":
            ext = "JSON Files (*.json)"
            default_name = f"toty_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            ext = "CSV Files (*.csv)"
            default_name = f"toty_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        path, _ = QFileDialog.getSaveFileName(self, "Save Export", default_name, ext)
        if not path:
            return

        try:
            if fmt == "json":
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            else:
                self._write_csv(data, path)

            QMessageBox.information(self, "Export Complete",
                                    f"Data exported to:\n{path}")
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))

    def _write_csv(self, data: dict, path: str):
        """Flatten nested data into a multi-sheet CSV."""
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["# Toty Data Export", data.get("export_date", "")])
            writer.writerow([])

            if "stats" in data:
                writer.writerow(["## Stats"])
                for k, v in data["stats"].items():
                    if isinstance(v, list):
                        writer.writerow([k, "; ".join(str(x) for x in v)])
                    else:
                        writer.writerow([k, v])
                writer.writerow([])

            if "diary" in data:
                writer.writerow(["## Diary"])
                writer.writerow(["Date", "Events"])
                for date_str, entry in sorted(data["diary"].items()):
                    events = entry.get("events", [])
                    writer.writerow([date_str, " | ".join(events)])
                writer.writerow([])

            if "mood" in data:
                writer.writerow(["## Mood"])
                writer.writerow(["current_mood", data["mood"].get("current_mood")])
                writer.writerow(["current_energy", data["mood"].get("current_energy")])
                for h in data["mood"].get("history", []):
                    writer.writerow(["snapshot", h])
                writer.writerow([])

            if "habits" in data:
                writer.writerow(["## Habits"])
                for k, v in data["habits"].items():
                    writer.writerow([k, json.dumps(v, default=str)])
                writer.writerow([])

            if "app_time" in data:
                writer.writerow(["## App Time"])
                for k, v in data["app_time"].items():
                    writer.writerow([k, v])
