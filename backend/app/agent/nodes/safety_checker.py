"""Safety check for financial responses — simplified, fewer warnings."""
from __future__ import annotations

import logging

from backend.app.agent.state import AgentState

logger = logging.getLogger(__name__)

DEFAULT_DISCLAIMER = "以上信息仅供参考，不构成投资建议。"

# Keywords that indicate unsafe content
UNSAFE_PATTERNS = [
    ("建议买入", "包含投资建议"),
    ("建议卖出", "包含投资建议"),
    ("一定会涨", "包含价格预测"),
    ("一定会跌", "包含价格预测"),
    ("保证收益", "包含收益保证"),
    ("必涨", "包含价格预测"),
    ("必跌", "包含价格预测"),
]


async def safety_checker(state: AgentState) -> AgentState:
    summary = state.answer.get("summary", "")
    if not summary:
        state.add_step("safety_checker", "No answer to check", "skip")
        return state

    # Simple keyword-based safety check (no extra LLM call)
    issues = []
    for pattern, issue in UNSAFE_PATTERNS:
        if pattern in summary:
            issues.append(issue)

    if issues:
        state.warnings.extend(issues)
        state.add_step("safety_checker", f"Issues: {issues}", "warning")
    else:
        state.add_step("safety_checker", "Passed")

    # Add disclaimer only for market answers, and only once
    if state.intent in ("market", "hybrid", "event"):
        if DEFAULT_DISCLAIMER not in state.warnings:
            state.warnings.append(DEFAULT_DISCLAIMER)

    return state