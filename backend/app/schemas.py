"""Request / Response schemas for the Financial QA API."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Requests ──────────────────────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None


# ── Market data ───────────────────────────────────────────────────────────────

class QuoteResponse(BaseModel):
    symbol: str
    price: Optional[float] = None
    currency: str = "USD"
    timestamp: Optional[str] = None
    provider: str = "yfinance"
    error: Optional[str] = None


class HistoryPoint(BaseModel):
    date: str
    close: float


class HistoryResponse(BaseModel):
    symbol: str
    range: str
    data: list[HistoryPoint] = []
    return_pct: Optional[float] = None
    trend: Optional[str] = None
    currency: str = "USD"
    provider: str = "yfinance"
    error: Optional[str] = None


class IntradayPoint(BaseModel):
    time: str
    price: float
    volume: Optional[float] = None


class IntradayResponse(BaseModel):
    symbol: str
    interval: str = "15m"
    data: list[IntradayPoint] = []
    current_price: Optional[float] = None
    change_pct: Optional[float] = None
    currency: str = "USD"
    provider: str = "akshare"
    trading_status: str = "unknown"  # open | closed | pre_market | after_hours
    warnings: list[str] = []
    error: Optional[str] = None


class ResolveResponse(BaseModel):
    symbol: str
    name: str = ""
    market: str = ""  # us | sh | sz | hk
    currency: str = "USD"
    found: bool = True


# ── Agent answer ──────────────────────────────────────────────────────────────

class AskResponse(BaseModel):
    answer_type: str = "knowledge"  # market | knowledge | hybrid
    summary: str = ""
    objective_data: dict[str, Any] = {}
    analysis: str = ""
    sources: list[dict[str, Any]] = []
    warnings: list[str] = []
    agent_steps: list[dict[str, Any]] = []
    cache_hit: bool = False
    fallback_used: bool = False
    data_quality: str = "complete"  # complete | partial | unavailable
    memory_used: bool = False
    self_check: dict[str, Any] = {}


# ── SSE event wrapper ────────────────────────────────────────────────────────

class SSEEvent(BaseModel):
    event: str  # agent_step | partial_answer | final_answer | error | done
    data: Any = None


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"