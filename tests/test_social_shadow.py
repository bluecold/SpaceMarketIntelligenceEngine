"""Shadow social source (Adanos daily X aggregates): parsing, shadow SSI and ingestion. Measured only."""
import asyncio
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.collectors.adanos_provider import parse_daily_trend
from app.collectors.base import SourceIncompatibleError
from app.config import settings
from app.database.connection import SessionLocal, init_db
from app.database.models import SocialShadowDailyModel
from app.database.repository import ensure_tickers_seeded, get_social_shadow_rows
from app.jobs import runner
from app.scoring.social_shadow import compute_shadow_scores

D0 = date(2026, 11, 1)


def _row(i, mentions=100, bull=40.0, bear=10.0):
    return {"date": (D0 + timedelta(days=i)).isoformat(), "mentions": mentions, "sentiment_score": 0.1,
            "bullish_pct": bull, "bearish_pct": bear, "buzz_score": 50.0}


# --- Parsing ----------------------------------------------------------------------------------------

def test_parse_daily_trend_sorts_and_types():
    payload = {"found": True, "daily_trend": [
        {"date": "2026-11-26", "mentions": 388, "sentiment_score": 0.183, "buzz_score": 43, "bullish_pct": 43, "bearish_pct": 10},
        {"date": "2026-11-25", "mentions": 486, "sentiment_score": 0.118, "buzz_score": 46, "bullish_pct": 46, "bearish_pct": 16},
    ]}
    rows = parse_daily_trend(payload)
    assert [r["date"] for r in rows] == ["2026-11-25", "2026-11-26"]
    assert rows[0]["mentions"] == 486 and rows[0]["bullish_pct"] == 46.0


def test_parse_not_found_and_incompatible():
    assert parse_daily_trend({"found": False}) == []
    with pytest.raises(SourceIncompatibleError):
        parse_daily_trend({"found": True})


# --- Shadow score -----------------------------------------------------------------------------------

def test_shadow_ssi_is_deviation_from_own_norm():
    rows = [_row(i) for i in range(10)] + [_row(10, bull=60.0, bear=5.0)]
    scored = compute_shadow_scores(rows)
    assert scored[0]["baseline_score"] is None and scored[0]["shadow_ssi"] is None  # no history yet
    steady = scored[9]
    assert steady["raw_score"] == 80.0                  # 50 + 50 * (40-10)/50
    assert 75.0 < steady["baseline_score"] < 80.0       # same norm, shrunk slightly towards neutral
    assert 50.0 < steady["shadow_ssi"] < 55.0           # a normal day sits near 50
    spike = scored[10]
    assert spike["raw_score"] > steady["raw_score"] and spike["shadow_ssi"] > steady["shadow_ssi"]


def test_shadow_scores_have_no_lookahead():
    rows = [_row(i, mentions=100 + 10 * i, bull=30.0 + i, bear=10.0) for i in range(20)]
    full = compute_shadow_scores(rows)
    for i in (5, 12, 19):
        prefix = compute_shadow_scores(rows[: i + 1])
        assert prefix[-1] == full[i]


def test_thin_days_are_shrunk_towards_neutral():
    rows = [_row(i) for i in range(10)] + [_row(10, mentions=2, bull=0.0, bear=50.0)]  # one bearish post
    last = compute_shadow_scores(rows)[-1]
    assert last["raw_score"] == 0.0 and 40.0 <= last["shadow_ssi"] < 50.0


def test_days_without_opinions_have_no_score():
    scored = compute_shadow_scores([_row(i) for i in range(5)] + [_row(5, bull=0.0, bear=0.0)])
    assert scored[-1]["raw_score"] is None and scored[-1]["shadow_ssi"] is None
    assert scored[-1]["volume_ratio"] == 1.0


# --- Ingestion --------------------------------------------------------------------------------------

class FakeAdanos:
    def __init__(self, fail=()):
        self.calls, self.fail = [], set(fail)

    async def fetch_daily(self, ticker, start, end):
        self.calls.append((ticker, start, end))
        if ticker in self.fail:
            raise RuntimeError("HTTP 500")
        n = (end - start).days + 1
        return [{"date": (start + timedelta(days=i)).isoformat(), "mentions": 50, "sentiment_score": 0.1,
                 "bullish_pct": 40.0, "bearish_pct": 10.0, "buzz_score": 40.0} for i in range(n)]


@pytest.fixture
def shadow_db(monkeypatch):
    init_db()
    db = SessionLocal()
    ensure_tickers_seeded(db)
    db.query(SocialShadowDailyModel).delete()
    db.commit()
    monkeypatch.setattr(settings, "ADANOS_SHADOW_ENABLED", True)
    monkeypatch.setattr(settings, "ADANOS_API_KEY", "sk_live_test")
    yield db
    db.query(SocialShadowDailyModel).delete()
    db.commit()
    db.close()


def test_ingest_stores_scores_and_respects_interval(shadow_db):
    today = date(2026, 11, 27)
    fake = FakeAdanos(fail={"SATL"})
    res = asyncio.run(runner.ingest_social_shadow(shadow_db, provider=fake, today=today))
    assert res["status"] == "partial" and res["tickers"]["SATL"]["status"] == "error"
    rows = get_social_shadow_rows(shadow_db, "ASTS")
    assert len(rows) == settings.ADANOS_HISTORY_DAYS and rows[-1].date == today.isoformat()
    assert rows[-1].shadow_ssi is not None
    n_calls = len(fake.calls)

    again = asyncio.run(runner.ingest_social_shadow(shadow_db, provider=fake, today=today))
    assert again["status"] == "skipped" and len(fake.calls) == n_calls   # inside ADANOS_FETCH_INTERVAL_HOURS

    asyncio.run(runner.ingest_social_shadow(shadow_db, provider=fake, today=today, force=True))
    start = fake.calls[-1][1]
    assert start == today - timedelta(days=settings.ADANOS_REFETCH_DAYS)  # incremental re-read
    assert len(get_social_shadow_rows(shadow_db, "ASTS")) == settings.ADANOS_HISTORY_DAYS  # upsert, no duplicates


def test_ingest_is_off_by_default(monkeypatch):
    monkeypatch.setattr(settings, "ADANOS_SHADOW_ENABLED", False)
    db = SessionLocal()
    try:
        res = asyncio.run(runner.ingest_social_shadow(db, provider=FakeAdanos()))
    finally:
        db.close()
    assert res["status"] == "skipped"


def test_scoring_never_reads_the_shadow_table():
    root = Path(__file__).resolve().parents[1] / "app"
    readers = [p for p in list((root / "scoring").glob("*.py")) + [root / "backtesting" / "engine.py"]
               if p.name != "social_shadow.py"
               and ("social_shadow" in p.read_text(encoding="utf-8") or "SocialShadowDaily" in p.read_text(encoding="utf-8"))]
    assert readers == []
