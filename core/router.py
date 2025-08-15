"""
core/router.py

Intent detection and slot extraction from free text.
- detect_intent: rule-first routing among 'destination', 'packing', 'attractions'
- update_slots_from_text: updates dates/month/city slots using simple heuristics
"""

import re

from util.dates import parse_dates, parse_month


PACKING_HINTS = {"pack", "packing", "suitcase", "what to bring"}
ATTRACTIONS_HINTS = {"see", "do", "attractions", "museum", "park", "things to do"}


def detect_intent(text):
    low = text.lower()
    if any(h in low for h in PACKING_HINTS):
        return "packing"
    if any(h in low for h in ATTRACTIONS_HINTS):
        return "attractions"
    return "destination"


def extract_city(text):
    """Very naive city guess: token after 'in' or first Capitalized token."""
    m = re.search(r"\bin\s+([A-Z][a-zA-Z\-]+)", text)
    if m:
        return m.group(1)
    m2 = re.search(r"\b([A-Z][a-zA-Z\-]{2,})\b", text)
    return m2.group(1) if m2 else None


def update_slots_from_text(text, session):
    """Update well-known slots based on the latest user input."""
    # dates
    dr = parse_dates(text)
    if dr:
        session.slots.start_date, session.slots.end_date = dr.to_iso_tuple()
        session.slots.month = None
    else:
        m = parse_month(text)
        if m:
            session.slots.month = str(m)

    # city
    city = extract_city(text)
    if city:
        session.slots.city = city
