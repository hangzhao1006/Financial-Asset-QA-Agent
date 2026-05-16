"""Pluggable embedding provider: OpenAI or local sentence-transformers."""
from __future__ import annotations

import logging
from typing import Optional

from openai import AsyncOpenAI

from backend.app.config import get_settings
from backend.app.services.cache import get_cache, CACHE_TTL

logger = logging.getLogger(__name__)

_oai_client: Optional[AsyncOpenAI] = None
_local_model = None


def _get_openai_client() -> AsyncOpenAI:
    global _oai_client
    if _oai_client is None:
        s = get_settings()
        _oai_client = AsyncOpenAI(api_key=s.openai_api_key, base_url=s.openai_base_url)
    return _oai_client


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts using the configured provider."""
    s = get_settings()
    cache = get_cache()

    # Check cache first
    results: list[Optional[list[float]]] = []
    uncached_indices: list[int] = []
    for i, t in enumerate(texts):
        cached = cache.get("embedding", t)
        if cached is not None:
            results.append(cached)
        else:
            results.append(None)
            uncached_indices.append(i)

    if not uncached_indices:
        return results  # type: ignore

    uncached_texts = [texts[i] for i in uncached_indices]

    if s.embedding_provider == "openai":
        embeddings = await _embed_openai(uncached_texts, s.embedding_model)
    else:
        embeddings = _embed_local(uncached_texts, s.embedding_model)

    for idx, emb in zip(uncached_indices, embeddings):
        results[idx] = emb
        cache.set("embedding", texts[idx], emb, CACHE_TTL["embedding"])

    return results  # type: ignore


async def _embed_openai(texts: list[str], model: str) -> list[list[float]]:
    client = _get_openai_client()
    try:
        resp = await client.embeddings.create(input=texts, model=model)
        return [d.embedding for d in resp.data]
    except Exception as exc:
        logger.warning("OpenAI embedding failed, trying local fallback: %s", exc)
        return _embed_local(texts, "BAAI/bge-m3")


def _embed_local(texts: list[str], model_name: str) -> list[list[float]]:
    """Local embedding using sentence-transformers."""
    global _local_model
    try:
        from sentence_transformers import SentenceTransformer
        if _local_model is None:
            _local_model = SentenceTransformer(model_name)
        vecs = _local_model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vecs]
    except ImportError:
        logger.error("sentence-transformers not installed for local embedding")
        raise
