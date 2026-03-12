import math
import json
import os
from datetime import datetime, date, timedelta

from core.settings import Settings

# Hijri month names
HIJRI_MONTHS = [
    "Muharram", "Safar", "Rabi al-Awwal", "Rabi al-Thani",
    "Jumada al-Ula", "Jumada al-Thani", "Rajab", "Sha'ban",
    "Ramadan", "Shawwal", "Dhul Qi'dah", "Dhul Hijjah",
]
HIJRI_MONTHS_AR = [
    "محرم", "صفر", "ربيع الأول", "ربيع الثاني",
    "جمادى الأولى", "جمادى الآخرة", "رجب", "شعبان",
    "رمضان", "شوال", "ذو القعدة", "ذو الحجة",
]

# Prayer period colors (for aura effect)
PRAYER_PERIOD_COLORS = {
    "Fajr":    "#1a237e",   # deep blue (pre-dawn)
    "Sunrise": "#ff8f00",   # amber (sunrise)
    "Dhuhr":   "#ffd600",   # gold (midday)
    "Asr":     "#e65100",   # deep orange (afternoon)
    "Maghrib": "#c62828",   # red-pink (sunset)
    "Isha":    "#4a148c",   # purple (night)
}


def gregorian_to_hijri(year: int, month: int, day: int) -> tuple[int, int, int]:
    """Convert Gregorian date to Hijri using the Kuwaiti algorithm."""
    if month < 3:
        year -= 1
        month += 12
    a = math.floor(year / 100.0)
    b = 2 - a + math.floor(a / 4.0)
    jd = (math.floor(365.25 * (year + 4716))
          + math.floor(30.6001 * (month + 1)) + day + b - 1524.5)
    l = math.floor(jd) - 1948440 + 10632
    n = math.floor((l - 1) / 10631)
    l = l - 10631 * n + 354
    j = (math.floor((10985 - l) / 5316)
         * math.floor((50 * l) / 17719)
         + math.floor(l / 5670) * math.floor((43 * l) / 15238))
    l = (l - math.floor((30 - j) / 15) * math.floor((17719 * j) / 50)
         - math.floor(j / 16) * math.floor((15238 * j) / 43) + 29)
    h_month = int(math.floor((24 * l) / 709))
    h_day = int(l - math.floor((709 * h_month) / 24))
    h_year = int(30 * n + j - 30)
    return h_year, h_month, h_day


class PrayerTimeManager:
    """Calculates Islamic prayer times using astronomical formulas.

    Supports: Umm Al-Qura, MWL, ISNA, Egyptian General Authority.
    No internet needed — pure math based on sun position.
    """

    PRAYER_NAMES = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
    PRAYER_NAMES_AR = ["الفجر", "الشروق", "الظهر", "العصر", "المغرب", "العشاء"]

    # Prayer periods: the time *between* one prayer and the next
    PRAYER_PERIODS = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]

    CALC_METHODS = {
        "umm_al_qura":  {"fajr_angle": 18.5, "isha_angle": 0, "isha_min": 90},
        "mwl":          {"fajr_angle": 18.0, "isha_angle": 17.0, "isha_min": 0},
        "isna":         {"fajr_angle": 15.0, "isha_angle": 15.0, "isha_min": 0},
        "egypt":        {"fajr_angle": 19.5, "isha_angle": 17.5, "isha_min": 0},
    }

    _STREAK_FILE = os.path.join(os.path.dirname(__file__), "..", "prayer_streak.json")

    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache_date = None
        self._cached_times = {}
        self._reminded = set()
        self._alerted = set()
        self._iqama_reminded = set()
        self._iqama_times = {}  # prayer_name -> datetime when alert fired
        self._streak_data = self._load_streak()

    def get_times(self, d: date = None) -> dict:
        if d is None:
            d = date.today()
        if self._cache_date == d and self._cached_times:
            return self._cached_times

        lat = self.settings.get("prayer_latitude")
        lng = self.settings.get("prayer_longitude")
        method = self.settings.get("prayer_calc_method")
        params = self.CALC_METHODS.get(method, self.CALC_METHODS["umm_al_qura"])

        times = self._calculate(d, lat, lng, params)
        self._cached_times = times
        self._cache_date = d
        return times

    def reset_daily(self):
        self._reminded.clear()
        self._alerted.clear()
        self._iqama_reminded.clear()
        self._iqama_times.clear()
        self._cache_date = None

    def check(self) -> dict | None:
        """Check if any prayer reminder or alert should fire now."""
        now = datetime.now()
        if now.date() != self._cache_date:
            self._reminded.clear()
            self._alerted.clear()

        times = self.get_times(now.date())
        remind_min = self.settings.get("prayer_reminder_min") or 10

        for name in self.PRAYER_NAMES:
            if name == "Sunrise":
                continue
            pt = times.get(name)
            if not pt:
                continue
            diff_sec = (pt - now).total_seconds()
            diff_min = diff_sec / 60

            if -1 <= diff_min <= 1 and name not in self._alerted:
                self._alerted.add(name)
                ar_name = self.PRAYER_NAMES_AR[self.PRAYER_NAMES.index(name)]
                return {
                    "type": "alert",
                    "prayer": name,
                    "prayer_ar": ar_name,
                    "time": pt.strftime("%I:%M %p"),
                    "minutes_left": 0,
                }

            if 0 < diff_min <= remind_min and name not in self._reminded:
                self._reminded.add(name)
                ar_name = self.PRAYER_NAMES_AR[self.PRAYER_NAMES.index(name)]
                return {
                    "type": "reminder",
                    "prayer": name,
                    "prayer_ar": ar_name,
                    "time": pt.strftime("%I:%M %p"),
                    "minutes_left": int(diff_min),
                }

        return None

    def get_next_prayer(self) -> tuple:
        now = datetime.now()
        times = self.get_times(now.date())
        for name in self.PRAYER_NAMES:
            pt = times.get(name)
            if pt and pt > now:
                ar = self.PRAYER_NAMES_AR[self.PRAYER_NAMES.index(name)]
                return (name, ar, pt)
        tomorrow = self.get_times(now.date() + timedelta(days=1))
        pt = tomorrow.get("Fajr")
        return ("Fajr", "الفجر", pt) if pt else ("Fajr", "الفجر", None)

    def get_all_times_text(self) -> str:
        times = self.get_times()
        lines = []
        now = datetime.now()
        for name in self.PRAYER_NAMES:
            pt = times.get(name)
            if pt:
                ar = self.PRAYER_NAMES_AR[self.PRAYER_NAMES.index(name)]
                marker = " ← next" if pt > now and not any(
                    times.get(p) and times[p] > now and times[p] < pt
                    for p in self.PRAYER_NAMES if p != name
                ) else ""
                passed = " ✓" if pt <= now else ""
                lines.append(f"{ar} {name}: {pt.strftime('%I:%M %p')}{passed}{marker}")
        return "\n".join(lines)

    # ── Current prayer period & progress ──

    def get_current_period(self) -> dict | None:
        """Return the current prayer period with progress (0.0-1.0) and color."""
        now = datetime.now()
        times = self.get_times(now.date())
        ordered = [(n, times.get(n)) for n in self.PRAYER_NAMES if times.get(n)]
        if not ordered:
            return None

        # Find which period we're in
        for i in range(len(ordered) - 1):
            name, start = ordered[i]
            _, end = ordered[i + 1]
            if start <= now < end:
                total = (end - start).total_seconds()
                elapsed = (now - start).total_seconds()
                progress = elapsed / total if total > 0 else 0.0
                ar = self.PRAYER_NAMES_AR[self.PRAYER_NAMES.index(name)]
                return {
                    "period": name,
                    "period_ar": ar,
                    "progress": min(1.0, max(0.0, progress)),
                    "color": PRAYER_PERIOD_COLORS.get(name, "#4a148c"),
                    "start": start,
                    "end": end,
                }

        # After Isha — night period  until tomorrow's Fajr
        last_name, last_time = ordered[-1]
        if now >= last_time:
            tomorrow = self.get_times(now.date() + timedelta(days=1))
            fajr_tomorrow = tomorrow.get("Fajr")
            if fajr_tomorrow:
                total = (fajr_tomorrow - last_time).total_seconds()
                elapsed = (now - last_time).total_seconds()
                progress = elapsed / total if total > 0 else 0.0
            else:
                progress = 0.5
            return {
                "period": "Isha",
                "period_ar": "العشاء",
                "progress": min(1.0, max(0.0, progress)),
                "color": PRAYER_PERIOD_COLORS["Isha"],
                "start": last_time,
                "end": fajr_tomorrow,
            }

        # Before Fajr — still Isha from yesterday
        first_name, first_time = ordered[0]
        if now < first_time:
            return {
                "period": "Isha",
                "period_ar": "العشاء",
                "progress": 0.8,
                "color": PRAYER_PERIOD_COLORS["Isha"],
                "start": None,
                "end": first_time,
            }
        return None

    # ── Iqama reminder (post-prayer nudge) ──

    def record_alert_time(self, prayer_name: str):
        """Record when an alert was fired, for iqama timing."""
        self._iqama_times[prayer_name] = datetime.now()

    def check_iqama(self, iqama_min: int = 15) -> dict | None:
        """Check if an iqama (have-you-prayed?) reminder should fire."""
        now = datetime.now()
        for name, alert_time in list(self._iqama_times.items()):
            if name in self._iqama_reminded:
                continue
            diff = (now - alert_time).total_seconds() / 60
            if iqama_min <= diff <= iqama_min + 2:
                self._iqama_reminded.add(name)
                ar = self.PRAYER_NAMES_AR[self.PRAYER_NAMES.index(name)]
                return {"prayer": name, "prayer_ar": ar}
        return None

    # ── Jummah (Friday) detection ──

    @staticmethod
    def is_jummah() -> bool:
        return datetime.now().weekday() == 4  # Friday

    # ── Hijri date ──

    @staticmethod
    def get_hijri_date() -> dict:
        today = date.today()
        h_year, h_month, h_day = gregorian_to_hijri(today.year, today.month, today.day)
        return {
            "year": h_year,
            "month": h_month,
            "day": h_day,
            "month_name": HIJRI_MONTHS[h_month - 1] if 1 <= h_month <= 12 else "?",
            "month_name_ar": HIJRI_MONTHS_AR[h_month - 1] if 1 <= h_month <= 12 else "?",
            "display": f"{h_day} {HIJRI_MONTHS[h_month - 1] if 1 <= h_month <= 12 else '?'} {h_year}",
            "display_ar": f"{h_day} {HIJRI_MONTHS_AR[h_month - 1] if 1 <= h_month <= 12 else '?'} {h_year}",
        }

    # ── Prayer streak tracking ──

    def _load_streak(self) -> dict:
        try:
            with open(self._STREAK_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {"current_streak": 0, "best_streak": 0,
                    "last_date": "", "today_prayers": [], "total_prayers": 0}

    def _save_streak(self):
        try:
            with open(self._STREAK_FILE, "w", encoding="utf-8") as f:
                json.dump(self._streak_data, f, indent=2)
        except OSError:
            pass

    def record_prayer(self, prayer_name: str):
        """Mark a prayer as acknowledged/prayed. Tracks streak."""
        today = date.today().isoformat()
        d = self._streak_data

        if d.get("last_date") != today:
            # Check if yesterday was tracked (for streak continuity)
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if d.get("last_date") == yesterday and len(d.get("today_prayers", [])) >= 3:
                d["current_streak"] = d.get("current_streak", 0) + 1
            elif d.get("last_date") != today:
                # Gap — reset streak unless it's a new day continuing
                if d.get("last_date") != yesterday:
                    d["current_streak"] = 0
            d["today_prayers"] = []
            d["last_date"] = today

        if prayer_name not in d["today_prayers"]:
            d["today_prayers"].append(prayer_name)
            d["total_prayers"] = d.get("total_prayers", 0) + 1

        # If all 5 prayers done today, increment streak
        required = {"Fajr", "Dhuhr", "Asr", "Maghrib", "Isha"}
        if required.issubset(set(d["today_prayers"])):
            if d.get("_streak_counted_today") != today:
                d["current_streak"] = d.get("current_streak", 0) + 1
                d["_streak_counted_today"] = today

        d["best_streak"] = max(d.get("best_streak", 0), d.get("current_streak", 0))
        self._save_streak()

    def get_streak(self) -> dict:
        d = self._streak_data
        today = date.today().isoformat()
        today_count = len(d.get("today_prayers", [])) if d.get("last_date") == today else 0
        return {
            "current": d.get("current_streak", 0),
            "best": d.get("best_streak", 0),
            "today_count": today_count,
            "today_prayers": d.get("today_prayers", []) if d.get("last_date") == today else [],
            "total": d.get("total_prayers", 0),
        }

    # ── Astronomical calculation engine ──

    @staticmethod
    def _to_rad(deg):
        return deg * math.pi / 180

    @staticmethod
    def _to_deg(rad):
        return rad * 180 / math.pi

    @staticmethod
    def _fix_angle(a):
        a = a - 360.0 * math.floor(a / 360.0)
        return a if a >= 0 else a + 360.0

    @staticmethod
    def _fix_hour(h):
        h = h - 24.0 * math.floor(h / 24.0)
        return h if h >= 0 else h + 24.0

    def _sun_position(self, jd):
        D = jd - 2451545.0
        g = self._fix_angle(357.529 + 0.98560028 * D)
        q = self._fix_angle(280.459 + 0.98564736 * D)
        L = self._fix_angle(q + 1.915 * math.sin(self._to_rad(g))
                            + 0.020 * math.sin(self._to_rad(2 * g)))
        e = 23.439 - 0.00000036 * D
        RA = self._to_deg(math.atan2(
            math.cos(self._to_rad(e)) * math.sin(self._to_rad(L)),
            math.cos(self._to_rad(L))
        )) / 15.0
        RA = self._fix_hour(RA)
        decl = self._to_deg(math.asin(
            math.sin(self._to_rad(e)) * math.sin(self._to_rad(L))
        ))
        eqt = q / 15.0 - RA
        return decl, eqt

    @staticmethod
    def _julian_date(year, month, day):
        if month <= 2:
            year -= 1
            month += 12
        A = math.floor(year / 100.0)
        B = 2 - A + math.floor(A / 4.0)
        return math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5

    def _compute_time(self, angle, jd, lat, decl, direction=None):
        cos_val = (-math.sin(self._to_rad(angle))
                   - math.sin(self._to_rad(lat)) * math.sin(self._to_rad(decl))) / \
                  (math.cos(self._to_rad(lat)) * math.cos(self._to_rad(decl)))
        cos_val = max(-1, min(1, cos_val))
        val = self._to_deg(math.acos(cos_val)) / 15.0
        return val

    def _calculate(self, d: date, lat: float, lng: float, params: dict) -> dict:
        jd = self._julian_date(d.year, d.month, d.day)
        decl, eqt = self._sun_position(jd + 0.5)

        tz_setting = self.settings.data.get("prayer_timezone")
        if tz_setting is not None:
            tz_offset = float(tz_setting)
        else:
            tz_offset = round(lng / 15.0)

        dhuhr = 12.0 - eqt + tz_offset - lng / 15.0

        sunrise_angle = 0.833
        sunrise_t = self._compute_time(sunrise_angle, jd, lat, decl)
        sunrise = dhuhr - sunrise_t
        sunset = dhuhr + sunrise_t

        fajr_angle = params["fajr_angle"]
        fajr_t = self._compute_time(fajr_angle, jd, lat, decl)
        fajr = dhuhr - fajr_t

        s = abs(lat - decl)
        asr_alt = self._to_deg(math.atan(1.0 / (1.0 + math.tan(self._to_rad(s)))))
        asr_t = self._compute_time(-asr_alt, jd, lat, decl)
        asr = dhuhr + asr_t

        if params["isha_min"] > 0:
            isha = sunset + params["isha_min"] / 60.0
        else:
            isha_angle = params["isha_angle"]
            isha_t = self._compute_time(isha_angle, jd, lat, decl)
            isha = dhuhr + isha_t

        def h_to_dt(h):
            h = self._fix_hour(h)
            hours = int(h)
            minutes = int((h - hours) * 60)
            try:
                return datetime(d.year, d.month, d.day, hours, minutes)
            except ValueError:
                return None

        return {
            "Fajr": h_to_dt(fajr),
            "Sunrise": h_to_dt(sunrise),
            "Dhuhr": h_to_dt(dhuhr),
            "Asr": h_to_dt(asr),
            "Maghrib": h_to_dt(sunset),
            "Isha": h_to_dt(isha),
        }

    def configure_location(self, lat: float, lng: float, method: str = None):
        self.settings.set("prayer_latitude", lat)
        self.settings.set("prayer_longitude", lng)
        self.settings.set("prayer_timezone", round(lng / 15.0))
        if method and method in self.CALC_METHODS:
            self.settings.set("prayer_calc_method", method)
        self._cache_date = None
        self._reminded.clear()
        self._alerted.clear()
        self._iqama_reminded.clear()
        self._iqama_times.clear()
