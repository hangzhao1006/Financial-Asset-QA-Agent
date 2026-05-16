"""Write conversation context back to session memory."""
from __future__ import annotations

from backend.app.agent.state import AgentState
from backend.app.memory.session_store import get_session_store, TurnRecord


async def context_writer(state: AgentState) -> AgentState:
    if not state.session_id:
        state.add_step("context_writer", "No session_id, skipping")
        return state

    store = get_session_store()
    session = store.get_or_create(state.session_id)

    turn = TurnRecord(
        question=state.question,
        answer_summary=state.answer.get("summary", "")[:300],
        intent=state.intent,
        entities=state.entities.get("symbols", []),
        time_range=state.entities.get("time_range", ""),
    )
    session.add_turn(turn)
    store.save(session)

    state.add_step("context_writer", f"Saved turn #{len(session.turns)} to session")
    return state
