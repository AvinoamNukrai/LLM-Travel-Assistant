"""
assistant/postprocess.py

Reply post-processing utilities applied after model generation.

Functions:
- limit_attractions_to_three(text, user_text=None):
  Normalizes a reply to exactly three attraction ideas. Prefers bullet-like items; otherwise
  harvests sentences and filters out questions and irrelevant lines. Avoids food ideas unless user asked.
"""

from __future__ import annotations


def limit_attractions_to_three(text: str, user_text: str | None = None) -> str:
    """Normalize a reply to exactly three attraction items.

    Strategy:
    - Prefer bullet-like lines; strip markers and keep first three (filter food unless asked).
    - If no bullets, harvest sentences from paragraphs and filter questions/irrelevant lines.
    - Ensure exactly three by padding last item if needed.
    """
    lines = text.splitlines()
    bullet_idxs: list[int] = []
    ideas: list[str] = []
    nonbullet_fragments: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            continue
        is_bullet = False
        if stripped.startswith(("-", "*", "•", "–", "—")):
            is_bullet = True
        elif stripped[0].isdigit() and (len(stripped) > 1 and stripped[1] in ")."):
            is_bullet = True
        if is_bullet:
            bullet_idxs.append(i)
            content = stripped.lstrip("-*•–— ")
            if content and content[0].isdigit() and len(content) > 1 and content[1] in ").":
                content = content[2:].lstrip()
            ideas.append(content.strip())
        else:
            nonbullet_fragments.append(stripped)

    ut = (user_text or "").lower()
    user_asked_food = ("food" in ut) or ("restaurant" in ut)
    if len(ideas) >= 3:
        filtered = ideas if user_asked_food else [s for s in ideas if not _mentions_food(s)]
        chosen = (filtered[:3] if len(filtered) >= 3 else ideas[:3])
        return "\n".join(f"- {s}" for s in chosen).rstrip()

    import re as _re
    extra_text = " ".join(nonbullet_fragments).strip()
    if extra_text:
        sentences = [s.strip() for s in _re.split(r"(?<=[.!?])\s+", extra_text) if s.strip()]
        def good(s: str) -> bool:
            low = s.lower()
            if "?" in s:
                return False
            if any(p in low for p in ["here are", "based on", "summary", "weather", "packing"]):
                return False
            return True
        for s in sentences:
            if len(ideas) >= 3:
                break
            if good(s) and s not in ideas:
                ideas.append(s)

    if not ideas:
        return "- (no ideas available)\n- (no ideas available)\n- (no ideas available)"
    non_food = ideas if user_asked_food else [s for s in ideas if not _mentions_food(s)]
    chosen = non_food or ideas
    while len(chosen) < 3:
        chosen.append(chosen[-1])
    return "\n".join(f"- {s}" for s in chosen[:3]).rstrip()


def _mentions_food(text: str) -> bool:
    low = text.lower()
    food_kw = ["food", "restaurant", "cuisine", "eat", "trattoria", "pizzeria", "gelato", "market", "street food"]
    return any(k in low for k in food_kw)


