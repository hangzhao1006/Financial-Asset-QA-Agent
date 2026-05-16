"""Simple query rewriter - no LLM call, instant."""
from __future__ import annotations

import re
import logging
from backend.app.services.cache import get_cache, CACHE_TTL

logger = logging.getLogger(__name__)

# Chinese to English concept mappings for bilingual search
CONCEPT_MAP = {
    "市盈率": "P/E ratio price earnings",
    "市净率": "P/B ratio price book",
    "每股收益": "EPS earnings per share",
    "股息收益率": "dividend yield",
    "市销率": "P/S ratio price sales",
    "毛利率": "gross margin",
    "净利率": "net margin",
    "营业利润率": "operating margin",
    "自由现金流": "free cash flow FCF",
    "收入": "revenue income",
    "净利润": "net income profit",
    "牛市": "bull market",
    "熊市": "bear market",
    "成交量": "volume trading",
    "波动率": "volatility",
    "贝塔系数": "beta coefficient",
    "移动平均线": "moving average SMA EMA",
    "分散投资": "diversification",
}


async def rewrite_query(question: str) -> list[str]:
    """Rewrite user question into retrieval-friendly queries."""
    cache = get_cache()
    cached = cache.get("query_rewrite", question)
    if cached:
        return cached

    queries = [question]

    # Add English terms for Chinese concepts
    q_lower = question.lower()
    for cn, en in CONCEPT_MAP.items():
        if cn in q_lower:
            queries.append(f"{cn} {en}")
            break

    # Remove filler words for cleaner search
    clean = re.sub(r'(什么是|是什么|请问|请解释|帮我|告诉我|我想知道)', '', question).strip()
    if clean and clean != question and len(clean) > 2:
        queries.append(clean)

    # Deduplicate
    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    cache.set("query_rewrite", question, unique, CACHE_TTL.get("query_rewrite", 300))
    return unique[:3]