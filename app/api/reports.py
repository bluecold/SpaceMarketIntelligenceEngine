from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.reports.daily_report import generate_daily_report
from app.backtesting.engine import run_historical_backtest

router = APIRouter(tags=["Reports & Backtesting"])


@router.get("/api/reports/daily")
def get_daily_report(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Returns the formal daily sector intelligence report."""
    return generate_daily_report(db)


@router.get("/api/backtest")
def get_backtest_results(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Returns comparative backtest metrics between Model A (X+Market) and Model B (X+Market+Polymarket)."""
    return run_historical_backtest(db)
