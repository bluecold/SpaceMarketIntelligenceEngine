from typing import Dict, Any
from fastapi import APIRouter
from app.database.connection import DbSession
from app.reports.daily_report import generate_daily_report
from app.backtesting.engine import run_historical_backtest

router = APIRouter(prefix="/api", tags=["Reports & Backtesting"])


@router.get("/reports/daily")
def get_daily_report(db: DbSession) -> Dict[str, Any]:
    """Returns the formal daily sector intelligence report."""
    return generate_daily_report(db)


@router.get("/backtest")
def get_backtest_results(db: DbSession) -> Dict[str, Any]:
    """Returns comparative backtest metrics between Model A (X+Market) and Model B (X+Market+Polymarket)."""
    return run_historical_backtest(db)
