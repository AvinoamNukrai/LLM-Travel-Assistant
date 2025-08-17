# Travel Assistant (CLI)

Minimal, conversation‑first travel assistant focusing on prompt engineering and conversational quality. Uses a free LLM (DeepSeek by default; Ollama supported) and one external API (Open‑Meteo) for weather.

## Quick start

1) Install deps:
```
pip install -r requirements.txt
```

2) Environment (DeepSeek or Ollama):
```
export DEEPSEEK_API_KEY=sk-...
export DEEPSEEK_MODEL=deepseek-chat
export HISTORY_TURNS=6
export HTTP_TIMEOUT=8
# Optional: use Ollama locally instead of DeepSeek
export LLM_PROVIDER=ollama
export OLLAMA_MODEL=qwen2.5:3b
export OLLAMA_BASE_URL=http://localhost:11434
```

3) Run CLI:
```
python -m app.cli
```

## What it does
- Handles three intents: destination, packing, attractions (plus meta/support)
- Maintains context via slots (city, dates/month, interests, kid flag, budget hint, etc.)
- Fetches weather from Open‑Meteo when dates/city known, and blends a concise "Tool facts" line (also influences attractions)
- Uses private chain‑of‑thought (internal) and outputs concise final answers only

## Transcripts
Each run creates a timestamped file under `transcripts/` that logs the conversation (user and assistant turns) for evaluation.

## Sample prompts
- "Surf near Europe in October, budget friendly"
- "What to pack for Rome Sep 10 to Sep 14?"
- "Things to do in London on Saturday with a stroller"
