import json
import re
import time

import httpx

from app.config import settings

# Sentinel returned when the LLM times out or fails — callers check for this
LLM_UNAVAILABLE = "__LLM_UNAVAILABLE__"


def _try_parse_json(text: str) -> dict | list | None:
    """Attempt to parse JSON with repair fallbacks for common LLM issues."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    brace_start = text.find("{")
    bracket_start = text.find("[")
    start = brace_start if brace_start != -1 else bracket_start
    if start == -1:
        return None

    json_str = text[start:]
    depth = 0
    in_string = False
    for i, ch in enumerate(json_str):
        if ch == '"' and (i == 0 or json_str[i - 1] != "\\"):
            in_string = not in_string
        if in_string:
            continue
        if ch in ("{", "["):
            depth += 1
        elif ch in ("}", "]"):
            depth -= 1
            if depth == 0:
                candidate = json_str[: i + 1]
                candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass

    return None


def complete(
    prompt: str,
    system: str = None,
    require_json: bool = False,
    timeout: int = None,
) -> str | dict:
    """
    Call the configured LLM provider.

    Args:
        timeout: Per-call timeout in seconds. Defaults to settings.LLM_TIMEOUT_SECONDS.
                 For background enrichment tasks, pass a larger value (30).

    Returns:
        Parsed dict/list when require_json=True, raw string otherwise.
        Returns LLM_UNAVAILABLE sentinel on timeout/network error —
        callers should fall back to direct vector search.
    """
    t = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS
    provider = settings.LLM_PROVIDER.lower()

    if provider == "anthropic":
        return _call_anthropic(prompt, system, require_json, t)
    elif provider == "google":
        return _call_google(prompt, system, require_json, t)
    else:
        raise ValueError(f"Unsupported LLM provider: {provider}")


def _call_anthropic(prompt: str, system: str, require_json: bool, timeout: int):
    headers = {
        "x-api-key": settings.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system

    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                text = response.json()["content"][0]["text"]
                if require_json:
                    result = _try_parse_json(text)
                    if result is not None:
                        return result
                    raise ValueError(f"Failed to parse JSON from: {text[:200]}")
                return text
        except httpx.TimeoutException:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return LLM_UNAVAILABLE
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return LLM_UNAVAILABLE


def _call_google(prompt: str, system: str, require_json: bool, timeout: int):
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={settings.GOOGLE_API_KEY}"
    )
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if system:
        payload["system_instruction"] = {"parts": [{"text": system}]}
    if require_json:
        payload["generationConfig"] = {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
        }

    for attempt in range(2):
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
                if require_json:
                    result = _try_parse_json(text)
                    if result is not None:
                        return result
                    raise ValueError(f"Failed to parse JSON from: {text[:200]}")
                return text
        except httpx.TimeoutException:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return LLM_UNAVAILABLE
        except Exception:
            if attempt == 0:
                time.sleep(0.5)
                continue
            return LLM_UNAVAILABLE


# ── Embeddings ────────────────────────────────────────────────────────────────
# Always uses Voyage AI (voyage-large-2, 1536 dims) regardless of LLM_PROVIDER.

VOYAGE_EMBED_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-large-2"


def embed(text: str) -> list[float]:
    """
    Generates a 1536-dim embedding via Voyage AI.
    Uses a longer timeout (15s) since enrichment is a background task.
    """
    if not settings.VOYAGE_API_KEY:
        raise RuntimeError("VOYAGE_API_KEY is not configured.")

    headers = {
        "Authorization": f"Bearer {settings.VOYAGE_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"input": [text], "model": VOYAGE_MODEL}

    for attempt in range(3):
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(VOYAGE_EMBED_URL, headers=headers, json=payload)
                response.raise_for_status()
                return response.json()["data"][0]["embedding"]
        except httpx.TimeoutException:
            if attempt < 2:
                time.sleep(1.5 ** attempt)
                continue
            raise
        except Exception:
            if attempt < 2:
                time.sleep(1.5 ** attempt)
                continue
            raise
