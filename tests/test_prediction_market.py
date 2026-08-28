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
        now = datetime.now(timezone.utc)
        # Step 1: Initial market snapshot at 50% from 24 hours ago
        initial_market = PredictionMarketData(
            external_id="poly-test-delta",
            ticker="ASTS",
            title="ASTS Test Market",
            description="",
            category="SPACE",
            status="ACTIVE",
            created_at=now - timedelta(hours=24),
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

        # Manually backdate the first snapshot to 24h ago in DB for testing
        from app.database.models import PredictionMarketSnapshotModel
        snap = db.query(PredictionMarketSnapshotModel).first()
        if snap:
            snap.timestamp = now - timedelta(hours=24)
            db.commit()

        # Step 2: Next ingestion (now) where yes_probability jumped to 70% and provider delta is 0.0
        updated_market = PredictionMarketData(
            external_id="poly-test-delta",
            ticker="ASTS",
            title="ASTS Test Market",
            description="",
            category="SPACE",
            status="ACTIVE",
            created_at=now,
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

        # Verify that save_prediction_markets calculated the +20.0 percentage point 24h delta
        assert updated_market.probability_change_24h == pytest.approx(20.0, 0.1)
    finally:
        db.close()


def test_save_prediction_markets_ignores_short_lookback_snapshots():
    """Verify that snapshots newer than 18 hours (e.g. 1 hour old) are NOT used to fabricate a 24h delta."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, PredictionMarketSnapshotModel
    from app.database.repository import save_prediction_markets

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()

    try:
        now = datetime.now(timezone.utc)
        # Snapshot from 1 hour ago
        initial_market = PredictionMarketData(
            external_id="poly-test-short",
            ticker="ASTS",
            title="ASTS 1h Market",
            description="",
            category="SPACE",
            status="ACTIVE",
            created_at=now - timedelta(hours=1),
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

        # Backdate snapshot to 1h ago
        snap = db.query(PredictionMarketSnapshotModel).first()
        if snap:
            snap.timestamp = now - timedelta(hours=1)
            db.commit()

        # Update market with jump to 70%
        updated_market = PredictionMarketData(
            external_id="poly-test-short",
            ticker="ASTS",
            title="ASTS 1h Market",
            description="",
            category="SPACE",
            status="ACTIVE",
            created_at=now,
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

        # Must NOT treat the 1-hour move as a 24-hour delta
        assert updated_market.probability_change_24h == 0.0
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


def test_gamma_provider_ticker_and_event_resolution():
    """
    Verify that PolymarketGammaProvider._parse_gamma_market resolves tickers and event_keys
    directly from title/slug/description when ticker is NOT passed (as in production runner).
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    provider = PolymarketGammaProvider()

    # 1. AST SpaceMobile direct market (ticker should be ASTS, event_key None)
    event_1 = {"id": "ev-1", "title": "Space Comms", "slug": "asts-commercial-broadband"}
    market_1 = {
        "id": "m-1",
        "question": "Will AST SpaceMobile launch commercial service before Q4 2026?",
        "description": "Resolves YES if BlueBird satellites provide service.",
        "outcomePrices": '["0.75", "0.25"]',
        "liquidityNum": 50000.0,
        "volumeNum": 100000.0,
        "spread": 0.02
    }
    parsed_1 = provider._parse_gamma_market(event_1, market_1, ticker=None)
    assert parsed_1 is not None
    assert parsed_1.ticker == "ASTS"

    # 2. Rocket Lab direct market (ticker should be RKLB)
    event_2 = {"id": "ev-2", "title": "Launch Market", "slug": "rocket-lab-neutron-launch"}
    market_2 = {
        "id": "m-2",
        "question": "Will Rocket Lab launch Neutron rocket in 2026?",
        "outcomePrices": '["0.65", "0.35"]',
        "liquidityNum": 80000.0,
        "volumeNum": 300000.0,
        "spread": 0.015
    }
    parsed_2 = provider._parse_gamma_market(event_2, market_2, ticker=None)
    assert parsed_2 is not None
    assert parsed_2.ticker == "RKLB"

    # 3. SpaceX Starship sector event (ticker should be SPCX, event_key should be spacex_starship_orbital_success)
    event_3 = {"id": "ev-3", "title": "Starship Flight", "slug": "spacex-starship-orbital-catch"}
    market_3 = {
        "id": "m-3",
        "question": "Will SpaceX successfully catch Starship from orbit in 2026?",
        "outcomePrices": '["0.82", "0.18"]',
        "liquidityNum": 200000.0,
        "volumeNum": 1000000.0,
        "spread": 0.01
    }
    parsed_3 = provider._parse_gamma_market(event_3, market_3, ticker=None)
    assert parsed_3 is not None
    assert parsed_3.ticker == "SPCX"
    assert parsed_3.event_key == "spacex_starship_orbital_success"

    # 4. US Space Force SDA sector event (ticker None, event_key us_space_force_sda_defense_contracts)
    event_4 = {"id": "ev-4", "title": "Space Defense", "slug": "us-space-force-sda-awards"}
    market_4 = {
        "id": "m-4",
        "question": "Will US Space Force SDA award Tranche 3 satellite constellation contracts?",
        "outcomePrices": '["0.70", "0.30"]',
        "liquidityNum": 100000.0,
        "volumeNum": 500000.0,
        "spread": 0.02
    }
    parsed_4 = provider._parse_gamma_market(event_4, market_4, ticker=None)
    assert parsed_4 is not None
    assert parsed_4.event_key == "us_space_force_sda_defense_contracts"


def test_pms_directional_calibration_and_zero_bias():
    """
    Test that PMS is strictly directional and does not suffer from non-directional quality bias:
      - 50% probability with 0 delta yields exactly 50.0 (neutral).
      - 0% probability with 0 delta yields 20.0 (deep bearish, unlocks dir_pred <= -0.25).
      - 100% probability with 0 delta yields 80.0 (strong bullish).
    """
    # 1. Neutral market
    neutral_m = PredictionMarketData(
        external_id="poly-neutral",
        ticker="ASTS",
        title="Neutral Probability Market",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=0.50,
        no_probability=0.50,
        volume=500000.0,
        liquidity=200000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=0.0
    )
    pms_neutral, conf_n, _, _ = calculate_prediction_market_score("ASTS", [neutral_m])
    assert pms_neutral == 50.0, f"Expected 50.0 neutral PMS, got {pms_neutral}"

    # 2. Impossible event (0% probability) - must yield bearish PMS without artificial quality bump
    bearish_m = PredictionMarketData(
        external_id="poly-bearish",
        ticker="ASTS",
        title="Zero Probability Market",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=0.0,
        no_probability=1.0,
        volume=500000.0,
        liquidity=200000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=0.0
    )
    pms_bearish, conf_b, _, _ = calculate_prediction_market_score("ASTS", [bearish_m])
    assert pms_bearish == 20.0, f"Expected 20.0 for 0% prob, got {pms_bearish}"
    dir_pred = (pms_bearish - 50.0) / 50.0
    assert dir_pred <= -0.25, f"Expected dir_pred <= -0.25, got {dir_pred}"

    # 3. Certain event (100% probability)
    bullish_m = PredictionMarketData(
        external_id="poly-bullish",
        ticker="ASTS",
        title="Certain Probability Market",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=1.0,
        no_probability=0.0,
        volume=500000.0,
        liquidity=200000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=0.0
    )
    pms_bullish, conf_bu, _, _ = calculate_prediction_market_score("ASTS", [bullish_m])
    assert pms_bullish == 80.0, f"Expected 80.0 for 100% prob, got {pms_bullish}"


def test_sector_event_negative_impact_delta_sign_preservation():
    """
    Verify that an unfavorable sector event (negative impact factor) properly inverts
    and scales the 24h probability delta in the aggregated pms_delta_24h.
    Example: Competitor FCC approval surging (+25% prob) has impact -0.20 on ASTS,
    so effective delta for ASTS must be -5.0% (bearish), not +25.0% (false bullish).
    """
    sector_event = PredictionMarketData(
        external_id="poly-starlink-fcc",
        ticker=None,
        event_key="starlink_fcc_approval",
        title="Starlink Direct-to-Cell FCC Approval",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=0.85,
        no_probability=0.15,
        volume=1000000.0,
        liquidity=300000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=25.0  # +25 pp surge in competitor's favor
    )

    custom_mapping = {
        "starlink_fcc_approval": {
            "ASTS": -0.20  # Competitor blow
        }
    }

    pms, conf, qual, bd = calculate_prediction_market_score(
        ticker="ASTS",
        direct_markets=[],
        sector_events=[sector_event],
        event_mappings=custom_mapping
    )

    assert pms is not None
    # Effective delta should be -5.0 pp (-0.20 * +25.0)
    assert bd["pms_delta_24h"] == -5.0, f"Expected -5.0 effective delta, got {bd['pms_delta_24h']}"
    # Raw delta is preserved for UI inspectability
    assert bd["markets"][0]["raw_delta_24h"] == 25.0
    assert bd["markets"][0]["adjusted_delta_24h"] == -5.0


def test_polymarket_provider_clob_history_deserialization(monkeypatch):
    """
    Verify that PolymarketGammaProvider.get_history properly deserializes CLOB prices-history
    into MarketProbabilityPoint objects with yes_probability and no_probability.
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider
    import httpx

    fake_clob_payload = {
        "history": [
            {"t": 1756400000, "p": 0.72, "v": 15420.0},
            {"t": 1756403600, "p": 0.75, "v": 22100.0},
            {"t": 1756407200, "p": 0.78, "v": 31500.0}
        ]
    }

    class FakeResponse:
        status_code = 200
        def json(self):
            return fake_clob_payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def get(self, url, params=None):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    provider = PolymarketGammaProvider()
    points = asyncio.run(provider.get_history("test-market-123"))

    assert len(points) == 3
    assert isinstance(points[0], MarketProbabilityPoint)
    assert points[0].yes_probability == 0.72
    assert points[0].no_probability == 0.28
    assert points[2].yes_probability == 0.78
    assert points[2].no_probability == 0.22


def test_polymarket_outcomes_dynamic_index_matching():
    """
    Verify that PolymarketGammaProvider dynamically resolves 'Yes' outcome index
    even when Polymarket returns outcomes in reverse order: ['No', 'Yes'].
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    provider = PolymarketGammaProvider()
    event_data = {"id": "ev-rev", "title": "Rocket Lab Launch", "slug": "rklb-neutron-launch"}
    
    # Reverse outcome order where "No" is index 0 ($0.25) and "Yes" is index 1 ($0.75)
    market_data = {
        "id": "m-rev",
        "question": "Will Rocket Lab launch Neutron in 2026?",
        "outcomes": '["No", "Yes"]',
        "outcomePrices": '["0.25", "0.75"]',
        "volumeNum": 100000.0,
        "liquidityNum": 50000.0,
        "spread": 0.02
    }

    parsed = provider._parse_gamma_market(event_data, market_data, ticker="RKLB")
    assert parsed is not None
    # Must correctly pick $0.75 for Yes, not $0.25
    assert parsed.yes_probability == 0.75, f"Expected 0.75 for Yes, got {parsed.yes_probability}"
    assert parsed.no_probability == 0.25
    assert parsed.polarity == 1


def test_negative_semantic_polarity_scoring():
    """
    Verify that negatively framed questions (e.g., 'Will the launch be delayed/fail?')
    are assigned polarity = -1 and scored with inverted directional probability.
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    provider = PolymarketGammaProvider()
    event_data = {"id": "ev-neg", "title": "ASTS Satellite Delay", "slug": "asts-satellite-delayed"}
    
    # Question framed negatively: high YES probability means high chance of delay/failure
    market_data = {
        "id": "m-neg",
        "question": "Will ASTS satellite deployment be delayed to 2027?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.90", "0.10"]',  # 90% chance of delay
        "volumeNum": 100000.0,
        "liquidityNum": 50000.0,
        "spread": 0.02,
        "priceChange24h": 10.0  # +10% increase in chance of delay
    }

    parsed = provider._parse_gamma_market(event_data, market_data, ticker="ASTS")
    assert parsed is not None
    assert parsed.polarity == -1, f"Expected polarity -1 for delay question, got {parsed.polarity}"

    # Calculate PMS for this negative market
    pms, conf, qual, bd = calculate_prediction_market_score("ASTS", [parsed])
    assert pms is not None
    # 90% chance of delay => prob_level is 10.0, momentum is negative => PMS must be deeply bearish (< 30)
    assert pms < 30.0, f"Expected bearish PMS (<30) for 90% delay probability, got {pms}"
    assert bd["markets"][0]["adjusted_delta_24h"] == -10.0








