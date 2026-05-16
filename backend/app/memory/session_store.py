"""Short-term session memory for multi-turn conversations."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TurnRecord:
    question: str
    answer_summary: str = ""
    intent: str = ""
    entities: list[str] | dict = field(default_factory=list)
    time_range: str = ""
    summary: str = ""
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.answer_summary and self.summary:
            self.answer_summary = self.summary


@dataclass
class SessionMemory:
    session_id: str
    turns: list[TurnRecord] = field(default_factory=list)
    last_entities: list[str] | dict = field(default_factory=list)
    last_intent: str = ""
    last_time_range: str = ""
    max_turns: int = 6
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add_turn(self, turn: TurnRecord) -> None:
        self.turns.append(turn)
        if len(self.turns) > self.max_turns:
            self.turns = self.turns[-self.max_turns:]
        if turn.entities:
            self.last_entities = turn.entities
        if turn.intent:
            self.last_intent = turn.intent
        if turn.time_range:
            self.last_time_range = turn.time_range
        self.updated_at = time.time()

    def get_context_summary(self) -> dict:
        return {
            "recent_turns": [
                {"q": t.question, "a": t.answer_summary[:200], "intent": t.intent, "entities": t.entities}
                for t in self.turns[-3:]
            ],
            "last_entities": self.last_entities,
            "last_intent": self.last_intent,
            "last_time_range": self.last_time_range,
        }


class SessionStore:
    """In-memory session store. Interface supports future SQLite/Redis swap."""

    def __init__(self, max_turns: int = 6) -> None:
        self.max_turns = max_turns
        self._sessions: dict[str, SessionMemory] = {}

    def get(self, session_id: str) -> Optional[SessionMemory]:
        return self._sessions.get(session_id)

    def get_or_create(self, session_id: str) -> SessionMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMemory(session_id=session_id, max_turns=self.max_turns)
        return self._sessions[session_id]

    def save(self, session: SessionMemory) -> None:
        self._sessions[session.session_id] = session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def add_turn(self, session_id: str, turn: TurnRecord) -> None:
        """Compatibility wrapper used by tests and simple callers."""
        session = self.get_or_create(session_id)
        session.add_turn(turn)
        self.save(session)

    def get_memory(self, session_id: str) -> dict:
        """Return a serializable memory snapshot for callers that do not need the object."""
        session = self.get(session_id)
        if not session:
            return {}
        return {
            "history": [
                {
                    "question": turn.question,
                    "summary": turn.answer_summary,
                    "intent": turn.intent,
                    "entities": turn.entities,
                    "time_range": turn.time_range,
                }
                for turn in session.turns
            ],
            "last_entities": session.last_entities,
            "last_intent": session.last_intent,
            "last_time_range": session.last_time_range,
        }


# Module-level singleton
_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
