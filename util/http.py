"""
util/http.py

Tiny HTTP helper for JSON GET with simple retries.
- Timeout can be configured via HTTP_TIMEOUT env (default 8s)
- Raises for HTTP status errors and bubbles network errors after retries
"""

import os
import time

import requests


def _env_timeout():
    try:
        return float(os.getenv("HTTP_TIMEOUT", "8"))
    except Exception:
        return 8.0


def get_json(url, params=None, headers=None, timeout=None, retries=1):
    """HTTP GET JSON with simple retry."""
    if timeout is None:
        timeout = _env_timeout()

    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # bubble after retries
            last_exc = exc
            if attempt < retries:
                time.sleep(0.35 * (attempt + 1))
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("get_json: unreachable")
