"""
util/dates.py

Date parsing helpers for free-text inputs.
- parse_dates: detect one or two dates and return ISO strings window
- parse_month: extract a month when specific dates are not present
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from dateutil import parser


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
    for token in text.replace("→", " ").replace("to", " ").replace("-", " ").split():
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
