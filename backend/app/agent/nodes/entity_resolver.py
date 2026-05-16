"""Rule-based entity resolver - no LLM call, instant."""
from __future__ import annotations

import re
from backend.app.agent.state import AgentState
from backend.app.services.market_data import SYMBOL_ALIASES, resolve_symbol


# Time range patterns
TIME_PATTERNS = [
    (r'7\s*[天日]|一周|1\s*week|7d', '7d'),
    (r'30\s*[天日]|一个月|1\s*month|30d|1m', '30d'),
    (r'3\s*个月|3\s*month|3m|90\s*[天日]', '3m'),
    (r'6\s*个月|6\s*month|6m|半年', '6m'),
    (r'1\s*年|一年|1\s*year|1y|12\s*个月', '1y'),
]


def _extract_symbols(question: str) -> list[str]:
    """Extract stock symbols from question text."""
    symbols = []
    q_lower = question.lower()

    # Check Chinese/English aliases
    for alias, symbol in SYMBOL_ALIASES.items():
        if alias in q_lower:
            if symbol not in symbols:
                symbols.append(symbol)

    # Check uppercase symbols like BABA, TSLA, AAPL (must be 3+ chars or known)
    # Exclude common English words that look like tickers
    EXCLUDE_WORDS = {"THE", "AND", "FOR", "ARE", "NOT", "HAS", "HAD", "WAS", "HIS", "HER",
                     "HOW", "WHY", "DID", "HIM", "ITS", "OUR", "WHO", "MAY", "CAN", "ALL"}
    words = re.findall(r'\b([A-Z]{3,5})\b', question)
    for w in words:
        if w in EXCLUDE_WORDS:
            continue
        resolved = resolve_symbol(w)
        if resolved not in symbols:
            symbols.append(resolved)

    # Check A-share codes (6 digits)
    codes = re.findall(r'\b(\d{6})\b', question)
    for code in codes:
        if code not in symbols:
            symbols.append(code)

    return symbols


def _extract_time_range(question: str) -> str:
    """Extract time range from question."""
    for pattern, range_str in TIME_PATTERNS:
        if re.search(pattern, question, re.IGNORECASE):
            return range_str
    return ""


def _extract_company_names(question: str) -> list[str]:
    """Extract company names mentioned."""
    names = []
    q_lower = question.lower()
    name_map = {
        "阿里巴巴": "阿里巴巴", "alibaba": "Alibaba",
        "特斯拉": "特斯拉", "tesla": "Tesla",
        "苹果": "苹果", "apple": "Apple",
        "谷歌": "谷歌", "google": "Google",
        "微软": "微软", "microsoft": "Microsoft",
        "英伟达": "英伟达", "nvidia": "NVIDIA",
        "腾讯": "腾讯", "tencent": "Tencent",
        "华为": "华为", "huawei": "Huawei",
        "百度": "百度", "baidu": "Baidu",
        "京东": "京东", "茅台": "贵州茅台",
        "比亚迪": "比亚迪", "宁德时代": "宁德时代",
        "拼多多": "拼多多", "网易": "网易",
    }
    for key, name in name_map.items():
        if key in q_lower and name not in names:
            names.append(name)
    return names


def _is_follow_up_question(question: str) -> bool:
    q = question.lower()
    follow_up_terms = ["他", "它", "其", "这个", "该公司", "那", "呢", "还有", "继续"]
    return any(term in q for term in follow_up_terms)


def _extract_metrics(question: str) -> list[str]:
    q = question.lower()
    metrics = []
    if any(token in q for token in ["市盈率", "pe", "p/e", "price-to-earnings", "price earnings"]):
        metrics.append("pe_ratio")
    if any(token in q for token in ["eps", "每股收益"]):
        metrics.append("eps")
    return metrics


async def entity_resolver(state: AgentState) -> AgentState:
    symbols = _extract_symbols(state.question)
    time_range = _extract_time_range(state.question)
    company_names = _extract_company_names(state.question)
    metrics = _extract_metrics(state.question)

    # Inherit from memory only for true follow-up questions. If the user names a
    # new company that we cannot map to a public ticker, do not incorrectly reuse
    # the previous symbol.
    if not symbols and state.memory.get("last_entities") and _is_follow_up_question(state.question):
        last = state.memory["last_entities"]
        symbols = last if isinstance(last, list) else last.get("symbols", [])
        if not time_range and isinstance(last, dict):
            time_range = last.get("time_range", "")
        state.memory_used = True

    state.entities = {
        "symbols": symbols,
        "company_names": company_names,
        "time_range": time_range,
        "metrics": metrics,
    }

    detail = f"symbols={symbols}, range={time_range or 'none'}, metrics={metrics}"
    state.add_step(
        "entity_resolver",
        detail,
        decision="Extract company/ticker, time range, and requested metrics from the query.",
        action="resolve_entities",
        action_input={"question": state.question},
        observation=detail,
    )
    return state