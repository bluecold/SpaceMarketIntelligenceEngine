"""Price chart: daily bar storage, overlays, markers and the candles endpoint (display only)."""
from datetime import datetime, timedelta

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, DailyBarModel, NewsItemModel, SSISnapshotModel
from app.database.repository import get_chart_events, get_daily_bars, save_daily_bars
from app.technical.chart import build_candles, build_levels, build_markers, snap_to_session


@pytest.fixture
def db():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    session = sessionmaker(bind=eng)()
    yield session
    session.close()
    eng.dispose()


def _frame(n=260, start="2025-11-03", base=10.0):
    idx = pd.bdate_range(start=start, periods=n, tz="America/New_York")
    close = [base + i * 0.05 for i in range(n)]
    return pd.DataFrame({
        "Open": [c - 0.1 for c in close], "High": [c + 0.3 for c in close],
        "Low": [c - 0.4 for c in close], "Close": close, "Volume": [1000 + i for i in range(n)],
    }, index=idx)


def test_save_daily_bars_upserts_and_skips_bad_rows(db):
    df = _frame(30)
    df.iloc[5, df.columns.get_loc("Close")] = float("nan")
    assert save_daily_bars(db, "ASTS", df) == 29
    assert db.query(DailyBarModel).count() == 29

    # The last (partial) bar is restated on the next run instead of being duplicated
    df2 = _frame(31)
    df2.iloc[29, df2.columns.get_loc("Close")] = 99.0
    save_daily_bars(db, "ASTS", df2)
    bars = get_daily_bars(db, "ASTS")
    assert len(bars) == 31
    assert [b.date for b in bars] == sorted(b.date for b in bars)
    assert bars[29].close == 99.0

    assert save_daily_bars(db, "ASTS", None) == 0
    assert save_daily_bars(db, "ASTS", pd.DataFrame({"Close": [1.0]})) == 0


def test_candle_overlays_have_no_lookahead(db):
    save_daily_bars(db, "RKLB", _frame(260))
    bars = get_daily_bars(db, "RKLB")
    full = build_candles(bars)

    assert full[198]["ema200"] is None and full[199]["ema200"] is not None
    assert full[18]["bb_middle"] is None and full[19]["bb_middle"] is not None
    assert full[-1]["bb_lower"] < full[-1]["bb_middle"] < full[-1]["bb_upper"]

    # Overlay at bar i must equal the overlay computed with bars 0..i only
    for i in (199, 230):
        assert build_candles(bars[: i + 1])[-1] == full[i]

    trimmed = build_candles(bars, limit=50)
    assert len(trimmed) == 50 and trimmed == full[-50:]

    levels = build_levels(bars)
    assert levels["high_52w"] == round(max(b.high for b in bars[-252:]), 4)
    assert levels["low_52w"] == round(min(b.low for b in bars[-252:]), 4)
    assert build_levels([]) == {"high_52w": None, "low_52w": None, "range_sessions": 0}
    assert build_candles([]) == []


def test_markers_snap_to_sessions_and_dedupe():
    sessions = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"]
    assert snap_to_session("2026-11-07", sessions) == "2026-11-09"  # Saturday -> Monday
    assert snap_to_session("2026-11-10", sessions) is None

    markers = build_markers(
        sessions,
        daily_bands=[("2026-10-30", "HOLD"), ("2026-11-03", "HOLD"), ("2026-11-04", "CAUTION"), ("2026-11-07", "WATCH")],
        catalyst_days=[
            {"day": "2026-11-05", "catalyst": "CAPITAL_RAISE", "title": "Offering priced"},
            {"day": "2026-11-05", "catalyst": "CAPITAL_RAISE", "title": "Recap of the offering"},
            {"day": "2026-10-01", "catalyst": "LAUNCH_DELAY", "title": "Before the visible window"},
        ],
        earnings_dates=["2026-11-06", "2027-02-25"],
    )
    assert [(m["time"], m["kind"], m["label"]) for m in markers] == [
        ("2026-11-04", "SIGNAL", "CAUTION"),
        ("2026-11-05", "CATALYST", "CAPITAL_RAISE"),
        ("2026-11-06", "EARNINGS", "EARNINGS"),
        ("2026-11-09", "SIGNAL", "WATCH"),
    ]
    assert markers[0]["direction"] == "BEARISH" and markers[3]["direction"] == "BULLISH"
    assert markers[1]["text"] == "Offering priced"
    assert build_markers([], [], [], []) == []


def test_chart_events_filter_old_rules_and_irrelevant_news(db):
    def snap(ts, band, rules, earnings=None):
        db.add(SSISnapshotModel(ticker="ASTS", timestamp=ts, base_signal=band, signal=band,
                                rules_version=rules, next_earnings_date=earnings, confidence=50.0,
                                data_completeness=100.0))

    snap(datetime(2026, 9, 10, 15, 0), "AVOID", "2.0.0")                    # Old formula: skipped
    snap(datetime(2026, 11, 3, 15, 0), "HOLD", "2.2.3", "2026-11-09")
    snap(datetime(2026, 11, 3, 20, 0), "CAUTION", "2.2.3", "2026-11-09")    # Last of the day wins
    snap(datetime(2026, 11, 5, 2, 0), "WATCH", "2.2.3", "2026-11-09")       # 02:00 UTC = Nov 4 in New York

    def news(url, published, catalyst, direction, relevance):
        db.add(NewsItemModel(ticker="ASTS", title=f"t-{url}", url=url, source="rss", published_at=published,
                             catalyst=catalyst, catalyst_direction=direction, relevance_score=relevance))

    news("a", datetime(2026, 11, 4, 16, 0), "CAPITAL_RAISE", "BEARISH", 0.9)
    news("b", datetime(2026, 11, 4, 16, 0), "LAUNCH", "BULLISH", 0.9)
    news("c", datetime(2026, 11, 4, 16, 0), "LAUNCH_DELAY", "BEARISH", 0.1)
    db.commit()

    events = get_chart_events(db, "ASTS", min_news_relevance=0.4)
    assert events["daily_bands"] == [("2026-11-03", "CAUTION"), ("2026-11-04", "WATCH")]
    assert [c["catalyst"] for c in events["catalyst_days"]] == ["CAPITAL_RAISE"]
    assert events["earnings_dates"] == ["2026-11-09"]


def test_candles_endpoint():
    from fastapi.testclient import TestClient
    from app.database.connection import SessionLocal
    from app.main import app

    session = SessionLocal()
    try:
        session.query(DailyBarModel).filter(DailyBarModel.ticker == "SPCE").delete()
        session.commit()
        start = (datetime(2026, 11, 11) - timedelta(days=120)).strftime("%Y-%m-%d")
        save_daily_bars(session, "SPCE", _frame(60, start=start))
    finally:
        session.close()

    client = TestClient(app)
    res = client.get("/api/tickers/spce/candles?days=40")
    assert res.status_code == 200
    body = res.json()
    assert body["ticker"] == "SPCE" and body["count"] == 40 and len(body["candles"]) == 40
    assert set(body["candles"][0]) == {"time", "open", "high", "low", "close", "volume",
                                       "ema200", "bb_upper", "bb_middle", "bb_lower"}
    assert body["levels"]["range_sessions"] == 60
    assert isinstance(body["markers"], list)

    assert client.get("/api/tickers/NOPE/candles").status_code == 404
