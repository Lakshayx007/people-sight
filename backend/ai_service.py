"""
ai_service.py
-------------
Groq integration, adapted from Onco-Sight's ai_service.py: same lazy client, in-process TTL cache and graceful
fallback when no key is set. Used for exactly two things (Hard rule 9):
  1. Ask the Data: turn a question into ONE SQL query + a chart spec (JSON mode). The model never sees query results.
  2. Short chart blurbs written only from rows the dashboard already returned.

Model: GROQ_MODEL (default openai/gpt-oss-120b — Groq retired llama-3.3-70b-versatile on 16-Aug-2026).
Rate limits (HTTP 429): one retry after a short wait, then a friendly error.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("people.ai")

DEFAULT_MODEL = "openai/gpt-oss-120b"
_cache: dict[str, tuple[float, Any]] = {}


class AIUnavailable(Exception):
    """No API key, package missing, or Groq unreachable."""


class AIRateLimited(Exception):
    """Groq returned 429 twice."""


class AIBadOutput(Exception):
    """The model did not return valid JSON."""


def model_name() -> str:
    return os.getenv("GROQ_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL


def available() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def _client():
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        return None
    try:
        from groq import Groq
        return Groq(api_key=key, max_retries=0, timeout=30)
    except ImportError:
        log.warning("groq package not installed — AI features disabled")
        return None


def _ttl() -> int:
    return int(os.getenv("GROQ_CACHE_TTL", "600"))


def _cache_get(key: str):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < _ttl():
        return hit[1]
    _cache.pop(key, None)
    return None


def _cache_set(key: str, val: Any) -> None:
    _cache[key] = (time.time(), val)


def _key(*args) -> str:
    return hashlib.sha256(json.dumps(args, sort_keys=True, default=str).encode()).hexdigest()


def _create(client, **kw):
    """One call with a single retry on 429."""
    from groq import APIConnectionError, APITimeoutError, AuthenticationError, BadRequestError, RateLimitError
    for attempt in (1, 2):
        try:
            return client.chat.completions.create(**kw)
        except BadRequestError as e:
            msg = str(e)
            if "reasoning_effort" in msg and "reasoning_effort" in kw:   # model does not take the parameter
                kw.pop("reasoning_effort")
                continue
            if "json_validate_failed" in msg:
                raise AIBadOutput("model output was not valid JSON") from e
            raise AIBadOutput(f"Groq rejected the request ({msg[:160]})") from e
        except RateLimitError as e:
            if attempt == 2:
                raise AIRateLimited("Groq rate limit reached") from e
            wait = 2.0
            try:
                wait = min(20.0, float(e.response.headers.get("retry-after", wait)))
            except Exception:  # noqa: BLE001
                pass
            log.info("Groq 429, retrying in %.1fs", wait)
            time.sleep(wait)
        except AuthenticationError as e:
            raise AIUnavailable("Groq rejected the API key") from e
        except (APIConnectionError, APITimeoutError) as e:
            raise AIUnavailable("Groq is not reachable") from e
    raise AIUnavailable("Groq call failed")


def _extra() -> dict:
    """gpt-oss models are reasoning models: keep reasoning short (their reasoning tokens count against max_tokens)."""
    return {"reasoning_effort": "low"} if model_name().startswith("openai/gpt-oss") else {}


def chat_json(messages: list[dict], max_tokens: int = 3000) -> dict:
    """Ask the model for a JSON object (JSON mode). Cached by message content."""
    key = _key("json", model_name(), messages)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    client = _client()
    if client is None:
        raise AIUnavailable("GROQ_API_KEY is not set")
    resp = _create(client, model=model_name(), messages=messages, temperature=0, max_tokens=max_tokens,
                   response_format={"type": "json_object"}, **_extra())
    text = (resp.choices[0].message.content or "").strip()
    try:
        out = json.loads(text)
    except json.JSONDecodeError as e:
        raise AIBadOutput("model did not return JSON") from e
    if not isinstance(out, dict):
        raise AIBadOutput("model did not return a JSON object")
    _cache_set(key, out)
    return out


BLURB_SYSTEM = """You write a two-sentence plain-English summary of ONE dashboard chart for HR leaders.
Use ONLY the rows given. Do not add numbers that are not in the rows, do not speculate about causes,
do not mention individuals. If a row is marked suppressed (n<5), say it is hidden for privacy.
Return JSON: {"blurb": "<two sentences>"}"""


def chart_blurb(title: str, rows: list[dict]) -> str:
    """Short description of a chart, written only from the rows the API already returned."""
    if not available():
        return "AI summaries need a Groq API key (GROQ_API_KEY). The chart and its SQL are unaffected."
    payload = json.dumps(rows[:40], default=str)[:4000]
    try:
        out = chat_json([{"role": "system", "content": BLURB_SYSTEM},
                         {"role": "user", "content": f"Chart title: {title}\nRows (JSON): {payload}"}], max_tokens=1200)
        return str(out.get("blurb", "")).strip() or "No summary returned."
    except AIRateLimited:
        return "Groq is busy (rate limit). Try again in a minute."
    except (AIUnavailable, AIBadOutput) as e:
        return f"AI summary unavailable: {e}."
