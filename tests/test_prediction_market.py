import asyncio
import pytest
from datetime import datetime, timedelta, timezone
from app.collectors.base import PredictionMarketData, MarketProbabilityPoint
from app.collectors.mock_polymarket_provider import MockPolymarketProvider
from app.prediction.quality import calculate_market_quality
from app.prediction.probability import calculate_probability_changes, calculate_prediction_momentum
from app.scoring.prediction import calculate_prediction_market_score
from app.config import settings


def test_market_quality_score_high_quality():
    """Test market quality calculation for deep, liquid, active markets."""
    quality = calculate_market_quality(
        liquidity=150000.0,
        volume=500000.0,
        spread=0.01,
        end_date=datetime.now(timezone.utc) + timedelta(days=60)
    )
    assert quality >= 75.0, f"Expected high quality score >= 75, got {quality}"


def test_market_quality_score_low_quality():
    """Test that low liquidity, illiquid or wide spread markets score below 30."""
    quality = calculate_market_quality(
        liquidity=50.0,
        volume=100.0,
        spread=0.20,
        end_date=datetime.now(timezone.utc) + timedelta(days=500)
    )
    assert quality < 30.0, f"Expected low quality score < 30, got {quality}"


def test_prediction_weight_disabled_on_low_quality():
    """
    Test Rule in Spec Section 35 & 115:
    If Market Quality < 30 -> Prediction Market Score effective weight is 0.
    """
    illiquid_market = PredictionMarketData(
        external_id="poly-test-illiquid",
        ticker="ASTS",
        title="Test Illiquid Market",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=0.90,
        no_probability=0.10,
        volume=20.0,
        liquidity=10.0,
        spread=0.25,
        quality_score=15.0,  # Below 30 threshold
        probability_change_24h=10.0
    )

    pms, confidence, avg_qual, breakdown = calculate_prediction_market_score(
        ticker="ASTS",
        direct_markets=[illiquid_market]
    )

    assert pms is None, "PMS should be None when no markets meet the min quality threshold"
    assert confidence == 0.0
    assert breakdown["status"] == "UNAVAILABLE_OR_LOW_QUALITY"


def test_prediction_market_score_calculation():
    """Test valid PMS calculation combining Probability, Momentum, Quality and Depth."""
    valid_market = PredictionMarketData(
        external_id="poly-asts-launch",
        ticker="ASTS",
        title="ASTS Satellite Deployment",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=0.75,
        no_probability=0.25,
        volume=100000.0,
        liquidity=50000.0,
        spread=0.02,
        quality_score=80.0,
        probability_change_24h=10.0
    )

    pms, confidence, avg_qual, breakdown = calculate_prediction_market_score(
        ticker="ASTS",
        direct_markets=[valid_market]
    )

    assert pms is not None
    assert 65.0 <= pms <= 90.0, f"Expected PMS score between 65 and 90, got {pms}"
    assert confidence > 50.0
    assert avg_qual == 80.0
    assert len(breakdown["markets"]) == 1


def test_cross_company_event_mapping():
    """Test that a sector-wide event properly impacts related tickers with impact mapping."""
    sector_event = PredictionMarketData(
        external_id="poly-starship-orbital-success",
        ticker=None,
        event_key="spacex_starship_orbital_success",
        title="SpaceX Starship Orbital Success",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=0.85,
        no_probability=0.15,
        volume=1000000.0,
        liquidity=300000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=5.0
    )

    custom_mapping = {
        "spacex_starship_orbital_success": {
            "ASTS": 0.30,
            "RKLB": 0.20
        }
    }

    # Test ASTS evaluation from sector event
    pms_asts, conf_asts, qual_asts, bd_asts = calculate_prediction_market_score(
        ticker="ASTS",
        direct_markets=[],
        sector_events=[sector_event],
        event_mappings=custom_mapping
    )

    assert pms_asts is not None
    assert pms_asts > 50.0, f"Positive impact from Starship should make ASTS PMS bullish, got {pms_asts}"
    assert len(bd_asts["markets"]) == 1
    assert bd_asts["markets"][0]["impact_factor"] == 0.30


def test_probability_changes_and_momentum():
    """Test calculation of delta 1h/6h/24h and probability momentum."""
    now = datetime.now(timezone.utc)
    history = [
        MarketProbabilityPoint(timestamp=now - timedelta(hours=25), yes_probability=0.50, no_probability=0.50),
        MarketProbabilityPoint(timestamp=now - timedelta(hours=6, minutes=10), yes_probability=0.60, no_probability=0.40),
        MarketProbabilityPoint(timestamp=now - timedelta(hours=1, minutes=10), yes_probability=0.68, no_probability=0.32),
    ]

    current_prob = 0.70
    d1, d6, d24 = calculate_probability_changes(current_prob, history)

    assert d24 == pytest.approx(20.0, 0.1)  # 0.70 - 0.50 = +20.0 percentage points
    assert d6 == pytest.approx(10.0, 0.1)   # 0.70 - 0.60 = +10.0 percentage points
    assert d1 == pytest.approx(2.0, 0.1)    # 0.70 - 0.68 = +2.0 percentage points

    momentum = calculate_prediction_momentum(probability_change_24h=d24)
    assert momentum > 70.0, f"Strong +20pp move should produce bullish momentum > 70, got {momentum}"


def test_mock_polymarket_provider():
    """Test Mock Polymarket Provider retrieval and ticker filtering synchronously."""
    async def _test():
        provider = MockPolymarketProvider()
        
        # Get all space markets
        all_markets = await provider.get_markets()
        assert len(all_markets) >= 5

        # Filter by ASTS
        asts_markets = await provider.get_markets(ticker="ASTS")
        assert len(asts_markets) >= 1
        assert any(m.ticker == "ASTS" for m in asts_markets)

        # Get history points for a market
        market = all_markets[0]
        history = await provider.get_history(market.external_id)
        assert len(history) >= 24
        assert history[-1].yes_probability == pytest.approx(market.yes_probability, 0.05)

    asyncio.run(_test())


def test_gamma_provider_24h_price_change_parsing():
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    provider = PolymarketGammaProvider()
    event_data = {"id": "event-1", "title": "Space Event", "slug": "space-event-slug"}
    market_raw = {
        "id": "market-101",
        "question": "Will ASTS deploy satellite?",
        "outcomePrices": '["0.80", "0.20"]',
        "oneDayPriceChange": "0.15",  # +15%
        "liquidityNum": 50000.0,
        "volumeNum": 200000.0,
        "spread": 0.02
    }

    parsed = provider._parse_gamma_market(event_data, market_raw, "ASTS")
    assert parsed is not None
    assert parsed.yes_probability == 0.80
    assert parsed.probability_change_24h == 15.0


def test_save_prediction_markets_derives_24h_delta_from_history():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base
    from app.database.repository import save_prediction_markets

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()

    try:
        # Step 1: Initial market snapshot at 50%
        initial_market = PredictionMarketData(
            external_id="poly-test-delta",
            ticker="ASTS",
            title="ASTS Test Market",
            description="",
            category="SPACE",
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            end_date=None,
            yes_probability=0.50,
            no_probability=0.50,
            volume=50000.0,
            liquidity=25000.0,
            spread=0.02,
            quality_score=75.0,
            probability_change_1h=0.0,
            probability_change_6h=0.0,
            probability_change_24h=0.0
        )
        save_prediction_markets(db, [initial_market])

        # Step 2: Next ingestion where yes_probability jumped to 70% and provider delta is 0.0
        updated_market = PredictionMarketData(
            external_id="poly-test-delta",
            ticker="ASTS",
            title="ASTS Test Market",
            description="",
            category="SPACE",
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            end_date=None,
            yes_probability=0.70,
            no_probability=0.30,
            volume=60000.0,
            liquidity=30000.0,
            spread=0.02,
            quality_score=75.0,
            probability_change_1h=0.0,
            probability_change_6h=0.0,
            probability_change_24h=0.0
        )
        save_prediction_markets(db, [updated_market])

        # Verify that save_prediction_markets calculated the +20.0 percentage point delta
        assert updated_market.probability_change_24h == pytest.approx(20.0, 0.1)
    finally:
        db.close()


def test_prediction_market_score_no_double_counting():
    """Verify that a market present in both direct_markets and sector_events is not double-counted."""
    now = datetime.now(timezone.utc)
    market = PredictionMarketData(
        external_id="poly-spacex-starship-orbital-catch",
        ticker="SPCX",
        title="Will SpaceX catch Starship on next flight?",
        description="",
        category="LAUNCH_VEHICLES",
        status="ACTIVE",
        created_at=now,
        end_date=None,
        yes_probability=0.75,
        no_probability=0.25,
        volume=800000.0,
        liquidity=250000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_1h=0.0,
        probability_change_6h=0.0,
        probability_change_24h=3.0,
        event_key="spacex_starship_orbital_success"
    )

    # Pass the same market in BOTH direct_markets and sector_events
    pms, conf, qual, breakdown = calculate_prediction_market_score(
        ticker="SPCX",
        direct_markets=[market],
        sector_events=[market]
    )

    assert pms is not None
    # Must be exactly 1 market in breakdown, not 2
    assert breakdown["market_count"] == 1
    assert len(breakdown["markets"]) == 1
    assert breakdown["markets"][0]["type"] == "DIRECT"


def test_get_recent_prediction_markets_event_key_filtering():
    """Verify that get_recent_prediction_markets only returns relevant event markets for each ticker."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, PredictionMarketModel
    from app.database.repository import get_recent_prediction_markets

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()

    try:
        now = datetime.now(timezone.utc)
        # Market 1: Direct for ASTS
        m1 = PredictionMarketModel(
            external_id="poly-asts-1", ticker="ASTS", title="ASTS Launch",
            status="ACTIVE", yes_probability=0.7, no_probability=0.3,
            volume=10000.0, liquidity=5000.0, spread=0.02, quality_score=80.0,
            event_key=None, created_at=now
        )
        # Market 2: Sector event for Direct-to-Cell (affects ASTS and SPCX, but NOT SPCE)
        m2 = PredictionMarketModel(
            external_id="poly-starlink-fcc", ticker=None, title="Starlink Direct to Cell FCC",
            status="ACTIVE", yes_probability=0.8, no_probability=0.2,
            volume=50000.0, liquidity=20000.0, spread=0.01, quality_score=85.0,
            event_key="spacex_starlink_direct_to_cell_fcc_approval", created_at=now
        )
        # Market 3: Direct for SPCE
        m3 = PredictionMarketModel(
            external_id="poly-spce-1", ticker="SPCE", title="SPCE Flight",
            status="ACTIVE", yes_probability=0.5, no_probability=0.5,
            volume=15000.0, liquidity=8000.0, spread=0.03, quality_score=70.0,
            event_key=None, created_at=now
        )
        db.add_all([m1, m2, m3])
        db.commit()

        # Query for ASTS: Should return m1 (direct) and m2 (mapped sector event)
        asts_markets = get_recent_prediction_markets(db, ticker="ASTS")
        asts_ids = [m.external_id for m in asts_markets]
        assert "poly-asts-1" in asts_ids
        assert "poly-starlink-fcc" in asts_ids
        assert "poly-spce-1" not in asts_ids

        # Query for SPCE: Should return m3 (direct) only, excluding m2 (since Starlink FCC is not mapped to SPCE)
        spce_markets = get_recent_prediction_markets(db, ticker="SPCE")
        spce_ids = [m.external_id for m in spce_markets]
        assert "poly-spce-1" in spce_ids
        assert "poly-starlink-fcc" not in spce_ids
        assert "poly-asts-1" not in spce_ids
    finally:
        db.close()



