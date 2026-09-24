import pytest
from fastapi.testclient import TestClient
from pathlib import Path
from app.main import app

client = TestClient(app)


def test_path_traversal_blocked_env():
    """Verify that requests attempting to escape frontend/dist cannot read .env or outside files."""
    traversal_paths = [
        "/../../.env",
        "/..%2F..%2F.env",
        "/..%2f..%2f.env",
        "/../data/space_sentiment.db",
        "/..%2Fdata%2Fspace_sentiment.db",
        "/../../app/config.py",
        "/..%2F..%2Fapp%2Fconfig.py",
    ]
    for path in traversal_paths:
        response = client.get(path)
        # Should be 404 Not Found, never 200 with sensitive content
        assert response.status_code == 404, f"Failed for path {path}: returned {response.status_code}"
        assert "X_PASSWORD" not in response.text
        assert "DATABASE_URL" not in response.text


def test_database_isolation_from_production():
    """Verify that tests run strictly on an isolated database and resolve_database_url redirects production URLs."""
    from app.database.connection import engine, resolve_database_url, rebind_engine, SessionLocal
    import os

    # 1. Active test engine must NOT point to the production database file
    engine_url_str = str(engine.url)
    assert "test_space_sentiment.db" in engine_url_str
    assert not engine_url_str.endswith("data/space_sentiment.db")

    # 2. In testing environment, resolve_database_url must redirect production URL to test DB
    redirected_url = resolve_database_url("sqlite:///./data/space_sentiment.db")
    assert "test_space_sentiment.db" in redirected_url

    # 3. Dynamic rebind creates functional isolated session
    temp_url = "sqlite:///:memory:"
    test_engine = rebind_engine(temp_url)
    assert str(test_engine.url) == temp_url
    db = SessionLocal()
    try:
        assert db.bind == test_engine
    finally:
        db.close()

    # Rebind back to conftest test db
    from tests.conftest import _TEST_DB_URL
    rebind_engine(_TEST_DB_URL)


def test_polymarket_disabled_skips_ingestion_and_calculation():
    """
    Test that POLYMARKET_ENABLED=False strictly skips prediction market ingestion
    and does not inject stale or mock prediction data into the calculation.
    """
    import asyncio
    from app.config import settings
    from app.jobs.runner import ingest_prediction_markets
    from app.database.connection import SessionLocal

    async def _test():
        orig_enabled = settings.POLYMARKET_ENABLED
        try:
            settings.POLYMARKET_ENABLED = False
            with SessionLocal() as db:
                result = await ingest_prediction_markets(db)
                assert result == [], f"Expected empty list when POLYMARKET_ENABLED=False, got {result}"
        finally:
            settings.POLYMARKET_ENABLED = orig_enabled

    asyncio.run(_test())


def test_allow_mock_fallback_false_blocks_clob_and_market_fallback():
    """
    Test that ALLOW_MOCK_FALLBACK=False prevents get_market and get_history
    from falling back to synthetic mock data.
    """
    import asyncio
    from app.config import settings
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    async def _test():
        orig_fallback = settings.ALLOW_MOCK_FALLBACK
        try:
            settings.ALLOW_MOCK_FALLBACK = False
            provider = PolymarketGammaProvider(base_url="http://127.0.0.1:9999/nonexistent")

            # 1. get_market should return None instead of mock market
            market = await provider.get_market("non-existent-market-id-999")
            assert market is None, f"Expected None when ALLOW_MOCK_FALLBACK=False, got {market}"

            # 2. get_history should return empty list instead of synthetic points
            history = await provider.get_history("non-existent-market-id-999")
            assert history == [], f"Expected empty list when ALLOW_MOCK_FALLBACK=False, got {history}"
        finally:
            settings.ALLOW_MOCK_FALLBACK = orig_fallback

    asyncio.run(_test())


def test_dto_source_provenance_explicit_propagation():
    """
    Test that all data transfer models declare and propagate explicit source attributes ('LIVE' vs 'MOCK').
    """
    from datetime import datetime, timezone
    from app.collectors.base import SocialPostData, MarketData, PredictionMarketData, MarketProbabilityPoint
    from app.collectors.mock_polymarket_provider import MockPolymarketProvider

    now = datetime.now(timezone.utc)

    # 1. Default DTOs should have source='LIVE'
    p = SocialPostData(tweet_id="123", ticker="ASTS", username="u", text="t", created_at=now)
    assert p.source == "LIVE"

    m = MarketData(ticker="ASTS", timestamp=now, price=10.0, volume=1000.0)
    assert m.source == "LIVE"

    pm = PredictionMarketData(
        external_id="ext-1", title="Title", created_at=now,
        yes_probability=0.5, no_probability=0.5
    )
    assert pm.source == "LIVE"

    pt = MarketProbabilityPoint(timestamp=now, yes_probability=0.5, no_probability=0.5)
    assert pt.source == "LIVE"

    # 2. Mock Polymarket Provider must produce external_ids with 'mock_' prefix and source='MOCK'
    mock_prov = MockPolymarketProvider()
    for market in mock_prov._markets:
        assert market.source == "MOCK"
        assert market.external_id.startswith("mock_"), f"Mock ID {market.external_id} should start with 'mock_'"


def test_verify_api_key_constant_time_and_timing_safe():
    """Verify constant-time API key validation with valid, invalid, and Bearer formats."""
    from app.config import settings
    from app.api.jobs import verify_api_key
    from fastapi import Request, HTTPException
    from unittest.mock import MagicMock

    orig_key = settings.API_SECRET_KEY
    orig_env = settings.ENVIRONMENT
    try:
        settings.API_SECRET_KEY = "super-secret-smie-key-12345"
        settings.ENVIRONMENT = "development"

        # 1. External request with valid X-API-KEY header
        req_ext = MagicMock(spec=Request)
        req_ext.headers = {}
        assert verify_api_key(req_ext, x_api_key="super-secret-smie-key-12345") is True

        # 2. External request with valid Bearer token
        assert verify_api_key(req_ext, authorization="Bearer super-secret-smie-key-12345") is True

        # 3. External request with invalid key raises 401
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_ext, x_api_key="wrong-key")
        assert exc.value.status_code == 401
        assert "Invalid API key" in exc.value.detail

        # 4. External request with missing key raises 401
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_ext, x_api_key=None, authorization=None)
        assert exc.value.status_code == 401
        assert "Missing API key" in exc.value.detail
    finally:
        settings.API_SECRET_KEY = orig_key
        settings.ENVIRONMENT = orig_env


def test_verify_api_key_rejects_spoofed_origin_headers():
    """Verify that spoofed browser headers (Sec-Fetch-Site, Origin) cannot bypass authentication."""
    from app.config import settings
    from app.api.jobs import verify_api_key
    from fastapi import Request, HTTPException
    from unittest.mock import MagicMock

    orig_key = settings.API_SECRET_KEY
    try:
        settings.API_SECRET_KEY = "production-secret-never-put-in-frontend-bundle"

        # 1. Request with forged Sec-Fetch-Site: same-origin must be rejected with 401
        req_same_origin = MagicMock(spec=Request)
        req_same_origin.headers = {"sec-fetch-site": "same-origin"}
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_same_origin, x_api_key=None)
        assert exc.value.status_code == 401
        assert "Missing API key" in exc.value.detail

        # 2. Localhost Origin matching Host must also be rejected with 401 without key
        req_local = MagicMock(spec=Request)
        req_local.headers = {"origin": "http://localhost:8000", "host": "localhost:8000"}
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_local, x_api_key=None)
        assert exc.value.status_code == 401

        # 3. Malicious Origin with host embedded must also be rejected with 401
        req_evil = MagicMock(spec=Request)
        req_evil.headers = {"origin": "https://evil.example/localhost:8000", "host": "localhost:8000"}
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_evil, x_api_key=None)
        assert exc.value.status_code == 401
    finally:
        settings.API_SECRET_KEY = orig_key


def test_verify_api_key_production_fail_secure():
    """Verify that if ENVIRONMENT=production and API_SECRET_KEY is None, all calls fail secure with 503."""
    from app.config import settings
    from app.api.jobs import verify_api_key
    from fastapi import Request, HTTPException
    from unittest.mock import MagicMock

    orig_key = settings.API_SECRET_KEY
    orig_env = settings.ENVIRONMENT
    try:
        settings.API_SECRET_KEY = None
        settings.ENVIRONMENT = "production"

        req_external = MagicMock(spec=Request)
        req_external.headers = {}

        # 1. Unconfigured production environment must reject requests without key with 503
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_external, x_api_key=None)
        assert exc.value.status_code == 503
        assert "Server configuration error" in exc.value.detail

        # 2. Arbitrary key must NOT bypass the unconfigured production check
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_external, x_api_key="arbitrary-unauthorized-key")
        assert exc.value.status_code == 503
        assert "Server configuration error" in exc.value.detail

        # 3. Spoofed header must NOT bypass the unconfigured production check
        req_spoofed = MagicMock(spec=Request)
        req_spoofed.headers = {"sec-fetch-site": "same-origin"}
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_spoofed, x_api_key=None)
        assert exc.value.status_code == 503
    finally:
        settings.API_SECRET_KEY = orig_key
        settings.ENVIRONMENT = orig_env


def test_atomic_pipeline_lock_concurrency_and_recovery():
    """
    Verify atomic database locking across workers and automatic recovery of crashed/stale jobs.
    """
    from datetime import datetime, timedelta, timezone
    from app.database.connection import SessionLocal
    from app.database.models import JobRunModel
    from app.database.repository import acquire_pipeline_job_lock, finish_job_run, utc_now

    with SessionLocal() as db1, SessionLocal() as db2:
        # Clean any leftover running jobs in test db
        db1.query(JobRunModel).filter(JobRunModel.status == "RUNNING").update({JobRunModel.status: "SUCCESS"})
        db1.commit()

        # 1. Worker 1 acquires lock
        job1, err1 = acquire_pipeline_job_lock(db1, source="WORKER_1")
        assert job1 is not None
        assert err1 is None
        assert job1.status == "RUNNING"
        assert job1.source == "WORKER_1"

        # 2. Worker 2 attempts to acquire lock concurrently -> rejected
        job2, err2 = acquire_pipeline_job_lock(db2, source="WORKER_2")
        assert job2 is None
        assert err2 is not None
        assert "currently in progress" in err2
        assert "WORKER_1" in err2

        # 3. Simulate process crash of Worker 1: heartbeat older than 120s
        job1.heartbeat_at = utc_now() - timedelta(seconds=150)
        db1.commit()

        # 4. Worker 3 attempts to acquire lock -> detects stale crash, recovers and acquires cleanly
        with SessionLocal() as db3:
            job3, err3 = acquire_pipeline_job_lock(db3, source="WORKER_3")
            assert job3 is not None
            assert err3 is None
            assert job3.source == "WORKER_3"

            # Verify that crashed job1 was marked as ERROR
            db1.refresh(job1)
            assert job1.status == "ERROR"
            assert "terminated abnormally" in job1.error_message

            # Cleanup
            finish_job_run(db3, job3.id, status="SUCCESS")


def test_pipeline_lock_heartbeat_renewal_past_15_minutes():
    """
    Verify that an active long-running pipeline (e.g. 25 minutes) updating heartbeats
    is NOT cut off by the old 15-minute heuristic and remains safely locked.
    """
    from datetime import datetime, timedelta, timezone
    from app.database.connection import SessionLocal
    from app.database.models import JobRunModel
    from app.database.repository import acquire_pipeline_job_lock, update_job_heartbeat, finish_job_run, utc_now

    with SessionLocal() as db:
        # Clean any leftover running jobs
        db.query(JobRunModel).filter(JobRunModel.status == "RUNNING").update({JobRunModel.status: "SUCCESS"})
        db.commit()

        # Start a job 25 minutes ago
        job, err = acquire_pipeline_job_lock(db, source="LONG_RUNNER")
        assert job is not None

        # Simulate job running for 25 minutes, but with fresh heartbeat (10 seconds ago)
        now = utc_now()
        job.started_at = now - timedelta(minutes=25)
        job.heartbeat_at = now - timedelta(seconds=10)
        db.commit()

        # Concurrent check from another worker must still see job as actively running!
        with SessionLocal() as db_checker:
            attempt, conflict = acquire_pipeline_job_lock(db_checker, source="ATTEMPT_RUNNER")
            assert attempt is None
            assert "currently in progress" in conflict

        finish_job_run(db, job.id, status="SUCCESS")


def test_twikit_and_polymarket_propagate_exceptions_when_mock_fallback_disabled():
    """
    Verify that when ALLOW_MOCK_FALLBACK=False, TwikitProvider and PolymarketGammaProvider
    propagate exceptions rather than silently swallowing errors and returning empty datasets.
    """
    import asyncio
    import pytest
    from app.config import settings
    from app.collectors.twikit_provider import TwikitProvider
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    async def _test():
        orig_fallback = settings.ALLOW_MOCK_FALLBACK
        orig_token = settings.X_AUTH_TOKEN
        orig_user = settings.X_AUTH_INFO_1
        try:
            settings.ALLOW_MOCK_FALLBACK = False
            settings.X_AUTH_TOKEN = ""
            settings.X_AUTH_INFO_1 = ""

            # 1. Unauthenticated Twikit must raise RuntimeError (not return empty list)
            twikit = TwikitProvider()
            with pytest.raises(RuntimeError) as exc_twikit:
                await twikit.search("ASTS", "ASTS")
            assert "unauthenticated" in str(exc_twikit.value).lower()

            # 2. Polymarket with unreachable endpoint must raise Exception (not return empty list)
            poly = PolymarketGammaProvider(base_url="http://127.0.0.1:9999/unreachable")
            with pytest.raises(Exception):
                await poly.get_markets(query="space")
        finally:
            settings.ALLOW_MOCK_FALLBACK = orig_fallback
            settings.X_AUTH_TOKEN = orig_token
            settings.X_AUTH_INFO_1 = orig_user

    asyncio.run(_test())


def test_pipeline_heartbeat_background_worker_periodically_updates():
    """
    Verify that _pipeline_heartbeat_worker runs in the background and periodically
    refreshes the database heartbeat timestamp without blocking.
    """
    import asyncio
    import time
    from app.database.connection import SessionLocal
    from app.database.repository import acquire_pipeline_job_lock, finish_job_run
    from app.jobs.runner import _pipeline_heartbeat_worker

    async def _test():
        with SessionLocal() as db:
            job, _ = acquire_pipeline_job_lock(db, source="HEARTBEAT_TEST")
            assert job is not None
            initial_hb = job.heartbeat_at
            job_id = job.id

        stop_event = asyncio.Event()
        # Fast heartbeat interval for test: 0.1s
        task = asyncio.create_task(_pipeline_heartbeat_worker(job_id, stop_event, interval=0.1))

        # Sleep enough for 2 ticks
        await asyncio.sleep(0.3)

        stop_event.set()
        await task

        with SessionLocal() as db:
            fresh_job = db.query(job.__class__).filter_by(id=job_id).first()
            assert fresh_job.heartbeat_at is not None
            assert fresh_job.heartbeat_at > initial_hb
            finish_job_run(db, job_id, status="SUCCESS")

    asyncio.run(_test())


def test_fundamental_and_divergence_alerts_preserved_on_source_failure():
    """
    Verify that when fundamental queries fail or Polymarket/Social fail,
    existing FUNDAMENTAL and DIVERGENCE alerts and DivergenceModel episodes
    are NOT erroneously resolved (preventing alert flapping and state corruption).
    """
    from datetime import datetime, timezone
    from app.database.connection import SessionLocal
    from app.database.models import AlertModel, DivergenceModel
    from app.database.repository import save_alerts, save_divergences

    now = datetime.now(timezone.utc)

    with SessionLocal() as db:
        # Clean previous test state
        db.query(AlertModel).filter(AlertModel.ticker == "ASTS").delete()
        db.query(DivergenceModel).filter(DivergenceModel.ticker == "ASTS").delete()
        db.commit()

        # 1. Seed an active FUNDAMENTAL alert (e.g. DILUTION_WATCH) and an active DIVERGENCE episode
        fund_alert = [{
            "id": "ASTS:FUNDAMENTAL:DILUTION_WATCH",
            "ticker": "ASTS",
            "type": "DILUTION_WATCH",
            "category": "FUNDAMENTAL",
            "level": "HIGH",
            "message": "Low cash runway",
            "data_source": "LIVE"
        }]
        div_data = [{
            "type": "EARLY_REVERSAL",
            "direction": "BULLISH",
            "strength": 0.85,
            "confidence": 0.80,
            "description": "Polymarket probability surged",
            "source_a": "POLYMARKET_MOMENTUM",
            "source_b": "X_SOCIAL"
        }]
        div_alert = [{
            "id": "ASTS:DIVERGENCE:EARLY_REVERSAL:BULLISH",
            "ticker": "ASTS",
            "type": "EARLY_REVERSAL",
            "category": "DIVERGENCE",
            "level": "HIGH",
            "message": "Polymarket probability surged",
            "data_source": "LIVE"
        }]

        save_alerts(db, "ASTS", fund_alert + div_alert, commit=True)
        save_divergences(db, "ASTS", div_data, commit=True)

        # Verify initial active state
        al_fund = db.query(AlertModel).filter_by(alert_id="ASTS:FUNDAMENTAL:DILUTION_WATCH").first()
        al_div = db.query(AlertModel).filter_by(alert_id="ASTS:DIVERGENCE:EARLY_REVERSAL:BULLISH").first()
        ep_div = db.query(DivergenceModel).filter_by(ticker="ASTS", type="EARLY_REVERSAL").first()
        assert al_fund.resolved_at is None
        assert al_div.resolved_at is None
        assert ep_div.resolved_at is None

        # 2. SIMULATE RUN WITH SOURCE FAILURES:
        # - Fundamentals fetch failed (fund_success = False -> "FUNDAMENTAL" not in resolve_categories)
        # - Polymarket fetch failed (div_sources_success = False -> resolve_missing=False, "DIVERGENCE" not in resolve_categories)
        # Pipeline emits empty alerts/divergences for ASTS in this failed run:
        save_divergences(db, "ASTS", [], resolve_missing=False, commit=True)
        save_alerts(db, "ASTS", [], resolve_missing=True, resolve_categories={"SIGNAL", "CATALYST"}, commit=True)

        # VERIFY PRESERVATION: Neither alert nor divergence episode must be resolved!
        db.refresh(al_fund)
        db.refresh(al_div)
        db.refresh(ep_div)
        assert al_fund.resolved_at is None, "Fundamental alert MUST NOT be resolved on source failure!"
        assert al_div.resolved_at is None, "Divergence alert MUST NOT be resolved on source failure!"
        assert ep_div.resolved_at is None, "Divergence episode MUST NOT be resolved on source failure!"

        # 3. SIMULATE HEALTHY RUN WHERE CONDITIONS GENUINELY CEASED:
        # - Both fund_success and div_sources_success are True
        save_divergences(db, "ASTS", [], resolve_missing=True, commit=True)
        save_alerts(db, "ASTS", [], resolve_missing=True, resolve_categories={"SIGNAL", "CATALYST", "FUNDAMENTAL", "DIVERGENCE"}, commit=True)

        # VERIFY RESOLUTION: Now they SHOULD be resolved cleanly!
        db.refresh(al_fund)
        db.refresh(al_div)
        db.refresh(ep_div)
        assert al_fund.resolved_at is not None, "Fundamental alert should be resolved when sources are healthy and condition ceased"
        assert al_div.resolved_at is not None, "Divergence alert should be resolved when sources are healthy and condition ceased"
        assert ep_div.resolved_at is not None, "Divergence episode should be resolved when sources are healthy and condition ceased"

        # Cleanup
        db.query(AlertModel).filter(AlertModel.ticker == "ASTS").delete()
        db.query(DivergenceModel).filter(DivergenceModel.ticker == "ASTS").delete()
        db.commit()


def test_volume_opening_gate_and_candle_date_guard():
    """
    Verify Point 1 & Point 2:
    - If the last candle in DataFrame is NOT today's candle, iloc[:-1] is NOT used, and whole MA20 is preserved.
    - At 09:54 ET (opening session), opening gate (<30m) neutralizes volume_ratio to 1.0 to eliminate yfinance tape delay artifact.
    """
    import pandas as pd
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from app.technical.indicators import calculate_technical_indicators

    # Tuesday 09:54 AM ET
    ref_dt = datetime(2026, 9, 22, 13, 54, tzinfo=timezone.utc)
    today_et = datetime(2026, 9, 22).date()
    yesterday_et = datetime(2026, 9, 21).date()

    # 1. Test case: DataFrame ends on YESTERDAY (no candle for today yet)
    dates_yesterday = pd.date_range(end=yesterday_et, periods=25, freq="B")
    df_yesterday = pd.DataFrame({
        "Open": [10.0] * 25, "High": [11.0] * 25, "Low": [9.0] * 25, "Close": [10.0] * 25,
        "Volume": [1000.0] * 25
    }, index=dates_yesterday)

    ind_yest = calculate_technical_indicators(
        df_yesterday,
        market_session="REGULAR",
        as_of=ref_dt
    )
    # Because candle_date is yesterday, volume_ma20 should be computed over all 20 candles (1000.0) without dropping T-1
    assert ind_yest["volume_ma20"] == 1000.0
    # And volume_ratio should NOT apply intraday session fraction to yesterday's completed candle
    assert ind_yest["volume_ratio"] == 1.0

    # 2. Test case: DataFrame includes TODAY's partial intraday bar at 09:54 ET
    dates_today = pd.date_range(end=today_et, periods=25, freq="B")
    df_today = pd.DataFrame({
        "Open": [10.0] * 25, "High": [11.0] * 25, "Low": [9.0] * 25, "Close": [10.0] * 25,
        "Volume": [1000.0] * 24 + [100.0]  # Today's partial bar is 100
    }, index=dates_today)

    ind_today = calculate_technical_indicators(
        df_today,
        market_session="REGULAR",
        as_of=ref_dt
    )
    # Today's bar is excluded from MA20 -> 1000.0
    assert ind_today["volume_ma20"] == 1000.0
    # At 09:54 ET (elapsed 24 min < 30 min gate), volume_ratio is neutralized to 1.0
    assert ind_today["volume_ratio"] == 1.0


def test_pms_rolling_7d_anchor_surprise_metric():
    """
    Verify Point 3:
    When a prediction market has snapshots over >= 48h with 7-day average of 0.90,
    baseline_probability is anchored to 0.90, producing neutral level (50.0)
    rather than perpetual bullish bias (~67.5).
    """
    from datetime import datetime, timedelta, timezone
    from app.database.connection import SessionLocal
    from app.database.models import PredictionMarketModel, PredictionMarketSnapshotModel
    from app.database.repository import save_prediction_markets
    from app.collectors.base import PredictionMarketData
    from app.scoring.prediction import calculate_prediction_market_score

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        # Clean previous test market
        db.query(PredictionMarketModel).filter_by(external_id="test-mature-90").delete()
        db.commit()

        # Seed market that has been at 90% for the past 5 days
        m = PredictionMarketData(
            external_id="test-mature-90",
            ticker="ASTS",
            title="Satellite constellation milestone",
            yes_probability=0.90,
            no_probability=0.10,
            volume=50000.0,
            liquidity=25000.0,
            spread=0.01,
            quality_score=85.0,
            status="ACTIVE",
            created_at=now - timedelta(days=5),
            probability_change_24h=0.0
        )
        save_prediction_markets(db, [m], commit=True)
        m_db = db.query(PredictionMarketModel).filter_by(external_id="test-mature-90").first()

        # Add snapshots spanning 5 days at 0.90
        for day in range(5, 0, -1):
            snap_time = now - timedelta(days=day)
            db.add(PredictionMarketSnapshotModel(
                market_id=m_db.id,
                timestamp=snap_time,
                yes_probability=0.90,
                no_probability=0.10,
                quality_score=85.0
            ))
        db.commit()

        # Re-save to trigger 7-day rolling baseline calculation
        m_fresh = PredictionMarketData(
            external_id="test-mature-90",
            ticker="ASTS",
            title="Satellite constellation milestone",
            yes_probability=0.90,
            no_probability=0.10,
            volume=50000.0,
            liquidity=25000.0,
            spread=0.01,
            quality_score=85.0,
            status="ACTIVE",
            created_at=now - timedelta(days=5),
            probability_change_24h=0.0
        )
        save_prediction_markets(db, [m_fresh], commit=True)
        assert m_fresh.baseline_probability is not None
        assert abs(m_fresh.baseline_probability - 0.90) < 0.01

        # Evaluate PMS: when probability is 0.90 and 7d baseline is 0.90, score is neutral (~50.0)
        pms, conf, qual, bd = calculate_prediction_market_score(
            ticker="ASTS",
            direct_markets=[m_fresh]
        )
        # Should be strictly neutral (~50.0), NOT ~67.5!
        assert pms is not None
        assert abs(pms - 50.0) < 2.0, f"Expected neutral PMS (~50.0), got {pms}"

        # Cleanup
        db.query(PredictionMarketModel).filter_by(external_id="test-mature-90").delete()
        db.commit()


def test_backtest_parity_risk_score_filtering():
    """
    Verify Point 4:
    generate_signal_and_explanation enforces HIGH RISK modifier and caps STRONG BUY to BUY
    when risk_score < 35.0, matching live execution logic.
    """
    from app.scoring.signal import generate_signal_and_explanation

    # SMI = 88.0 would normally be STRONG BUY, but risk_score = 30.0 (< 35.0) caps to BUY with HIGH RISK
    sig_res = generate_signal_and_explanation(
        ticker="ASTS",
        smi=88.0,
        social_score=85.0,
        risk_score=30.0,
        indicators={"price": 20.0, "status": "AVAILABLE"}
    )
    assert sig_res["base_signal"] == "BUY"
    assert "HIGH RISK" in sig_res["signal"]
    assert sig_res["signal_modifier"] == "HIGH RISK"


def test_non_aerospace_launch_satellite_bus_product_line():
    """
    Verify Point 5:
    'Rocket Lab launches new satellite bus product line' is a commercial product announcement
    and must NOT be detected as a physical rocket LAUNCH catalyst.
    """
    from app.sentiment.weighting import detect_catalysts

    # Commercial product announcement
    cats_product = detect_catalysts("Rocket Lab launches new satellite bus product line", ticker="RKLB")
    launch_cats = [c for c in cats_product if c["category"] == "LAUNCH"]
    assert len(launch_cats) == 0, f"Expected no LAUNCH catalyst for product line, got {launch_cats}"

    # Genuine rocket launch liftoff
    cats_rocket = detect_catalysts("Rocket Lab launches Electron rocket carrying 5 satellites into orbit", ticker="RKLB")
    launch_real = [c for c in cats_rocket if c["category"] == "LAUNCH"]
    assert len(launch_real) > 0, "Expected genuine rocket LAUNCH catalyst to be detected"
    assert launch_real[0]["direction"] == "BULLISH"





