"""Gamma / CLOB field semantics for the Polymarket provider.

Field names and behaviors were checked against live gamma-api / clob responses (2026-11):
- Gamma has no `resolved` / `resolutionDate`; settlement is `umaResolutionStatus == "resolved"`, timed by
  `umaEndDate` / `closedTime` (the latter as '2024-08-31 16:04:49+00').
- `active` stays True on closed and resolved markets, so it is not a lifecycle flag.
- Markets carry `oneHourPriceChange` and `oneDayPriceChange`, but nothing for 6h.
- CLOB prices-history serves only {t, p}; without `fidelity` it returns 1-minute points.
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.collectors.base import PredictionMarketData
from app.collectors.polymarket_provider import PolymarketGammaProvider, _parse_gamma_datetime
from app.config import settings


def _patch_httpx(monkeypatch, handler):
    """Route every httpx.AsyncClient in the provider through an in-process handler (no network)."""
    from app.collectors import polymarket_provider as pp

    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(pp.httpx, "AsyncClient", factory)


def _market(**fields):
    base = {"question": "Starship flight 12 reaches orbit?", "outcomes": '["Yes", "No"]', "outcomePrices": '["1", "0"]'}
    base.update(fields)
    return base


def test_closed_without_final_oracle_is_closed_not_resolved():
    """`closed` only means trading stopped; a proposed/disputed UMA answer can still change."""
    provider = PolymarketGammaProvider()
    for uma in (None, "proposed", "disputed"):
        m = provider._parse_gamma_market(
            event={"id": "ev"},
            m=_market(id=f"m-{uma}", closed=True, active=True, umaResolutionStatus=uma,
                      closedTime="2024-08-31 16:04:49+00"),
            ticker="SPCX",
        )
        assert m is not None
        assert m.status == "CLOSED", f"uma={uma}"
        assert m.resolution_date is None


def test_final_oracle_answer_is_resolved_with_oracle_date():
    m = PolymarketGammaProvider()._parse_gamma_market(
        event={"id": "ev"},
        m=_market(id="m-res", closed=True, active=True, umaResolutionStatus="resolved",
                  umaEndDate="2024-08-31T16:04:49Z", closedTime="2024-08-31 16:04:49+00"),
        ticker="SPCX",
    )
    assert m.status == "RESOLVED"
    assert m.resolution_date == datetime(2024, 8, 31, 16, 4, 49, tzinfo=timezone.utc)


def test_active_flag_alone_keeps_open_market_active():
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat().replace("+00:00", "Z")
    m = PolymarketGammaProvider()._parse_gamma_market(
        event={"id": "ev"},
        m=_market(id="m-open", closed=False, active=True, umaResolutionStatuses="[]", endDate=future,
                  outcomePrices='["0.6", "0.4"]'),
        ticker="ASTS",
    )
    assert m.status == "ACTIVE"
    assert m.end_date is not None and m.end_date.tzinfo is not None


def test_archived_market_is_closed():
    m = PolymarketGammaProvider()._parse_gamma_market(
        event={"id": "ev"}, m=_market(id="m-arch", closed=False, archived=True), ticker="SPCX"
    )
    assert m.status == "CLOSED"


def test_hourly_and_daily_changes_parsed_and_6h_left_unknown():
    m = PolymarketGammaProvider()._parse_gamma_market(
        event={"id": "ev"},
        m=_market(id="m-chg", outcomePrices='["0.675", "0.325"]', oneHourPriceChange=-0.025,
                  oneDayPriceChange=0.0115),
        ticker="ASTS",
    )
    assert m.probability_change_1h == -2.5
    assert m.probability_change_24h == 1.15
    assert m.probability_change_6h is None  # Gamma has no 6h field; never fabricate 0.0


def test_missing_changes_stay_unknown():
    m = PolymarketGammaProvider()._parse_gamma_market(event={"id": "ev"}, m=_market(id="m-none"), ticker="ASTS")
    assert m.probability_change_1h is None
    assert m.probability_change_24h is None  # lets save_prediction_markets derive it from snapshots


def test_datetime_parser_handles_gamma_formats():
    expected = datetime(2024, 8, 31, 16, 4, 49, tzinfo=timezone.utc)
    assert _parse_gamma_datetime("2024-08-31 16:04:49+00") == expected
    assert _parse_gamma_datetime("2024-08-31T16:04:49Z") == expected
    assert _parse_gamma_datetime("2024-08-31T16:04:49") == expected  # naive read as UTC
    assert _parse_gamma_datetime("not a date") is None
    assert _parse_gamma_datetime(None) is None


def test_clob_history_sends_interval_and_fidelity(monkeypatch):
    seen = {}
    token = "1" * 70

    def handler(request: httpx.Request):
        seen.update(dict(request.url.params))
        return httpx.Response(200, json={"history": [
            {"t": 1793595621, "p": 0.7}, {"t": None, "p": 0.1}, {"t": 1793599221, "p": 0.675},
        ]})

    _patch_httpx(monkeypatch, handler)
    provider = PolymarketGammaProvider(clob_url="http://clob.test")
    points = asyncio.run(provider.get_history("x", clob_token_id=token))
    assert seen == {"interval": "1w", "fidelity": "60", "market": token}
    assert [p.yes_probability for p in points] == [0.7, 0.675]  # point without a timestamp dropped
    assert all(p.volume == 0.0 for p in points)  # the CLOB serves no volume
    assert points[0].timestamp.tzinfo is not None

    asyncio.run(provider.get_history("x", clob_token_id=token, interval="max", fidelity=1440))
    assert seen["interval"] == "max" and seen["fidelity"] == "1440"


@pytest.mark.parametrize("kwargs", [{"interval": "2d"}, {"interval": "1min"}, {"fidelity": 0}])
def test_clob_history_rejects_invalid_window(kwargs):
    with pytest.raises(ValueError):
        asyncio.run(PolymarketGammaProvider().get_history("x", clob_token_id="1" * 70, **kwargs))


def test_reconcile_moves_vanished_markets_out_of_active(monkeypatch):
    """A market missing from the open sweep is looked up by id: RESOLVED/CLOSED are stored, while a
    still-open or failed lookup leaves the row untouched, and markets seen in the sweep are not queried."""
    from app.database.connection import SessionLocal
    from app.database.models import PredictionMarketModel
    from app.database.repository import save_prediction_markets, ensure_tickers_seeded
    from app.jobs.runner import reconcile_stale_prediction_markets

    tag = uuid.uuid4().hex[:6]
    ids = {k: f"recon-{tag}-{k}" for k in ("resolved", "closed", "open", "error", "seen")}
    now = datetime.now(timezone.utc)
    gamma = {
        ids["resolved"]: _market(id=ids["resolved"], closed=True, active=True, umaResolutionStatus="resolved",
                                 umaEndDate="2026-11-01T12:00:00Z"),
        ids["closed"]: _market(id=ids["closed"], closed=True, active=True, umaResolutionStatus="proposed"),
        ids["open"]: _market(id=ids["open"], closed=False, active=True, outcomePrices='["0.5", "0.5"]',
                             endDate=(now + timedelta(days=30)).isoformat()),
    }
    requested = []

    def handler(request: httpx.Request):
        market_id = request.url.path.rsplit("/", 1)[-1]
        requested.append(market_id)
        if market_id in gamma:
            return httpx.Response(200, json=gamma[market_id])
        return httpx.Response(500, json={"error": "boom"})

    _patch_httpx(monkeypatch, handler)
    orig_fallback, orig_max = settings.ALLOW_MOCK_FALLBACK, settings.POLYMARKET_RECONCILE_MAX
    try:
        settings.ALLOW_MOCK_FALLBACK = False
        settings.POLYMARKET_RECONCILE_MAX = 10_000
        with SessionLocal() as db:
            ensure_tickers_seeded(db)
            save_prediction_markets(db, [
                PredictionMarketData(external_id=i, ticker="SPCX", title="Starship orbit?", created_at=now,
                                     yes_probability=0.5, no_probability=0.5, source="LIVE")
                for i in ids.values()
            ])
            asyncio.run(reconcile_stale_prediction_markets(
                db, PolymarketGammaProvider(base_url="http://gamma.test"), {ids["seen"]}
            ))
            rows = {r.external_id: r for r in db.query(PredictionMarketModel)
                    .filter(PredictionMarketModel.external_id.in_(list(ids.values()))).all()}

        assert rows[ids["resolved"]].status == "RESOLVED"
        assert rows[ids["resolved"]].resolution_date == datetime(2026, 11, 1, 12, 0, 0)
        assert rows[ids["closed"]].status == "CLOSED"
        assert rows[ids["closed"]].resolution_date is None
        assert rows[ids["open"]].status == "ACTIVE"
        assert rows[ids["error"]].status == "ACTIVE"
        assert rows[ids["seen"]].status == "ACTIVE"
        assert ids["seen"] not in requested
    finally:
        settings.ALLOW_MOCK_FALLBACK, settings.POLYMARKET_RECONCILE_MAX = orig_fallback, orig_max


def _legacy_db(tmp_path, allow_mock: bool):
    """A throwaway SQLite file with one legacy 'poly-' row stored as LIVE, one real LIVE row and their
    snapshots; init_db is then re-run with the relabel migration still pending."""
    from sqlalchemy import create_engine, text
    from app.database.connection import init_db

    eng = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    init_db(target_engine=eng)
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM schema_migrations WHERE version = 'v2_2_legacy_mock_polymarket_relabel'"))
        for pk, ext in ((1, "poly-spacex-starship-orbital-catch"), (2, "5177347")):
            conn.execute(text(
                "INSERT INTO prediction_markets (id, external_id, title, status, source, created_at, collected_at, "
                "yes_probability, no_probability) VALUES (:id, :ext, 'Starship catch?', 'ACTIVE', 'LIVE', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0.4, 0.6)"
            ), {"id": pk, "ext": ext})
            conn.execute(text(
                "INSERT INTO prediction_market_snapshots (market_id, timestamp, yes_probability, no_probability) "
                "VALUES (:id, CURRENT_TIMESTAMP, 0.4, 0.6)"
            ), {"id": pk})

    orig = settings.ALLOW_MOCK_FALLBACK
    try:
        settings.ALLOW_MOCK_FALLBACK = allow_mock
        init_db(target_engine=eng)
    finally:
        settings.ALLOW_MOCK_FALLBACK = orig
    with eng.connect() as conn:
        markets = dict(conn.execute(text("SELECT external_id, source FROM prediction_markets")).fetchall())
        snaps = conn.execute(text("SELECT market_id FROM prediction_market_snapshots ORDER BY market_id")).fetchall()
    eng.dispose()
    return markets, [s[0] for s in snaps]


def test_legacy_poly_ids_relabelled_mock_when_fallback_allowed(tmp_path):
    markets, snaps = _legacy_db(tmp_path, allow_mock=True)
    assert markets == {"poly-spacex-starship-orbital-catch": "MOCK", "5177347": "LIVE"}
    assert snaps == [1, 2]


def test_legacy_poly_ids_purged_under_strict_governance(tmp_path):
    markets, snaps = _legacy_db(tmp_path, allow_mock=False)
    assert markets == {"5177347": "LIVE"}
    assert snaps == [2]


def test_reconcile_respects_limit(monkeypatch):
    from app.database.connection import SessionLocal
    from app.jobs.runner import reconcile_stale_prediction_markets

    calls = []

    def handler(request: httpx.Request):
        calls.append(request.url.path)
        return httpx.Response(500)

    _patch_httpx(monkeypatch, handler)
    orig_fallback, orig_max = settings.ALLOW_MOCK_FALLBACK, settings.POLYMARKET_RECONCILE_MAX
    try:
        settings.ALLOW_MOCK_FALLBACK = False
        settings.POLYMARKET_RECONCILE_MAX = 0
        with SessionLocal() as db:
            assert asyncio.run(reconcile_stale_prediction_markets(
                db, PolymarketGammaProvider(base_url="http://gamma.test"), set()
            )) == 0
        assert calls == []
    finally:
        settings.ALLOW_MOCK_FALLBACK, settings.POLYMARKET_RECONCILE_MAX = orig_fallback, orig_max
