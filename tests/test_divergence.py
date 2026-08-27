import pytest
from app.divergence.detector import detect_divergences


def test_bullish_divergence_spec_113():
    """
    Test Bullish Divergence according to Spec Section 113:
    Social/Prediction is high/bullish, but price return is negative.
    """
    results = detect_divergences(
        ticker="ASTS",
        social_score=80.0,
        prediction_score=75.0,
        price_return_1d=-2.5
    )

    assert len(results) >= 1
    div_types = [r.type for r in results]
    assert "BULLISH_DIVERGENCE" in div_types
    bull_div = next(r for r in results if r.type == "BULLISH_DIVERGENCE")
    assert bull_div.direction == "BULLISH"
    assert bull_div.confidence >= 0.70


def test_bearish_divergence():
    """Test Bearish Divergence when Social and/or Prediction are weak while price rises/overbought."""
    results = detect_divergences(
        ticker="SPCE",
        social_score=30.0,
        prediction_score=35.0,
        price_return_1d=+3.0,
        rsi=76.0
    )

    assert len(results) >= 1
    div_types = [r.type for r in results]
    assert "BEARISH_DIVERGENCE" in div_types
    bear_div = next(r for r in results if r.type == "BEARISH_DIVERGENCE")
    assert bear_div.direction == "BEARISH"


def test_bullish_confirmation():
    """Test Multi-source Bullish Confirmation (Social + Polymarket + Price + Volume surge)."""
    results = detect_divergences(
        ticker="RKLB",
        social_score=78.0,
        prediction_score=82.0,
        price_return_1d=+4.2,
        volume_ratio=1.6
    )

    assert len(results) >= 1
    div_types = [r.type for r in results]
    assert "BULLISH_CONFIRMATION" in div_types
    conf = next(r for r in results if r.type == "BULLISH_CONFIRMATION")
    assert conf.strength >= 0.85
    assert conf.confidence >= 0.85


def test_early_reversal_by_24h_delta_bullish():
    """
    Test Bullish Early Reversal driven by 24h Polymarket Probability Surge (ΔPMS_24h >= +15%).
    Smart capital moves in Polymarket before social sentiment or price react.
    """
    results = detect_divergences(
        ticker="ASTS",
        social_score=48.0,  # Neutral/fearful social sentiment
        prediction_score=68.0,
        prediction_delta_24h=17.0,  # +17 pp shift in 24h
        price_return_1d=0.5
    )

    assert len(results) >= 1
    div_types = [r.type for r in results]
    assert "EARLY_REVERSAL" in div_types
    rev = next(r for r in results if r.type == "EARLY_REVERSAL")
    assert rev.direction == "BULLISH"
    assert rev.source_a == "POLYMARKET_MOMENTUM"
    assert rev.confidence >= 0.80
    assert "+17.0%" in rev.description


def test_early_reversal_by_24h_delta_bearish():
    """
    Test Bearish Early Reversal driven by 24h Polymarket Probability Collapse (ΔPMS_24h <= -15%).
    Polymarket probability dumps while retail social remains euphoric.
    """
    results = detect_divergences(
        ticker="SPCE",
        social_score=75.0,  # Euphoric retail
        prediction_score=35.0,
        prediction_delta_24h=-20.0,  # -20 pp drop in 24h
        price_return_1d=1.0
    )

    assert len(results) >= 1
    div_types = [r.type for r in results]
    assert "EARLY_REVERSAL" in div_types
    rev = next(r for r in results if r.type == "EARLY_REVERSAL")
    assert rev.direction == "BEARISH"
    assert rev.source_a == "POLYMARKET_MOMENTUM"
    assert rev.confidence >= 0.80
    assert "-20.0%" in rev.description


def test_early_reversal_watch():
    """
    Test Early Reversal Structural Fallback:
    Retail social sentiment is deeply fearful/bearish, but Prediction Market smart capital is high.
    """
    results = detect_divergences(
        ticker="SATL",
        social_score=28.0,
        prediction_score=74.0,
        prediction_delta_24h=None,  # Delta unavailable, fallback to level
        price_return_1d=0.0
    )

    assert len(results) >= 1
    div_types = [r.type for r in results]
    assert "EARLY_REVERSAL" in div_types
    rev = next(r for r in results if r.type == "EARLY_REVERSAL")
    assert rev.direction == "BULLISH"
    assert "Early Reversal" in rev.description


def test_bearish_confirmation_critical_alert():
    """Verify that multi-source BEARISH_CONFIRMATION yields CRITICAL severity alert in signal engine."""
    from app.scoring.signal import generate_signal_and_explanation

    res = generate_signal_and_explanation(
        ticker="SPCE",
        smi=25.0,
        social_score=25.0,
        prediction_score=20.0,
        price_change_1d=-5.0,
        indicators={"status": "AVAILABLE", "price": 1.1, "ema200": 2.5, "rsi14": 28.0, "volume_ratio": 1.8}
    )

    # 1. Base signal STRONG AVOID must generate CRITICAL alert
    strong_avoid_alert = next((a for a in res["alerts"] if a["type"] == "STRONG_AVOID"), None)
    assert strong_avoid_alert is not None
    assert strong_avoid_alert["level"] == "CRITICAL"

    # 2. BEARISH_CONFIRMATION must generate CRITICAL alert
    bear_conf_alert = next((a for a in res["alerts"] if a["type"] == "BEARISH_CONFIRMATION"), None)
    assert bear_conf_alert is not None
    assert bear_conf_alert["level"] == "CRITICAL"


def test_divergence_result_default_factory_dynamic_timestamp():
    """Verify that DivergenceResult timestamp is dynamically generated via default_factory, not module import time."""
    from datetime import datetime, timezone
    import time
    from app.divergence.detector import DivergenceResult

    t_before = datetime.now(timezone.utc)
    time.sleep(0.01)
    res = DivergenceResult(
        ticker="ASTS",
        type="BULLISH_DIVERGENCE",
        source_a="X_SOCIAL",
        source_b="PRICE_ACTION",
        direction="BULLISH",
        strength=0.8,
        confidence=0.8,
        description="Test divergence"
    )
    time.sleep(0.01)
    t_after = datetime.now(timezone.utc)

    assert res.timestamp >= t_before
    assert res.timestamp <= t_after


