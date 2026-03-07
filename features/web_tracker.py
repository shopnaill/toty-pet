import os
import re
import json
import time
from datetime import date


WEB_TRACKER_PATH = "web_visits.json"


class WebsiteTracker:
    """Tracks website visits from browser window titles."""

    KNOWN_SITES = [
        "youtube", "google", "github", "stackoverflow", "reddit",
        "twitter", "facebook", "instagram", "linkedin", "twitch",
        "netflix", "spotify", "discord", "whatsapp", "telegram",
        "amazon", "ebay", "wikipedia", "medium", "notion",
        "figma", "canva", "chatgpt", "claude", "copilot",
    ]

    def __init__(self):
        self.data: dict = {
            "visits": {},
            "daily": {},
            "last_site": "",
            "last_site_time": 0,
        }
        self._load()

    def _load(self):
        if os.path.exists(WEB_TRACKER_PATH):
            try:
                with open(WEB_TRACKER_PATH, "r") as f:
                    self.data.update(json.load(f))
            except (json.JSONDecodeError, IOError):
                pass

    def save(self):
        with open(WEB_TRACKER_PATH, "w") as f:
            json.dump(self.data, f, indent=4)

    def record_window(self, title: str):
        site = self._detect_site(title)
        if not site:
            self._end_current()
            return

        now = time.time()
        today = date.today().isoformat()

        if self.data["last_site"] == site and self.data["last_site_time"] > 0:
            elapsed = now - self.data["last_site_time"]
            if elapsed < 30:
                visits = self.data.setdefault("visits", {})
                entry = visits.setdefault(site, {"count": 0, "total_sec": 0})
                entry["total_sec"] = entry.get("total_sec", 0) + elapsed
        elif self.data["last_site"] != site:
            visits = self.data.setdefault("visits", {})
            entry = visits.setdefault(site, {"count": 0, "total_sec": 0})
            entry["count"] = entry.get("count", 0) + 1
            entry["last_seen"] = now

            daily = self.data.setdefault("daily", {})
            day_data = daily.setdefault(today, {})
            day_data[site] = day_data.get(site, 0) + 1

        self.data["last_site"] = site
        self.data["last_site_time"] = now

    def _end_current(self):
        self.data["last_site"] = ""
        self.data["last_site_time"] = 0

    def _detect_site(self, title: str) -> str:
        title_lower = title.lower()
        for site in self.KNOWN_SITES:
            if site in title_lower:
                return site
        domain_match = re.search(r'([\w-]+\.(?:com|org|net|io|dev|co))', title_lower)
        if domain_match:
            return domain_match.group(1)
        return ""

    def get_top_sites(self, n: int = 10) -> list[tuple[str, int, float]]:
        visits = self.data.get("visits", {})
        items = []
        for site, info in visits.items():
            count = info.get("count", 0)
            mins = info.get("total_sec", 0) / 60
            items.append((site, count, mins))
        items.sort(key=lambda x: -x[1])
        return items[:n]

    def get_today_sites(self) -> dict:
        today = date.today().isoformat()
        return self.data.get("daily", {}).get(today, {})

    def get_report_text(self) -> str:
        lines = ["--- Most Visited Sites ---"]
        top = self.get_top_sites(8)
        if not top:
            lines.append("No sites tracked yet.")
        else:
            for site, count, mins in top:
                time_str = f"{int(mins)}m" if mins >= 1 else f"{int(mins*60)}s"
                lines.append(f"  {site}: {count} visits ({time_str})")
        today_sites = self.get_today_sites()
        if today_sites:
            lines.append("\n--- Today ---")
            for site, count in sorted(today_sites.items(), key=lambda x: -x[1])[:5]:
                lines.append(f"  {site}: {count} visits")
        return "\n".join(lines)
