"""Lightweight self-check of generated answer against evidence — no extra LLM call."""
from __future__ import annotations

import logging

from backend.app.agent.state import AgentState

logger = logging.getLogger(__name__)


async def self_checker(state: AgentState) -> AgentState:
    summary = state.answer.get("summary", "")
    if not summary:
        state.add_step("self_checker", "No answer to check", "skip")
        return state

    # Simple evidence-based checks
    has_market = any(e["type"].startswith("market_") for e in state.evidence)
    has_rag = any(e["type"] == "rag_chunk" for e in state.evidence)
    has_news = any(e["type"] == "news_search" for e in state.evidence)

    issues = []

    # Market intent should have market evidence
    if state.intent == "market" and not has_market:
        issues.append("行情问题但无市场数据支撑")

    # Knowledge intent should have RAG evidence
    if state.intent == "knowledge" and not has_rag:
        issues.append("知识问题但无知识库检索结果，回答基于模型通用知识")

    state.self_check = {
        "passed": len(issues) == 0,
        "has_market_evidence": has_market,
        "has_rag_evidence": has_rag,
        "has_news_evidence": has_news,
        "issues": issues,
    }

    if issues:
        state.warnings.extend(issues)
        state.add_step("self_checker", f"Issues: {issues}", "warning")
    else:
        state.add_step("self_checker", "Passed")

    return state