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

