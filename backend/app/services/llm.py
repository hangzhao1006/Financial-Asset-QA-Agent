"""OpenAI-compatible chat completion wrapper with fallback."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from openai import AsyncOpenAI

from backend.app.config import get_settings

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        s = get_settings()
        _client = AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)
    return _client


async def chat(
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    response_format: Optional[dict] = None,
) -> str:
    """Send chat completion. Falls back to FALLBACK_LLM_MODEL on error."""
    s = get_settings()
    client = _get_client()
    primary = model or s.openai_model
    fallback = s.fallback_llm_model

    for m in [primary, fallback]:
        try:
            kwargs: dict[str, Any] = dict(
                model=m,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response_format:
                kwargs["response_format"] = response_format
            resp = await client.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except Exception as exc:
            logger.warning("LLM call failed model=%s: %s", m, exc)
            if m == fallback:
                raise
    return ""


async def chat_json(
    messages: list[dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.1,
) -> dict:
    """Chat expecting JSON response."""
    raw = await chat(
        messages,
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        if "```" in raw:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(raw[start:end])
        return {"raw": raw}
