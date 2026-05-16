"""Market data provider — AKShare (国内数据源).

AKShare 是开源免费的国内金融数据接口，数据来自新浪、东方财富、腾讯等国内源。
支持 A股、港股、美股行情。

Priority:
  1. AKShare — 国内源，速度快，免费
  2. yfinance — 备用
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd

from backend.app.schemas import QuoteResponse, HistoryResponse, HistoryPoint, IntradayResponse, IntradayPoint, ResolveResponse
from backend.app.services.cache import get_cache, CACHE_TTL

logger = logging.getLogger(__name__)

# ── Symbol aliases ──────────────────────────────────────────────────────────

SYMBOL_ALIASES: dict[str, str] = {
    "阿里巴巴": "BABA",
    "alibaba": "BABA",
    "特斯拉": "TSLA",
    "tesla": "TSLA",
    "苹果": "AAPL",
    "apple": "AAPL",
    "谷歌": "GOOGL",
    "google": "GOOGL",
    "微软": "MSFT",
    "microsoft": "MSFT",
    "亚马逊": "AMZN",
    "amazon": "AMZN",
    "英伟达": "NVDA",
    "nvidia": "NVDA",
    "腾讯": "00700",
    "tencent": "00700",
    "百度": "BIDU",
    "baidu": "BIDU",
    "京东": "JD",
    "meta": "META",
    "台积电": "TSM",
    "tsmc": "TSM",
    "拼多多": "PDD",
    "网易": "NTES",
    "比亚迪": "002594",
    "贵州茅台": "600519",
    "茅台": "600519",
    "中国平安": "601318",
    "平安": "601318",
    "招商银行": "600036",
    "宁德时代": "300750",
}

DEMO_PRICES: dict[str, float] = {
    "BABA": 140.06,
    "TSLA": 322.16,
    "AAPL": 210.79,
    "NVDA": 134.38,
    "MSFT": 449.26,
    "AMZN": 186.54,
    "GOOGL": 170.28,
    "00700": 380.40,
    "600519": 1520.00,
}

DEMO_FUNDAMENTALS: dict[str, dict[str, float | str]] = {
    "BABA": {"pe_ratio": 15.8, "eps": 8.86, "provider": "demo"},
    "TSLA": {"pe_ratio": 92.4, "eps": 3.49, "provider": "demo"},
    "AAPL": {"pe_ratio": 32.1, "eps": 6.57, "provider": "demo"},
    "NVDA": {"pe_ratio": 51.6, "eps": 2.60, "provider": "demo"},
    "MSFT": {"pe_ratio": 36.8, "eps": 12.20, "provider": "demo"},
    "AMZN": {"pe_ratio": 48.2, "eps": 3.87, "provider": "demo"},
    "GOOGL": {"pe_ratio": 24.7, "eps": 6.90, "provider": "demo"},
    "00700": {"pe_ratio": 18.9, "eps": 20.12, "provider": "demo"},
    "600519": {"pe_ratio": 23.5, "eps": 64.70, "provider": "demo"},
}

DEMO_RETURNS: dict[str, float] = {
    "BABA": 1.6,
    "TSLA": -2.8,
    "AAPL": 0.9,
    "NVDA": 3.4,
    "MSFT": 1.1,
    "AMZN": -0.7,
    "GOOGL": 0.4,
    "00700": 2.2,
    "600519": -1.3,
}

# 判断市场类型
def _detect_market(symbol: str) -> str:
    """Detect which market a symbol belongs to."""
    s = symbol.strip()
    # A股：6位纯数字
    if s.isdigit() and len(s) == 6:
        if s.startswith(("6", "9")):
            return "sh"  # 上交所
        elif s.startswith(("0", "2", "3")):
            return "sz"  # 深交所
    # 港股：5位数字或以 .HK 结尾
    if s.isdigit() and len(s) == 5:
        return "hk"
    if s.upper().endswith(".HK"):
        return "hk"
    # 其他视为美股
    return "us"


RANGE_MAP = {
    "7d": 7,
    "30d": 30,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "1y": 365,
}


def resolve_symbol(raw: str) -> str:
    """Resolve a name or alias to a ticker symbol."""
    key = raw.strip().lower()
    if key in SYMBOL_ALIASES:
        return SYMBOL_ALIASES[key]
    return raw.strip().upper()


# ── AKShare provider ────────────────────────────────────────────────────────

def _fetch_akshare_us(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """Fetch US stock data via AKShare (新浪美股)."""
    try:
        import akshare as ak

        df = ak.stock_us_daily(symbol=symbol, adjust="qfq")
        if df is None or df.empty:
            return None

        # AKShare US columns: date, open, high, low, close, volume
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.rename(columns={"close": "Close", "open": "Open", "high": "High", "low": "Low", "volume": "Volume"})
        return df.tail(days + 5)

    except Exception as exc:
        logger.warning("AKShare US fetch failed for %s: %s", symbol, exc)
        return None


def _fetch_akshare_a(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """Fetch A-share data via AKShare (东方财富)."""
    try:
        import akshare as ak

        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust="qfq",
        )
        if df is None or df.empty:
            return None

        # Columns: 日期, 开盘, 收盘, 最高, 最低, 成交量, ...
        df["日期"] = pd.to_datetime(df["日期"])
        df = df.set_index("日期").sort_index()
        df = df.rename(columns={"收盘": "Close", "开盘": "Open", "最高": "High", "最低": "Low", "成交量": "Volume"})
        return df.tail(days + 5)

    except Exception as exc:
        logger.warning("AKShare A-share fetch failed for %s: %s", symbol, exc)
        return None


def _fetch_akshare_hk(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """Fetch HK stock data via AKShare."""
    try:
        import akshare as ak

        # 港股代码去掉 .HK 后缀
        code = symbol.replace(".HK", "").replace(".hk", "").zfill(5)

        df = ak.stock_hk_daily(symbol=code, adjust="qfq")
        if df is None or df.empty:
            return None

        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        df = df.rename(columns={"close": "Close", "open": "Open", "high": "High", "low": "Low", "volume": "Volume"})
        return df.tail(days + 5)

    except Exception as exc:
        logger.warning("AKShare HK fetch failed for %s: %s", symbol, exc)
        return None


def _fetch_akshare(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """Route to the right AKShare function by market."""
    market = _detect_market(symbol)

    if market in ("sh", "sz"):
        return _fetch_akshare_a(symbol, days)
    elif market == "hk":
        return _fetch_akshare_hk(symbol, days)
    else:
        return _fetch_akshare_us(symbol, days)


# ── yfinance fallback ───────────────────────────────────────────────────────

def _fetch_yfinance(symbol: str, days: int) -> Optional[pd.DataFrame]:
    """Fallback to yfinance."""
    try:
        import yfinance as yf

        period = "1mo" if days <= 30 else "3mo" if days <= 90 else "1y"
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)

        if df is None or df.empty:
            return None
        return df

    except Exception as exc:
        logger.warning("yfinance fetch failed for %s: %s", symbol, exc)
        return None


# ── Unified fetch ───────────────────────────────────────────────────────────

def _fetch_data(symbol: str, days: int = 30) -> tuple[Optional[pd.DataFrame], str]:
    """Try AKShare first, then yfinance. Returns (df, provider)."""
    # AKShare 优先
    df = _fetch_akshare(symbol, days)
    if df is not None and not df.empty:
        return df, "akshare"

    # yfinance 备用
    df = _fetch_yfinance(symbol, days)
    if df is not None and not df.empty:
        return df, "yfinance"

    return None, "none"


# ── Currency detection ──────────────────────────────────────────────────────

def _get_currency(symbol: str) -> str:
    market = _detect_market(symbol)
    if market in ("sh", "sz"):
        return "CNY"
    elif market == "hk":
        return "HKD"
    return "USD"


# ── Public API ──────────────────────────────────────────────────────────────

def get_quote(symbol: str) -> QuoteResponse:
    """Get current / latest quote for a symbol."""
    cache = get_cache()
    cached = cache.get("quote", symbol)
    if cached:
        return QuoteResponse(**cached, symbol=symbol)

    try:
        df, provider = _fetch_data(symbol, days=5)

        if df is None or df.empty:
            demo_price = DEMO_PRICES.get(symbol)
            if demo_price is not None:
                return QuoteResponse(
                    symbol=symbol,
                    price=demo_price,
                    currency=_get_currency(symbol),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    provider="demo",
                )
            return QuoteResponse(symbol=symbol, error="无法从任何数据源获取行情数据")

        latest = df.iloc[-1]
        price = float(latest["Close"])
        ts = datetime.now(timezone.utc).isoformat()
        currency = _get_currency(symbol)

        result = QuoteResponse(
            symbol=symbol,
            price=round(price, 4),
            currency=currency,
            timestamp=ts,
            provider=provider,
        )
        cache.set("quote", symbol, result.model_dump(exclude={"symbol"}), CACHE_TTL["quote"])
        return result

    except Exception as exc:
        logger.error("Quote error for %s: %s", symbol, exc)
        return QuoteResponse(symbol=symbol, error=str(exc))


def get_fundamentals(symbol: str) -> dict:
    """Get basic fundamental metrics such as PE ratio.

    The free realtime providers used by this project may not always expose
    fundamentals consistently, so we provide a clearly marked demo fallback for
    common demo assets.
    """
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        info = getattr(ticker, "info", {}) or {}
        pe_ratio = info.get("trailingPE") or info.get("forwardPE")
        eps = info.get("trailingEps") or info.get("forwardEps")
        if pe_ratio is not None or eps is not None:
            return {
                "symbol": symbol,
                "pe_ratio": round(float(pe_ratio), 2) if pe_ratio is not None else None,
                "eps": round(float(eps), 2) if eps is not None else None,
                "provider": "yfinance",
                "is_demo_data": False,
            }
    except Exception as exc:
        logger.warning("Fundamentals fetch failed for %s: %s", symbol, exc)

    demo = DEMO_FUNDAMENTALS.get(symbol)
    if demo:
        return {
            "symbol": symbol,
            "pe_ratio": demo.get("pe_ratio"),
            "eps": demo.get("eps"),
            "provider": demo.get("provider", "demo"),
            "is_demo_data": True,
            "warning": "外部基本面数据源不可用，当前展示本地演示基本面数据",
        }

    return {
        "symbol": symbol,
        "pe_ratio": None,
        "eps": None,
        "provider": "none",
        "is_demo_data": False,
        "warning": "暂未获取到该资产的市盈率数据",
    }


def get_history(symbol: str, range_str: str = "7d") -> HistoryResponse:
    """Get historical prices and calculate return."""
    cache = get_cache()
    cache_key = f"{symbol}:{range_str}"
    cached = cache.get("history", cache_key)
    if cached:
        return HistoryResponse(**cached, symbol=symbol)

    days = RANGE_MAP.get(range_str, 7)

    try:
        df, provider = _fetch_data(symbol, days=days)

        if df is None or df.empty:
            demo_price = DEMO_PRICES.get(symbol)
            if demo_price is not None:
                demo_return = DEMO_RETURNS.get(symbol, 0.8)
                points = _build_history_fallback_points(
                    latest_price=demo_price,
                    return_pct=demo_return,
                    days=days,
                )
                trend = "上涨" if demo_return > 2 else "下跌" if demo_return < -2 else "震荡"
                result = HistoryResponse(
                    symbol=symbol,
                    range=range_str,
                    data=points,
                    return_pct=demo_return,
                    trend=trend,
                    currency=_get_currency(symbol),
                    provider="demo",
                )
                cache.set("history", cache_key, result.model_dump(exclude={"symbol"}), CACHE_TTL["history"])
                return result

            return HistoryResponse(
                symbol=symbol, range=range_str,
                error="无法从任何数据源获取历史数据",
            )

        df = df.tail(days)

        points = [
            HistoryPoint(
                date=idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10],
                close=round(float(row["Close"]), 4),
            )
            for idx, row in df.iterrows()
        ]

        # Calculate return
        ret = None
        trend = None
        if len(points) >= 2:
            start_price = points[0].close
            end_price = points[-1].close
            if start_price > 0:
                ret = round(((end_price - start_price) / start_price) * 100, 2)

        if ret is not None:
            if ret > 2:
                trend = "上涨"
            elif ret < -2:
                trend = "下跌"
            else:
                trend = "震荡"

        currency = _get_currency(symbol)

        result = HistoryResponse(
            symbol=symbol,
            range=range_str,
            data=points,
            return_pct=ret,
            trend=trend,
            currency=currency,
            provider=provider,
        )
        cache.set("history", cache_key, result.model_dump(exclude={"symbol"}), CACHE_TTL["history"])
        return result

    except Exception as exc:
        logger.error("History error for %s: %s", symbol, exc)
        return HistoryResponse(symbol=symbol, range=range_str, error=str(exc))


def _build_history_fallback_points(
    latest_price: float,
    return_pct: float,
    days: int,
) -> list[HistoryPoint]:
    """Create a clearly demo-backed historical series for offline evaluation."""
    count = max(2, min(days, 30))
    start_price = latest_price / (1 + return_pct / 100) if return_pct != -100 else latest_price
    today = datetime.now(timezone.utc).date()
    points: list[HistoryPoint] = []

    for i in range(count):
        weight = i / (count - 1) if count > 1 else 1
        wiggle = (0.002 if i % 2 == 0 else -0.0015) if i not in (0, count - 1) else 0
        price = (start_price + (latest_price - start_price) * weight) * (1 + wiggle)
        date = today - timedelta(days=count - 1 - i)
        points.append(HistoryPoint(date=date.isoformat(), close=round(price, 4)))

    return points


# ── Intraday ────────────────────────────────────────────────────────────────

def get_intraday(symbol: str, interval: str = "15m") -> IntradayResponse:
    """Get intraday price data for today (or last trading day)."""
    cache = get_cache()
    cache_key = f"{symbol}:{interval}"
    cached = cache.get("intraday", cache_key)
    if cached:
        return IntradayResponse(**cached, symbol=symbol)

    warnings: list[str] = []

    try:
        df: Optional[pd.DataFrame] = None
        provider = "none"

        # Use yfinance for intraday when available. If the dependency or network
        # fails, continue to the daily-data fallback instead of returning an
        # empty chart.
        try:
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="1d", interval=interval)
            provider = "yfinance"

            if df is None or df.empty:
                # Try 5d to get last trading day
                df = ticker.history(period="5d", interval=interval)
                if df is not None and not df.empty:
                    warnings.append("非交易时段，展示最近交易日数据")
        except Exception as exc:
            logger.warning("yfinance intraday unavailable for %s: %s", symbol, exc)
            warnings.append("日内实时数据源不可用，尝试使用 fallback 走势")

        if df is None or df.empty:
            # Fallback: build a multi-point visual series from recent daily data.
            # The UI requires more than one point to render a chart, so returning a
            # single close price makes the homepage look broken even when quote
            # data exists. Mark this clearly as a non-intraday fallback.
            daily_df, prov = _fetch_data(symbol, days=7)
            if daily_df is not None and not daily_df.empty:
                latest = daily_df.iloc[-1]
                latest_price = round(float(latest["Close"]), 4)
                previous_price = None
                if len(daily_df) >= 2:
                    previous_price = round(float(daily_df.iloc[-2]["Close"]), 4)

                points = _build_intraday_fallback_points(
                    latest_price=latest_price,
                    previous_price=previous_price,
                    volume=float(latest.get("Volume", 0)) if "Volume" in latest.index else None,
                )
                change_pct = None
                if previous_price and previous_price > 0:
                    change_pct = round(((latest_price - previous_price) / previous_price) * 100, 2)

                result = IntradayResponse(
                    symbol=symbol,
                    interval=interval,
                    data=points,
                    current_price=latest_price,
                    change_pct=change_pct,
                    currency=_get_currency(symbol),
                    provider=f"{prov}_fallback",
                    trading_status="closed",
                    warnings=["日内数据不可用，展示基于最近收盘价的演示走势"],
                )
                cache.set("intraday", cache_key, result.model_dump(exclude={"symbol"}), 120)
                return result

            demo_price = DEMO_PRICES.get(symbol)
            if demo_price is not None:
                points = _build_intraday_fallback_points(
                    latest_price=demo_price,
                    previous_price=demo_price * 0.992,
                )
                return IntradayResponse(
                    symbol=symbol,
                    interval=interval,
                    data=points,
                    current_price=demo_price,
                    change_pct=0.81,
                    currency=_get_currency(symbol),
                    provider="demo",
                    trading_status="demo",
                    warnings=["外部行情源不可用，当前展示本地离线演示走势"],
                )

            return IntradayResponse(
                symbol=symbol, interval=interval,
                error="无法获取日内数据",
            )

        points = [
            IntradayPoint(
                time=idx.strftime("%H:%M") if hasattr(idx, "strftime") else str(idx)[:16],
                price=round(float(row["Close"]), 4),
                volume=float(row.get("Volume", 0)) if "Volume" in row.index else None,
            )
            for idx, row in df.iterrows()
        ]

        current_price = points[-1].price if points else None
        change_pct = None
        if len(points) >= 2:
            open_price = points[0].price
            if open_price > 0:
                change_pct = round(((current_price - open_price) / open_price) * 100, 2)

        result = IntradayResponse(
            symbol=symbol,
            interval=interval,
            data=points,
            current_price=current_price,
            change_pct=change_pct,
            currency=_get_currency(symbol),
            provider=provider,
            trading_status="closed",  # simplified
            warnings=warnings,
        )
        cache.set("intraday", cache_key, result.model_dump(exclude={"symbol"}), 120)
        return result

    except Exception as exc:
        logger.error("Intraday error for %s: %s", symbol, exc)
        return IntradayResponse(symbol=symbol, interval=interval, error=str(exc))


def _build_intraday_fallback_points(
    latest_price: float,
    previous_price: Optional[float] = None,
    volume: Optional[float] = None,
) -> list[IntradayPoint]:
    """Create a small non-realtime series so the chart can render during demos.

    This is intentionally marked by the caller as fallback data. It should never
    be presented as real intraday ticks.
    """
    times = ["09:30", "10:15", "11:00", "11:45", "13:30", "14:15", "15:00", "16:00"]
    start_price = previous_price if previous_price and previous_price > 0 else latest_price * 0.995
    weights = [0.0, 0.18, 0.34, 0.48, 0.63, 0.78, 0.9, 1.0]
    wiggles = [0.0, 0.0015, -0.0008, 0.001, -0.0012, 0.0009, -0.0004, 0.0]

    points: list[IntradayPoint] = []
    for time_label, weight, wiggle in zip(times, weights, wiggles):
        interpolated = start_price + (latest_price - start_price) * weight
        price = round(interpolated * (1 + wiggle), 4)
        points.append(IntradayPoint(time=time_label, price=price, volume=volume))
    return points


# ── Asset resolve ───────────────────────────────────────────────────────────

# Reverse map for display names
SYMBOL_NAMES: dict[str, str] = {
    "BABA": "阿里巴巴 Alibaba",
    "TSLA": "特斯拉 Tesla",
    "AAPL": "苹果 Apple",
    "GOOGL": "谷歌 Google",
    "MSFT": "微软 Microsoft",
    "AMZN": "亚马逊 Amazon",
    "NVDA": "英伟达 NVIDIA",
    "00700": "腾讯 Tencent",
    "BIDU": "百度 Baidu",
    "JD": "京东 JD.com",
    "META": "Meta",
    "TSM": "台积电 TSMC",
    "PDD": "拼多多 Pinduoduo",
    "NTES": "网易 NetEase",
    "002594": "比亚迪 BYD",
    "600519": "贵州茅台 Kweichow Moutai",
    "601318": "中国平安 Ping An",
    "600036": "招商银行 CMB",
    "300750": "宁德时代 CATL",
}


def resolve_asset_info(query: str) -> ResolveResponse:
    """Resolve user query to standard asset info."""
    symbol = resolve_symbol(query)
    market = _detect_market(symbol)
    currency = _get_currency(symbol)
    name = SYMBOL_NAMES.get(symbol, symbol)

    return ResolveResponse(
        symbol=symbol,
        name=name,
        market=market,
        currency=currency,
        found=True,
    )