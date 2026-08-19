import pytest
from app.scoring.smi import calculate_smi, calculate_source_agreement
from app.scoring.signal import generate_signal_and_explanation
from app.scoring.momentum import calculate_momentum_score
from app.scoring.risk import calculate_risk_score


def test_missing_prediction_market_spec_116():
    """
    Test Spec Section 116:
    Missing Polymarket data should not break SMI calculation,
    and weights should normalize adaptively.
    """
    result = calculate_smi(
        social_score=80.0,
        prediction_score=None,
        news_score=70.0,
        momentum_score=75.0,
        fundamental_score=80.0,
        risk_score=60.0,
        post_count=25,
        news_count=3
    )

    assert result is not None
    assert "smi" in result
    assert 70.0 <= result["smi"] <= 85.0
    assert result["prediction_score"] is None
    # Weights should sum to 1.0
    weights_sum = sum(result["normalized_weights"].values())
    assert weights_sum == pytest.approx(1.0, 0.01)


def test_prediction_weight_disabled_on_low_quality_spec_115():
    """
    Test Spec Section 115:
    If Prediction Quality < 30, effective weight of Prediction Market is 0.
    """
    result = calculate_smi(
        social_score=80.0,
        prediction_score=95.0,
        prediction_quality=20.0,  # Below 30 threshold
        news_score=70.0,
        momentum_score=60.0,
        post_count=20,
        news_count=2
    )

    assert result["prediction_score"] is None
    assert "prediction" not in result["normalized_weights"]
    weights_sum = sum(result["normalized_weights"].values())
    assert weights_sum == pytest.approx(1.0, 0.01)


def test_source_agreement_calculation():
    """Test source agreement calculation for concordant vs contradictory signals."""
    # Concordant bullish sources
    agreement_bullish = calculate_source_agreement([0.80, 0.72, 0.60, 0.55])
    assert agreement_bullish >= 0.70, f"Expected high agreement >= 0.70, got {agreement_bullish}"

    # Contradictory sources (Social Bullish, Price Bearish)
    agreement_divergent = calculate_source_agreement([0.80, 0.70, -0.60])
    assert agreement_divergent < 0.20, f"Expected low/negative agreement < 0.20, got {agreement_divergent}"


def test_smi_signal_with_polymarket_and_divergences():
    """Test full signal generation with SMI, Polymarket, and active divergence alerts."""
    indicators = {
        "status": "AVAILABLE",
        "price": 28.0,
        "ema200": 22.0,
        "rsi14": 64.0,
        "volume_ratio": 1.4
    }
    
    smi_res = calculate_smi(
        social_score=82.0,
        prediction_score=76.0,
        prediction_quality=85.0,
        news_score=80.0,
        momentum_score=75.0,
        risk_score=40.0,
        post_count=35,
        news_count=4
    )

    sig_res = generate_signal_and_explanation(
        ticker="ASTS",
        smi=smi_res["smi"],
        social_score=smi_res["social_score"],
        technical_score_raw=35.0,
        indicators=indicators,
        social_stats={"weighted_bullish_pct": 74.0},
        catalysts_found=[{"category": "LAUNCH", "direction": "BULLISH", "importance": "HIGH"}],
        prediction_score=smi_res["prediction_score"]
    )

    assert sig_res["signal"] in ["BUY", "STRONG BUY"]
    assert "Polymarket" in sig_res["explanation"]
    assert len(sig_res["reasons"]) >= 3
