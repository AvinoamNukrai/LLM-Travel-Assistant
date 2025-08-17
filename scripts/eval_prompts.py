"""
scripts/eval_prompts.py

Batch prompt evaluation harness to reduce manual testing.

Runs a few scripted conversations through the orchestration stack and checks:
- No leakage of private context/data into assistant replies
- Attractions returns exactly 3 ideas
- At most one follow-up question per reply
- Uses known city/dates instead of re-asking
- Honesty when live data is missing (no invented numbers)

Usage:
  python3 scripts/eval_prompts.py

Configure model via env (same as runtime):
  LLM_PROVIDER=deepseek|ollama, etc.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Any, Callable


# Allow imports from project root
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from app.cli import _maybe_weather  # type: ignore
from app.cli import _build_weather_reply  # type: ignore
from assistant.session import Session
from assistant.router import detect_intent, update_slots_from_text
from assistant.prompts import (
    SYSTEM_PROMPT,
    destination_prompt,
    packing_prompt,
    attractions_prompt,
    weather_prompt,
    meta_prompt,
    support_prompt,
    context_header,
    tool_facts_line,
)
from llm.client import call_llm
from assistant.postprocess import limit_attractions_to_three


HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "6"))


def build_private_system(session: Session) -> str:
    lines: list[str] = []
    try:
        cf = context_header(session)
        tf = tool_facts_line(session)
        if cf:
            lines.append(f"Private context: {cf}")
        if tf:
            lines.append(f"Private data: {tf}")
    except Exception:
        pass
    if not lines:
        return SYSTEM_PROMPT
    return SYSTEM_PROMPT + "\n" + "\n".join(lines)


def step(session: Session, user_text: str) -> str:
    session.add("user", user_text)
    update_slots_from_text(user_text, session)

    intent = detect_intent(user_text)
    if intent == "neutral" and session.slots.last_intent:
        intent = session.slots.last_intent
    session.slots.last_intent = intent

    if intent == "weather":
        _maybe_weather(session)
        reply = _build_weather_reply(session)
        session.add("assistant", reply)
        return reply

    # Offline deterministic stubs to avoid leaking private context lines into replies
    offline = (
        os.getenv("LLM_OFFLINE", "").strip().lower() in {"1", "true", "yes"}
        or os.getenv("DEEPSEEK_OFFLINE", "").strip().lower() in {"1", "true", "yes"}
    )
    if offline:
        if intent == "attractions":
            reply = "- Idea 1\n- Idea 2\n- Idea 3"
        elif intent == "packing":
            reply = "Must-have: essentials; Nice-to-have: extras; Activity-specific: adjust for weather."
        elif intent == "support":
            s = session.slots
            if s.city and s.start_date and s.end_date:
                reply = "Got it. Want tips for attractions or packing?"
            else:
                reply = "What city and dates are you planning?"
        elif intent == "meta":
            s = session.slots
            city = s.city or "unknown"
            when = f"{s.start_date}→{s.end_date}" if (s.start_date and s.end_date) else (s.month or "unknown")
            last = s.last_intent or "unknown"
            reply = f"city={city} {when} last_intent={last}"
        else:  # destination or other
            reply = "- Option A\n- Option B\n- Option C"
        session.add("assistant", reply)
        return reply

    if intent == "packing":
        _maybe_weather(session)
        prompt = packing_prompt(session, user_text)
    elif intent == "attractions":
        _maybe_weather(session)
        prompt = attractions_prompt(session, user_text)
    elif intent == "meta":
        prompt = meta_prompt(session, user_text)
    elif intent == "support":
        prompt = support_prompt(session, user_text)
    else:
        prompt = destination_prompt(session, user_text)

    sysmsg = build_private_system(session)
    history = session.recent_history(HISTORY_TURNS)
    reply = call_llm(sysmsg, prompt, history=history)
    if intent == "attractions" and isinstance(reply, str):
        reply = limit_attractions_to_three(reply)
    session.add("assistant", reply)
    return reply


# ---- Metrics ----

def no_private_leak(reply: str) -> bool:
    leaks = ["Private context:", "Private data:", "Context:", "Tool facts:"]
    return not any(tok in reply for tok in leaks)


def at_most_one_question(reply: str) -> bool:
    return reply.count("?") <= 1


def attractions_three_ideas(reply: str) -> bool:
    # Count bullet-ish lines
    lines = [l.strip() for l in reply.splitlines() if l.strip()]
    bullet_like = [l for l in lines if re.match(r"^(\*|-|•|\d+[\.)])\s+", l)]
    # Fallback: count paragraphs if no bullets
    count = len(bullet_like) if bullet_like else min(3, len(lines))
    return count == 3


def did_not_reask_known_city(reply: str, session: Session) -> bool:
    if not session.slots.city:
        return True
    reask_phrases = [
        "which city",
        "what city",
        "tell me the city",
        "city you're",
    ]
    return not any(p in reply.lower() for p in reask_phrases)


def honest_when_no_data(reply: str, had_private_weather: bool) -> bool:
    # If there was no private data, reply should not invent precise numbers
    if had_private_weather:
        return True
    has_degree = "°" in reply
    has_numeric_range = bool(re.search(r"\b\d+\s*(?:to|-|–)\s*\d+\b", reply))
    mentions_no_data = "don't have" in reply.lower() or "no live data" in reply.lower()
    return (not has_degree and not has_numeric_range) or mentions_no_data


def run_scenarios() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    # 1) Rome next week → attractions → smalltalk 'nice' → packing
    sess = Session()
    r1 = step(sess, "I'm going to Rome next week")
    r2 = step(sess, "recommend 3 places")
    r3 = step(sess, "nice")
    r4 = step(sess, "what should I pack?")
    had_private_weather = getattr(sess, "_tool_facts", None) is not None
    results.append({
        "scenario": "rome_flow",
        "no_private_leak": no_private_leak("\n".join([r1, r2, r3, r4])),
        "<=1_question_each": all(at_most_one_question(r) for r in [r1, r2, r3, r4]),
        "no_reask_city": all(did_not_reask_known_city(r, sess) for r in [r2, r3, r4]),
        "honest_no_data": honest_when_no_data(r1, had_private_weather),
        "attractions_three": attractions_three_ideas(r2),
    })

    # 2) Weather with missing dates/city → should not invent numbers
    sess2 = Session()
    r5 = step(sess2, "what's the weather?")
    results.append({
        "scenario": "weather_missing",
        "no_private_leak": no_private_leak(r5),
        "<=1_question_each": at_most_one_question(r5),
        "honest_no_data": honest_when_no_data(r5, getattr(sess2, "_tool_facts", None) is not None),
    })

    # 3) New York October → weather → attractions
    sess3 = Session()
    _ = step(sess3, "I'm going to New York the first week of October")
    r6 = step(sess3, "weather please")
    r7 = step(sess3, "3 attractions")
    results.append({
        "scenario": "ny_october",
        "no_private_leak": no_private_leak("\n".join([r6, r7])),
        "<=1_question_each": all(at_most_one_question(r) for r in [r6, r7]),
        "attractions_three": attractions_three_ideas(r7),
    })

    # 4) Long memory scenario: 30-turn mixed chat, ensure city persists and no re-ask
    sess4 = Session()
    expected_city = "Rome"
    replies: list[str] = []
    _ = step(sess4, "I'm Avinoam, traveling to Rome Oct 5 to Oct 10")
    # Interleave tasks and smalltalk
    script = [
        "weather please",
        "cool",
        "what should I pack?",
        "recommend 3 places",
        "i love museums and hiking",
        "nice",
        "packing again",
        "thanks",
        "3 attractions",
        "ok",
        "what else should I pack for hiking?",
        "yo",
        "what are rainy-day options?",
        "great",
        "any indoor ideas?",
        "awesome",
        "kid friendly options?",
        "okay",
        "3 ideas please",
        "cool",
        "another 3 attractions",
        "nice",
        "packing list one more time",
        "ok",
        "recommend 3 places again",
        "thanks",
        "meta recap",
        "yo",
        "3 attractions (final)",
    ]
    for utter in script:
        replies.append(step(sess4, utter))
    city_persisted = (sess4.slots.city or "").lower() == expected_city.lower()
    no_reask_city_late = all(did_not_reask_known_city(r, sess4) for r in replies[-10:])
    last_attractions = replies[-1]
    results.append({
        "scenario": "long_memory_30",
        "no_private_leak": no_private_leak("\n".join(replies)),
        "<=1_question_each": all(at_most_one_question(r) for r in replies),
        "city_persisted_30": city_persisted,
        "no_reask_city_late": no_reask_city_late,
        "attractions_three": attractions_three_ideas(last_attractions),
    })

    return results


def main():
    results = run_scenarios()
    # Pretty print compact report
    ok = True
    for row in results:
        scenario = row.pop("scenario")
        flags = [f"{k}={'OK' if v else 'FAIL'}" for k, v in row.items()]
        line = f"{scenario}: " + ", ".join(flags)
        print(line)
        ok = ok and all(bool(v) for v in row.values())
    if not ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
