"""
util/dates.py

Date parsing helpers for free-text inputs.
- parse_dates: detect one or two dates and return ISO strings window
- parse_month: extract a month when specific dates are not present
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from dateutil import parser
from datetime import timezone


ISO_DATE_FMT = "%Y-%m-%d"


@dataclass
class DateRange:
    start: datetime
    end: datetime

    def to_iso_tuple(self):
        return self.start.strftime(ISO_DATE_FMT), self.end.strftime(ISO_DATE_FMT)


def parse_dates(text):
    """Parse one or two dates from free text.

    Returns None if no dates found. If only one date is found, uses a 4-day window.
    """
    candidates = []
    # Handle common relative phrases
    now = datetime.now(timezone.utc)
    today_str = now.strftime(ISO_DATE_FMT)
    tomorrow_str = (now + timedelta(days=1)).strftime(ISO_DATE_FMT)

    # Compute ranges for week/weekend/month
    def week_range(offset_weeks: int = 0):
        start = now + timedelta(days=7 * offset_weeks)
        # start today, 7-day window
        return start, start + timedelta(days=6)

    def weekend_range(offset_weeks: int = 0):
        # approximate: Friday of the target week to Sunday
        start_of_week = now - timedelta(days=now.weekday()) + timedelta(days=7 * offset_weeks)
        fri = start_of_week + timedelta(days=4)
        sun = start_of_week + timedelta(days=6)
        return fri, sun

    def month_range(offset_months: int = 0):
        # simple month arithmetic without external deps
        year = now.year + ((now.month - 1 + offset_months) // 12)
        month = ((now.month - 1 + offset_months) % 12) + 1
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        # last day: next month minus one day
        nyear = year + (month // 12)
        nmonth = (month % 12) + 1
        next_month_start = datetime(nyear, nmonth, 1, tzinfo=timezone.utc)
        end = next_month_start - timedelta(days=1)
        return start, end

    normalized = (
        text.replace("→", " ")
        .replace(" to ", " ")
        .replace("-", " ")
        .replace("tomorrow", tomorrow_str)
        .replace("today", today_str)
        .replace("tonight", today_str)
    )

    # Expand broader phrases by appending explicit ISO ranges
    if "this week" in normalized.lower():
        s, e = week_range(0)
        normalized += f" {s.strftime(ISO_DATE_FMT)} {e.strftime(ISO_DATE_FMT)}"
    if "next week" in normalized.lower():
        s, e = week_range(1)
        normalized += f" {s.strftime(ISO_DATE_FMT)} {e.strftime(ISO_DATE_FMT)}"
    if "this weekend" in normalized.lower():
        s, e = weekend_range(0)
        normalized += f" {s.strftime(ISO_DATE_FMT)} {e.strftime(ISO_DATE_FMT)}"
    if "next weekend" in normalized.lower():
        s, e = weekend_range(1)
        normalized += f" {s.strftime(ISO_DATE_FMT)} {e.strftime(ISO_DATE_FMT)}"
    if "this month" in normalized.lower():
        s, e = month_range(0)
        normalized += f" {s.strftime(ISO_DATE_FMT)} {e.strftime(ISO_DATE_FMT)}"
    for token in normalized.split():
        try:
            dt = parser.parse(token, fuzzy=True, dayfirst=False)
            candidates.append(dt)
        except Exception:
            continue

    if not candidates:
        return None

    candidates.sort()
    if len(candidates) == 1:
        start = candidates[0]
        end = start + timedelta(days=4)
        return DateRange(start=start, end=end)

    start, end = candidates[0], candidates[-1]
    if (end - start).days > 14:
        end = start + timedelta(days=14)
    return DateRange(start=start, end=end)


def parse_month(text):
    try:
        dt = parser.parse(text, fuzzy=True, default=datetime(2000, 1, 1))
        return dt.month
    except Exception:
        return None


def month_to_season(month: int, lat: float | None = None) -> str:
    """Return meteorological season name for a given month.
    If lat provided and < 0, use southern hemisphere seasons.
    """
    hemi_north = True if (lat is None or lat >= 0) else False
    # Northern hemisphere seasons
    seasons_n = {12: "winter", 1: "winter", 2: "winter",
                 3: "spring", 4: "spring", 5: "spring",
                 6: "summer", 7: "summer", 8: "summer",
                 9: "autumn", 10: "autumn", 11: "autumn"}
    if hemi_north:
        return seasons_n.get(month, "unknown")
    # Southern hemisphere invert two seasons
    seasons_s = {12: "summer", 1: "summer", 2: "summer",
                 3: "autumn", 4: "autumn", 5: "autumn",
                 6: "winter", 7: "winter", 8: "winter",
                 9: "spring", 10: "spring", 11: "spring"}
    return seasons_s.get(month, "unknown")
