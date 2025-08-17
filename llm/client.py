"""
llm/client.py

DeepSeek-only LLM client.
- Provides a single entrypoint: call_llm(system_prompt, user_prompt, history=None)
- Sends a chat completion request to DeepSeek's API
- History is a list of {'role': 'user'|'assistant', 'content': str}

Environment variables:
- LLM_PROVIDER       (deepseek | ollama) default deepseek
- DEEPSEEK_API_URL   (default: https://api.deepseek.com)
- DEEPSEEK_API_KEY   (required for deepseek)
- DEEPSEEK_MODEL     (default: deepseek-chat)
- OLLAMA_BASE_URL    (default: http://localhost:11434)
- OLLAMA_MODEL       (default: qwen2.5:3b)
- DEEPSEEK_OFFLINE   (set to 1/true to stub responses without calling the API)
"""

import os
import requests


def call_llm(system_prompt, user_prompt, history=None):
    """
    Call an LLM with system + user prompts and optional history.
    Provider is selected by LLM_PROVIDER env: 'deepseek' (default) or 'ollama'.

    Args:
        system_prompt: Persistent system instruction (str)
        user_prompt: Per-turn prompt constructed by the orchestrator (str)
        history: List of past messages as dicts: {'role': 'user'|'assistant', 'content': str}

    Returns:
        Model response text (str), trimmed.
    """
    provider = os.getenv("LLM_PROVIDER", "deepseek").strip().lower()
    offline = os.getenv("DEEPSEEK_OFFLINE", "").strip().lower() in {"1", "true", "yes"}

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    if offline:
        preview = (user_prompt or "").strip().splitlines()[0][:120]
        return f"[offline] {preview}" if preview else "[offline] OK"

    if provider == "ollama":
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
        try:
            resp = requests.post(
                f"{base}/api/chat",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
                json={"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 512}},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            content = (data.get("message") or {}).get("content", "")
            return (content or "").strip()
        except requests.HTTPError as http_err:
            status = getattr(http_err.response, "status_code", None)
            try:
                msg = http_err.response.json().get("error") or http_err.response.text
            except Exception:
                msg = http_err.response.text if getattr(http_err, "response", None) else None
            hint = "Is Ollama running? Start it with 'ollama serve' and pull a model, e.g., 'ollama pull qwen2.5:3b'."
            if status:
                return f"Ollama error (HTTP {status}). {msg or ''} {hint}".strip()
            return f"Ollama connection failed. {hint}"
        except Exception:
            return "Unable to reach Ollama at OLLAMA_BASE_URL. Ensure the daemon is running (ollama serve)."

    # Default: DeepSeek
    base = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com")
    key = os.getenv("DEEPSEEK_API_KEY", "")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    endpoint = f"{base.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}

    try:
        resp = requests.post(
            endpoint,
            headers=headers,
            json={"model": model, "messages": messages, "temperature": 0.3},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        return (content or "").strip()
    except requests.HTTPError as http_err:
        status = getattr(http_err.response, "status_code", None)
        return f"DeepSeek error (HTTP {status}). Check DEEPSEEK_API_KEY or try LLM_PROVIDER=ollama."
    except Exception:
        return "Network issue while contacting the model. Please try again shortly."
