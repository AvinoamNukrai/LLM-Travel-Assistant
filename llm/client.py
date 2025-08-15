"""
llm/client.py

DeepSeek-only LLM client.
- Provides a single entrypoint: call_llm(system_prompt, user_prompt, history=None)
- Sends a chat completion request to DeepSeek's API
- History is a list of {'role': 'user'|'assistant', 'content': str}

Environment variables:
- DEEPSEEK_API_URL  (default: https://api.deepseek.com)
- DEEPSEEK_API_KEY  (required)
- DEEPSEEK_MODEL    (default: deepseek-chat)
"""

import os
import requests


def call_llm(system_prompt, user_prompt, history=None):
    """
    Call the DeepSeek chat API with system + user prompts and optional history.

    Args:
        system_prompt: Persistent system instruction (str)
        user_prompt: Per-turn prompt constructed by the orchestrator (str)
        history: List of past messages as dicts: {'role': 'user'|'assistant', 'content': str}

    Returns:
        Model response text (str), trimmed.
    """
    base = os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com")
    key = os.getenv("DEEPSEEK_API_KEY", "")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_prompt})

    resp = requests.post(
        f"{base}/chat/completions",
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
