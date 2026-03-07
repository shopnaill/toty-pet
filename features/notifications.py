import os
import re
import time
import sqlite3
import shutil
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime


class WindowsNotificationReader:
    """Reads Windows toast notifications from the system database.

    Windows stores all notifications in a SQLite database at
    %LOCALAPPDATA%/Microsoft/Windows/Notifications/wpndatabase.db

    We copy the DB (it's locked by the OS), read new toast entries,
    parse the XML payload, and return them.
    """

    _EPOCH_DIFF = 116444736000000000

    _APP_NAMES = {
        "whatsapp": "WhatsApp",
        "telegram": "Telegram",
        "discord": "Discord",
        "teams": "Teams",
        "outlook": "Outlook",
        "slack": "Slack",
        "chrome": "Chrome",
        "edge": "Edge",
        "firefox": "Firefox",
        "spotify": "Spotify",
        "steam": "Steam",
        "xbox": "Xbox",
        "facebook": "Facebook",
        "instagram": "Instagram",
        "messenger": "Messenger",
        "skype": "Skype",
        "viber": "Viber",
        "twitter": "Twitter",
        "twitch": "Twitch",
        "snapchat": "Snapchat",
        "notion": "Notion",
        "todoist": "Todoist",
    }

    def __init__(self):
        self._db_path = os.path.join(
            os.environ.get("LOCALAPPDATA", ""),
            "Microsoft", "Windows", "Notifications", "wpndatabase.db",
        )
        self._last_seen_id = 0
        self._available = os.path.exists(self._db_path)
        self._tmp_path = os.path.join(tempfile.gettempdir(), "toty_wpn_copy.db")
        if self._available:
            self._init_last_id()

    def _init_last_id(self):
        try:
            shutil.copy2(self._db_path, self._tmp_path)
            conn = sqlite3.connect(self._tmp_path)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(Id) FROM Notification WHERE Type='toast'")
            row = cursor.fetchone()
            if row and row[0]:
                self._last_seen_id = row[0]
            conn.close()
        except Exception:
            pass
        finally:
            try:
                os.remove(self._tmp_path)
            except OSError:
                pass

    def _filetime_to_datetime(self, ft: int) -> datetime:
        timestamp = (ft - self._EPOCH_DIFF) / 10_000_000
        try:
            return datetime.fromtimestamp(timestamp)
        except (OSError, ValueError):
            return datetime.now()

    def _friendly_app_name(self, primary_id: str) -> str:
        if not primary_id:
            return "Unknown"
        pid_lower = primary_id.lower()
        for key, name in self._APP_NAMES.items():
            if key in pid_lower:
                return name
        parts = primary_id.split("_")[0].split(".")[-1]
        spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', parts)
        return spaced if len(spaced) < 30 else spaced[:30]

    def _parse_payload(self, payload) -> list[str]:
        texts = []
        if not payload:
            return texts
        try:
            xml_str = payload if isinstance(payload, str) else payload.decode("utf-8", errors="replace")
            root = ET.fromstring(xml_str)
            for tag in (
                ".//{http://schemas.microsoft.com/windows/2012/tiles}text",
                ".//text",
            ):
                elems = root.findall(tag)
                for elem in elems:
                    if elem.text and elem.text.strip():
                        texts.append(elem.text.strip())
                if texts:
                    break
        except (ET.ParseError, Exception):
            pass
        return texts

    def check_new(self) -> list[dict]:
        """Check for new toast notifications since last check."""
        if not self._available:
            return []

        new_notifications = []
        conn = None
        try:
            copied = False
            for _ in range(2):
                try:
                    shutil.copy2(self._db_path, self._tmp_path)
                    copied = True
                    break
                except (PermissionError, OSError):
                    time.sleep(0.3)
            if not copied:
                return []

            conn = sqlite3.connect(self._tmp_path)
            conn.execute("PRAGMA journal_mode=WAL")
            cursor = conn.cursor()
            cursor.execute("""
                SELECT n.Id, h.PrimaryId, n.ArrivalTime, n.Payload
                FROM Notification n
                LEFT JOIN NotificationHandler h ON n.HandlerId = h.RecordId
                WHERE n.Type = 'toast' AND n.Id > ?
                ORDER BY n.ArrivalTime ASC
            """, (self._last_seen_id,))

            for row in cursor.fetchall():
                nid, primary_id, arrival, payload = row
                texts = self._parse_payload(payload)
                title = texts[0] if texts else ""
                body = texts[1] if len(texts) > 1 else ""
                app_name = self._friendly_app_name(primary_id or "")
                arrival_dt = self._filetime_to_datetime(arrival) if arrival else datetime.now()

                new_notifications.append({
                    "id": nid,
                    "app": app_name,
                    "title": title,
                    "body": body,
                    "time": arrival_dt,
                })
                if nid > self._last_seen_id:
                    self._last_seen_id = nid

            conn.close()
        except Exception:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        finally:
            try:
                os.remove(self._tmp_path)
            except OSError:
                pass

        return new_notifications
