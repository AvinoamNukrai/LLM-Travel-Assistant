"""
core/prompts.py

Prompt templates and helpers.
- SYSTEM_PROMPT: concise, context-aware travel planner behavior
- destination_prompt / packing_prompt / attractions_prompt: per-intent prompts
- context_header / tool_facts_line: compact lines prepended to user prompt
"""

from core.session import Session


SYSTEM_PROMPT = (
    "You are a helpful, concise travel planner. Maintain context across turns. "
    "Ask at most one targeted follow-up when a critical detail is missing. "
    "If you used live weather data, briefly mention that. Think step by step privately. "
    "Output only the final answer in a clean, concise format."
)


def tool_facts_line(session):
    """Return the precomputed 'Tool facts' line if present and relevant."""
    if getattr(session, "_tool_facts", None):
        return session._tool_facts
    return None


def context_header(session):
    """Build a compact 'Context: ...' header from known slots."""
    parts = []
    s = session.slots
    parts.append(f"city={s.city or '?'}")
    if s.start_date and s.end_date:
        parts.append(f"{s.start_date}→{s.end_date}")
    elif s.month:
        parts.append(f"month={s.month}")
    if s.interests:
        parts.append(f"interests={s.interests}")
    if s.budget_hint:
        parts.append(f"budget={s.budget_hint}")
    if s.kid_friendly is not None:
        parts.append(f"kid={str(s.kid_friendly).lower()}")
    return "Context: " + " ".join(parts)


def destination_prompt(session, user_text):
    cf = context_header(session)
    return (
        f"{cf}\n"
        "Task: Suggest three destination options that fit the context. "
        "Give one-line reasons. If a critical detail is missing, ask one clarifying question at the end.\n"
        f"User: {user_text}"
    )


def packing_prompt(session, user_text):
    cf = context_header(session)
    tf = tool_facts_line(session)
    tf_line = (tf + "\n") if tf else ""
    return (
        f"{cf}\n"
        f"{tf_line}"
        "Task: Provide must-have, nice-to-have, and activity-specific packing lists. "
        "Keep lines short. Include the brief weather line above only once.\n"
        f"User: {user_text}"
    )


def attractions_prompt(session, user_text):
    cf = context_header(session)
    return (
        f"{cf}\n"
        "Task: List five concise ideas. Include one indoor/rainy option. Include a kid-friendly pick only if relevant.\n"
        f"User: {user_text}"
    )
