"""Source freshness checks (app/monitoring/freshness.py) on a throwaway in-memory database."""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.database.models import (
    AlertModel, Base, JobRunModel, MarketSnapshotModel, NewsItemModel, PredictionMarketModel,
    PredictionMarketSnapshotModel, SocialPostModel,
)
from app.monitoring import freshness as fr

REF = datetime(2026, 11, 3, 18, 0)  # Tuesday 13:00 New York


@pytest.fixture
def db():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    session = sessionmaker(bind=eng)()
    yield session
    session.close()
    eng.dispose()


@pytest.fixture
def live_providers(monkeypatch):
    """conftest switches every provider to mock; these checks only run for live providers."""
    monkeypatch.setattr(settings, "X_PROVIDER", "twikit")
    monkeypatch.setattr(settings, "NEWS_PROVIDER", "rss")
    monkeypatch.setattr(settings, "POLYMARKET_PROVIDER", "polymarket")
    monkeypatch.setattr(settings, "POLYMARKET_ENABLED", True)


def _post(db, ticker, created, source="LIVE", tid=None):
    db.add(SocialPostModel(tweet_id=tid or f"{ticker}-{created.isoformat()}-{source}", ticker=ticker, username="u",
                           text="t", created_at=created, collected_at=created, source=source,
                           sentiment_score=0.0, sentiment_label="neutral"))
    db.commit()


def _news(db, published, url=None, source="Reuters"):
    db.add(NewsItemModel(ticker="ASTS", title="h", url=url or f"https://n/{published.isoformat()}", source=source,
                         published_at=published, collected_at=published))
    db.commit()


def _market(db, ticker, candle, ts=REF - timedelta(minutes=5), status="AVAILABLE"):
    db.add(MarketSnapshotModel(ticker=ticker, timestamp=ts, candle_date=candle, market_status=status))
    db.commit()


# --- Calendar ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("ref, expected", [
    (datetime(2026, 11, 2, 15, 0), date(2026, 10, 30)),   # Mon 10:00 EST, open+60min not reached: Friday
    (datetime(2026, 11, 2, 16, 0), date(2026, 11, 2)),    # Mon 11:00 EST: Monday's partial candle
    (datetime(2026, 11, 2, 23, 0), date(2026, 11, 2)),    # Monday evening
    (datetime(2026, 11, 7, 18, 0), date(2026, 11, 6)),    # Saturday: Friday
    (datetime(2026, 11, 26, 18, 0), date(2026, 11, 25)),  # Thanksgiving: Wednesday
    (datetime(2026, 11, 27, 14, 0), date(2026, 11, 25)),  # Friday after Thanksgiving before the open
])
def test_expected_candle_date_follows_us_calendar(ref, expected):
    assert fr.expected_candle_date(ref, grace_minutes=60) == expected


# --- Individual checks ------------------------------------------------------------------------------

def test_social_fresh_stale_and_no_data(db, live_providers):
    _post(db, "ASTS", REF - timedelta(hours=2))
    _post(db, "SATL", REF - timedelta(hours=30))
    _post(db, "SPCE", REF - timedelta(hours=1), source="MOCK")  # mock rows never count as fresh data
    assert fr.check_social(db, "ASTS", REF)["status"] == fr.OK
    stale = fr.check_social(db, "SATL", REF)
    assert stale["status"] == fr.STALE and stale["age_hours"] == 30.0
    assert fr.check_social(db, "SPCE", REF)["status"] == fr.NO_DATA


def test_social_ignores_posts_after_reference(db, live_providers):
    """Measured at a past run, a post collected later must not make that run look fresh."""
    _post(db, "ASTS", REF - timedelta(hours=20))
    _post(db, "ASTS", REF + timedelta(hours=1))
    assert fr.check_social(db, "ASTS", REF)["status"] == fr.STALE


def test_mock_providers_are_not_checked(db, monkeypatch):
    monkeypatch.setattr(settings, "X_PROVIDER", "mock")
    monkeypatch.setattr(settings, "NEWS_PROVIDER", "mock")
    monkeypatch.setattr(settings, "POLYMARKET_PROVIDER", "mock")
    assert fr.check_social(db, "ASTS", REF)["status"] == fr.MOCK
    assert fr.check_news(db, REF)["status"] == fr.MOCK
    assert fr.check_polymarket(db, REF)["status"] == fr.MOCK
    monkeypatch.setattr(settings, "POLYMARKET_ENABLED", False)
    assert fr.check_polymarket(db, REF)["status"] == fr.DISABLED


def test_news_is_global_and_skips_mock_rows(db, live_providers):
    _news(db, REF - timedelta(hours=30))
    _news(db, REF - timedelta(hours=1), url="mock_https://x/1")
    _news(db, REF - timedelta(hours=1), source="Mock News")
    assert fr.check_news(db, REF)["status"] == fr.STALE
    _news(db, REF - timedelta(hours=3))
    assert fr.check_news(db, REF)["status"] == fr.OK


def test_polymarket_uses_snapshots_not_overwritten_collected_at(db, live_providers):
    m = PredictionMarketModel(external_id="1", title="q", source="LIVE", collected_at=REF,
                              yes_probability=0.5, no_probability=0.5)
    db.add(m)
    db.commit()
    db.add(PredictionMarketSnapshotModel(market_id=m.id, timestamp=REF - timedelta(hours=10),
                                         yes_probability=0.5, no_probability=0.5))
    db.commit()
    assert fr.check_polymarket(db, REF)["status"] == fr.STALE  # collected_at=REF does not count
    db.add(PredictionMarketSnapshotModel(market_id=m.id, timestamp=REF - timedelta(hours=1),
                                         yes_probability=0.5, no_probability=0.5))
    db.commit()
    assert fr.check_polymarket(db, REF)["status"] == fr.OK


def test_market_candle_behind_or_missing_is_stale(db):
    _market(db, "ASTS", "2026-11-03")
    _market(db, "RKLB", "2026-11-02")  # Tuesday 13:00 NY still serving Monday's candle
    _market(db, "SATL", None, status="DATA_UNAVAILABLE")
    assert fr.check_market(db, "ASTS", REF)["status"] == fr.OK
    behind = fr.check_market(db, "RKLB", REF)
    assert behind["status"] == fr.STALE and behind["expected_candle"] == "2026-11-03"
    assert "DATA_UNAVAILABLE" in fr.check_market(db, "SATL", REF)["detail"]
    assert fr.check_market(db, "SPCE", REF)["status"] == fr.NO_DATA


def test_pipeline_manual_without_scheduler_and_stale_with_it(db, monkeypatch):
    db.add(JobRunModel(job_name="full_pipeline", status="SUCCESS", started_at=REF - timedelta(hours=5),
                       finished_at=REF - timedelta(hours=5)))
    db.commit()
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
    assert fr.check_pipeline(db, REF)["status"] == fr.MANUAL
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", True)
    monkeypatch.setattr(settings, "JOB_INTERVAL_MINUTES", 60)
    monkeypatch.setattr(settings, "PIPELINE_STALE_INTERVALS", 3.0)
    assert fr.check_pipeline(db, REF)["status"] == fr.STALE
    assert fr.check_pipeline(db, REF - timedelta(hours=3))["status"] == fr.OK


# --- Alert and report -------------------------------------------------------------------------------

def test_alert_lists_only_problem_sources():
    checks = {
        "social": {"status": fr.STALE, "detail": "newest X post 30.0h old (limit 12h)"},
        "news": {"status": fr.OK, "detail": "fine"},
        "polymarket": {"status": fr.MOCK},
        "market": {"status": fr.NO_DATA, "detail": "no market snapshot stored"},
    }
    a = fr.build_freshness_alert("asts", checks)
    assert a["id"] == "ASTS:SYSTEM:SOURCE_STALE" and a["category"] == "SYSTEM" and a["level"] == "WARNING"
    assert "X: newest X post 30.0h old" in a["message"] and "Price feed" in a["message"]
    assert "News" not in a["message"] and "Polymarket" not in a["message"]
    assert fr.build_freshness_alert("ASTS", {"social": {"status": fr.OK}, "news": {"status": fr.MOCK}}) is None


def test_alert_opens_and_resolves_through_save_alerts(db, live_providers):
    """SYSTEM must be in resolve_categories (the runner adds it) for the alert to close once data is fresh."""
    from app.database.repository import save_alerts

    _market(db, "ASTS", "2026-11-03")
    _news(db, REF - timedelta(hours=1))
    m = PredictionMarketModel(external_id="1", title="q", source="LIVE", yes_probability=0.5, no_probability=0.5)
    db.add(m)
    db.commit()
    db.add(PredictionMarketSnapshotModel(market_id=m.id, timestamp=REF - timedelta(hours=1),
                                         yes_probability=0.5, no_probability=0.5))
    _post(db, "ASTS", REF - timedelta(hours=20))
    db.commit()

    alert = fr.build_freshness_alert("ASTS", fr.ticker_source_checks(db, "ASTS", REF))
    assert alert is not None
    save_alerts(db, "ASTS", [alert], resolve_categories={"SYSTEM"})
    row = db.query(AlertModel).filter(AlertModel.alert_id == "ASTS:SYSTEM:SOURCE_STALE").one()
    assert row.resolved_at is None

    _post(db, "ASTS", REF - timedelta(minutes=30))
    assert fr.build_freshness_alert("ASTS", fr.ticker_source_checks(db, "ASTS", REF)) is None
    save_alerts(db, "ASTS", [], resolve_categories={"SYSTEM"})
    db.refresh(row)
    assert row.resolved_at is not None


def test_report_measures_sources_at_last_successful_run(db, live_providers, monkeypatch):
    """With the scheduler off and the last run long ago, sources fresh *at that run* are ok: an idle
    scheduler must not look like every provider failing."""
    monkeypatch.setattr(settings, "ENABLE_SCHEDULER", False)
    run_end = REF - timedelta(days=3)
    db.add(JobRunModel(job_name="full_pipeline", status="SUCCESS", started_at=run_end, finished_at=run_end))
    _news(db, run_end - timedelta(hours=1))
    db.commit()
    report = fr.evaluate_data_freshness(db, now=REF)
    assert report["reference_time"] == run_end.isoformat() + "Z"
    assert report["pipeline"]["status"] == fr.MANUAL
    assert report["news"]["status"] == fr.OK
    assert "social:ASTS" in report["problems"]  # no posts at all in this database
    assert report["status"] == "stale"


def test_health_endpoint_exposes_freshness():
    from fastapi.testclient import TestClient
    from app.main import app

    body = TestClient(app).get("/api/health").json()
    assert "data_freshness" in body
    assert body["data_freshness"]["status"] in ("ok", "stale", "error")
    if body["data_freshness"]["status"] != "ok":
        assert body["status"] == "degraded"
