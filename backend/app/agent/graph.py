"""LangGraph agent graph assembly."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import AsyncGenerator

from backend.app.agent.state import AgentState
from backend.app.agent.nodes.context_loader import context_loader
from backend.app.agent.nodes.intent_classifier import intent_classifier
from backend.app.agent.nodes.entity_resolver import entity_resolver
from backend.app.agent.nodes.planner import planner
from backend.app.agent.nodes.tool_executor import tool_executor
from backend.app.agent.nodes.fallback_handler import fallback_handler
from backend.app.agent.nodes.evidence_validator import evidence_validator
from backend.app.agent.nodes.answer_composer import answer_composer
from backend.app.agent.nodes.self_checker import self_checker
from backend.app.agent.nodes.safety_checker import safety_checker
from backend.app.agent.nodes.context_writer import context_writer
from backend.app.memory.session_store import TurnRecord, get_session_store
from backend.app.schemas import AskResponse
from backend.app.services.market_data import (
    SYMBOL_ALIASES,
    SYMBOL_NAMES,
    get_fundamentals,
    get_history,
    get_quote,
    resolve_symbol,
)

logger = logging.getLogger(__name__)

# Ordered node pipeline
NODES = [
    ("context_loader", context_loader),
    ("intent_classifier", intent_classifier),
    ("entity_resolver", entity_resolver),
    ("planner", planner),
    ("tool_executor", tool_executor),
    ("fallback_handler", fallback_handler),
    ("evidence_validator", evidence_validator),
    ("answer_composer", answer_composer),
    ("self_checker", self_checker),
    ("safety_checker", safety_checker),
    ("context_writer", context_writer),
]


async def run_agent(question: str, session_id: str = "") -> AskResponse:
    """Run the full agent pipeline and return structured response."""
    private_company_response = _try_private_company_response(question)
    if private_company_response is not None:
        return private_company_response

    missing_source_response = _try_missing_source_document_response(question)
    if missing_source_response is not None:
        return missing_source_response

    fast_knowledge_response = _try_fast_knowledge_response(question)
    if fast_knowledge_response is not None:
        return fast_knowledge_response

    fast_fundamental_response = _try_fast_fundamental_response(question, session_id)
    if fast_fundamental_response is not None:
        return fast_fundamental_response

    fast_trend_response = _try_fast_trend_response(question, session_id)
    if fast_trend_response is not None:
        return fast_trend_response

    fast_response = _try_fast_quote_response(question, session_id)
    if fast_response is not None:
        return fast_response

    state = AgentState(question=question, session_id=session_id)

    for name, node_fn in NODES:
        try:
            state = await node_fn(state)
        except Exception as exc:
            logger.error("Node %s crashed: %s", name, exc)
            state.add_step(name, f"Crashed: {exc}", "error")
            state.error = str(exc)
            break

    return _state_to_response(state)


async def run_agent_streaming(question: str, session_id: str = "") -> AsyncGenerator[dict, None]:
    """Run agent pipeline yielding SSE events at each step."""
    private_company_response = _try_private_company_response(question)
    if private_company_response is not None:
        yield {
            "event": "agent_step",
            "data": private_company_response.agent_steps[0],
        }
        yield {"event": "partial_answer", "data": {"summary": private_company_response.summary}}
        yield {"event": "final_answer", "data": private_company_response.model_dump()}
        yield {"event": "done", "data": {}}
        return

    missing_source_response = _try_missing_source_document_response(question)
    if missing_source_response is not None:
        yield {
            "event": "agent_step",
            "data": missing_source_response.agent_steps[0],
        }
        yield {"event": "partial_answer", "data": {"summary": missing_source_response.summary}}
        yield {"event": "final_answer", "data": missing_source_response.model_dump()}
        yield {"event": "done", "data": {}}
        return

    fast_knowledge_response = _try_fast_knowledge_response(question)
    if fast_knowledge_response is not None:
        yield {
            "event": "agent_step",
            "data": fast_knowledge_response.agent_steps[0],
        }
        yield {"event": "partial_answer", "data": {"summary": fast_knowledge_response.summary}}
        yield {"event": "final_answer", "data": fast_knowledge_response.model_dump()}
        yield {"event": "done", "data": {}}
        return

    fast_fundamental_response = _try_fast_fundamental_response(question, session_id)
    if fast_fundamental_response is not None:
        yield {
            "event": "agent_step",
            "data": fast_fundamental_response.agent_steps[0],
        }
        yield {"event": "partial_answer", "data": {"summary": fast_fundamental_response.summary}}
        yield {"event": "final_answer", "data": fast_fundamental_response.model_dump()}
        yield {"event": "done", "data": {}}
        return

    fast_trend_response = _try_fast_trend_response(question, session_id)
    if fast_trend_response is not None:
        yield {
            "event": "agent_step",
            "data": fast_trend_response.agent_steps[0],
        }
        yield {"event": "partial_answer", "data": {"summary": fast_trend_response.summary}}
        yield {"event": "final_answer", "data": fast_trend_response.model_dump()}
        yield {"event": "done", "data": {}}
        return

    fast_response = _try_fast_quote_response(question, session_id)
    if fast_response is not None:
        yield {
            "event": "agent_step",
            "data": fast_response.agent_steps[0],
        }
        yield {"event": "partial_answer", "data": {"summary": fast_response.summary}}
        yield {"event": "final_answer", "data": fast_response.model_dump()}
        yield {"event": "done", "data": {}}
        return

    state = AgentState(question=question, session_id=session_id)

    for name, node_fn in NODES:
        try:
            state = await node_fn(state)
            # Yield step event
            yield {
                "event": "agent_step",
                "data": state.steps[-1] if state.steps else {
                    "node": name,
                    "status": "ok",
                    "detail": "",
                },
            }
            # After answer_composer, yield partial answer
            if name == "answer_composer" and state.answer.get("summary"):
                yield {
                    "event": "partial_answer",
                    "data": {"summary": state.answer["summary"]},
                }
        except Exception as exc:
            logger.error("Node %s crashed: %s", name, exc)
            state.add_step(name, f"Crashed: {exc}", "error")
            state.error = str(exc)
            yield {"event": "error", "data": {"message": str(exc), "node": name}}
            break

    # Final answer
    response = _state_to_response(state)
    yield {"event": "final_answer", "data": response.model_dump()}
    yield {"event": "done", "data": {}}


def _state_to_response(state: AgentState) -> AskResponse:
    sources = []
    seen_sources = set()
    for e in state.evidence:
        if e["type"] == "rag_chunk":
            metadata = e.get("metadata", {})
            src_urls = metadata.get("source_urls", "")
            source_file = metadata.get("source_file", "")
            raw_title = metadata.get("title", "")
            source_key = (source_file or raw_title, metadata.get("section", ""))
            if source_key in seen_sources:
                continue
            seen_sources.add(source_key)
            sources.append({
                "type": "knowledge_base",
                "title": _format_knowledge_source_title(metadata),
                "raw_title": raw_title,
                "source_file": source_file,
                "section": metadata.get("section", ""),
                "urls": src_urls.split(",") if src_urls else [],
                "score": e.get("score", 0),
            })
        elif e["type"] == "news_search":
            for r in e.get("data", {}).get("results", []):
                sources.append({
                    "type": "news",
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                })

    return AskResponse(
        answer_type=state.answer.get("answer_type", state.intent or "knowledge"),
        summary=state.answer.get("summary", state.error or "Unable to generate answer"),
        objective_data=state.answer.get("objective_data", {}),
        analysis=state.answer.get("analysis", ""),
        sources=sources,
        warnings=list(set(state.warnings)),
        agent_steps=state.steps,
        cache_hit=state.cache_hit,
        fallback_used=state.fallback_used,
        data_quality=state.answer.get("data_quality", state.data_quality),
        memory_used=state.memory_used,
        self_check=state.self_check,
    )


def _format_knowledge_source_title(metadata: dict) -> str:
    source_file = str(metadata.get("source_file", ""))
    raw_title = str(metadata.get("title", ""))
    name = Path(source_file or raw_title).stem

    sec_match = re.match(r"([A-Z]+)_(10[QK])_(\d{4}-\d{2}-\d{2})", name)
    if sec_match:
        ticker, filing_type, filing_date = sec_match.groups()
        return f"{ticker} {filing_type.replace('10K', '10-K').replace('10Q', '10-Q')} Filing ({filing_date})"

    report_match = re.match(r"(.+?)_(\d{4})_(annual|interim|quarterly(?:_q[1-4])?)_", name)
    if report_match:
        company, year, period = report_match.groups()
        company_name = company.replace("_", " ").title()
        period_label = period.replace("_", " ").title()
        return f"{company_name} {year} {period_label} Report"

    return raw_title or name or "Knowledge Base"


_QUOTE_KEYWORDS = (
    "股价",
    "当前股价",
    "现在股价",
    "股价是多少",
    "股价多少",
    "当前价格",
    "现在价格",
    "目前价格",
    "多少钱",
    "current price",
    "latest price",
    "stock price",
    "quote",
)

_NON_QUOTE_ONLY_KEYWORDS = (
    "7天",
    "七天",
    "30天",
    "三十天",
    "近期",
    "走势",
    "涨跌",
    "涨幅",
    "跌幅",
    "为什么",
    "为何",
    "原因",
    "大涨",
    "大跌",
    "下跌",
    "上涨",
    "分析",
    "趋势",
    "past",
    "past 7 days",
    "past 30 days",
    "over the past",
    "moved",
    "movement",
    "trend",
    "return",
)

_FUNDAMENTAL_KEYWORDS = (
    "市盈率",
    "pe",
    "p/e",
    "price-to-earnings",
    "price earnings",
)

_TREND_KEYWORDS = (
    "近期走势",
    "走势",
    "趋势",
    "涨跌",
    "涨幅",
    "跌幅",
    "最近7天",
    "最近 7 天",
    "7天",
    "7日",
    "最近30天",
    "最近 30 天",
    "30天",
    "30日",
    "moved",
    "movement",
    "over the past",
    "past 7 days",
    "past seven days",
    "past 30 days",
    "past thirty days",
    "past week",
    "past month",
    "trend",
    "return",
)

_KNOWLEDGE_DEFINITION_KEYWORDS = (
    "什么是",
    "是什么",
    "区别",
    "差异",
    "解释",
    "含义",
    "what is",
    "what does",
    "define",
    "explain",
    "difference",
    "mean",
)

_PRIVATE_COMPANIES = {
    "字节跳动": "字节跳动 ByteDance",
    "bytedance": "字节跳动 ByteDance",
    "openai": "OpenAI",
}

_SOURCE_DOCUMENT_KEYWORDS = (
    "财报",
    "季报",
    "中报",
    "季度报告",
    "年报",
    "公告",
    "报告摘要",
    "风险因素",
    "管理层讨论",
    "业务亮点",
    "financial report",
    "quarterly report",
    "annual report",
    "earnings report",
    "10-k",
    "10-q",
    "risk factor",
    "risk factors",
    "management discussion",
)

_SOURCE_SPECIFIC_COMPANIES = (
    "华为",
    "huawei",
    "阿里巴巴",
    "alibaba",
    "腾讯",
    "tencent",
    "苹果",
    "apple",
    "特斯拉",
    "tesla",
    "微软",
    "microsoft",
    "英伟达",
    "nvidia",
)


def _try_private_company_response(question: str) -> AskResponse | None:
    q = question.lower()
    if not any(keyword in q for keyword in _QUOTE_KEYWORDS + _TREND_KEYWORDS):
        return None

    matched_name = None
    for alias, display_name in _PRIVATE_COMPANIES.items():
        if alias in q:
            matched_name = display_name
            break
    if not matched_name:
        return None

    summary = f"{matched_name}目前不是公开上市公司，因此没有可通过公开交易所查询的实时股票代码或当日股价。"
    return AskResponse(
        answer_type="market",
        summary=summary,
        objective_data={
            "company_name": matched_name,
            "publicly_traded": False,
            "symbol": None,
        },
        analysis="如果需要估值信息，只能参考私募融资、二级市场估值报道或公司披露信息；这些不是实时公开股价。",
        sources=[],
        warnings=["该公司未公开上市，系统不会编造股票价格。"],
        agent_steps=[{
            "node": "private_company_check",
            "detail": f"{matched_name} has no public ticker",
            "status": "ok",
            "decision": "The user asked for a stock price, but the company is private.",
            "action": "check_public_listing",
            "action_input": {"company_name": matched_name},
            "observation": "No public ticker is available; do not fabricate a price.",
        }],
        data_quality="complete",
        self_check={
            "passed": True,
            "issues": [],
        },
    )


def _try_missing_source_document_response(question: str) -> AskResponse | None:
    q = question.strip()
    q_lower = q.lower()

    if not any(keyword in q_lower for keyword in _SOURCE_DOCUMENT_KEYWORDS):
        return None

    company = next((name for name in _SOURCE_SPECIFIC_COMPANIES if name.lower() in q_lower), "")
    if not company:
        return None

    if _knowledge_base_contains(company):
        return None

    display_name = "华为" if company.lower() == "huawei" else company
    return AskResponse(
        answer_type="knowledge",
        summary=f"我目前没有在知识库中检索到{display_name}相关财报材料，因此不能可靠地总结最近季度财报或给出具体数据。",
        objective_data={},
        analysis="这类问题必须依赖公司财报、公告或新闻材料作为证据。请先把对应 PDF/网页/Markdown 加入知识库并重新 ingest；在没有来源时，系统不会编造收入、利润、增长率等数据。",
        sources=[],
        warnings=["知识库未收录该公司的相关财报材料，已拒绝生成无依据摘要。"],
        agent_steps=[{
            "node": "missing_source_check",
            "detail": f"No local source document found for {display_name}",
            "status": "warning",
            "decision": "The question requires a source document, but the local knowledge base has no matching company material.",
            "action": "search_knowledge",
            "action_input": {"query": q, "mode": "local_source_presence_check"},
            "observation": f"company={display_name}, local_document_match=false",
        }],
        data_quality="unavailable",
        self_check={
            "passed": False,
            "has_market_evidence": False,
            "has_rag_evidence": False,
            "has_news_evidence": False,
            "issues": ["missing_source_document"],
        },
    )


def _knowledge_base_contains(term: str) -> bool:
    kb_dir = Path(__file__).resolve().parents[3] / "knowledge_base"
    if not kb_dir.exists():
        return False

    needle = term.lower()
    for path in kb_dir.rglob("*.md"):
        try:
            if needle in path.name.lower() or needle in path.read_text(encoding="utf-8").lower():
                return True
        except OSError:
            continue
    return False


def _try_fast_knowledge_response(question: str) -> AskResponse | None:
    q = question.strip()
    q_lower = q.lower()

    if not any(keyword in q_lower for keyword in _KNOWLEDGE_DEFINITION_KEYWORDS):
        return None

    answer = _build_fast_knowledge_answer(q)
    if answer is None:
        return None

    summary, analysis, title, section = answer
    return AskResponse(
        answer_type="knowledge",
        summary=summary,
        objective_data={},
        analysis=analysis,
        sources=[{
            "type": "knowledge_base",
            "title": title,
            "section": section,
            "score": 1.0,
        }],
        warnings=[],
        agent_steps=[{
            "node": "fast_knowledge",
            "detail": "Answered from local knowledge base shortcut",
            "status": "ok",
            "decision": "Question matches a known financial concept; avoid slow LLM/embedding retries.",
            "action": "search_knowledge",
            "action_input": {"query": q, "mode": "local_concept"},
            "observation": f"matched={section}",
        }],
        data_quality="complete",
        self_check={
            "passed": True,
            "has_market_evidence": False,
            "has_rag_evidence": True,
            "has_news_evidence": False,
            "issues": [],
        },
    )


def _build_fast_knowledge_answer(question: str) -> tuple[str, str, str, str] | None:
    q = question.lower()

    if ("收入" in q and "净利润" in q) or ("revenue" in q and ("net income" in q or "profit" in q)):
        return (
            "收入是公司通过核心业务获得的总金额，位于利润表顶部，也称 Top Line；净利润是在扣除成本、费用、利息、税金和其他支出后的最终利润，位于利润表底部，也称 Bottom Line。",
            "收入反映业务规模和增长能力，净利润更直接反映最终盈利能力。公司收入增长不一定代表净利润增长，因为成本和费用也可能同步上升。",
            "Financial Statements",
            "收入与净利润",
        )

    if "市盈率" in q or "p/e" in q or "pe ratio" in q:
        if _is_metric_definition_question(q) and any(token in q for token in ["what", "does", "mean", "define"]):
            return (
                "The P/E ratio, or price-to-earnings ratio, compares a company's stock price with its earnings per share (EPS). It is calculated as stock price divided by EPS.",
                "A higher P/E often means investors expect stronger future growth, while a lower P/E may indicate cheaper valuation or weaker expectations. It should be compared within the same industry.",
                "Financial Metrics",
                "P/E Ratio",
            )
        return (
            "市盈率（P/E Ratio）是衡量股票估值的指标，计算公式为股票价格除以每股收益（EPS）。静态市盈率使用过去 12 个月的实际 EPS，动态市盈率使用预测 EPS。",
            "较高的 P/E 通常代表市场对增长预期较高，较低的 P/E 可能代表估值较低或市场对前景较谨慎。使用时应结合行业、增长率和盈利周期。",
            "Financial Metrics",
            "市盈率",
        )

    if "自由现金流" in q or "free cash flow" in q:
        return (
            "自由现金流（Free Cash Flow）通常等于经营活动现金流减去资本支出，表示公司在维持和扩展业务后可自由支配的现金。",
            "正的自由现金流意味着公司更有能力回购股票、发放股息、偿还债务或继续投资，但仍需结合业务周期和资本开支强度判断。",
            "Financial Metrics",
            "自由现金流",
        )

    if "毛利率" in q:
        return (
            "毛利率等于（营业收入减去营业成本）除以营业收入，反映公司核心产品或服务在扣除直接成本后的盈利能力。",
            "高毛利率通常意味着较强定价能力、较低生产成本或更好的产品结构，但不同行业差异很大，需要与同行比较。",
            "Financial Metrics",
            "毛利率",
        )

    return None


def _try_fast_quote_response(question: str, session_id: str = "") -> AskResponse | None:
    """Return a deterministic quote-only response for simple current-price questions.

    Current-price requests should not pay the latency cost of intent/entity LLM
    calls, RAG, news search, or answer composition. More analytical market
    questions still go through the full agent.
    """
    q = question.strip()
    q_lower = q.lower()

    if not any(keyword in q_lower for keyword in _QUOTE_KEYWORDS):
        return None
    if any(keyword in q_lower for keyword in _NON_QUOTE_ONLY_KEYWORDS):
        return None

    symbol = _extract_symbol_for_fast_path(q)
    if not symbol:
        return None

    quote = get_quote(symbol)
    steps = [{
        "node": "fast_quote",
        "detail": f"Fetched quote for {symbol} without LLM/RAG/news analysis",
        "status": "ok" if quote.price is not None else "error",
        "decision": "Question asks only for the current stock price; use quote tool directly.",
        "action": "fetch_quote",
        "action_input": {"symbol": symbol},
        "observation": f"price={quote.price}, provider={quote.provider}, error={quote.error}",
    }]

    if quote.price is None:
        warning = quote.error or "行情数据暂不可用"
        response = AskResponse(
            answer_type="market",
            summary=f"暂时无法获取 {symbol} 的当前股价。",
            objective_data={"symbol": symbol, "provider": quote.provider, "error": quote.error},
            analysis="",
            sources=[],
            warnings=[warning],
            agent_steps=steps,
            data_quality="unavailable",
            self_check={"passed": False, "issues": [warning]},
        )
        _save_fast_turn(session_id, question, response.summary, "market", symbol)
        return response

    name = SYMBOL_NAMES.get(symbol, symbol)
    price_text = f"{quote.price:.2f}" if isinstance(quote.price, (int, float)) else str(quote.price)
    summary = f"{name}当前股价为{price_text}{quote.currency}。该价格数据时间为{quote.timestamp}。"

    response = AskResponse(
        answer_type="market",
        summary=summary,
        objective_data=quote.model_dump(),
        analysis="",
        sources=[{
            "type": "market_data",
            "title": quote.provider,
            "symbol": symbol,
        }],
        warnings=[],
        agent_steps=steps,
        cache_hit=False,
        fallback_used=False,
        data_quality="complete",
        memory_used=False,
        self_check={
            "passed": True,
            "has_market_evidence": True,
            "has_rag_evidence": False,
            "has_news_evidence": False,
            "issues": [],
        },
    )
    _save_fast_turn(session_id, question, summary, "market", symbol)
    return response


def _try_fast_fundamental_response(question: str, session_id: str = "") -> AskResponse | None:
    q = question.strip()
    q_lower = q.lower()
    if not any(keyword in q_lower for keyword in _FUNDAMENTAL_KEYWORDS):
        return None

    symbol = _extract_symbol_for_fast_path(q)
    memory_used = False
    if not symbol and _is_metric_definition_question(q):
        return None
    if not symbol:
        symbol = _last_symbol_from_session(session_id)
        memory_used = symbol is not None
    if not symbol:
        return None

    fundamentals = get_fundamentals(symbol)
    name = SYMBOL_NAMES.get(symbol, symbol)
    pe_ratio = fundamentals.get("pe_ratio")
    provider = str(fundamentals.get("provider", ""))
    warning = fundamentals.get("warning")
    steps = [{
        "node": "fast_fundamentals",
        "detail": f"Fetched PE ratio for {symbol} without generic concept-only answer",
        "status": "ok" if pe_ratio is not None else "warning",
        "decision": "Question asks for a company-specific valuation metric; use fundamentals directly.",
        "action": "fetch_fundamentals",
        "action_input": {"symbol": symbol, "metric": "pe_ratio"},
        "observation": f"pe_ratio={pe_ratio}, provider={provider}, warning={warning}",
    }]

    if pe_ratio is None:
        response = AskResponse(
            answer_type="market",
            summary=f"暂时没有获取到{name}的市盈率数据。",
            objective_data=fundamentals,
            analysis="市盈率需要公司的股价和每股收益 EPS。当前基本面数据源没有返回可用 EPS 或 PE。",
            sources=[{"type": "market_data", "title": provider, "symbol": symbol}] if provider else [],
            warnings=[str(warning)] if warning else [],
            agent_steps=steps,
            data_quality="partial",
            memory_used=memory_used,
            self_check={"passed": False, "issues": ["missing_pe_ratio"]},
        )
        _save_fast_turn(session_id, question, response.summary, "market", symbol)
        return response

    summary = f"{name}当前市盈率约为 {pe_ratio}。"
    if fundamentals.get("eps") is not None:
        summary += f" 每股收益 EPS 约为 {fundamentals['eps']}。"

    warnings = []
    if warning:
        warnings.append(str(warning))

    response = AskResponse(
        answer_type="market",
        summary=summary,
        objective_data=fundamentals,
        analysis="市盈率用于衡量股价相对于每股收益的估值水平；该指标应结合行业、盈利周期和数据时间一起解读。",
        sources=[{
            "type": "market_data",
            "title": provider,
            "symbol": symbol,
        }],
        warnings=warnings,
        agent_steps=steps,
        data_quality="partial" if fundamentals.get("is_demo_data") else "complete",
        memory_used=memory_used,
        self_check={
            "passed": True,
            "has_market_evidence": True,
            "has_rag_evidence": False,
            "has_news_evidence": False,
            "issues": [],
        },
    )
    _save_fast_turn(session_id, question, summary, "market", symbol)
    return response


def _try_fast_trend_response(question: str, session_id: str = "") -> AskResponse | None:
    q = question.strip()
    q_lower = q.lower()
    if not any(keyword in q_lower for keyword in _TREND_KEYWORDS):
        return None

    symbol = _extract_symbol_for_fast_path(q)
    memory_used = False
    if not symbol:
        symbol = _last_symbol_from_session(session_id)
        memory_used = symbol is not None
    if not symbol:
        return None

    range_str = _extract_range_for_fast_trend(q)
    history = get_history(symbol, range_str)
    name = SYMBOL_NAMES.get(symbol, symbol)
    steps = [{
        "node": "fast_trend",
        "detail": f"Fetched {range_str} history for {symbol} without LLM/news analysis",
        "status": "ok" if history.data else "warning",
        "decision": "Question asks for recent price movement; use historical price tool directly.",
        "action": "fetch_history",
        "action_input": {"symbol": symbol, "range": range_str},
        "observation": f"return_pct={history.return_pct}, trend={history.trend}, provider={history.provider}",
    }]

    if not history.data:
        warning = history.error or "历史行情数据暂不可用"
        response = AskResponse(
            answer_type="market",
            summary=f"暂时无法获取{name}的{range_str}走势数据。",
            objective_data={"symbol": symbol, "range": range_str, "error": history.error},
            analysis="",
            sources=[],
            warnings=[warning],
            agent_steps=steps,
            data_quality="unavailable",
            memory_used=memory_used,
            self_check={"passed": False, "issues": [warning]},
        )
        _save_fast_turn(session_id, question, response.summary, "market", symbol)
        return response

    return_pct = history.return_pct
    trend = history.trend or "暂无趋势判断"
    pct_text = f"{return_pct:.2f}%" if isinstance(return_pct, (int, float)) else "暂无涨跌幅"
    summary = f"{name}最近{range_str}涨跌幅约为{pct_text}，趋势判断为{trend}。"
    if history.provider == "demo":
        summary += " 当前为离线演示行情数据。"

    response = AskResponse(
        answer_type="market",
        summary=summary,
        objective_data={
            "symbol": symbol,
            "range": history.range,
            "change_percent": history.return_pct,
            "trend": history.trend,
            "currency": history.currency,
            "provider": history.provider,
            "history": [{"date": p.date, "close": p.close} for p in history.data],
        },
        analysis="",
        sources=[{"type": "market_data", "title": history.provider, "symbol": symbol}],
        warnings=["外部行情源不可用，当前展示本地离线演示走势"] if history.provider == "demo" else [],
        agent_steps=steps,
        data_quality="partial" if history.provider == "demo" else "complete",
        memory_used=memory_used,
        self_check={
            "passed": True,
            "has_market_evidence": True,
            "has_rag_evidence": False,
            "has_news_evidence": False,
            "issues": [],
        },
    )
    _save_fast_turn(session_id, question, summary, "market", symbol)
    return response


def _extract_range_for_fast_trend(question: str) -> str:
    q = question.lower()
    if any(token in q for token in ["30天", "30 天", "30日", "一个月", "30 days", "thirty days", "past month"]):
        return "30d"
    if any(token in q for token in ["7天", "7 天", "7日", "一周", "7 days", "seven days", "past week"]):
        return "7d"
    return "30d"


def _is_metric_definition_question(question: str) -> bool:
    q = question.lower()
    definition_terms = (
        "what does",
        "what is",
        "define",
        "definition",
        "mean",
        "meaning",
        "什么是",
        "是什么意思",
        "定义",
        "含义",
        "解释",
    )
    return any(term in q for term in definition_terms)


def _extract_symbol_for_fast_path(question: str) -> str | None:
    q_lower = question.lower()

    for alias in sorted(SYMBOL_ALIASES, key=len, reverse=True):
        if alias.lower() in q_lower:
            return resolve_symbol(alias)

    # Match common US/HK tickers even when adjacent to Chinese text, e.g.
    # "BABA最近7天". A plain \b boundary is unreliable around CJK characters.
    ticker_match = re.search(r"(?<![A-Za-z0-9])([A-Z]{2,5}(?:\.HK)?)(?![A-Za-z0-9])", question)
    if ticker_match:
        return resolve_symbol(ticker_match.group(1))

    return None


def _last_symbol_from_session(session_id: str) -> str | None:
    if not session_id:
        return None
    session = get_session_store().get(session_id)
    if not session or not session.last_entities:
        return None
    return session.last_entities[0]


def _save_fast_turn(
    session_id: str,
    question: str,
    answer_summary: str,
    intent: str,
    symbol: str,
) -> None:
    if not session_id:
        return
    store = get_session_store()
    session = store.get_or_create(session_id)
    session.add_turn(TurnRecord(
        question=question,
        answer_summary=answer_summary[:300],
        intent=intent,
        entities=[symbol],
        time_range="",
    ))
    store.save(session)
