"""LangGraph Agent state definition."""
from __future__ import annotations

from typing import Any, Optional
from dataclasses import dataclass, field


@dataclass
class AgentState:
    """Mutable state passed through the LangGraph agent nodes."""
    question: str = ""
    session_id: str = ""
    memory: dict = field(default_factory=dict)
    intent: str = ""
    intent_confidence: float = 0.0
    entities: dict = field(default_factory=dict)
    plan: list[str] = field(default_factory=list)
    tool_results: dict[str, Any] = field(default_factory=dict)
    fallbacks: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    answer: dict = field(default_factory=dict)
    self_check: dict = field(default_factory=dict)
    safety_check: dict = field(default_factory=dict)
    steps: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None
    cache_hit: bool = False
    fallback_used: bool = False
    data_quality: str = "complete"
    memory_used: bool = False

    def add_step(
        self,
        node: str,
        detail: str = "",
        status: str = "ok",
        decision: str = "",
        action: str | None = None,
        action_input: dict | None = None,
        observation: str = "",
    ) -> None:
        """Append an inspectable agent step.

        The original UI only needed node/detail/status. The optional fields make
        the trace closer to a ReAct-style trajectory without changing control
        flow: decision -> action -> observation.
        """
        step = {"node": node, "detail": detail, "status": status}
        if decision:
            step["decision"] = decision
        if action:
            step["action"] = action
        if action_input:
            step["action_input"] = action_input
        if observation:
            step["observation"] = observation
        self.steps.append(step)

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "session_id": self.session_id,
            "memory": self.memory,
            "intent": self.intent,
            "entities": self.entities,
            "plan": self.plan,
            "tool_results": {k: _safe_serialize(v) for k, v in self.tool_results.items()},
            "fallbacks": self.fallbacks,
            "evidence": self.evidence,
            "answer": self.answer,
            "self_check": self.self_check,
            "steps": self.steps,
            "warnings": self.warnings,
            "error": self.error,
        }


def _safe_serialize(v):
    if hasattr(v, "model_dump"):
        return v.model_dump()
    if hasattr(v, "__dict__"):
        return v.__dict__
    return v
