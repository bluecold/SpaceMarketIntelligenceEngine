from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.database.repository import get_history_series
from app.config import INITIAL_TICKERS

router = APIRouter(tags=["History"])


@router.get("/api/tickers/{ticker}/history")
def get_ticker_history(ticker: str, limit: int = 100, db: Session = Depends(get_db)) -> Dict[str, Any]:
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
