
![WhatsApp Image 2025-08-18 at 00 05 15](https://github.com/user-attachments/assets/e27d8809-f5d9-41bd-9387-3fcaf8974ee7)



How to Run the Program: 

Running the chat in the Terminal: 
LLM_PROVIDER=ollama OLLAMA_MODEL=llama3.1:8b python3 -m app.cli



Running the web page:
run this command for the backend (first terminal): 
    export LLM_PROVIDER=ollama
    export OLLAMA_MODEL=llama3.1:8b
    python3 api.py

run this command for the frontend from the 'web' folder (second terminal): 
    npm run dev



Key prompt-engineering choices:

- System guardrails and privacy: Per-intent rules, a one-time intro, and “don’t echo private lines” keep replies tightly scoped, prevent leakage, and avoid question spam or drift.
- Private context injection: Compact Context: and Tool facts: are added only to the system message so the model uses memory/live data without exposing it, reducing re-asking and keeping responses focused.
- Intent-specific prompts with strict formats: Clear scopes per intent—attractions = exactly three bullets (with an indoor option), meta = context-only, support = minimal/one question max—produce consistent, concise outputs that match UX expectations.
- Deterministic weather answers: Tool-first synthesis from live data, with an explicit “no live data” message when missing, treats tool output as authoritative to avoid hallucinated numbers and keep guidance reliable.
- Ambiguity handling (e.g., “nice”): City extraction prioritizes prepositions/verbs and known aliases, blocks weak adjective fallbacks, and confirms via geocoding before setting—disambiguating compliments from locations and preventing false positives.
- Smalltalk/gratitude routing: Short acknowledgments without suggestions, and weather hints that override routing, keep conversations on track while remaining polite and responsive.
- Post-processing enforcement: Normalizing attractions to three non-food items (unless food is requested) guarantees the exact output shape even if the model deviates.
- Memory and stability: Structured slots, last_intent persistence on neutral turns, and bounded recent history preserve essential context without bloating prompts and reduce intent thrashing.
- Stable generation: Low temperature and capped output make behavior predictable and reproducible across turns.



See the simple_example.pdf file for the full example chat!
