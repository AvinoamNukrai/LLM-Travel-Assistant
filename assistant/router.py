"""
assistant/router.py

Intent detection and slot extraction from free text.

Key functions:
- detect_intent(text): classify user input into intents like 'destination', 'packing', 'attractions', 'weather',
  plus control intents ('support', 'meta', 'end', 'neutral'). Weather is prioritized to avoid misrouting.
- has_weather_hint(text): quick boolean for weather-related keywords.
- is_smalltalk(text): short, friendly smalltalk detector that doesn't override content intents.
- extract_city(text): robust heuristic extractor that prefers explicit prepositions ("in/at/near") and verb forms
  ("visit/going to"), supports common aliases (e.g., NYC → New York). Returns (city, source) where source is
  'prep' or 'fallback'.
- update_slots_from_text(text, session): updates session slots (dates, month, city/country/coords via geocode,
  budget hint, kid friendly, interests). Avoids overwriting city with weak fallbacks.
"""

import re

from util.dates import parse_dates, parse_month
from assistant.tools.weather import geocode_city


PACKING_HINTS = {
    "pack", "packing", "suitcase", "what to bring", "bring", "wear", "clothes", "clothing"
}
ATTRACTIONS_HINTS = {
    "see", "do", "attractions", "museum", "park", "things to do", "things to see",
    "place", "places", "spots", "sights", "landmarks", "recommendations", "recommendation", "reccomendations",
    "visit"
}
WEATHER_HINTS = {
    "weather", "forecast", "temperature", "temp", "rain", "precip", "precipitation",
    "snow", "hot", "cold", "humid", "humidity", "wind", "windy", "sunny", "cloudy",
    "climate", "conditions", "wetaher", "wheather", "wether"
}
META_HINTS = {
    "remember", "do you remember", "which city", "what city", "which dates", "what dates",
    "what am i traveling", "where am i going", "what am i going", "recap", "summary", "context",
}
DESTINATION_HINTS = {
    "destination", "recommend", "suggest", "ideas", "where to go", "trip ideas", "vacation", "destinations",
    "recommendations", "recommendation"
}
SMALLTALK_HINTS = {
    "hi", "hello", "hey", "yo", "thanks", "thank you", "ok", "okay", "my name is", "hii", "heyy",
    "nice", "cool", "great", "awesome", "amazing", "niccce", "niccceeee"
}

END_HINTS = {
    "nothing", "no thanks", "no thank you", "not now", "later", "that's all", "thats all", "that's it", "thats it",
    "bye", "goodbye", "gtg", "i'm good", "im good", "we're good", "were good", "all good", "done"
}

FRUSTRATION_HINTS = {"wtf", "dumb", "stupid", "you don't", "not understand", "annoying", "!!!", "????"}

COUNTRY_ALIASES: dict[str, str] = {
    # Common countries and aliases
    "israel": "Israel",
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "italy": "Italy",
    "france": "France",
    "spain": "Spain",
    "germany": "Germany",
    "japan": "Japan",
}


def _contains_hint(low: str, hints: set[str]) -> bool:
    """Return True if any hint in `hints` appears in `low`.

    - Single-token hints are matched with word boundaries.
    - Multi-word phrases are matched as substrings (already lowercased).
    """
    for h in hints:
        if " " in h:
            if h in low:
                return True
            continue
        if re.search(r"\b" + re.escape(h) + r"\b", low):
            return True
    return False


def detect_intent(text):
    """Classify user input into a high-level intent.

    Prioritizes explicit weather and attractions patterns, then handles meta/end/support,
    destination/packing/attractions, finally falling back to 'neutral'.
    """
    low = text.lower()
    word_count = len(low.split())
    if re.search(r"\b(top\s*(3|three)|3\s*(places|attractions)|where\s+to\s+visit|what\s+to\s+see)\b", low):
        return "attractions"
    if _contains_hint(low, WEATHER_HINTS):
        return "weather"
    if _contains_hint(low, META_HINTS) or re.search(r"\b(which|what)\s+(city|dates?)\b", low):
        return "meta"
    if _contains_hint(low, END_HINTS):
        return "end"
    if _contains_hint(low, FRUSTRATION_HINTS):
        return "neutral"
    if _contains_hint(low, SMALLTALK_HINTS) and word_count <= 6:
        return "support"
    if re.search(r"\b(?:travel(?:ling|ing)?|go(?:ing)?|head(?:ing)?)\s+to\s+[A-Za-z]", low) or re.search(r"\bvisit(?:ing)?\s+[A-Za-z]", low):
        return "destination"
    if _contains_hint(low, PACKING_HINTS):
        return "packing"
    if _contains_hint(low, ATTRACTIONS_HINTS):
        return "attractions"
    if _contains_hint(low, DESTINATION_HINTS):
        return "destination"
    return "neutral"


def has_weather_hint(text: str) -> bool:
    """Quick boolean: does the text mention weather concepts?"""
    return _contains_hint(text.lower(), WEATHER_HINTS)


def is_smalltalk(text: str) -> bool:
    """Return True for brief greetings/acknowledgements that are not travel requests."""
    low = text.lower().strip()
    word_count = len(low.split())
    if any(h in low for h in WEATHER_HINTS | PACKING_HINTS | ATTRACTIONS_HINTS | DESTINATION_HINTS | META_HINTS):
        return False
    return any(h in low for h in SMALLTALK_HINTS) and word_count <= 6


def extract_city(text):
    """Extract a likely city (or country alias) from free text.

    Strategy:
    1) Prefer explicit prepositions (in/at/near/around/going to)
    2) Consider verbs (visit/going/heading/traveling to)
    3) Recognize common aliases (e.g., NYC → New York)
    4) Short single/dual-word fallback for terse inputs (e.g., 'Rome')

    Returns (city, source) where source is 'prep' or 'fallback', or (None, None) if none found.
    """
    low = text.lower()
    stop_after = {"for", "next", "this", "week", "month", "today", "tomorrow", "on", "from", "to", "in", "at", "with", "and", "or", "the",
                  "what", "whats", "what’s", "is", "are", "was", "were", "how", "where", "which", "who", "whom", "whose",
                  "do", "does", "did", "there", "here", "please", "pls", "about", "of", "weather", "forecast", "city", "date", "dates"}
    banned_fallback = {"nice", "cool", "great", "awesome", "amazing"}
    banned_activity = {"hiking", "museum", "museums", "packing", "weather", "ideas", "attractions", "places", "recommendations", "recommendation", "visit", "visiting", "top"}

    def _normalize_aliases(name: str) -> str:
        """Map informal names/aliases to canonical forms (e.g., 'nyc' → 'New York')."""
        low = name.strip().lower()
        aliases = {
            "nyc": "New York",
            "new york city": "New York",
            "la": "Los Angeles",
            "sf": "San Francisco",
            "sfo": "San Francisco",
            "saint petersburg": "St Petersburg",
        }
        return aliases.get(low, name)

    def _match_alias_in_text(text_in: str) -> str | None:
        """Return a canonical city if a known alias is found anywhere in the text."""
        patterns = [
            (r"\bnyc\b", "New York"),
            (r"\bnew\s+york\s+city\b", "New York"),
            (r"\bnew\s+york\b", "New York"),
            (r"\bla\b", "Los Angeles"),
            (r"\blos\s+angeles\b", "Los Angeles"),
            (r"\bsf\b", "San Francisco"),
            (r"\bsfo\b", "San Francisco"),
            (r"\bsan\s+francisco\b", "San Francisco"),
            (r"\bisrael\b", "Israel"),
        ]
        for rx, city_name in patterns:
            if re.search(rx, text_in, re.IGNORECASE):
                return city_name
        return None

    def pick_after(match_group: str) -> str | None:
        """Heuristically pick up to 3 tokens after a preposition/verb to form a city name."""
        raw = match_group.strip()
        tokens = re.findall(r"[A-Za-z\-]+", raw)
        picked: list[str] = []
        month_tokens = {"jan","january","feb","february","mar","march","apr","april","may","jun","june","jul","july","aug","august","sep","sept","september","oct","october","nov","november","dec","december"}
        leading_skip = {"visit", "visiting", "top", "places", "travel", "travelling", "traveling", "go", "going", "head", "heading", "want"}
        started = False
        for t in tokens:
            tl = t.lower()
            if not started:
                if tl in leading_skip:
                    continue
                if tl in stop_after:
                    continue
            if started and (tl in stop_after or tl in month_tokens):
                break
            if any(ch.isdigit() for ch in t):
                if not started:
                    continue
                break
            if tl in month_tokens:
                if not started:
                    continue
                break
            if not started and tl in banned_activity:
                continue
            picked.append(t)
            started = True
            if len(picked) >= 3:
                break
        if not picked:
            return None
        candidate = _normalize_aliases(" ".join(picked))
        if candidate.lower() in banned_activity:
            return None
        return candidate

    m0 = re.search(r"^\s*([A-Za-z][A-Za-z\-\s]{2,}?)\s+(?:in|at|near|around)\b", text, re.IGNORECASE)
    if m0:
        cand = pick_after(m0.group(1))
        if cand:
            return cand, "prep"

    m1 = re.search(r"\b(?:in|at|near|around|going to)\s+([A-Za-z][A-Za-z\-\s]{2,})", text, re.IGNORECASE)
    if m1:
        cand = pick_after(m1.group(1))
        if cand:
            return cand, "prep"

    m2 = re.search(r"\b(?:visiting|visit|to|go to|going to|heading to|travelling to|traveling to|want(?:\s+to)?)\s+([A-Za-z][A-Za-z\-\s]{2,})", text, re.IGNORECASE)
    if m2:
        cand = pick_after(m2.group(1))
        if cand:
            return cand, "prep"

    alias_hit = _match_alias_in_text(text)
    if alias_hit:
        return alias_hit, "prep"

    raw = text.strip()
    if 1 <= len(raw.split()) <= 3:
        cand = pick_after(raw)
        if cand and cand.lower() not in banned_fallback and cand.lower() not in banned_activity:
            return cand, "fallback"

    return None, None


def update_slots_from_text(text, session):
    """Update session slots from user text.

    - Dates/month via `parse_dates`/`parse_month`
    - City/country/coords via `geocode_city` (avoids weak fallbacks overwriting existing city)
    - Budget/kid-friendly hints, and interest buckets
    """
    dr = parse_dates(text)
    if dr:
        session.slots.start_date, session.slots.end_date = dr.to_iso_tuple()
        session.slots.month = None
    else:
        m = parse_month(text)
        if m:
            session.slots.month = str(m)

    city, source = extract_city(text)
    if city:
        try:
            geo = geocode_city(city)
        except Exception:
            geo = None
        if geo:
            if source == "fallback" and session.slots.city:
                pass
            else:
                session.slots.city = geo.name
                session.slots.country = geo.country
                session.slots.lat, session.slots.lon = geo.lat, geo.lon

    low = text.lower()
    if any(k in low for k in ["budget", "cheap", "affordable", "low cost", "low-cost", "inexpensive"]):
        session.slots.budget_hint = "budget"
    elif any(k in low for k in ["mid-range", "midrange", "moderate"]):
        session.slots.budget_hint = "mid"
    elif any(k in low for k in ["luxury", "upscale", "5 star", "5-star"]):
        session.slots.budget_hint = "luxury"

    if any(k in low for k in ["kid", "kids", "child", "children", "stroller", "family"]):
        session.slots.kid_friendly = True
    if any(k in low for k in ["adults only", "adult-only", "no kids"]):
        session.slots.kid_friendly = False

    interests = []
    buckets = {
        "beach": ["beach", "coast", "island", "surf"],
        "museum": ["museum", "gallery", "exhibit"],
        "food": ["food", "restaurant", "eat", "cuisine", "street food"],
        "hiking": ["hike", "hiking", "trail", "trek", "mountain"],
        "nightlife": ["bar", "club", "nightlife", "party"],
        "history": ["history", "historic", "castle", "ruins"],
        "shopping": ["shopping", "market", "mall", "boutique"],
    }
    for name, kws in buckets.items():
        if any(k in low for k in kws):
            interests.append(name)
    if interests:
        session.slots.interests = ",".join(sorted(set(interests)))


