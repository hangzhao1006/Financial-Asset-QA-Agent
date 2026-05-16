"""RAG pipeline: vector store interaction, retrieval, and evidence assembly."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import chromadb

from backend.app.config import get_settings
from backend.app.services.embedding import embed_texts
from backend.app.services.query_rewriter import rewrite_query
from backend.app.services.reranker import rerank, RankedChunk
from backend.app.services.cache import get_cache, CACHE_TTL

logger = logging.getLogger(__name__)

_collection: Optional[chromadb.Collection] = None


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        s = get_settings()
        client = chromadb.PersistentClient(path=s.chroma_persist_dir)
        _collection = client.get_or_create_collection(
            name="financial_knowledge",
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


async def retrieve(
    question: str,
    top_k_initial: int = 8,
    top_k_final: int = 4,
    similarity_threshold: float = 0.3,
) -> list[RankedChunk]:
    """Full retrieval pipeline: rewrite → embed → vector search → rerank."""
    cache = get_cache()
    cached = cache.get("rag_retrieval", question)
    if cached:
        return [RankedChunk(**c) for c in cached]

    # Query rewrite
    queries = await rewrite_query(question)
    logger.info("Rewritten queries: %s", queries)

    collection = _get_collection()

    # Embed all queries. If the online embedding provider and local fallback are
    # unavailable, keep report Q&A usable through a lexical scan of stored chunks.
    try:
        all_embeddings = await embed_texts(queries)
    except Exception as exc:
        logger.warning("Embedding unavailable; falling back to lexical RAG search: %s", exc)
        return _lexical_retrieve(collection, question, top_k=top_k_final)

    # Search across all query variants
    seen_ids: set[str] = set()
    raw_chunks: list[dict] = []

    for emb in all_embeddings:
        try:
            results = collection.query(
                query_embeddings=[emb],
                n_results=top_k_initial,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.warning("Chroma query failed: %s", exc)
            continue

        if not results["documents"] or not results["documents"][0]:
            continue

        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            chunk_id = f"{meta.get('source_file', meta.get('doc_id', ''))}_{meta.get('chunk_index', 0)}"
            similarity = 1 - dist  # cosine distance → similarity
            if chunk_id not in seen_ids and similarity >= similarity_threshold:
                seen_ids.add(chunk_id)
                raw_chunks.append({"text": doc, "metadata": meta, "similarity": similarity})

    if not raw_chunks:
        return _lexical_retrieve(collection, question, top_k=top_k_final)

    # Rerank
    ranked = await rerank(question, raw_chunks, top_k=top_k_final)

    # Cache results
    cache.set(
        "rag_retrieval",
        question,
        [{"text": r.text, "metadata": r.metadata, "score": r.score, "original_rank": r.original_rank} for r in ranked],
        CACHE_TTL["rag_retrieval"],
    )

    return ranked


def _lexical_retrieve(collection: chromadb.Collection, question: str, top_k: int) -> list[RankedChunk]:
    """Fallback retrieval for demos when query embeddings are unavailable.

    This is intentionally simple: score stored chunks by overlap with company,
    report, year, and finance terms from the question. It is not a replacement
    for vector retrieval, but prevents report Q&A from collapsing when network
    access to the embedding provider is temporarily unavailable.
    """
    terms = _query_terms(question)
    if not terms:
        return []

    try:
        stored = collection.get(include=["documents", "metadatas"])
    except Exception as exc:
        logger.warning("Lexical Chroma scan failed: %s", exc)
        return []

    documents = stored.get("documents") or []
    metadatas = stored.get("metadatas") or []
    scored: list[tuple[float, int, str, dict]] = []

    for idx, (doc, meta) in enumerate(zip(documents, metadatas)):
        meta_blob = " ".join([
            str(meta.get("source_file", "")),
            str(meta.get("title", "")),
            str(meta.get("section", "")),
        ]).lower()
        doc_blob = doc[:2000].lower()
        blob = " ".join([
            meta_blob,
            doc[:2000],
        ]).lower()
        score = 0.0
        for term in terms:
            weight = _term_weight(term)
            if term in meta_blob:
                score += weight * 3
            elif term in doc_blob:
                score += weight
        if score > 0:
            scored.append((score, idx, doc, meta))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        RankedChunk(text=doc, metadata=meta, score=min(score / 10.0, 1.0), original_rank=rank)
        for rank, (score, _idx, doc, meta) in enumerate(scored[:top_k])
    ]


def _query_terms(question: str) -> list[str]:
    q = question.lower()
    terms = set(re.findall(r"[a-z0-9][a-z0-9_-]{1,}", q))
    terms.update(re.findall(r"\d{4}", q))

    synonym_map = {
        "华为": ["华为", "huawei"],
        "腾讯": ["腾讯", "tencent", "00700"],
        "阿里巴巴": ["阿里巴巴", "alibaba", "baba"],
        "贵州茅台": ["贵州茅台", "茅台", "kweichow", "moutai", "600519"],
        "茅台": ["贵州茅台", "茅台", "kweichow", "moutai", "600519"],
        "苹果": ["苹果", "apple", "aapl"],
        "apple": ["apple", "aapl"],
        "特斯拉": ["特斯拉", "tesla", "tsla"],
        "tesla": ["tesla", "tsla"],
        "英伟达": ["英伟达", "nvidia", "nvda"],
        "微软": ["微软", "microsoft", "msft"],
    }
    for key, values in synonym_map.items():
        if key in q:
            terms.update(v.lower() for v in values)

    finance_terms = [
        "年报", "中报", "季报", "财报", "收入", "净利润", "风险", "风险因素",
        "管理层讨论", "经营", "业务亮点", "annual", "interim", "quarterly",
        "report", "revenue", "risk", "risks", "factor", "factors",
        "management", "discussion", "business",
    ]
    for term in finance_terms:
        if term in q:
            terms.add(term)

    if "10-k" in terms:
        terms.add("10k")
    if "10-q" in terms:
        terms.add("10q")

    return sorted(terms, key=len, reverse=True)


def _term_weight(term: str) -> float:
    if re.fullmatch(r"\d{4}", term):
        return 3.0
    if term in {"huawei", "tencent", "alibaba", "kweichow", "moutai", "apple", "aapl", "tesla", "tsla"}:
        return 3.0
    if term in {"华为", "腾讯", "阿里巴巴", "贵州茅台", "茅台", "苹果", "特斯拉"}:
        return 3.0
    if term in {"10-k", "10-q", "10k", "10q", "annual", "interim", "quarterly", "年报", "中报", "季报"}:
        return 2.0
    return 1.0


async def add_documents(
    texts: list[str],
    metadatas: list[dict],
    ids: list[str],
) -> None:
    """Add documents to the vector store."""
    embeddings = await embed_texts(texts)
    collection = _get_collection()
    collection.add(
        documents=texts,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=ids,
    )
    logger.info("Added %d chunks to Chroma", len(texts))