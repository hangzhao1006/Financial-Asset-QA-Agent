"""Compose structured answer using LLM and evidence."""
from __future__ import annotations

import json
import logging

from backend.app.agent.state import AgentState
from backend.app.services.llm import chat_json
from backend.app.prompts.answer_prompts import (
    ANSWER_MARKET_PROMPT,
    ANSWER_KNOWLEDGE_PROMPT,
    ANSWER_HYBRID_PROMPT,
)

logger = logging.getLogger(__name__)


async def answer_composer(state: AgentState) -> AgentState:
    intent = state.intent
    memory_ctx = json.dumps(state.memory, ensure_ascii=False) if state.memory else "No context"

    # Gather evidence strings
    market_data = _format_market_evidence(state)
    rag_context = _format_rag_evidence(state)
    news_data = _format_news_evidence(state)

    if intent == "knowledge" and not _has_rag_evidence(state):
        fallback = _build_local_knowledge_answer(state.question)
        if fallback:
            state.answer = fallback
            if "知识库未检索到直接材料，已使用本地概念知识兜底回答" not in state.warnings:
                state.warnings.append("知识库未检索到直接材料，已使用本地概念知识兜底回答")
            state.add_step(
                "answer_composer",
                "Used local concept fallback",
                "warning",
                decision="No RAG evidence was retrieved, but the question matches a known finance concept.",
                action="compose_local_concept_answer",
                action_input={"question": state.question},
                observation=f"data_quality={fallback.get('data_quality')}",
            )
            return state

        state.answer = _build_insufficient_knowledge_answer(state.question)
        if "知识库未检索到该问题的可引用材料，已拒绝生成无依据摘要" not in state.warnings:
            state.warnings.append("知识库未检索到该问题的可引用材料，已拒绝生成无依据摘要")
        state.add_step(
            "answer_composer",
            "No RAG evidence; refused unsupported knowledge answer",
            "warning",
            decision="The question asks for source-specific information, but retrieval returned no evidence.",
            action="refuse_unsupported_summary",
            action_input={"question": state.question},
            observation="rag_chunks=0",
        )
        return state

    try:
        if intent == "market":
            prompt = ANSWER_MARKET_PROMPT.format(
                market_data=market_data, news_data=news_data,
                memory_context=memory_ctx, question=state.question,
            )
        elif intent == "knowledge":
            prompt = ANSWER_KNOWLEDGE_PROMPT.format(
                rag_context=rag_context, memory_context=memory_ctx,
                question=state.question,
            )
        else:  # hybrid, event
            prompt = ANSWER_HYBRID_PROMPT.format(
                market_data=market_data, rag_context=rag_context,
                news_data=news_data, memory_context=memory_ctx,
                question=state.question,
            )

        result = await chat_json([{"role": "user", "content": prompt}], temperature=0.3)

        state.answer = {
            "answer_type": intent,
            "summary": result.get("summary", ""),
            "objective_data": result.get("objective_data", {}),
            "analysis": result.get("analysis", ""),
            "data_quality": result.get("data_quality", state.data_quality),
        }

        # Auto-populate objective_data from market evidence if LLM didn't
        if intent in ("market", "hybrid", "event") and not state.answer["objective_data"]:
            state.answer["objective_data"] = _build_objective_data(state)

        # Merge warnings (filter out redundant ones from LLM)
        result_warnings = result.get("warnings", [])
        for w in result_warnings:
            # Skip generic/redundant warnings the LLM tends to add
            if any(skip in w for skip in ["不构成", "投资建议", "仅供参考", "disclaimer", "past performance"]):
                continue
            if w not in state.warnings:
                state.warnings.append(w)

        state.add_step("answer_composer", f"Generated {intent} answer")

    except Exception as exc:
        logger.error("Answer composition failed: %s", exc)
        fallback = (
            _build_rag_evidence_answer(state)
            if intent == "knowledge" and _has_rag_evidence(state)
            else _build_local_knowledge_answer(state.question)
            if intent == "knowledge"
            else _build_local_market_answer(state)
        )
        if fallback:
            state.answer = fallback
            warning = (
                "LLM/RAG 暂不可用，已使用本地知识库兜底回答"
                if intent == "knowledge"
                else "LLM 暂不可用，已基于可用工具证据生成保守兜底回答"
            )
            if warning not in state.warnings:
                state.warnings.append(warning)
            state.add_step(
                "answer_composer",
                "Used local evidence fallback",
                "warning",
                decision="LLM answer composition failed; use deterministic evidence-preserving fallback.",
                action="compose_local_fallback",
                action_input={"intent": intent},
                observation=f"answer_type={fallback.get('answer_type')}, data_quality={fallback.get('data_quality')}",
            )
        else:
            state.answer = {
                "answer_type": intent,
                "summary": f"抱歉，生成回答时出现错误: {exc}",
                "objective_data": {},
                "analysis": "",
                "data_quality": "unavailable",
            }
            state.add_step("answer_composer", f"Failed: {exc}", "error")

    return state


def _format_market_evidence(state: AgentState) -> str:
    parts = []
    for e in state.evidence:
        if e["type"] == "market_quote":
            d = e["data"]
            parts.append(f"Quote {e['symbol']}: price={d.get('price')}, currency={d.get('currency')}, time={d.get('timestamp')}")
        elif e["type"] == "market_history":
            d = e["data"]
            parts.append(f"History {e['symbol']}: range={d.get('range')}, return={d.get('return_pct')}%, trend={d.get('trend')}, points={len(d.get('data', []))}")
    return "\n".join(parts) if parts else "No market data available"


def _format_rag_evidence(state: AgentState) -> str:
    parts = []
    for e in state.evidence:
        if e["type"] == "rag_chunk":
            parts.append(f"[{e.get('metadata', {}).get('title', 'unknown')}] {e['text'][:600]}")
    return "\n---\n".join(parts) if parts else "No knowledge base results found"


def _format_news_evidence(state: AgentState) -> str:
    for e in state.evidence:
        if e["type"] == "news_search":
            results = e.get("data", {}).get("results", [])
            parts = [f"- {r['title']}: {r['content'][:200]}" for r in results[:5]]
            return "\n".join(parts)
    return "No news data available"


def _has_rag_evidence(state: AgentState) -> bool:
    return any(e.get("type") == "rag_chunk" for e in state.evidence)


def _build_objective_data(state: AgentState) -> dict:
    """Build objective_data dict from raw market evidence."""
    obj: dict = {}
    for e in state.evidence:
        if e["type"] == "market_quote":
            d = e.get("data", {})
            obj.update({
                "symbol": e.get("symbol", ""),
                "price": d.get("price"),
                "currency": d.get("currency", "USD"),
                "timestamp": d.get("timestamp"),
                "provider": d.get("provider", ""),
            })
        elif e["type"] == "market_history":
            d = e.get("data", {})
            obj.update({
                "symbol": e.get("symbol", ""),
                "change_percent": d.get("return_pct"),
                "trend": d.get("trend"),
                "range": d.get("range"),
                "history": [{"date": p.get("date"), "close": p.get("close")} for p in d.get("data", [])[-30:]],
            })
    return obj


def _build_insufficient_knowledge_answer(question: str) -> dict:
    return {
        "answer_type": "knowledge",
        "summary": "我目前没有在知识库中检索到可引用的相关材料，因此不能可靠地总结这份财报或给出具体数据。",
        "objective_data": {},
        "analysis": "这类问题需要公司财报、公告或新闻材料作为证据。请先把对应财报加入知识库，或换成已收录资料中的问题；在没有来源时，系统不会编造收入、利润、增长率等数据。",
        "data_quality": "unavailable",
    }


def _build_rag_evidence_answer(state: AgentState) -> dict | None:
    chunks = [e for e in state.evidence if e.get("type") == "rag_chunk"]
    if not chunks:
        return None

    question = state.question
    source_titles = []
    snippets = []
    for evidence in chunks[:4]:
        metadata = evidence.get("metadata", {})
        title = metadata.get("title") or metadata.get("source_file") or "knowledge source"
        if title not in source_titles:
            source_titles.append(title)
        text = " ".join(str(evidence.get("text", "")).split())
        if text:
            snippets.append(text[:220])

    if _looks_english(question.lower()):
        summary = (
            f"Based on the retrieved report excerpts for: {question} "
            f"The most relevant sources are {', '.join(source_titles[:3])}. "
            f"Key retrieved evidence: {' '.join(snippets[:2])}"
        )
        analysis = (
            "The LLM composer was unavailable, so this is a conservative extractive summary from retrieved RAG chunks. "
            "Use the cited sources for verification before relying on exact wording or figures."
        )
    else:
        summary = (
            f"根据已检索到的财报片段，问题“{question}”可以先参考这些来源："
            f"{'、'.join(source_titles[:3])}。"
            f"关键证据片段：{' '.join(snippets[:2])}"
        )
        analysis = (
            "LLM 生成器暂不可用，因此这里返回的是基于 RAG 召回片段的保守摘要。"
            "涉及精确数字、同比或完整段落时，应回到来源文件核对。"
        )

    return {
        "answer_type": "knowledge",
        "summary": summary[:900],
        "objective_data": {},
        "analysis": analysis,
        "data_quality": "partial",
    }


def _build_local_market_answer(state: AgentState) -> dict | None:
    """Conservative fallback for market/event/safety questions when LLM is down."""
    if state.intent not in ("market", "hybrid", "event"):
        return None

    objective_data = _build_objective_data(state)
    q = state.question.lower()
    if _is_investment_advice_question(q):
        return {
            "answer_type": state.intent,
            "summary": "我不能直接给出买入或卖出结论。可以参考已获取的行情数据、公司基本面、估值、风险承受能力和投资期限做进一步分析；以上信息仅供参考，不构成投资建议。",
            "objective_data": objective_data,
            "analysis": "投资决策需要结合个人目标和风险偏好，系统只提供信息整理，不给出买入或卖出指令。",
            "data_quality": "partial" if objective_data else "unavailable",
        }

    if state.intent == "event":
        history = _latest_history_evidence(state)
        if history:
            symbol = history.get("symbol", "")
            data = history.get("data", {})
            return_pct = data.get("return_pct")
            trend = data.get("trend") or "暂无趋势判断"
            pct_text = f"{return_pct:.2f}%" if isinstance(return_pct, (int, float)) else "暂无涨跌幅"
            return {
                "answer_type": "event",
                "summary": f"已先查看 {symbol} 的价格走势，当前区间涨跌幅约为 {pct_text}，趋势判断为{trend}。目前没有可引用的新闻证据，因此不能确认具体上涨原因或把走势归因于某个事件。",
                "objective_data": objective_data,
                "analysis": "因果类问题需要同时有价格验证和新闻/公告证据；缺少新闻来源时，应明确说明证据不足，避免编造原因。",
                "data_quality": "partial",
            }

    if objective_data:
        return {
            "answer_type": state.intent,
            "summary": "已获取到部分行情数据，但 LLM 暂不可用，因此只返回结构化客观数据，不做额外解读。",
            "objective_data": objective_data,
            "analysis": "",
            "data_quality": "partial",
        }

    return None


def _is_investment_advice_question(question: str) -> bool:
    advice_terms = ["应该买", "买入", "卖出", "值得买吗", "should i buy", "should i sell", "buy this stock"]
    return any(term in question for term in advice_terms)


def _latest_history_evidence(state: AgentState) -> dict | None:
    for evidence in reversed(state.evidence):
        if evidence.get("type") == "market_history":
            return evidence
    return None


def _build_local_knowledge_answer(question: str) -> dict | None:
    """Deterministic fallback for core finance concepts in the demo KB."""
    q = question.lower()

    if "市盈率" in q or "p/e" in q or "pe ratio" in q:
        if _looks_english(q):
            return {
                "answer_type": "knowledge",
                "summary": "The P/E ratio, or price-to-earnings ratio, compares a company's stock price with its earnings per share (EPS). It is calculated as stock price divided by EPS. A higher P/E often means investors expect stronger future growth, while a lower P/E may indicate cheaper valuation or weaker expectations.",
                "objective_data": {},
                "analysis": "P/E should be compared within the same industry and interpreted together with growth, profitability, accounting quality, and the earnings cycle.",
                "data_quality": "partial",
            }
        return {
            "answer_type": "knowledge",
            "summary": "市盈率（P/E Ratio）是衡量股票估值的指标，计算公式为股票价格除以每股收益（EPS）。静态市盈率使用过去 12 个月的实际 EPS，动态市盈率使用预测 EPS。较高的 P/E 通常代表市场对增长预期较高，较低的 P/E 可能代表估值较低或市场对前景较谨慎。",
            "objective_data": {},
            "analysis": "使用市盈率时应结合行业、盈利周期、公司增长率和一次性收益/费用，不能单独作为投资结论。",
            "data_quality": "partial",
        }

    if "收入" in q and "净利润" in q:
        return {
            "answer_type": "knowledge",
            "summary": "收入是公司通过核心业务获得的总金额，位于利润表顶部，也称 Top Line；净利润是在扣除成本、费用、利息、税金和其他支出后的最终利润，位于利润表底部，也称 Bottom Line。",
            "objective_data": {},
            "analysis": "收入反映业务规模和增长能力，净利润更直接反映最终盈利能力。公司收入增长不一定代表净利润增长，因为成本和费用也可能同步上升。",
            "data_quality": "partial",
        }

    if "自由现金流" in q or "free cash flow" in q:
        return {
            "answer_type": "knowledge",
            "summary": "自由现金流（Free Cash Flow）通常等于经营活动现金流减去资本支出，表示公司在维持和扩展业务后可自由支配的现金。",
            "objective_data": {},
            "analysis": "正的自由现金流意味着公司更有能力回购股票、发放股息、偿还债务或继续投资。它可能与净利润不同，因为净利润包含折旧、应收账款等非现金或权责发生制项目。",
            "data_quality": "partial",
        }

    if "牛市" in q or "熊市" in q:
        return {
            "answer_type": "knowledge",
            "summary": "牛市通常指市场价格持续上涨并进入乐观阶段，常用标准是较低点上涨 20% 以上；熊市通常指市场从高点下跌 20% 以上，并伴随风险偏好下降和投资者信心减弱。",
            "objective_data": {},
            "analysis": "牛市和熊市是市场阶段描述，不等于对未来走势的确定预测，应结合宏观环境、企业盈利和估值水平判断。",
            "data_quality": "partial",
        }

    if "毛利率" in q:
        return {
            "answer_type": "knowledge",
            "summary": "毛利率等于（营业收入减去营业成本）除以营业收入，反映公司核心产品或服务在扣除直接成本后的盈利能力。",
            "objective_data": {},
            "analysis": "高毛利率通常意味着较强定价能力、较低生产成本或更好的产品结构，但不同行业差异很大，需要与同行比较。",
            "data_quality": "partial",
        }

    if "贝塔" in q or "beta" in q:
        return {
            "answer_type": "knowledge",
            "summary": "贝塔系数（Beta）衡量个股相对于市场整体的波动性。Beta 等于 1 表示与市场大致同步波动，大于 1 表示波动通常更大，小于 1 表示波动通常更小。",
            "objective_data": {},
            "analysis": "Beta 是风险暴露指标，不代表资产一定上涨或下跌，也不能单独衡量公司基本面质量。",
            "data_quality": "partial",
        }

    return None


def _looks_english(question: str) -> bool:
    return any(token in question for token in ["what", "does", "mean", "define", "ratio"])