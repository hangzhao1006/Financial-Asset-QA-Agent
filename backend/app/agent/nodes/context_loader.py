"""Load session memory context into agent state."""
from __future__ import annotations
from backend.app.agent.state import AgentState
from backend.app.memory.session_store import get_session_store


async def context_loader(state: AgentState) -> AgentState:
    store = get_session_store()
    if state.session_id:
        session = store.get(state.session_id)
        if session:
            state.memory = session.get_context_summary()
            state.memory_used = bool(session.turns)
            state.add_step("context_loader", f"Loaded {len(session.turns)} turns from session")
        else:
            state.add_step("context_loader", "New session, no history")
    else:
        state.add_step("context_loader", "No session_id provided")
    return state
