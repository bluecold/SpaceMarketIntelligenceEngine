"""Source freshness: catch providers that answer without error but stop delivering new data.

Provenance (LIVE/MOCK/DEGRADED) records whether a fetch failed. It cannot see a provider that keeps
answering with nothing new: twikit with an expired session returning no tweets, a news feed repeating old
items, yfinance serving yesterday's candle. Each check here reads the database only (no network) and
measures how old the newest item of a source was at a reference time:

- inside the pipeline the reference is "now", right after the ticker's sources were ingested;
- in /api/health it is the end of the last successful run, so a scheduler that simply has not run yet
  shows up as a pipeline problem, not as every source going stale at once.

Statuses: ok, stale, no_data (live provider but no live rows at all), mock / disabled (not checked),
manual (pipeline check with the scheduler off).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.collectors.market_provider import _EASTERN_TZ, get_us_market_holidays
from app.config import INITIAL_TICKERS, settings
from app.database.models import (
    JobRunModel, MarketSnapshotModel, NewsItemModel, PredictionMarketModel,
    PredictionMarketSnapshotModel, SocialPostModel,
)

OK, STALE, NO_DATA, MOCK, DISABLED, MANUAL = "ok", "stale", "no_data", "mock", "disabled", "manual"
PROBLEM_STATUSES = {STALE, NO_DATA}
SESSION_OPEN = time(9, 30)


def _naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _age_check(newest: Optional[datetime], ref: datetime, threshold_hours: float, label: str) -> Dict[str, Any]:
    if newest is None:
        return {"status": NO_DATA, "newest": None, "age_hours": None, "threshold_hours": threshold_hours,
                "detail": f"no live {label} stored"}
    age = max(0.0, (ref - newest).total_seconds() / 3600.0)
    status = STALE if age > threshold_hours else OK
    return {"status": status, "newest": _iso(newest), "age_hours": round(age, 1),
            "threshold_hours": threshold_hours,
            "detail": f"newest {label} {age:.1f}h old" + (f" (limit {threshold_hours:g}h)" if status == STALE else "")}


# --- Calendar ---------------------------------------------------------------------------------------

def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in get_us_market_holidays(d.year)


def expected_candle_date(ref_utc: datetime, grace_minutes: Optional[int] = None) -> date:
    """Latest US session that opened at least `grace_minutes` before the reference: from then on the price
    feed serves that day's (possibly partial) daily candle."""
    grace = settings.MARKET_CANDLE_GRACE_MINUTES if grace_minutes is None else grace_minutes
    ny = ref_utc.replace(tzinfo=timezone.utc).astimezone(_EASTERN_TZ) - timedelta(minutes=grace)
    d = ny.date()
    if ny.time() < SESSION_OPEN:
        d -= timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


# --- Checks -----------------------------------------------------------------------------------------

def check_social(db: Session, ticker: str, ref: datetime) -> Dict[str, Any]:
    if settings.X_PROVIDER.lower() == "mock":
        return {"status": MOCK}
    newest = (db.query(func.max(SocialPostModel.created_at))
              .filter(SocialPostModel.ticker == ticker, SocialPostModel.source == "LIVE",
                      SocialPostModel.created_at <= ref)
              .scalar())
    return _age_check(_naive_utc(newest), ref, settings.SOCIAL_STALE_HOURS, "X post")


def check_news(db: Session, ref: datetime) -> Dict[str, Any]:
    """Across all tickers: a single ticker can go days without coverage, the whole feed cannot."""
    if getattr(settings, "NEWS_PROVIDER", "rss").lower() == "mock":
        return {"status": MOCK}
    newest = (db.query(func.max(NewsItemModel.published_at))
              .filter(NewsItemModel.published_at <= ref)
              .filter(~NewsItemModel.url.like("mock_%"))
              .filter(or_(NewsItemModel.source.is_(None), NewsItemModel.source != "Mock News"))
              .scalar())
    return _age_check(_naive_utc(newest), ref, settings.NEWS_STALE_HOURS, "news item")


def check_polymarket(db: Session, ref: datetime) -> Dict[str, Any]:
    """Snapshots, not prediction_markets.collected_at: that column is overwritten on every sweep."""
    if not getattr(settings, "POLYMARKET_ENABLED", True):
        return {"status": DISABLED}
    if settings.POLYMARKET_PROVIDER.lower() == "mock":
        return {"status": MOCK}
    newest = (db.query(func.max(PredictionMarketSnapshotModel.timestamp))
              .join(PredictionMarketModel, PredictionMarketModel.id == PredictionMarketSnapshotModel.market_id)
              .filter(PredictionMarketModel.source == "LIVE", PredictionMarketSnapshotModel.timestamp <= ref)
              .scalar())
    return _age_check(_naive_utc(newest), ref, settings.POLYMARKET_STALE_HOURS, "Polymarket snapshot")


def check_market(db: Session, ticker: str, ref: datetime) -> Dict[str, Any]:
    snap = (db.query(MarketSnapshotModel)
            .filter(MarketSnapshotModel.ticker == ticker, MarketSnapshotModel.timestamp <= ref)
            .order_by(MarketSnapshotModel.timestamp.desc())
            .first())
    expected = expected_candle_date(ref)
    base = {"expected_candle": expected.isoformat()}
    if snap is None:
        return {"status": NO_DATA, "candle": None, **base, "detail": "no market snapshot stored"}
    candle = snap.candle_date
    if not candle:
        return {"status": STALE, "candle": None, **base,
                "detail": f"price feed returned no candle ({snap.market_status or 'unknown status'})"}
    try:
        candle_d = date.fromisoformat(str(candle)[:10])
    except ValueError:
        return {"status": STALE, "candle": str(candle), **base, "detail": f"unreadable candle date {candle!r}"}
    if candle_d < expected:
        return {"status": STALE, "candle": candle_d.isoformat(), **base,
                "detail": f"latest candle {candle_d.isoformat()}, expected {expected.isoformat()}"}
    return {"status": OK, "candle": candle_d.isoformat(), **base, "detail": f"candle {candle_d.isoformat()}"}


def check_pipeline(db: Session, now: datetime) -> Dict[str, Any]:
    last = (db.query(JobRunModel)
            .filter(JobRunModel.status == "SUCCESS", JobRunModel.finished_at.isnot(None))
            .order_by(JobRunModel.finished_at.desc())
            .first())
    finished = _naive_utc(last.finished_at) if last else None
    age = round((now - finished).total_seconds() / 3600.0, 1) if finished else None
    out = {"last_success": _iso(finished), "age_hours": age}
    if not getattr(settings, "ENABLE_SCHEDULER", False):
        return {"status": MANUAL, **out, "detail": "scheduler off: runs are manual"}
    limit = settings.PIPELINE_STALE_INTERVALS * settings.JOB_INTERVAL_MINUTES / 60.0
    out["threshold_hours"] = round(limit, 2)
    if finished is None:
        return {"status": NO_DATA, **out, "detail": "no successful run yet"}
    if age > limit:
        return {"status": STALE, **out, "detail": f"last successful run {age:.1f}h ago (limit {limit:g}h)"}
    return {"status": OK, **out, "detail": f"last successful run {age:.1f}h ago"}


# --- Alerts and report ------------------------------------------------------------------------------

SOURCE_LABELS = {"social": "X", "news": "News (all tickers)", "polymarket": "Polymarket", "market": "Price feed"}


def ticker_source_checks(db: Session, ticker: str, ref: Optional[datetime] = None) -> Dict[str, Dict[str, Any]]:
    ref = _naive_utc(ref) or datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "social": check_social(db, ticker, ref),
        "news": check_news(db, ref),
        "polymarket": check_polymarket(db, ref),
        "market": check_market(db, ticker, ref),
    }


def build_freshness_alert(ticker: str, checks: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One SYSTEM alert per ticker naming every source that stopped delivering, or None when all are fresh."""
    bad = [(k, c) for k, c in checks.items() if c.get("status") in PROBLEM_STATUSES]
    if not bad:
        return None
    parts = [f"{SOURCE_LABELS.get(k, k)}: {c.get('detail', c['status'])}" for k, c in bad]
    return {
        "id": f"{ticker.upper()}:SYSTEM:SOURCE_STALE",
        "type": "SOURCE_STALE",
        "category": "SYSTEM",
        "level": "WARNING",
        "message": f"📡 {ticker.upper()}: source not delivering new data. " + "; ".join(parts),
    }


def evaluate_data_freshness(db: Session, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Full report for /api/health. Sources are measured at the end of the last successful run."""
    now = _naive_utc(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    pipeline = check_pipeline(db, now)
    ref = datetime.fromisoformat(pipeline["last_success"][:-1]) if pipeline.get("last_success") else now
    tickers = [t.symbol for t in INITIAL_TICKERS]
    per_ticker = {tk: ticker_source_checks(db, tk, ref) for tk in tickers}
    report = {
        "reference_time": _iso(ref),
        "pipeline": pipeline,
        "news": per_ticker[tickers[0]]["news"] if tickers else check_news(db, ref),
        "polymarket": per_ticker[tickers[0]]["polymarket"] if tickers else check_polymarket(db, ref),
        "social": {tk: c["social"] for tk, c in per_ticker.items()},
        "market": {tk: c["market"] for tk, c in per_ticker.items()},
    }
    problems: List[str] = []
    if pipeline["status"] in PROBLEM_STATUSES:
        problems.append("pipeline")
    for key in ("news", "polymarket"):
        if report[key].get("status") in PROBLEM_STATUSES:
            problems.append(key)
    for key in ("social", "market"):
        problems += [f"{key}:{tk}" for tk, c in report[key].items() if c.get("status") in PROBLEM_STATUSES]
    report["status"] = "stale" if problems else "ok"
    report["problems"] = problems
    return report
