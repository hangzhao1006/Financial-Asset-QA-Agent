"""LLM-powered Planner - the Agent brain that decides which tools to call.

This is the core 'agent' node: the LLM sees the question, intent, entities,
and available tools, then decides what actions to take. This is analogous to
smolagents' ToolCallingAgent deciding which tool to invoke.
"""
from __future__ import annotations

import json
import logging

from backend.app.agent.state import AgentState
from backend.app.services.llm import chat_json

logger = logging.getLogger(__name__)

PLANNER_PROMPT = """You are a financial QA agent planner. Given a user question, intent, and extracted entities,
decide which tools to call to gather evidence for answering.

Available tools:
- fetch_quote: Get current stock price. Requires: symbol. Returns price, currency, timestamp.
- fetch_history: Get historical prices + return. Requires: symbol, range (7d/30d/3m/6m/1y). Returns prices, return%, trend.
- search_knowledge: Search the financial knowledge base (RAG). For concept/term questions and company report / filing questions. Requires: query string.
- search_news: Search web for recent news about a company/event. Requires: query string.

Rules:
- For market price questions: MUST use fetch_quote
- For market trend/movement questions: MUST use fetch_history
- For financial concept/term questions: MUST use search_knowledge
- For annual report, quarterly report, 10-K, 10-Q, risk factor, revenue-from-report, or management discussion questions: MUST use search_knowledge
- For "why did stock move" questions: use fetch_history + search_news
- You can call multiple tools
- Do NOT call tools that are unnecessary

User question: {question}
Intent: {intent}
Entities: {entities}
Memory context: {memory}

Respond in JSON:
{{
  "reasoning": "brief explanation of your plan",
  "actions": [
    {{"tool": "tool_name", "params": {{"key": "value"}}}}
  ]
}}
"""


async def planner(state: AgentState) -> AgentState:
    entities = state.entities or {}
    symbols = entities.get("symbols", [])
    time_range = entities.get("time_range", "7d") or "7d"

    memory_str = ""
    if state.memory.get("last_entities"):
        memory_str = f"Previous entities: {state.memory['last_entities']}"

    prompt = PLANNER_PROMPT.format(
        question=state.question,
        intent=state.intent,
        entities=json.dumps(entities, ensure_ascii=False),
        memory=memory_str or "none",
    )

    try:
        result = await chat_json(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        actions = result.get("actions", [])
        reasoning = result.get("reasoning", "")

        # Validate and normalize actions
        valid_tools = {"fetch_quote", "fetch_history", "search_knowledge", "search_news"}
        validated_actions = []
        for action in actions:
            tool = action.get("tool", "")
            if tool in valid_tools:
                validated_actions.append(action)

        state.plan = validated_actions
        state.add_step(
            "planner",
            f"Plan: {reasoning} -> {[a['tool'] for a in validated_actions]}",
            decision=reasoning or "Select tools based on intent and extracted entities.",
            action="plan_tools",
            action_input={"intent": state.intent, "entities": entities},
            observation=f"actions={[a['tool'] for a in validated_actions]}",
        )

    except Exception as exc:
        logger.error("Planner LLM call failed: %s", exc)

        # Fallback: rule-based plan based on intent
        fallback_plan = _fallback_plan(state.intent, symbols, time_range, state.question)
        state.plan = fallback_plan
        state.add_step(
            "planner",
            f"Fallback plan: {[a['tool'] for a in fallback_plan]}",
            "warning",
            decision="LLM planner failed; use deterministic fallback plan.",
            action="plan_tools_fallback",
            action_input={"intent": state.intent, "symbols": symbols, "time_range": time_range},
            observation=f"actions={[a['tool'] for a in fallback_plan]}",
        )

    return state


def _fallback_plan(intent: str, symbols: list, time_range: str, question: str) -> list:
    """Simple rule-based fallback if LLM planner fails."""
    actions = []

    if intent in ("market", "hybrid", "event"):
        for sym in symbols:
            actions.append({"tool": "fetch_quote", "params": {"symbol": sym}})
            if intent != "market" or time_range:
                actions.append({"tool": "fetch_history", "params": {"symbol": sym, "range": time_range}})

    if intent in ("knowledge", "hybrid"):
        actions.append({"tool": "search_knowledge", "params": {"query": question}})

    if intent == "event":
        actions.append({"tool": "search_news", "params": {"query": question}})

    return actions