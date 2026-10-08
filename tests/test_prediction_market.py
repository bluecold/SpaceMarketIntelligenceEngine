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
        event_mappings=custom_mapping,
        allow_sector_only=True
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

        # Step 2: Next ingestion (now) where yes_probability jumped to 70% and provider delta is None (missing)
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
            probability_change_24h=None
        )
        save_prediction_markets(db, [updated_market])

        # Verify that save_prediction_markets calculated the +20.0 percentage point 24h delta when delta was None
        assert updated_market.probability_change_24h == pytest.approx(20.0, 0.1)

        # Step 3: Explicit 0.0 delta must be preserved and NOT overwritten by history (R2-06 contract)
        flat_market = PredictionMarketData(
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
        save_prediction_markets(db, [flat_market])
        assert flat_market.probability_change_24h == 0.0
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
      - 50% probability with 0 delta yields exactly 50.0 (neutral) when baseline is 0.50.
      - 20% aerospace milestone with 0 delta yields exactly 50.0 (neutral) with default base rate 0.20.
      - 0% probability with 0 delta yields 30.0 (bearish, unlocks dir_pred <= -0.25).
      - 100% probability with 0 delta yields 70.0 (strong bullish, dir_pred >= +0.25).
    """
    # 1. Neutral 50/50 market
    neutral_m = PredictionMarketData(
        external_id="poly-neutral",
        ticker="ASTS",
        title="Neutral Probability Market",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=0.50,
        no_probability=0.50,
        baseline_probability=0.50,
        volume=500000.0,
        liquidity=200000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=0.0
    )
    pms_neutral, conf_n, _, _ = calculate_prediction_market_score("ASTS", [neutral_m])
    assert pms_neutral == 50.0, f"Expected 50.0 neutral PMS, got {pms_neutral}"

    # 1b. Neutral 20% aerospace milestone market (default base rate 0.20)
    milestone_20 = PredictionMarketData(
        external_id="poly-milestone-20",
        ticker="RKLB",
        title="Will Rocket Lab launch Neutron in 2026?",
        status="ACTIVE",
        created_at=datetime.now(timezone.utc),
        yes_probability=0.20,
        no_probability=0.80,
        volume=500000.0,
        liquidity=200000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=0.0,
        polarity=1
    )
    pms_m20, _, _, _ = calculate_prediction_market_score("RKLB", [milestone_20])
    assert pms_m20 == 50.0, f"Expected 50.0 neutral PMS for 20% milestone, got {pms_m20}"

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
    assert pms_bearish == 30.0, f"Expected 30.0 for 0% prob, got {pms_bearish}"
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
    assert pms_bullish == 70.0, f"Expected 70.0 for 100% prob, got {pms_bullish}"


def test_framing_paradox_resolution_and_milestone_calibration():
    """
    Validates complete resolution of framing paradox:
    - Positive framing: 'Will Rocket Lab launch Neutron in 2026?' (P=0.20, delta=0) -> PMS = 50.0
    - Negative framing: 'Will Rocket Lab Neutron launch be delayed?' (P=0.20, delta=0) -> PMS = 50.0
    - Symmetry: Both framings of the exact same 20% event yield identical neutral PMS (50.0).
    - Dynamic delta response: +5pp surge in positive milestone raises PMS to bullish lean (56.0).
    """
    now = datetime.now(timezone.utc)
    market_pos = PredictionMarketData(
        external_id="poly-frame-pos",
        ticker="RKLB",
        title="Will Rocket Lab launch Neutron in 2026?",
        status="ACTIVE",
        created_at=now,
        yes_probability=0.20,
        no_probability=0.80,
        volume=500000.0,
        liquidity=200000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=0.0,
        polarity=1
    )
    market_neg = PredictionMarketData(
        external_id="poly-frame-neg",
        ticker="RKLB",
        title="Will Rocket Lab Neutron launch be delayed?",
        status="ACTIVE",
        created_at=now,
        yes_probability=0.20,
        no_probability=0.80,
        volume=500000.0,
        liquidity=200000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=0.0,
        polarity=-1
    )

    pms_pos, _, _, _ = calculate_prediction_market_score("RKLB", [market_pos])
    pms_neg, _, _, _ = calculate_prediction_market_score("RKLB", [market_neg])

    assert pms_pos == 50.0, f"Expected 50.0 for 20% milestone, got {pms_pos}"
    assert pms_neg == 50.0, f"Expected 50.0 for 20% delay risk, got {pms_neg}"
    assert pms_pos == pms_neg, "Framing paradox violation: positive and negative framings must evaluate identically at baseline!"

    # Test momentum response: +5pp surge from 20% to 25% (delta = +5.0)
    market_surge = PredictionMarketData(
        external_id="poly-frame-surge",
        ticker="RKLB",
        title="Will Rocket Lab launch Neutron in 2026?",
        status="ACTIVE",
        created_at=now,
        yes_probability=0.25,
        no_probability=0.75,
        volume=500000.0,
        liquidity=200000.0,
        spread=0.01,
        quality_score=90.0,
        probability_change_24h=5.0,
        polarity=1
    )
    pms_surge, _, _, _ = calculate_prediction_market_score("RKLB", [market_surge])
    assert pms_surge > 55.0, f"Expected bullish lean > 55.0 on +5pp surge, got {pms_surge}"


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
        event_mappings=custom_mapping,
        allow_sector_only=True
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


def test_polymarket_resolution_rule_does_not_invert_positive_question():
    """
    Validates the fix for audit issue 9:
    'Will Rocket Lab launch successfully?' with resolution rule
    'Resolves No in case of launch failure.' must maintain polarity = 1.
    The negative resolution condition for 'No' must not invert a favorable question.
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    provider = PolymarketGammaProvider()
    event_data = {
        "id": "ev-pos-audit",
        "title": "Rocket Lab Launch Success",
        "slug": "rocket-lab-electron-launch",
        "description": "Market resolution rules: Resolves No in case of launch failure, delay, or mission cancellation."
    }
    market_data = {
        "id": "m-pos-audit",
        "question": "Will Rocket Lab launch successfully?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.85", "0.15"]',  # 85% chance of success
        "volumeNum": 250000.0,
        "liquidityNum": 100000.0,
        "spread": 0.01,
        "priceChange24h": 5.0
    }

    parsed = provider._parse_gamma_market(event_data, market_data, ticker="RKLB")
    assert parsed is not None
    assert parsed.polarity == 1, f"Expected polarity 1 (bullish on YES), got {parsed.polarity}"

    # Calculate PMS for this market: 85% probability of success should be highly bullish (> 70)
    pms, conf, qual, bd = calculate_prediction_market_score("RKLB", [parsed])
    assert pms is not None
    assert pms > 70.0, f"Expected bullish PMS (>70) for 85% success probability, got {pms}"
    assert bd["markets"][0]["probability"] == 0.85
    assert bd["markets"][0]["polarity"] == 1


def test_polymarket_explicit_reviewable_polarity_mapping():
    """
    Validates that explicit reviewable polarity mapping (PMS_EXPLICIT_POLARITY_MAP)
    takes precedence over automated heuristic classification.
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider, PMS_EXPLICIT_POLARITY_MAP

    provider = PolymarketGammaProvider()
    test_market_id = "custom-override-market-123"
    PMS_EXPLICIT_POLARITY_MAP[test_market_id] = -1

    try:
        event_data = {"id": "ev-override", "title": "Overridden Market", "slug": "overridden-slug"}
        market_data = {
            "id": test_market_id,
            "question": "Neutral sounding space event question?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.50", "0.50"]'
        }
        parsed = provider._parse_gamma_market(event_data, market_data, ticker="ASTS")
        assert parsed is not None
        assert parsed.polarity == -1, f"Expected explicit override polarity -1, got {parsed.polarity}"
    finally:
        PMS_EXPLICIT_POLARITY_MAP.pop(test_market_id, None)


def test_polymarket_status_inference_active_closed_resolved():
    """
    Test that PolymarketGammaProvider dynamically parses market status:
    - Active market with future end_date -> ACTIVE
    - Market with closed=True -> CLOSED / RESOLVED
    - Market with resolutionDate -> RESOLVED
    - Market with past end_date -> CLOSED
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    provider = PolymarketGammaProvider()
    future_date = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    past_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()

    # 1. Active future market
    m1 = provider._parse_gamma_market(
        event={"id": "ev-1", "title": "Future Launch", "active": True, "closed": False},
        m={"id": "m-1", "question": "Will ASTS launch satellite?", "endDate": future_date, "outcomes": '["Yes", "No"]', "outcomePrices": '["0.7", "0.3"]'},
        ticker="ASTS"
    )
    assert m1 is not None
    assert m1.status == "ACTIVE"
    assert m1.end_date is not None

    # 2. Closed market
    m2 = provider._parse_gamma_market(
        event={"id": "ev-2", "title": "Closed Event", "active": False, "closed": True},
        m={"id": "m-2", "question": "Did Rocket Lab launch in 2025?", "closed": True, "outcomes": '["Yes", "No"]', "outcomePrices": '["1.0", "0.0"]'},
        ticker="RKLB"
    )
    assert m2 is not None
    assert m2.status in ("CLOSED", "RESOLVED")

    # 3. Market with resolutionDate
    m3 = provider._parse_gamma_market(
        event={"id": "ev-3", "title": "Resolved Event", "active": False, "closed": True},
        m={"id": "m-3", "question": "SpaceX Starship orbital flight test", "resolutionDate": past_date, "resolved": True, "outcomes": '["Yes", "No"]', "outcomePrices": '["1.0", "0.0"]'},
        ticker="SPCX"
    )
    assert m3 is not None
    assert m3.status == "RESOLVED"
    assert m3.resolution_date is not None

    # 4. Market with past endDate and not explicitly marked closed
    m4 = provider._parse_gamma_market(
        event={"id": "ev-4", "title": "Past Event", "active": True, "closed": False},
        m={"id": "m-4", "question": "Expired contract", "endDate": past_date, "outcomes": '["Yes", "No"]', "outcomePrices": '["0.5", "0.5"]'},
        ticker="LUNR"
    )
    assert m4 is not None
    assert m4.status == "CLOSED"


def test_repository_upsert_updates_status_and_resolution_date():
    """
    Test that save_prediction_markets updates status, resolution_date, probabilities and quality
    when an existing market transitions to RESOLVED/CLOSED.
    """
    import uuid
    from app.database.connection import SessionLocal
    from app.database.repository import save_prediction_markets, ensure_tickers_seeded
    from app.database.models import PredictionMarketModel

    with SessionLocal() as db:
        ensure_tickers_seeded(db)
        market_ext_id = f"poly-audit-15-test-{uuid.uuid4().hex[:6]}"

        # 1. Initial insert as ACTIVE
        initial_market = PredictionMarketData(
            external_id=market_ext_id,
            ticker="ASTS",
            title="ASTS Q1 Deployment",
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
            yes_probability=0.60,
            no_probability=0.40,
            volume=50000.0,
            liquidity=25000.0,
            spread=0.02,
            quality_score=75.0
        )
        save_prediction_markets(db, [initial_market])

        saved = db.query(PredictionMarketModel).filter(PredictionMarketModel.external_id == market_ext_id).first()
        assert saved is not None
        assert saved.status == "ACTIVE"
        assert saved.yes_probability == 0.60

        # 2. Update to RESOLVED
        res_date = datetime.now(timezone.utc)
        updated_market = PredictionMarketData(
            external_id=market_ext_id,
            ticker="ASTS",
            title="ASTS Q1 Deployment (Resolved)",
            status="RESOLVED",
            created_at=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=30),
            resolution_date=res_date,
            yes_probability=1.00,
            no_probability=0.00,
            volume=75000.0,
            liquidity=0.0,
            spread=0.00,
            quality_score=90.0
        )
        save_prediction_markets(db, [updated_market])

        updated = db.query(PredictionMarketModel).filter(PredictionMarketModel.external_id == market_ext_id).first()
        assert updated is not None
        assert updated.status == "RESOLVED"
        assert updated.yes_probability == 1.00
        assert updated.resolution_date is not None


def test_get_recent_prediction_markets_filters_expired_and_stale():
    """
    Test that get_recent_prediction_markets filters out:
    - Markets with status != ACTIVE
    - Markets with past end_date
    - Markets with stale collected_at beyond max_age_days
    """
    import uuid
    from app.database.connection import SessionLocal
    from app.database.repository import save_prediction_markets, get_recent_prediction_markets, ensure_tickers_seeded, utc_now
    from app.database.models import PredictionMarketModel

    with SessionLocal() as db:
        ensure_tickers_seeded(db)
        now = utc_now()
        uid = uuid.uuid4().hex[:6]
        id_active = f"poly-filter-active-{uid}"
        id_expired = f"poly-filter-expired-{uid}"
        id_closed = f"poly-filter-closed-{uid}"
        id_stale = f"poly-filter-stale-{uid}"

        # 1. Fresh active market
        m_active = PredictionMarketData(
            external_id=id_active,
            ticker="RKLB",
            title="RKLB Active Mission",
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=20),
            yes_probability=0.80,
            no_probability=0.20,
            quality_score=80.0
        )

        # 2. Expired market (end_date in past)
        m_expired = PredictionMarketData(
            external_id=id_expired,
            ticker="RKLB",
            title="RKLB Expired Mission",
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) - timedelta(days=2),
            yes_probability=0.50,
            no_probability=0.50,
            quality_score=70.0
        )

        # 3. Closed market
        m_closed = PredictionMarketData(
            external_id=id_closed,
            ticker="RKLB",
            title="RKLB Closed Mission",
            status="CLOSED",
            created_at=datetime.now(timezone.utc),
            end_date=datetime.now(timezone.utc) + timedelta(days=10),
            yes_probability=0.50,
            no_probability=0.50,
            quality_score=70.0
        )

        save_prediction_markets(db, [m_active, m_expired, m_closed])

        # 4. Stale market (manually backdate collected_at in DB)
        m_stale = PredictionMarketModel(
            external_id=id_stale,
            ticker="RKLB",
            title="RKLB Stale Mission",
            status="ACTIVE",
            created_at=now - timedelta(days=20),
            end_date=now + timedelta(days=20),
            yes_probability=0.70,
            no_probability=0.30,
            quality_score=75.0,
            collected_at=now - timedelta(days=15)
        )
        db.add(m_stale)
        db.commit()

        # Query recent markets for RKLB with default max_age_days=7
        recent_rklb = get_recent_prediction_markets(db, ticker="RKLB", max_age_days=7, include_expired=False)
        returned_ids = [m.external_id for m in recent_rklb]

        assert id_active in returned_ids
        assert id_expired not in returned_ids
        assert id_closed not in returned_ids
        assert id_stale not in returned_ids


def test_gamma_clob_token_ids_parsing():
    """
    Verify that PolymarketGammaProvider._parse_gamma_market extracts the correct
    clob_token_id according to the YES outcome index, as well as condition_id.
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    provider = PolymarketGammaProvider()
    event_data = {"id": "ev-100", "title": "ASTS Satellite Launch", "slug": "asts-satellite-launch"}
    
    # 1. Normal order ["Yes", "No"] with JSON string clobTokenIds
    m_json_str = {
        "id": "916715",
        "conditionId": "0xabc123condition",
        "question": "Will AST SpaceMobile launch satellite in 2026?",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.75", "0.25"]',
        "clobTokenIds": '["21742633143463909520857905973063548906377770857508003661148888062955562858712", "48331023948230948203948230948230948230948230948230948230948230948230948230948"]',
        "volume": "100000",
        "liquidity": "25000",
        "spread": "0.02"
    }
    parsed = provider._parse_gamma_market(event_data, m_json_str, "ASTS")
    assert parsed is not None
    assert parsed.external_id == "916715"
    assert parsed.condition_id == "0xabc123condition"
    assert parsed.clob_token_id == "21742633143463909520857905973063548906377770857508003661148888062955562858712"
    assert parsed.yes_probability == 0.75

    # 2. Reverse order ["No", "Yes"] with python list clobTokenIds
    m_reverse = {
        "id": "916716",
        "conditionId": "0xdef456condition",
        "question": "Will Rocket Lab launch Neutron in 2026?",
        "outcomes": ["No", "Yes"],
        "outcomePrices": ["0.30", "0.70"],
        "clobTokenIds": ["token_no_123", "token_yes_456"],
        "volumeNum": 50000,
        "liquidityNum": 15000,
        "spread": 0.02
    }
    parsed_rev = provider._parse_gamma_market(event_data, m_reverse, "RKLB")
    assert parsed_rev is not None
    assert parsed_rev.clob_token_id == "token_yes_456"
    assert parsed_rev.yes_probability == 0.70


def test_get_history_with_gamma_id_resolution(monkeypatch):
    """
    Verify that PolymarketGammaProvider.get_history automatically resolves
    a short Gamma ID into its CLOB token ID before fetching prices-history.
    """
    from app.collectors.polymarket_provider import PolymarketGammaProvider
    import httpx

    gamma_id = "916715"
    clob_token = "21742633143463909520857905973063548906377770857508003661148888062955562858712"

    gamma_market_resp = {
        "id": gamma_id,
        "conditionId": "0xabc123",
        "question": "ASTS Satellite",
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.80", "0.20"],
        "clobTokenIds": [clob_token, "other_token"]
    }

    clob_history_resp = {
        "history": [
            {"t": 1756400000, "p": 0.75, "v": 5000.0},
            {"t": 1756403600, "p": 0.80, "v": 12000.0}
        ]
    }

    requested_urls = []

    class FakeResponse:
        def __init__(self, status_code, json_data):
            self.status_code = status_code
            self._json = json_data
        def json(self):
            return self._json

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        async def get(self, url, params=None):
            requested_urls.append((url, params))
            if "gamma-api.polymarket.com/markets/916715" in url:
                return FakeResponse(200, gamma_market_resp)
            elif "clob.polymarket.com/prices-history" in url:
                # If queried with CLOB token, return data; if queried with gamma ID, return empty
                if params and params.get("market") == clob_token:
                    return FakeResponse(200, clob_history_resp)
                return FakeResponse(200, {"history": []})
            return FakeResponse(404, {})

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    provider = PolymarketGammaProvider()
    
    # Call get_history with gamma ID
    points = asyncio.run(provider.get_history(gamma_id))
    assert len(points) == 2
    assert points[0].yes_probability == 0.75
    assert points[1].yes_probability == 0.80

    # Ensure gamma lookup happened and CLOB was called with clob_token
    assert any("gamma-api.polymarket.com/markets/916715" in req[0] for req in requested_urls)
    assert any(req[1] and req[1].get("market") == clob_token for req in requested_urls if "prices-history" in req[0])


def test_save_prediction_markets_clob_token_persistence():
    """
    Verify that save_prediction_markets persists clob_token_id and condition_id to DB
    and updates them on subsequent upserts.
    """
    import uuid
    from app.database.connection import get_db
    from app.database.models import PredictionMarketModel
    from app.database.repository import save_prediction_markets

    uid = str(uuid.uuid4())[:8]
    ext_id = f"test_clob_persist_{uid}"
    clob_id = f"clob_token_{uid}"
    cond_id = f"cond_{uid}"

    db = next(get_db())
    try:
        m = PredictionMarketData(
            external_id=ext_id,
            ticker="ASTS",
            title="ASTS Test Market",
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            yes_probability=0.65,
            no_probability=0.35,
            clob_token_id=clob_id,
            condition_id=cond_id
        )

        # 1. Insert
        inserted = save_prediction_markets(db, [m])
        assert inserted == 1

        db_item = db.query(PredictionMarketModel).filter(PredictionMarketModel.external_id == ext_id).first()
        assert db_item is not None
        assert db_item.clob_token_id == clob_id
        assert db_item.condition_id == cond_id

        # 2. Update with new clob_token_id
        m.clob_token_id = f"updated_{clob_id}"
        save_prediction_markets(db, [m])

        db.refresh(db_item)
        assert db_item.clob_token_id == f"updated_{clob_id}"
    finally:
        db.query(PredictionMarketModel).filter(PredictionMarketModel.external_id == ext_id).delete()
        db.commit()
        db.close()












def _pm(external_id, yes, ticker="SPCX", **kw):
    base = dict(
        external_id=external_id, ticker=ticker, title=kw.pop("title", external_id), status="ACTIVE",
        created_at=datetime.now(timezone.utc), yes_probability=yes, no_probability=1.0 - yes,
        volume=500000.0, liquidity=200000.0, spread=0.01, quality_score=90.0, probability_change_24h=0.0
    )
    base.update(kw)
    return PredictionMarketData(**base)


def test_sector_events_alone_give_no_pms_by_default():
    """A ticker without direct markets gets no PMS from sector proxies (pillar excluded, not anchored near 50)."""
    ev = _pm("poly-starship-dock", 0.52, ticker=None, event_key="spacex_starship_orbital_success")
    pms, conf, _, bd = calculate_prediction_market_score("ASTS", direct_markets=[], sector_events=[ev])
    assert pms is None
    assert conf == 0.0
    assert bd["status"] == "SECTOR_ONLY_EXCLUDED"
    assert bd["sector_event_count"] == 1

    # With a direct market present, sector events still contribute alongside it
    direct = _pm("poly-asts-direct", 0.20, ticker="ASTS")
    pms2, _, _, bd2 = calculate_prediction_market_score("ASTS", direct_markets=[direct], sector_events=[ev])
    assert pms2 is not None
    assert {m["type"] for m in bd2["markets"]} == {"DIRECT", "SECTOR_EVENT"}


def test_range_buckets_of_exclusive_events_are_skipped():
    """'<5', '5-6', '7-8'... buckets carry no direction one by one: they must not drag the PMS bearish."""
    buckets = [
        _pm(f"poly-bucket-{label}", p, outcome_group="evt-starship-count", outcome_label=label, baseline_probability=p)
        for label, p in [("<5", 0.47), ("5-6", 0.535), ("7-8", 0.0125), ("9-10", 0.006), ("15-16", 0.0005)]
    ]
    assert all(b.is_range_bucket for b in buckets)
    pms, _, _, bd = calculate_prediction_market_score("SPCX", direct_markets=buckets)
    assert pms is None
    assert bd["range_bucket_count"] == 5

    # A named outcome of an exclusive event ("SpaceX" in "Largest IPO") stays directional
    named = _pm("poly-ipo-spacex", 0.435, outcome_group="evt-largest-ipo", outcome_label="SpaceX", baseline_probability=0.435)
    assert not named.is_range_bucket
    pms_named, _, _, bd_named = calculate_prediction_market_score("SPCX", direct_markets=buckets + [named])
    assert pms_named == 50.0
    assert bd_named["market_count"] == 1


def test_long_shot_market_at_its_own_baseline_is_neutral():
    """A 3.5% market sitting at its 7-day average is neutral; the old 0.05 base-rate floor scored it ~43."""
    m = _pm("poly-doge1-2026", 0.035, baseline_probability=0.0355)
    pms, _, _, _ = calculate_prediction_market_score("SPCX", direct_markets=[m])
    assert 49.0 <= pms <= 50.0


def test_event_key_matching_uses_word_boundaries():
    from app.collectors.polymarket_provider import match_event_key_from_text
    # "sda" inside "Wednesday"/"Thursday" must not map a geomagnetic-storm market to Space Force contracts
    assert match_event_key_from_text("Will the highest geomagnetic storm level on Thursday be G1?") is None
    assert match_event_key_from_text("Will the SDA award Tranche 3 contracts?") == "us_space_force_sda_defense_contracts"
    assert match_event_key_from_text("Will two SpaceX Starships dock together?") == "spacex_starship_orbital_success"


def test_gamma_provider_marks_neg_risk_outcome_groups():
    from app.collectors.polymarket_provider import PolymarketGammaProvider

    provider = PolymarketGammaProvider()
    event = {"id": "evt-77", "title": "How many SpaceX Starship launches reach space in 2026?", "slug": "starship-count", "negRisk": True}
    raw = {"id": "m-1", "question": "Will 5-6 SpaceX Starship launches reach space in 2026?", "groupItemTitle": "5-6",
           "outcomePrices": '["0.53", "0.47"]', "liquidityNum": 50000.0, "volumeNum": 200000.0, "spread": 0.02}
    parsed = provider._parse_gamma_market(event, raw, None)
    assert parsed.outcome_group == "evt-77"
    assert parsed.outcome_label == "5-6"
    assert parsed.is_range_bucket

    ladder = provider._parse_gamma_market(
        {"id": "evt-78", "title": "Two SpaceX Starships dock together by...?", "slug": "dock", "negRisk": False},
        {**raw, "id": "m-2", "question": "Will two SpaceX Starships dock together by December 31, 2027?", "groupItemTitle": "December 31, 2027"},
        None
    )
    assert ladder.outcome_group is None
    assert not ladder.is_range_bucket


def test_get_recent_prediction_markets_direct_only():
    """Verify that get_recent_prediction_markets with direct_only=True returns only direct ticker contracts."""
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
        m1 = PredictionMarketModel(
            external_id="poly-asts-1", ticker="ASTS", title="ASTS Satellite Direct Contract",
            status="ACTIVE", yes_probability=0.7, no_probability=0.3,
            volume=10000.0, liquidity=5000.0, spread=0.02, quality_score=80.0,
            event_key=None, created_at=now
        )
        m2 = PredictionMarketModel(
            external_id="poly-starlink-fcc", ticker=None, title="SpaceX Starlink FCC Approval",
            status="ACTIVE", yes_probability=0.8, no_probability=0.2,
            volume=50000.0, liquidity=20000.0, spread=0.01, quality_score=85.0,
            event_key="spacex_starlink_direct_to_cell_fcc_approval", created_at=now
        )
        m3 = PredictionMarketModel(
            external_id="poly-macro-1", ticker=None, title="Human landing on Moon",
            status="ACTIVE", yes_probability=0.4, no_probability=0.6,
            volume=100000.0, liquidity=40000.0, spread=0.01, quality_score=90.0,
            event_key=None, created_at=now
        )
        db.add_all([m1, m2, m3])
        db.commit()

        # With direct_only=False (legacy), ASTS gets m1 (direct), m2 (mapped sector), and m3 (unmapped macro)
        legacy_markets = get_recent_prediction_markets(db, ticker="ASTS", direct_only=False)
        legacy_ids = [m.external_id for m in legacy_markets]
        assert "poly-asts-1" in legacy_ids
        assert "poly-starlink-fcc" in legacy_ids

        # With direct_only=True (Single-Asset Focus), ASTS gets ONLY m1 (direct)
        direct_markets = get_recent_prediction_markets(db, ticker="ASTS", direct_only=True)
        direct_ids = [m.external_id for m in direct_markets]
        assert direct_ids == ["poly-asts-1"]

        # When a ticker has no direct contracts (e.g. RKLB in this db), it gets an empty list
        rklb_direct = get_recent_prediction_markets(db, ticker="RKLB", direct_only=True)
        assert rklb_direct == []
    finally:
        db.close()

