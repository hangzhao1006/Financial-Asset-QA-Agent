"""Pluggable reranker: LLM relevance scoring or cross-encoder."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from backend.app.config import get_settings
from backend.app.services.llm import chat_json

logger = logging.getLogger(__name__)


@dataclass
class RankedChunk:
    text: str
    metadata: dict
    score: float
    original_rank: int


async def rerank(
    query: str,
    chunks: list[dict],
    top_k: int = 5,
) -> list[RankedChunk]:
    """Rerank retrieved chunks using configured provider."""
    s = get_settings()

    if s.rerank_provider == "none" or not chunks:
        return [
            RankedChunk(text=c["text"], metadata=c.get("metadata", {}), score=1.0 - i * 0.05, original_rank=i)
            for i, c in enumerate(chunks[:top_k])
        ]

    if s.rerank_provider == "cross_encoder":
        return _rerank_cross_encoder(query, chunks, top_k, s.rerank_model)

    # Default: llm_relevance
    return await _rerank_llm(query, chunks, top_k)


async def _rerank_llm(query: str, chunks: list[dict], top_k: int) -> list[RankedChunk]:
    """Use LLM to score relevance of each chunk."""
    prompt = """Score the relevance of each passage to the query. Return JSON:
{"scores": [{"index": 0, "score": 0.0-1.0}, ...]}

Query: {query}

Passages:
{passages}"""

    passages = "\n\n".join(
        f"[{i}] {c['text'][:500]}" for i, c in enumerate(chunks[:10])
    )

    try:
        result = await chat_json(
            [{"role": "user", "content": prompt.format(query=query, passages=passages)}],
            temperature=0.0,
        )
        scores = {s["index"]: s["score"] for s in result.get("scores", [])}
    except Exception as exc:
        logger.warning("LLM rerank failed: %s", exc)
        scores = {i: 1.0 - i * 0.05 for i in range(len(chunks))}

    ranked = []
    for i, c in enumerate(chunks):
        ranked.append(RankedChunk(
            text=c["text"],
            metadata=c.get("metadata", {}),
            score=scores.get(i, 0.5),
            original_rank=i,
        ))

    ranked.sort(key=lambda x: x.score, reverse=True)
    return ranked[:top_k]


def _rerank_cross_encoder(
    query: str, chunks: list[dict], top_k: int, model_name: str
) -> list[RankedChunk]:
    """Cross-encoder reranking using sentence-transformers."""
    try:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder(model_name or "cross-encoder/ms-marco-MiniLM-L-6-v2")
        pairs = [(query, c["text"][:512]) for c in chunks]
        scores = model.predict(pairs)
        ranked = []
        for i, (c, s) in enumerate(zip(chunks, scores)):
            ranked.append(RankedChunk(
                text=c["text"], metadata=c.get("metadata", {}), score=float(s), original_rank=i
            ))
        ranked.sort(key=lambda x: x.score, reverse=True)
        return ranked[:top_k]
    except ImportError:
        logger.error("sentence-transformers not installed for cross-encoder rerank")
        return [
            RankedChunk(text=c["text"], metadata=c.get("metadata", {}), score=0.5, original_rank=i)
            for i, c in enumerate(chunks[:top_k])
        ]
