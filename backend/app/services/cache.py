"""In-memory TTL cache with Redis adapter stub."""
from __future__ import annotations

import time
import hashlib
import json
from typing import Any, Optional


class TTLCache:
    """Simple in-memory cache with per-key TTL."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    def _make_key(self, prefix: str, raw_key: str) -> str:
        h = hashlib.sha256(raw_key.encode()).hexdigest()[:16]
        return f"{prefix}:{h}"

    def get(self, prefix: str, raw_key: str) -> Optional[Any]:
        k = self._make_key(prefix, raw_key)
        entry = self._store.get(k)
        if entry is None:
            return None
        value, expires = entry
        if time.time() > expires:
            del self._store[k]
            return None
        return value

    def set(self, prefix: str, raw_key: str, value: Any, ttl: int = 60) -> None:
        k = self._make_key(prefix, raw_key)
        self._store[k] = (value, time.time() + ttl)

    def delete(self, prefix: str, raw_key: str) -> None:
        k = self._make_key(prefix, raw_key)
        self._store.pop(k, None)

    def clear(self) -> None:
        self._store.clear()


# Module-level singleton
_cache = TTLCache()


def get_cache() -> TTLCache:
    return _cache


# TTL presets (seconds)
CACHE_TTL = {
    "quote": 45,
    "history": 600,
    "embedding": 1800,
    "rag_retrieval": 1800,
    "web_search": 3600,
    "intent": 120,
    "entity": 120,
    "query_rewrite": 600,
}
