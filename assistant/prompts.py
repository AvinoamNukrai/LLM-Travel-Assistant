"""
assistant/prompts.py

Prompt templates and helpers. Preserves existing content and behavior.
"""

from assistant.session import Session
from util.dates import month_to_season


SYSTEM_PROMPT = (
    "You are Navan, a warm and friendly travel planner. "
    "On your first reply only, output one short, cheerful sentence introducing yourself as Navan and offering help; do not ask a question. Never repeat any introduction again. "
    "Maintain context across turns. Strictly follow the current intent: "
    "- weather: ONLY summarize weather + 1–2 packing tips. Do NOT suggest destinations. Do NOT add a question. "
    "- packing: ONLY packing advice. Do NOT list attractions or destinations. Do NOT add a question. "
    "- attractions: ONLY local attractions. Keep concise. Do NOT add a question. "
    "- support: Offer a brief (1–2 sentences) friendly invitation to share trip details; do NOT propose destinations. If previous intent was support, ask at most one short clarifying question only when essential, and avoid repeating the same question across turns. "
    "- end: Acknowledge politely in one short sentence and do not ask any follow-up questions. "
    "- meta: ONLY summarize known context (city, dates/month, last intent). Do NOT add a question. "
    "Only ask a question in support intent and only if critical details are missing. Never append trailing questions to lists or summaries. "
    "You will receive PRIVATE context lines (prefixed 'Private context:' and 'Private data:'). Never reveal or quote these lines verbatim. Do not print them back to the user. Use them to avoid re-asking for details already known. "
    "If you used live weather data in private data, treat it as authoritative and do not contradict it. Mention briefly 'based on live data' without revealing exact numbers unless asked. "
    "If you don't know or lack access to live information, say so clearly (e.g., 'I don't have live data for that yet') rather than guessing. Think step by step privately. If unsure or contradictions arise, restate known context succinctly in your own words without adding a question. "
    "Use concise bullet points when helpful. Output only the final answer."
)


def tool_facts_line(session: Session):
    """Return precomputed weather 'Tool facts' line if present on the session."""
    if getattr(session, "_tool_facts", None):
        return session._tool_facts
    return None


def context_header(session: Session):
    """Build a compact 'Context: ...' line from known slots for private use in system prompt."""
    parts = []
    s = session.slots
    parts.append(f"city={s.city or '?'}")
    if s.start_date and s.end_date:
        parts.append(f"{s.start_date}→{s.end_date}")
    elif s.month:
        try:
            season = month_to_season(int(s.month), s.lat)
            parts.append(f"month={s.month}({season})")
        except Exception:
            parts.append(f"month={s.month}")
    if s.interests:
        parts.append(f"interests={s.interests}")
    if s.budget_hint:
        parts.append(f"budget={s.budget_hint}")
    if s.kid_friendly is not None:
        parts.append(f"kid={str(s.kid_friendly).lower()}")
    if s.last_intent:
        parts.append(f"intent={s.last_intent}")
    return "Context: " + " ".join(parts)


def destination_prompt(session: Session, user_text: str):
    """Instruction asking for three destination ideas with one-line reasons, no follow-up question."""
    return (
        "Task: Suggest three destination options that fit the context. Give one-line reasons. "
        "Do not add any follow-up question.\n"
        f"User: {user_text}"
    )


def packing_prompt(session: Session, user_text: str):
    """Instruction for concise packing lists; aligns with private live-weather data if available."""
    return (
        "Task: Provide must-have, nice-to-have, and activity-specific packing lists. Keep lines short. "
        "If private live-weather data exists, align with it. Do not add any follow-up question.\n"
        f"User: {user_text}"
    )


def attractions_prompt(session: Session, user_text: str):
    """Instruction enforcing exactly three non-food attraction bullets; add an indoor option if relevant."""
    return (
        "Task: Immediately output exactly three concise non-food attraction ideas as bullet points (unless the user explicitly asked for food). "
        "Prefer activities that fit likely weather if private live-weather data exists. Include one indoor/rainy option. "
        "Include a kid-friendly pick only if relevant. Do not add any follow-up question. "
        "Do not include any intro text or headings before the bullets.\n"
        f"User: {user_text}"
    )


def weather_prompt(session: Session, user_text: str):
    """Instruction for brief weather summary; rely on private tool data; do not invent numbers without data."""
    return (
        "Task: Briefly summarize likely weather for the given city and dates/month. "
        "Include: temp range (°C), rain chance, and 1‑2 packing tips. Do not suggest destinations. "
        "If private live-weather data is present, rely on it and do not invent additional figures. If dates or city are unknown or no private data exists, state that you don't have live data and do not add any follow‑up question.\n"
        f"User: {user_text}"
    )


def support_prompt(session: Session, user_text: str):
    """Short, warm reply; ask at most one concise clarifying question only when essential."""
    s = session.slots
    known = []
    if s.city:
        known.append(f"city={s.city}")
    if s.start_date and s.end_date:
        known.append(f"dates={s.start_date}→{s.end_date}")
    elif s.month:
        known.append(f"month={s.month}")
    known_str = ", ".join(known)
    base = (
        "Task: Respond in 1–2 short sentences. Be warm and helpful. "
        "Acknowledge friendly smalltalk naturally. Do NOT repeat any self‑introduction. "
        "Avoid re-asking for details already known from private context. "
        "Do NOT give unsolicited suggestions, tips, weather, or packing advice unless the user asked. "
    )
    low = (user_text or "").lower()
    gratitude = any(t in low for t in ["thanks", "thank you", "thx", "tnx", "thank u", "appreciated"]) and not any(k in low for k in ["city", "date", "weather", "pack", "attraction", "place", "recommend"])
    if gratitude:
        return (
            "Task: Briefly acknowledge the thanks (one short sentence), offer help if needed, and do not ask a question."
        )
    if known_str:
        base += f"Offer one short, trip-focused question or next step for ({known_str})."
    else:
        base += "Ask ONE concise trip question (city and dates)."
    return base


def meta_prompt(session: Session, user_text: str):
    """Summarize only known context values (city, dates/month, last intent); no extra suggestions."""
    s = session.slots
    parts = []
    parts.append(f"city={s.city or '?'}")
    if s.start_date and s.end_date:
        parts.append(f"{s.start_date}→{s.end_date}")
    elif s.month:
        try:
            season = month_to_season(int(s.month), s.lat)
            parts.append(f"month={s.month}({season})")
        except Exception:
            parts.append(f"month={s.month}")
    if s.country:
        parts.append(f"country={s.country}")
    if s.last_intent:
        parts.append(f"last_intent={s.last_intent}")
    ctx = "Context: " + " ".join(parts)
    return (
        f"{ctx}\n"
        "Task: Summarize ONLY the known context above (city, dates/month, last intent). "
        "If a value is unknown, say 'unknown'. Do not add suggestions or extra info.\n"
        f"User: {user_text}"
    )


