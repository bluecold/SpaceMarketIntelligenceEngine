from typing import List, Dict, Any, Annotated
from fastapi import APIRouter, HTTPException, Path, Query
from app.database.connection import DbSession
from app.database.repository import get_history_series
from app.config import INITIAL_TICKERS

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
