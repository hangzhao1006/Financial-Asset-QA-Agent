"""Fallback market data providers (Alpha Vantage / Stooq stubs)."""
from __future__ import annotations

import logging
from backend.app.schemas import QuoteResponse, HistoryResponse

logger = logging.getLogger(__name__)


def get_quote_alpha_vantage(symbol: str, api_key: str) -> QuoteResponse:
    """Stub for Alpha Vantage quote – not implemented yet."""
    logger.info("Alpha Vantage fallback not implemented for %s", symbol)
    return QuoteResponse(symbol=symbol, error="Alpha Vantage provider not configured")


def get_history_alpha_vantage(symbol: str, range_str: str, api_key: str) -> HistoryResponse:
    """Stub for Alpha Vantage history – not implemented yet."""
    logger.info("Alpha Vantage history fallback not implemented for %s", symbol)
    return HistoryResponse(symbol=symbol, range=range_str, error="Alpha Vantage provider not configured")
