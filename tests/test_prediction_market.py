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
