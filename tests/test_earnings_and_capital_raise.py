"""v2.2.3: CAPITAL_RAISE wording seen in real headlines and the informational EARNINGS modifier."""
import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.collectors import market_provider as mp
from app.database.connection import SessionLocal
from app.database.repository import save_ssi_snapshot
from app.scoring.signal import generate_signal_and_explanation
from app.sentiment.weighting import detect_catalysts

ET = ZoneInfo("America/New_York")
INDICATORS = {"price": 10.0, "status": "AVAILABLE", "rsi14": 55.0}


def _categories(text, ticker):
    return {c["category"] for c in detect_catalysts(text, ticker=ticker)}


@pytest.mark.parametrize("text,ticker", [
    ("Rocket Lab (NASDAQ: RKLB) Completes $1.94B Stock Offering To Fully Fund Iridium Acquisition", "RKLB"),
    ("Virgin Galactic Completes Debt-For-Equity Swap, SPCE Stock Slips", "SPCE"),
    ("Virgin Galactic (SPCE) Is Down 10.7% After Swapping Debt For Equity", "SPCE"),
])
def test_capital_raise_detects_real_headlines(text, ticker):
    assert "CAPITAL_RAISE" in _categories(text, ticker)


@pytest.mark.parametrize("text,ticker", [
    ("ASTS Stock Eyes Weekly Comeback: AT&T Says AST SpaceMobile Satellite Offering Will Come To Fruition", "ASTS"),
    ("Virgin Galactic Holdings stock gains in premarket as investors digest Q2 2026 loss and cash burn", "SPCE"),
])
def test_capital_raise_ignores_product_offering_and_cash_burn(text, ticker):
    assert "CAPITAL_RAISE" not in _categories(text, ticker)


@pytest.mark.parametrize("days,expected", [(0, "EARNINGS TODAY"), (3, "EARNINGS IN 3D"), (7, "EARNINGS IN 7D")])
def test_earnings_modifier_is_informational(days, expected):
    plain = generate_signal_and_explanation(ticker="RKLB", smi=80.0, indicators=INDICATORS)
    res = generate_signal_and_explanation(ticker="RKLB", smi=80.0, indicators=INDICATORS, days_to_earnings=days)
    assert res["base_signal"] == plain["base_signal"] == "BUY"
    assert res["signal_modifier"] == expected
    assert res["signal"] == f"BUY ({expected})"
    assert "Earnings report" in res["explanation"]


@pytest.mark.parametrize("days", [None, -1, 8])
def test_earnings_modifier_outside_window(days):
    res = generate_signal_and_explanation(ticker="RKLB", smi=80.0, indicators=INDICATORS, days_to_earnings=days)
    assert res["signal_modifier"] is None
    assert "Earnings report" not in res["explanation"]


def test_earnings_modifier_adds_to_gates():
    res = generate_signal_and_explanation(
        ticker="RKLB", smi=80.0, indicators=INDICATORS, days_to_earnings=2,
        catalysts_found=[{"category": "CAPITAL_RAISE", "direction": "BEARISH", "importance": "HIGH"}]
    )
    assert res["base_signal"] == "WATCH"
    assert res["signal_modifier"] == "CATALYST RISK | EARNINGS IN 2D"


class _FakeTicker:
    def __init__(self, index=None, error=None):
        self._index, self._error = index, error

    def get_earnings_dates(self, limit=8):
        if self._error:
            raise self._error
        return pd.DataFrame({"EPS Estimate": [None] * len(self._index)}, index=pd.DatetimeIndex(self._index))


def test_next_earnings_picks_nearest_future_date(monkeypatch):
    now = pd.Timestamp(datetime.now(ET))
    index = [now + timedelta(days=40), now + timedelta(days=5), now - timedelta(days=30)]
    monkeypatch.setattr(mp.yf, "Ticker", lambda s: _FakeTicker(index))
    assert mp._fetch_next_earnings_sync("RKLB") == (now + timedelta(days=5)).date().isoformat()


def test_next_earnings_none_when_only_past_or_failing(monkeypatch):
    now = pd.Timestamp(datetime.now(ET))
    monkeypatch.setattr(mp.yf, "Ticker", lambda s: _FakeTicker([now - timedelta(days=3)]))
    assert mp._fetch_next_earnings_sync("RKLB") is None
    monkeypatch.setattr(mp.yf, "Ticker", lambda s: _FakeTicker(error=RuntimeError("blocked")))
    assert mp._fetch_next_earnings_sync("RKLB") is None


def test_failed_earnings_lookup_is_not_cached(monkeypatch):
    mp._EARNINGS_CACHE.clear()
    calls = []
    monkeypatch.setattr(mp, "_fetch_next_earnings_sync", lambda t: calls.append(t))
    provider_cls = next(v for v in vars(mp).values() if isinstance(v, type) and "get_next_earnings_date" in vars(v))
    provider = provider_cls.__new__(provider_cls)
    asyncio.run(provider.get_next_earnings_date("RKLB"))
    asyncio.run(provider.get_next_earnings_date("RKLB"))
    assert len(calls) == 2


def test_snapshot_persists_next_earnings_date():
    db = SessionLocal()
    try:
        snap = save_ssi_snapshot(db, {
            "ticker": "RKLB", "ssi": 50.0, "social_score": 50.0, "signal": "HOLD",
            "confidence": 50.0, "data_completeness": 50.0, "next_earnings_date": "2026-11-09"
        })
        db.refresh(snap)
        assert snap.next_earnings_date == "2026-11-09"
    finally:
        db.close()
