"""Validate collected evidence before answer generation."""
from __future__ import annotations

from backend.app.agent.state import AgentState


async def evidence_validator(state: AgentState) -> AgentState:
    market_evidence = [e for e in state.evidence if e["type"].startswith("market_")]
    rag_evidence = [e for e in state.evidence if e["type"] == "rag_chunk"]
    news_evidence = [e for e in state.evidence if e["type"] == "news_search"]

    validation = {
        "market_evidence_count": len(market_evidence),
        "rag_evidence_count": len(rag_evidence),
        "news_evidence_count": len(news_evidence),
        "total": len(state.evidence),
        "sufficient": True,
        "issues": [],
    }

    # Market intent requires market data
    if state.intent == "market" and not market_evidence:
        validation["sufficient"] = False
        validation["issues"].append("Market intent but no market data available")

    # Knowledge intent with no RAG results
    if state.intent == "knowledge" and not rag_evidence:
        validation["issues"].append("No RAG evidence found; answer will use general knowledge with disclaimer")

    state.tool_results["evidence_validation"] = validation
    state.add_step("evidence_validator",
                   f"Evidence: market={len(market_evidence)}, rag={len(rag_evidence)}, news={len(news_evidence)}")
    return state
