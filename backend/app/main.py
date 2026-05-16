"""FastAPI application for Financial Asset QA System."""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from backend.app.schemas import (
    AskRequest,
    AskResponse,
    QuoteResponse,
    HistoryResponse,
    HealthResponse,
    ResolveResponse,
    IntradayResponse,
)
from backend.app.services.market_data import get_quote, get_history, get_intraday, resolve_symbol, resolve_asset_info
from backend.app.agent.graph import run_agent, run_agent_streaming

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Financial Asset QA System starting up...")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Financial Asset QA System",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse()


# ── Market data ───────────────────────────────────────────────────────────────

@app.get("/api/assets/{symbol}/quote", response_model=QuoteResponse)
async def asset_quote(symbol: str):
    resolved = resolve_symbol(symbol)
    result = get_quote(resolved)
    if result.error and result.price is None:
        raise HTTPException(status_code=502, detail=result.error)
    return result


@app.get("/api/assets/{symbol}/history", response_model=HistoryResponse)
async def asset_history(symbol: str, range: str = "7d"):
    if range not in ("7d", "30d", "1m", "3m", "6m", "1y"):
        raise HTTPException(status_code=400, detail=f"Invalid range: {range}")
    resolved = resolve_symbol(symbol)
    result = get_history(resolved, range)
    if result.error and not result.data:
        raise HTTPException(status_code=502, detail=result.error)
    return result


# ── QA endpoints ──────────────────────────────────────────────────────────

@app.get("/api/assets/resolve")
async def asset_resolve(query: str = ""):
    """Resolve company name / symbol to standard asset info."""
    if not query.strip():
        raise HTTPException(status_code=400, detail="query is required")
    result = resolve_asset_info(query)
    return result


@app.get("/api/assets/{symbol}/intraday", response_model=IntradayResponse)
async def asset_intraday(symbol: str, interval: str = "15m"):
    if interval not in ("1m", "5m", "15m", "30m", "60m"):
        raise HTTPException(status_code=400, detail=f"Invalid interval: {interval}")
    resolved = resolve_symbol(symbol)
    result = get_intraday(resolved, interval)
    if result.error and not result.data:
        raise HTTPException(status_code=502, detail=result.error)
    return result

@app.post("/api/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    try:
        response = await run_agent(req.question, req.session_id or "")
        return response
    except Exception as exc:
        logger.error("Ask endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/ask/stream")
async def ask_stream(req: AskRequest):
    async def event_generator():
        try:
            async for event in run_agent_streaming(req.question, req.session_id or ""):
                data = json.dumps(event["data"], ensure_ascii=False, default=str)
                yield f"event: {event['event']}\ndata: {data}\n\n"
        except Exception as exc:
            error_data = json.dumps({"message": str(exc)}, ensure_ascii=False)
            yield f"event: error\ndata: {error_data}\n\n"
            yield f"event: done\ndata: {{}}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )