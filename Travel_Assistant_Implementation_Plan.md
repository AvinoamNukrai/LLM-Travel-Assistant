# Travel Assistant — Focused, Minimal, and Scalable Plan

## 1) Scope and Goals
- **Goal**: Build a travel assistant that has natural conversations, uses one free LLM, integrates one external API, and keeps context.
- **Core intents**: destination, packing, attractions.
- **Non-goals**: RAG/vector DB, multiple external APIs, complex UI, user accounts, databases (beyond optional transcript files).

## 2) Definition of Done (DOD)
- **Destination**: Given month and interests, returns three options with one-line reasons; asks one targeted follow-up if a critical detail is missing.
- **Packing**: Given city and dates or month, fetches weather; returns must-have and activity-specific lists; mentions highs, lows, and rain chance in one short line.
- **Attractions**: Given city and day, returns five concise ideas; includes one indoor/rainy alternative; includes a kid-friendly pick only if relevant.
- **Context**: Remembers city, dates or month, interests, kid flag, last intent, coordinates.
- **Error handling**: Resolves ambiguity with a brief question; falls back when tools fail; corrects contradictions by restating known slots and asking to update.

## 3) Minimal Architecture
```
travel_assistant/
  app/
    cli.py                  # chat loop and orchestration
  core/
    session.py              # Slots, Session
    router.py               # intent detection, slot updates
    prompts.py              # system + intent templates
  tools/
    weather.py              # geocoding + forecast from one provider
  llm/
    client.py               # single LLM wrapper (Ollama or DeepSeek)
  util/
    dates.py                # date parsing, month extraction, range clamp
    http.py                 # GET helper with timeout + simple retries
  transcripts/
    samples.md              # curated conversations for submission
  README.md
  requirements.txt
```

## 4) Dependencies
- **Runtime**: Python 3.10+
- **Libraries**: `requests`, `python-dateutil`
- **UI**: CLI (Streamlit one-pager is a stretch)
- **LLM**: Choose one provider (configurable): Ollama (local) or DeepSeek (API)

## 5) Configuration (Environment Variables)
- **Core**:
  - `LLM_PROVIDER` = `ollama` | `deepseek`
  - `HTTP_TIMEOUT` = e.g., `8`
  - `HISTORY_TURNS` = e.g., `6` (cap the number of past turns included in prompts)
- **Ollama**:
  - `OLLAMA_URL` = `http://localhost:11434`
  - `OLLAMA_MODEL` = `llama3` | `qwen2.5` | similar
- **DeepSeek**:
  - `DEEPSEEK_API_URL` = `https://api.deepseek.com`
  - `DEEPSEEK_API_KEY` = `***`
  - `DEEPSEEK_MODEL` = `deepseek-chat` | similar

## 6) Decision Table — Tools vs LLM
- If `city` and exact `start_date/end_date` exist → call weather for that range; blend facts into prompt.
- Else if `city` and `month` exist → call weather for a 7‑day representative window in that month; label as approximate.
- Else → skip tools; answer from LLM knowledge.
- Cache by key: `lat,lon,start,end` (do not call the same range twice in a session).
- "Tool facts" line format (when present):
  - `Tool facts: Rome 2024-09-10→14 | highs 27°C, lows 17°C, rain 20%`

## 7) Session Memory (Slots)
`city, country, start_date, end_date, month, interests, budget_hint, kid_friendly, lat, lon, last_intent`
- Update on each turn. Never ask twice for a filled slot.
- Cap prompt history to the last `HISTORY_TURNS` messages to prevent bloat.

## 8) Routing and Slot Updates
- **Router (rule-first)**: `pack`, `packing` → packing; `see`, `do`, `attractions`, `museum`, `park` → attractions; otherwise destination.
- **LLM fallback**: If rules tie or are low-confidence, ask the LLM to classify intent briefly (or ask a one-line clarifying question).
- **Slot helpers**:
  - Dates: parse one or two dates, convert to ISO, clamp very long ranges.
  - Month: extract month name when no specific dates are found.
  - City: simple heuristic (e.g., token after "in"); if geocoding yields multiple matches, present the top 2–3 to pick from.

## 9) Prompts — Compact, Safe, and CoT-Aware
- **System prompt (always on; example)**:
  "You are a helpful, concise travel planner. Maintain context across turns. Ask at most one targeted follow-up when a critical detail is missing. If you used live weather data, briefly mention that. Think step by step privately. Output only the final answer in a clean, concise format."

- **Chain‑of‑thought policy**:
  - The assistant reasons privately. We encourage internal steps but only display the final answer.
  - Optional developer protocol (hidden): model may produce `REASONING: ...` and `FINAL: ...`; the app will display only `FINAL`.

- **User prompt structure (constructed per turn)**:
  1) Header with known slots (one compact line).
  2) Optional "Tool facts" line if weather was used.
  3) Task text (based on intent).

- **Intent templates (examples)**:
  - Destination:
    - Header: `Context: city=? month=October interests=surf budget=mid kid=?`
    - Task: "Suggest three destination options that fit the context. Give one‑line reasons. If a critical detail is missing, ask one clarifying question at the end."
  - Packing:
    - Header: `Context: city=Rome 2024-09-10→14 interests=food tours`
    - Tool facts (if any): `Tool facts: Rome 2024-09-10→14 | highs 27°C, lows 17°C, rain 20%`
    - Task: "Provide must‑have, nice‑to‑have, and activity‑specific packing lists. Keep lines short. Include the brief weather line above only once."
  - Attractions:
    - Header: `Context: city=London day=Saturday kid_friendly=true`
    - Task: "List five concise ideas. Include one indoor/rainy option. Include a kid‑friendly pick only if relevant."

- **Conciseness guardrails**:
  - Prefer 3–5 bullets per section; aim for ~12–18 words per bullet.
  - Avoid repeated weather mentions and redundant qualifiers.

## 10) Error Handling Behaviors
- **Ambiguity**: Present two likely interpretations in one short sentence; ask the user to pick.
- **Tool failure**: Add a brief disclaimer (“live weather unavailable”), provide a reasonable non-live fallback, invite retry.
- **Contradictions**: Restate known slots in one line; ask whether to update; continue with the corrected state.
- **Long/invalid date ranges**: Clamp or switch to month‑based approximation and label as such.

## 11) Build Steps and Acceptance Checks
1) **Project skeleton**
   - Create folders and empty modules.
   - Accept: imports succeed; CLI entry runs a no‑op loop.
2) **Session and router**
   - Implement `Session`, `Slots`, rule‑based router, slot updaters.
   - Accept: prompts display filled slots after sample inputs.
3) **Weather tool**
   - Geocode via Open‑Meteo; fetch daily forecast; normalize to `{dates, tmax, tmin, pop}`; cache by key.
   - Accept: returns compact dict for valid city and date range.
4) **Prompts**
   - System + three intent templates; include one "Tool facts" line when present; apply conciseness guardrails.
   - Accept: generated prompt strings are compact and deterministic given the same slots.
5) **LLM wrapper**
   - `call_llm(system, user)`; retry once on transient errors; return trimmed string; provider chosen via `LLM_PROVIDER`.
   - Accept: returns a response for simple sample prompts.
6) **Orchestration in CLI**
   - Turn flow: detect intent → update slots → maybe geocode → maybe weather → build prompts → call LLM → print reply; maintain capped history.
   - Accept: end‑to‑end works for three sample inputs; context carries across turns.
7) **Polish**
   - Ensure single targeted follow‑up; weather mention only when used; short outputs.
   - Accept: transcripts read naturally and match DOD.

## 12) Test Plan and Transcripts
- **Unit checks**: router intent selection on varied phrasing; date parser on common formats; weather tool happy path and graceful error path.
- **Transcripts** (add to `transcripts/samples.md`):
  1. Destination — “Surf near Europe in October, budget friendly” → three options, one line each, one follow‑up about budget or flight time.
  2. Packing — “What to pack for Rome Sep 10 to Sep 14” → brief weather line + compact lists.
  3. Attractions — “Things to do in London on Saturday with a stroller” → five ideas; one indoor option; kid‑friendly pick.

## 13) Delivery Checklist
- Minimal, modular code; no unused files.
- README with quick run steps, decision table, prompt rationale.
- Transcripts: three concise sessions showing context and tool blending.
- Clear chain‑of‑thought policy (private reasoning; final answer only).
- No RAG, no second API, no heavy UI.

## 14) Stretch (Only If Time Remains)
- One‑page Streamlit UI that wraps the same orchestration (identical behavior to CLI).
- Small on‑disk transcript log (JSONLines) for later review.
