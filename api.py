from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from assistant.session import Session
from assistant.router import detect_intent, update_slots_from_text, is_smalltalk, has_weather_hint
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
from assistant.postprocess import limit_attractions_to_three
from assistant.tools.weather import geocode_city, fetch_weather, summarize_weather
from llm.client import call_llm


app = FastAPI(title="Navan Travel Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str
    message: str


SESSIONS: dict[str, Session] = {}


def get_session(session_id: str) -> Session:
    sess = SESSIONS.get(session_id)
    if not sess:
        sess = Session()
        SESSIONS[session_id] = sess
    return sess


def _maybe_weather(session: Session) -> None:
    try:
        s = session.slots
        if not (s.city and s.start_date and s.end_date):
            return
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
        pass


def _build_weather_reply(session: Session) -> str:
    try:
        _maybe_weather(session)
    except Exception:
        pass
    tf = getattr(session, "_tool_facts", None)
    city = session.slots.city or "the city"
    when = f"{session.slots.start_date}→{session.slots.end_date}" if (session.slots.start_date and session.slots.end_date) else (session.slots.month or "your dates")
    if not tf:
        return f"I don't have live weather details for {city} ({when}) yet. Please confirm city and dates."
    
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


@app.post("/api/chat")
def chat(req: ChatRequest):
    sess = get_session(req.session_id)
    user = (req.message or "").strip()
    if not user:
        return JSONResponse({"reply": ""})

    sess.add("user", user)
    update_slots_from_text(user, sess)

    prev_intent = sess.slots.last_intent
    detected = detect_intent(user)
    if has_weather_hint(user):
        detected = "weather"
    if is_smalltalk(user):
        intent = "support"
    else:
        intent = prev_intent if (detected == "neutral" and prev_intent) else detected
    if intent in {"destination", "packing", "attractions", "weather"}:
        sess.slots.last_intent = intent

    private_lines = []
    try:
        cf_line = context_header(sess)
        if cf_line:
            private_lines.append(f"Private context: {cf_line}")
        if intent in {"weather", "packing", "attractions"}:
            tf_line = tool_facts_line(sess)
            if tf_line:
                private_lines.append(f"Private data: {tf_line}")
    except Exception:
        pass

    if intent == "packing":
        _maybe_weather(sess)
        prompt = packing_prompt(sess, user)
    elif intent == "attractions":
        _maybe_weather(sess)
        prompt = attractions_prompt(sess, user)
    elif intent == "destination":
        prompt = destination_prompt(sess, user)
    elif intent == "meta":
        prompt = meta_prompt(sess, user)
    elif intent == "weather":
        _maybe_weather(sess)
        reply = _build_weather_reply(sess)
        sess.add("assistant", reply)
        return {"reply": reply}
    elif intent == "support":
        prompt = support_prompt(sess, user)
    elif intent == "end":
        prompt = "Task: Acknowledge politely in one short sentence. Do not ask any questions."
    else:
        prompt = support_prompt(sess, user)

    history_turns = int(os.getenv("HISTORY_TURNS", "6"))
    history = sess.recent_history(history_turns)
    sysmsg = SYSTEM_PROMPT
    if private_lines:
        sysmsg = sysmsg + "\n" + "\n".join(private_lines)
    reply = call_llm(sysmsg, prompt, history=history)
    if intent == "attractions" and isinstance(reply, str):
        processed = limit_attractions_to_three(reply, user)
        reply = processed
    sess.add("assistant", reply)
    return {"reply": reply}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)
