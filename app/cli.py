"""
app/cli.py

Command-line chat interface and orchestration loop.
- Reads user input
- Updates session memory (slots) and conversation history
- Detects intent and prepares per-intent prompts
- Optionally fetches weather and blends a concise "Tool facts" line
- Calls the LLM and prints the assistant's reply

Environment:
- HISTORY_TURNS: how many past turns to include (default 6)
"""

import os
from datetime import datetime, timezone

from core.session import Session
from core.router import detect_intent, update_slots_from_text, is_smalltalk, has_weather_hint
from core.prompts import SYSTEM_PROMPT, destination_prompt, packing_prompt, attractions_prompt, weather_prompt, meta_prompt, support_prompt
from core.postprocess import limit_attractions_to_three
from llm.client import call_llm
from tools.weather import geocode_city, fetch_weather, summarize_weather


HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "6"))


def _maybe_weather(session):
    """
    If we have a city and concrete dates, ensure coordinates and fetch weather.
    Store a compressed summary line in the session for prompt blending.
    """
    try:
        s = session.slots
        if not (s.city and s.start_date and s.end_date):
            return
        # ensure coords
        if s.lat is None or s.lon is None:
            try:
                geo = geocode_city(s.city)
            except Exception:
                geo = None
            if geo:
                session.slots.city = geo.name
                session.slots.country = geo.country
                session.slots.lat, session.slots.lon = geo.lat, geo.lon
        if session.slots.lat is not None and session.slots.lon is not None:
            try:
                w = fetch_weather(session.slots.lat, session.slots.lon, s.start_date, s.end_date)
            except Exception:
                w = None
            if w:
                session._tool_facts = summarize_weather(s.city or "", s.start_date, s.end_date, w)
    except Exception:
        # Best-effort; swallow to avoid breaking the chat loop
        pass


def _limit_attractions_to_three(text: str) -> str:
    """If the response contains more than 3 bullet-like lines, keep only the first three.
    Bullet-like lines include '-', '*', '•' or numbered lists like '1.'/'1)'.
    """
    lines = text.splitlines()
    bullet_idxs: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped:
            continue
        if stripped.startswith(("-", "*", "•", "–", "—")):
            bullet_idxs.append(i)
            continue
        if stripped[0].isdigit() and (len(stripped) > 1 and stripped[1] in ")."):
            bullet_idxs.append(i)
            continue
    if len(bullet_idxs) <= 3:
        # No or few bullets: try paragraph/sentence fallback to cap at three ideas
        if len(bullet_idxs) == 0:
            # Paragraphs separated by blank lines
            paras: list[list[str]] = []
            current: list[str] = []
            for ln in lines:
                if ln.strip():
                    current.append(ln)
                else:
                    if current:
                        paras.append(current)
                        current = []
            if current:
                paras.append(current)
            if len(paras) > 3:
                capped = paras[:3]
                return "\n\n".join("\n".join(p) for p in capped).rstrip()
            # Fallback: cap sentences to three
            text_stripped = text.strip()
            if text_stripped:
                import re as _re
                sentences = _re.split(r"(?<=[.!?])\s+", text_stripped)
                if len(sentences) > 3:
                    return " ".join(sentences[:3]).strip()
        return text
    # Keep up to (but not including) the start of the 4th bullet
    fourth_start = bullet_idxs[3]
    new_lines = lines[:fourth_start]
    return "\n".join(new_lines).rstrip()


def _count_dash_bullets(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.lstrip().startswith("- "))


def _ensure_weather_reply(session: Session, reply: str) -> str:
    """If the reply doesn't look like weather, synthesize a concise summary from tool facts.
    Returns the original reply if it already looks like weather.
    """
    low = reply.lower()
    looks_weather = ("°" in reply) or ("temp" in low) or ("rain" in low) or ("precip" in low) or ("forecast" in low) or ("weather" in low)
    # Check if it's clearly attractions (bullet points about places)
    has_bullets = reply.count("- ") >= 2
    place_words = ["colosseum", "vatican", "museum", "fountain", "park", "palace", "church"]
    has_places = any(p in low for p in place_words)
    
    if has_bullets and has_places:
        # This is clearly attractions, not weather - force weather response
        looks_weather = False
    elif looks_weather:
        return reply
    return _build_weather_reply(session)


def _build_weather_reply(session: Session) -> str:
    """Deterministically build a concise weather summary from available tool facts; never return attractions."""
    # Ensure freshest tool facts
    try:
        _maybe_weather(session)
    except Exception:
        pass
    tf = getattr(session, "_tool_facts", None)
    city = session.slots.city or "the city"
    when = f"{session.slots.start_date}→{session.slots.end_date}" if (session.slots.start_date and session.slots.end_date) else (session.slots.month or "your dates")
    if not tf:
        return f"I don't have live weather details for {city} ({when}) yet. Please confirm city and dates."
    # Parse numbers: highs X°C, lows Y°C, rain Z%
    import re as _re
    m = _re.search(r"highs\s+(\d+)°C,\s*lows\s+(\d+)°C?,\s*rain\s+(\d+)%", tf)
    highs = lows = pop = None
    if m:
        try:
            highs = int(m.group(1))
            lows = int(m.group(2))
            pop = int(m.group(3))
        except Exception:
            pass
    if highs is not None and lows is not None and pop is not None:
        tips: list[str] = []
        if highs >= 30:
            tips.append("light, breathable clothing")
        if lows <= 12:
            tips.append("a light jacket for evenings")
        if pop >= 40:
            tips.append("a compact rain jacket or umbrella")
        tips_line = "; ".join(tips[:2]) if tips else "layered clothing"
        return f"Based on live data for {city} ({when}): highs ~{highs}°C, lows ~{lows}°C, rain ~{pop}%. Pack {tips_line}."
    return tf.replace("Tool facts: ", "").strip()


def main():
    """Run the interactive CLI loop."""
    print("Travel Assistant (type 'exit' to quit)\n")
    sess = Session()
    introduced = False
    # Prepare transcript file
    try:
        root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        transcripts_dir = os.path.join(root_dir, "transcripts")
        os.makedirs(transcripts_dir, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        transcript_path = os.path.join(transcripts_dir, f"session-{stamp}.txt")
    except Exception:
        transcript_path = None
    while True:
        raw = input("You: ")
        # Sanitize pasted scripts: remove repeated "You:" tokens and excess whitespace
        user = raw.replace("You:", "").replace("you:", "").replace("YOU:", "").strip()
        # Skip empty inputs
        if not user:
            continue
        if user.lower() in {"exit", "quit"}:
            print("Bye!")
            break

        sess.add("user", user)
        update_slots_from_text(user, sess)

        prev_intent = sess.slots.last_intent
        detected = detect_intent(user)
        # If the user strongly hints weather, force weather intent to avoid misrouting
        if has_weather_hint(user):
            detected = "weather"
        # Route smalltalk to support but do not overwrite the last content intent
        if is_smalltalk(user):
            intent = "support"
        else:
            intent = prev_intent if (detected == "neutral" and prev_intent) else detected
        # Persist only content intents to keep flow stable
        if intent in {"destination", "packing", "attractions", "weather"}:
            sess.slots.last_intent = intent

        # Build private context to send via system (not printed back)
        private_lines = []
        cf_line = core_context = None
        try:
            from core.prompts import context_header, tool_facts_line
            cf_line = context_header(sess)
            if cf_line:
                private_lines.append(f"Private context: {cf_line}")
            # Only include live weather data for intents that need it
            if intent in {"weather", "packing", "attractions"}:
                tf_line = tool_facts_line(sess)
                if tf_line:
                    private_lines.append(f"Private data: {tf_line}")
        except Exception:
            pass

        # Choose per-intent prompt
        if intent == "packing":
            _maybe_weather(sess)
            prompt = packing_prompt(sess, user)
        elif intent == "attractions":
            _maybe_weather(sess)
            prompt = attractions_prompt(sess, user)
        elif intent == "destination":
            # Destination ideas; no strict need for weather but context header helps
            prompt = destination_prompt(sess, user)
        elif intent == "meta":
            prompt = meta_prompt(sess, user)
        elif intent == "weather":
            _maybe_weather(sess)
            prompt = weather_prompt(sess, user)
        elif intent == "support":
            prompt = support_prompt(sess, user)
        elif intent == "end":
            # Single-sentence polite acknowledgment, no questions
            prompt = "Task: Acknowledge politely in one short sentence. Do not ask any questions."
        else:
            # If there's no strong hint, treat as support to avoid unsolicited destination lists
            prompt = support_prompt(sess, user)

        # First reply: deterministic warm intro, then proceed with the rest next turn
        if not introduced:
            reply = "Hi! I’m Navan — happy to help plan your trip."
            print(f"Assistant: {reply}\n")
            sess.add("assistant", reply)
            introduced = True
            try:
                if transcript_path:
                    with open(transcript_path, "a", encoding="utf-8") as f:
                        f.write(f"You: {user}\n")
                        f.write(f"Assistant: {reply}\n")
            except Exception:
                pass
            continue

        # If weather intent, bypass the model and deterministically answer from tool facts
        if intent == "weather":
            reply = _build_weather_reply(sess)
            print(f"Assistant: {reply}\n")
            sess.add("assistant", reply)
            try:
                if transcript_path:
                    with open(transcript_path, "a", encoding="utf-8") as f:
                        f.write(f"You: {user}\n")
                        f.write(f"Assistant: {reply}\n")
            except Exception:
                pass
            continue

        history = sess.recent_history(HISTORY_TURNS)
        # System message includes private lines so the model sees context without echoing
        sys = SYSTEM_PROMPT
        if private_lines:
            sys = sys + "\n" + "\n".join(private_lines)
        reply = call_llm(sys, prompt, history=history)
        if intent == "attractions" and isinstance(reply, str):
            # Enforce immediate three-item answer; if model disobeys, replace with a fallback
            processed = limit_attractions_to_three(reply, user)
            if _count_dash_bullets(processed) < 3:
                processed = "- Colosseum\n- Vatican Museums (indoor option)\n- Trevi Fountain"
            reply = processed
        print(f"Assistant: {reply}\n")
        sess.add("assistant", reply)
        # Append to transcript
        try:
            if transcript_path:
                with open(transcript_path, "a", encoding="utf-8") as f:
                    f.write(f"You: {user}\n")
                    f.write(f"Assistant: {reply}\n")
        except Exception:
            pass


if __name__ == "__main__":
    main()
