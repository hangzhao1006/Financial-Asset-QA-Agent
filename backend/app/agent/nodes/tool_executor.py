"""Execute planned tools and collect evidence.

The planner produces actions like:
  [{"tool": "fetch_quote", "params": {"symbol": "BABA"}}]

This node executes each action and appends results to state.evidence.
"""
from __future__ import annotations

import logging

from backend.app.agent.state import AgentState
from backend.app.services.market_data import get_quote, get_history, resolve_symbol
from backend.app.services.rag import retrieve
from backend.app.services.news_search import search_news

logger = logging.getLogger(__name__)


async def tool_executor(state: AgentState) -> AgentState:
    if not state.plan:
        state.add_step("tool_executor", "No actions planned", "skip")
        return state

    symbols = state.entities.get("symbols", [])
    time_range = state.entities.get("time_range", "7d") or "7d"
    executed = []

    for action in state.plan:
        # Support both dict format (from LLM planner) and string format (legacy)
        if isinstance(action, dict):
            tool_name = action.get("tool", "")
            params = action.get("params", {})
        elif isinstance(action, str):
            tool_name = action
            params = {}
        else:
            continue

        try:
            if tool_name == "fetch_quote":
                target_symbols = params.get("symbol", None)
                if target_symbols:
                    syms = [target_symbols] if isinstance(target_symbols, str) else target_symbols
                else:
                    syms = symbols

                for sym in syms:
                    resolved = resolve_symbol(sym)
                    quote = get_quote(resolved)
                    state.tool_results[f"quote_{resolved}"] = quote
                    if quote.price is not None:
                        state.evidence.append({
                            "type": "market_quote",
                            "symbol": resolved,
                            "data": quote.model_dump(),
                        })
                executed.append(f"fetch_quote({syms})")
                state.add_step(
                    "tool_executor",
                    f"fetch_quote({syms})",
                    action="fetch_quote",
                    action_input={"symbols": syms},
                    observation=f"quotes fetched for {syms}",
                )

            elif tool_name == "fetch_history":
                target_symbols = params.get("symbol", None)
                rng = params.get("range", time_range)
                if target_symbols:
                    syms = [target_symbols] if isinstance(target_symbols, str) else target_symbols
                else:
                    syms = symbols

                for sym in syms:
                    resolved = resolve_symbol(sym)
                    hist = get_history(resolved, rng)
                    state.tool_results[f"history_{resolved}"] = hist
                    if hist.data:
                        state.evidence.append({
                            "type": "market_history",
                            "symbol": resolved,
                            "data": hist.model_dump(),
                        })
                executed.append(f"fetch_history({syms}, {rng})")
                state.add_step(
                    "tool_executor",
                    f"fetch_history({syms}, {rng})",
                    action="fetch_history",
                    action_input={"symbols": syms, "range": rng},
                    observation=f"history fetched for {syms}, range={rng}",
                )

            elif tool_name == "search_knowledge":
                query = params.get("query", state.question)
                chunks = await retrieve(query)
                state.tool_results["rag_chunks"] = chunks
                for c in chunks:
                    state.evidence.append({
                        "type": "rag_chunk",
                        "text": c.text,
                        "metadata": c.metadata,
                        "score": c.score,
                    })
                executed.append(f"search_knowledge({len(chunks)} chunks)")
                state.add_step(
                    "tool_executor",
                    f"search_knowledge({len(chunks)} chunks)",
                    action="search_knowledge",
                    action_input={"query": query},
                    observation=f"retrieved {len(chunks)} knowledge chunks",
                )

            elif tool_name == "search_news":
                query = params.get("query", "")
                if not query:
                    # Build query from entities
                    parts = [resolve_symbol(s) for s in symbols]
                    parts.extend(state.entities.get("company_names", []))
                    query = " ".join(parts) + " stock news"

                news = await search_news(query)
                state.tool_results["news"] = news
                if news.get("results"):
                    state.evidence.append({
                        "type": "news_search",
                        "data": news,
                    })
                executed.append(f"search_news({len(news.get('results', []))} results)")
                state.add_step(
                    "tool_executor",
                    f"search_news({len(news.get('results', []))} results)",
                    action="search_news",
                    action_input={"query": query},
                    observation=f"retrieved {len(news.get('results', []))} news results",
                )

            else:
                logger.warning("Unknown tool: %s", tool_name)
                executed.append(f"unknown:{tool_name}")

        except Exception as exc:
            logger.error("Tool %s failed: %s", tool_name, exc)
            state.add_step("tool_executor", f"{tool_name} failed: {exc}", "error")
            executed.append(f"{tool_name}(FAILED)")

    state.add_step(
        "tool_executor",
        f"Executed: {', '.join(executed)}",
        decision="Execute planned tools and attach returned evidence to state.",
        observation=f"executed={executed}",
    )
    return state