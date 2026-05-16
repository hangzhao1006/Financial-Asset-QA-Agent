"""Rule-based intent classifier - no LLM call, instant."""
from __future__ import annotations

import re
from backend.app.agent.state import AgentState
from backend.app.services.market_data import SYMBOL_ALIASES

# Keywords that indicate market intent
MARKET_KEYWORDS = [
    "股价", "价格", "多少钱", "行情", "涨跌", "涨幅", "跌幅", "走势",
    "趋势", "最近", "近期", "今天", "昨天", "本周", "上周",
    "7天", "7日", "30天", "30日", "一周", "一个月",
    "price", "quote", "trend", "stock",
]

# Keywords that indicate knowledge intent
KNOWLEDGE_KEYWORDS = [
    "什么是", "是什么", "定义", "解释", "区别", "差异", "如何计算",
    "概念", "含义", "意思", "怎么理解", "公式",
    "what is", "what are", "define", "explain", "difference",
    "市盈率", "市净率", "毛利率", "净利率", "自由现金流",
    "EPS", "P/E", "P/B", "ROE", "ROA", "EBITDA",
]

# Keywords that indicate source-document / report Q&A. These should route to RAG
# even when the question mentions a listed company ticker or asset name.
REPORT_KEYWORDS = [
    "财报", "年报", "季报", "中报", "季度报告", "年度报告", "报告",
    "管理层讨论", "经营要点", "业务亮点", "风险因素",
    "10-k", "10-q", "annual report", "quarterly report", "interim report",
    "risk factor", "risk factors", "management discussion", "business risks",
]

# Keywords that indicate event/hybrid intent
EVENT_KEYWORDS = [
    "为什么", "为何", "原因", "大涨", "大跌", "暴涨", "暴跌",
    "发生了什么", "怎么了", "新闻", "事件",
    "why", "reason", "news", "surge", "crash",
]

# All known ticker symbols (uppercase)
KNOWN_SYMBOLS = set(v.upper() for v in SYMBOL_ALIASES.values()) | set(k.upper() for k in SYMBOL_ALIASES.keys())


def _has_asset_reference(question: str) -> bool:
    """Check if question references a specific asset."""
    q = question.lower()
    # Check aliases
    for alias in SYMBOL_ALIASES:
        if alias in q:
            return True
    # Check uppercase symbols like BABA, TSLA
    words = re.findall(r'[A-Z]{2,5}', question)
    for w in words:
        if w in KNOWN_SYMBOLS:
            return True
    # Check A-share codes
    if re.search(r'\b\d{6}\b', question):
        return True
    return False


async def intent_classifier(state: AgentState) -> AgentState:
    q = state.question.lower()
    has_asset = _has_asset_reference(state.question)

    # Score each intent
    market_score = sum(1 for kw in MARKET_KEYWORDS if kw in q)
    knowledge_score = sum(1 for kw in KNOWLEDGE_KEYWORDS if kw in q)
    report_score = sum(1 for kw in REPORT_KEYWORDS if kw in q)
    event_score = sum(1 for kw in EVENT_KEYWORDS if kw in q)

    # Determine intent
    if report_score > 0:
        intent = "knowledge"
        conf = 0.95
    elif event_score > 0 and has_asset:
        intent = "event"
        conf = 0.85
    elif market_score > 0 and has_asset:
        intent = "market"
        conf = 0.9
    elif knowledge_score > 0 and not has_asset:
        intent = "knowledge"
        conf = 0.9
    elif has_asset:
        intent = "market"
        conf = 0.7
    elif knowledge_score > 0:
        intent = "knowledge"
        conf = 0.8
    else:
        # Default: if has asset reference -> market, else knowledge
        intent = "market" if has_asset else "knowledge"
        conf = 0.5

    # Check memory for follow-up
    if state.memory.get("last_entities") and not has_asset:
        if any(kw in q for kw in ["那", "它", "这个", "呢", "还有"]):
            intent = state.memory.get("last_intent", intent)
            conf = 0.75

    state.intent = intent
    state.intent_confidence = conf
    state.add_step(
        "intent_classifier",
        f"{intent} (conf={conf})",
        decision="Classify the user request before selecting tools.",
        action="classify_intent",
        action_input={"question": state.question},
        observation=f"intent={intent}, confidence={conf}, has_asset={has_asset}, report_score={report_score}",
    )
    return state