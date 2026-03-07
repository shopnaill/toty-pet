import math
from datetime import datetime, date, timedelta

from core.settings import Settings


class PrayerTimeManager:
    """Calculates Islamic prayer times using astronomical formulas.

    Supports: Umm Al-Qura, MWL, ISNA, Egyptian General Authority.
    No internet needed — pure math based on sun position.
    """

    PRAYER_NAMES = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
    PRAYER_NAMES_AR = ["الفجر", "الشروق", "الظهر", "العصر", "المغرب", "العشاء"]

    CALC_METHODS = {
        "umm_al_qura":  {"fajr_angle": 18.5, "isha_angle": 0, "isha_min": 90},
        "mwl":          {"fajr_angle": 18.0, "isha_angle": 17.0, "isha_min": 0},
        "isna":         {"fajr_angle": 15.0, "isha_angle": 15.0, "isha_min": 0},
        "egypt":        {"fajr_angle": 19.5, "isha_angle": 17.5, "isha_min": 0},
    }

    def __init__(self, settings: Settings):
        self.settings = settings
        self._cache_date = None
        self._cached_times = {}
        self._reminded = set()
        self._alerted = set()

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
