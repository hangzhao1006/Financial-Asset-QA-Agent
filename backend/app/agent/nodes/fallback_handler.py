"""Handle tool failures with evidence-preserving fallback."""
from __future__ import annotations

import logging

from backend.app.agent.state import AgentState
from backend.app.services.market_data import get_quote, get_history, resolve_symbol

logger = logging.getLogger(__name__)


async def fallback_handler(state: AgentState) -> AgentState:
    symbols = state.entities.get("symbols", [])
    time_range = state.entities.get("time_range", "7d") or "7d"

    # Check if market data is needed but missing
    if state.intent in ("market", "hybrid", "event") and symbols:
        has_quote = any(k.startswith("quote_") for k in state.tool_results)
        has_history = any(k.startswith("history_") for k in state.tool_results)

        if not has_quote and "fetch_quote" in state.plan:
            state.fallbacks.append("market_quote_missing")
            state.fallback_used = True
            state.warnings.append("无法获取实时行情数据")
            state.data_quality = "partial"

        if not has_history and "fetch_history" in state.plan:
            state.fallbacks.append("market_history_missing")
            state.fallback_used = True
            state.warnings.append("无法获取历史价格数据")
            state.data_quality = "partial"

    # Check RAG results
    if state.intent in ("knowledge", "hybrid") and "rag_retrieve" in state.plan:
        chunks = state.tool_results.get("rag_chunks", [])
        if not chunks:
            state.fallbacks.append("rag_empty")
            state.fallback_used = True
            if state.intent == "knowledge":
                state.warnings.append("知识库中未找到相关内容，回答可能不完整")
                state.data_quality = "partial"

    # Check news
    if "news_search" in state.plan:
        news = state.tool_results.get("news", {})
        if not news.get("results"):
            state.fallbacks.append("news_unavailable")
            if state.intent == "event":
                state.warnings.append("未接入新闻检索或未找到相关新闻")

    if not state.evidence:
        state.data_quality = "unavailable"
        state.warnings.append("当前无可用数据来源，回答受限")

    if state.fallbacks:
        state.add_step("fallback_handler", f"Fallbacks triggered: {state.fallbacks}")
    else:
        state.add_step("fallback_handler", "No fallbacks needed")

    return state
