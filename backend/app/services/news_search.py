"""Web/news search via Tavily or SerpAPI (optional)."""
from __future__ import annotations

import logging
from typing import Optional

from backend.app.config import get_settings
from backend.app.services.cache import get_cache, CACHE_TTL

logger = logging.getLogger(__name__)


async def search_news(query: str, max_results: int = 5) -> dict:
    """Search for news using configured provider. Returns dict with results and provider."""
    cache = get_cache()
    cached = cache.get("web_search", query)
    if cached:
        return cached

    s = get_settings()

    if s.tavily_api_key:
        result = await _search_tavily(query, s.tavily_api_key, max_results)
    elif s.serpapi_api_key:
        result = _search_serpapi(query, s.serpapi_api_key, max_results)
    else:
        result = {
            "provider": "none",
            "results": [],
            "error": "No search API key configured (TAVILY_API_KEY or SERPAPI_API_KEY)",
        }

    if result.get("results"):
        cache.set("web_search", query, result, CACHE_TTL["web_search"])

    return result


async def _search_tavily(query: str, api_key: str, max_results: int) -> dict:
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, max_results=max_results, search_depth="basic")
        results = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("content", "")[:500],
            }
            for r in response.get("results", [])
        ]
        return {"provider": "tavily", "results": results}
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return {"provider": "tavily", "results": [], "error": str(exc)}


def _search_serpapi(query: str, api_key: str, max_results: int) -> dict:
    """SerpAPI stub."""
    logger.info("SerpAPI not implemented yet")
    return {"provider": "serpapi", "results": [], "error": "SerpAPI not implemented"}
