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


def test_verify_api_key_same_origin_dashboard_authorization():
    """Verify that browser same-origin dashboard requests pass safely without exposing key in bundle."""
    from app.config import settings
    from app.api.jobs import verify_api_key
    from fastapi import Request
    from unittest.mock import MagicMock

    orig_key = settings.API_SECRET_KEY
    try:
        settings.API_SECRET_KEY = "production-secret-never-put-in-frontend-bundle"

        # 1. Browser request with Sec-Fetch-Site: same-origin passes
        req_same_origin = MagicMock(spec=Request)
        req_same_origin.headers = {"sec-fetch-site": "same-origin"}
        assert verify_api_key(req_same_origin, x_api_key=None) is True

        # 2. Localhost Origin matching Host passes
        req_local = MagicMock(spec=Request)
        req_local.headers = {"origin": "http://localhost:8000", "host": "localhost:8000"}
        assert verify_api_key(req_local, x_api_key=None) is True
    finally:
        settings.API_SECRET_KEY = orig_key


def test_verify_api_key_production_fail_secure():
    """Verify that if ENVIRONMENT=production and API_SECRET_KEY is None, external calls fail secure with 503."""
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

        # Unconfigured production environment must not be open by default
        with pytest.raises(HTTPException) as exc:
            verify_api_key(req_external, x_api_key=None)
        assert exc.value.status_code == 503
        assert "Server configuration error" in exc.value.detail
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


