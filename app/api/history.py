from typing import List, Dict, Any, Annotated
from fastapi import APIRouter, HTTPException, Path, Query
from app.database.connection import DbSession
from app.database.repository import get_history_series, get_daily_bars, get_chart_events, get_latest_market_snapshot
from app.config import INITIAL_TICKERS, settings
from app.technical.chart import build_candles, build_levels, build_markers

router = APIRouter(prefix="/api/tickers", tags=["History"])


@router.get("/{ticker}/history")
def get_ticker_history(
    ticker: Annotated[str, Path(description="Ticker symbol (e.g. ASTS, RKLB)")],
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=1000, description="Max history snapshots to return")] = 100
) -> Dict[str, Any]:
    ticker_sym = ticker.upper()
    ticker_cfg = next((t for t in INITIAL_TICKERS if t.symbol == ticker_sym), None)

    if not ticker_cfg:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in configuration.")

    history_data = get_history_series(db, ticker_sym, limit=limit)

    return {
        "ticker": ticker_sym,
        "name": ticker_cfg.name,
        "count": len(history_data),
        "history": history_data
    }


@router.get("/{ticker}/candles")
def get_ticker_candles(
    ticker: Annotated[str, Path(description="Ticker symbol (e.g. ASTS, RKLB)")],
    db: DbSession,
    days: Annotated[int, Query(ge=20, le=2000, description="Max daily candles to return")] = 260
) -> Dict[str, Any]:
    """Daily candles with EMA200/Bollinger overlays and event markers. Context for the reader: scoring never uses it."""
    ticker_sym = ticker.upper()
    ticker_cfg = next((t for t in INITIAL_TICKERS if t.symbol == ticker_sym), None)

    if not ticker_cfg:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in configuration.")

    bars = get_daily_bars(db, ticker_sym)
    candles = build_candles(bars, limit=days)
    session_dates = [c["time"] for c in candles]
    events = get_chart_events(db, ticker_sym, min_news_relevance=settings.NEWS_MIN_RELEVANCE)

    # The last bar is still forming while the regular session is open
    mkt_snap = get_latest_market_snapshot(db, ticker_sym)
    last_bar_partial = bool(
        candles and mkt_snap and mkt_snap.market_session == "REGULAR" and mkt_snap.candle_date == candles[-1]["time"]
    )
    upcoming = [d for d in events["earnings_dates"] if candles and d > candles[-1]["time"]]

    return {
        "ticker": ticker_sym,
        "name": ticker_cfg.name,
        "count": len(candles),
        "candles": candles,
        "levels": build_levels(bars),
        "markers": build_markers(session_dates, events["daily_bands"], events["catalyst_days"], events["earnings_dates"]),
        "next_earnings_date": upcoming[0] if upcoming else None,
        "last_bar_partial": last_bar_partial,
        "last_bar_updated_at": (bars[-1].updated_at.isoformat() + "Z") if bars and bars[-1].updated_at else None,
    }
