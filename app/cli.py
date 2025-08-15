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

from core.session import Session
from core.router import detect_intent, update_slots_from_text
from core.prompts import SYSTEM_PROMPT, destination_prompt, packing_prompt, attractions_prompt
from llm.client import call_llm
from tools.weather import geocode_city, fetch_weather, summarize_weather


HISTORY_TURNS = int(os.getenv("HISTORY_TURNS", "6"))


def _maybe_weather(session):
    """
    If we have a city and concrete dates, ensure coordinates and fetch weather.
    Store a compressed summary line in the session for prompt blending.
    """
    s = session.slots
    if s.city and s.start_date and s.end_date:
        # ensure coords
        if s.lat is None or s.lon is None:
            geo = geocode_city(s.city)
            if geo:
                session.slots.city = geo.name
                session.slots.country = geo.country
                session.slots.lat, session.slots.lon = geo.lat, geo.lon
        if session.slots.lat is not None and session.slots.lon is not None:
            w = fetch_weather(session.slots.lat, session.slots.lon, s.start_date, s.end_date)
            if w:
                session._tool_facts = summarize_weather(s.city or "", s.start_date, s.end_date, w)


def main():
    """Run the interactive CLI loop."""
    print("Travel Assistant (type 'exit' to quit)\n")
    sess = Session()
    while True:
        user = input("You: ").strip()
        if not user:
            continue
        if user.lower() in {"exit", "quit"}:
            print("Bye!")
            break

        sess.add("user", user)
        update_slots_from_text(user, sess)

        intent = detect_intent(user)
        sess.slots.last_intent = intent

        if intent == "packing":
            _maybe_weather(sess)
            prompt = packing_prompt(sess, user)
        elif intent == "attractions":
            prompt = attractions_prompt(sess, user)
        else:
            prompt = destination_prompt(sess, user)

        history = sess.recent_history(HISTORY_TURNS)
        reply = call_llm(SYSTEM_PROMPT, prompt, history=history)
        print(f"Assistant: {reply}\n")
        sess.add("assistant", reply)


if __name__ == "__main__":
    main()
