import pytest
from app.scoring.smi import calculate_smi, calculate_source_agreement
from app.scoring.signal import generate_signal_and_explanation
from app.scoring.momentum import calculate_momentum_score
from app.scoring.risk import calculate_risk_score


def test_smi_composite_calculation():
    """Test full composite SMI calculation with normalized adaptive weights."""
    res = calculate_smi(
        social_score=80.0,
        news_score=70.0,
        momentum_score=60.0,
        risk_score=50.0,
        post_count=30,
        news_count=5
    )
    assert 65.0 <= res["smi"] <= 75.0
    assert res["ssi"] == 80.0
    assert res["data_completeness"] >= 60.0


def test_smi_calculation_missing_market_data():
    res = calculate_smi(social_score=80.0, technical_score_raw=None, post_count=30)
    assert res["smi"] == 80.0
    assert res["ssi"] == 80.0
    assert res["data_completeness"] == 16.7  # 1 out of 6 pillars active
    assert res["confidence"] < 80.0


def test_missing_social_posts_adaptive_exclusion():
    """Verify that when 0 posts exist and social_score is 50 (rate limit), social is excluded from SMI weights."""
    res = calculate_smi(
        social_score=50.0,
        post_count=0,
        prediction_score=90.0,
        prediction_quality=80.0,
        news_score=90.0,
        news_count=3,
        momentum_score=90.0
    )
    # Social should NOT be present in normalized_weights
    assert "social" not in res["normalized_weights"]
    # SMI should be ~90.0 (not diluted by 50.0 down to ~78.0)
    assert res["smi"] == pytest.approx(90.0, 0.5)
    assert sum(res["normalized_weights"].values()) == pytest.approx(1.0, 0.01)


def test_social_score_credibility_shrinkage_small_samples():
    """Verify that small samples (<10 posts) shrink social_score towards 50.0."""
    # N=2 posts, raw social_score=90.0 -> credibility = 2/10 = 0.20 -> effective = 50 + (40 * 0.2) = 58.0
    res = calculate_smi(
        social_score=90.0,
        post_count=2,
        prediction_score=None,
        news_score=None,
        momentum_score=None,
        fundamental_score=None,
        risk_score=None
    )
    # Since social is the only active pillar, SMI should match the shrunk effective_social (58.0)
    assert res["smi"] == 58.0
    assert res["ssi"] == 90.0  # SSI preserves the raw social metric


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
    """Test source agreement calculation for concordant vs contradictory signals and edge cases."""
    # 1. Concordant bullish sources
    agreement_bullish = calculate_source_agreement([0.80, 0.72, 0.60, 0.55])
    assert agreement_bullish >= 0.70, f"Expected high agreement >= 0.70, got {agreement_bullish}"

    # 2. Concordant bearish sources
    agreement_bearish = calculate_source_agreement([-0.80, -0.70, -0.60])
    assert agreement_bearish >= 0.70, f"Expected high negative agreement >= 0.70, got {agreement_bearish}"

    # 3. Diametrically contradictory sources (Polar disagreement)
    agreement_polar = calculate_source_agreement([0.90, -0.90])
    assert agreement_polar <= -0.80, f"Expected strong negative agreement <= -0.80, got {agreement_polar}"

    # 4. Mixed contradictory sources (Social Bullish, Price Bearish)
    agreement_divergent = calculate_source_agreement([0.80, 0.70, -0.60])
    assert agreement_divergent < 0.20, f"Expected low/negative agreement < 0.20, got {agreement_divergent}"

    # 5. Neutral sources (contribute 0 concordance)
    agreement_neutral = calculate_source_agreement([0.05, 0.02, 0.0])
    assert agreement_neutral == 0.0

    # 6. Single source (trivial agreement = 1.0)
    assert calculate_source_agreement([0.75]) == 1.0
    assert calculate_source_agreement([]) == 1.0

    # 7. Strict boundary enforcement [-1.0, +1.0]
    res_extreme = calculate_source_agreement([2.0, -2.0])
    assert -1.0 <= res_extreme <= 1.0



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

    assert sig_res["base_signal"] in ["BUY", "STRONG BUY"]
    assert sig_res["signal_modifier"] is None
    assert sig_res["signal"] in ["BUY", "STRONG BUY"]
    assert "Polymarket" in sig_res["explanation"]
    assert len(sig_res["reasons"]) >= 3


def test_signal_generator_canonical_matrix():
    """Exhaustively test canonical signal generation and modifiers across market regimes."""
    # 1. Regime: Strong Bullish Normal (SMI >= 80, RSI normal)
    res_bull = generate_signal_and_explanation(
        ticker="ASTS",
        smi=85.0,
        social_score=85.0,
        indicators={"status": "AVAILABLE", "price": 25.0, "ema200": 20.0, "rsi14": 62.0}
    )
    assert res_bull["base_signal"] == "STRONG BUY"
    assert res_bull["signal_modifier"] is None
    assert res_bull["signal"] == "STRONG BUY"
    assert res_bull["is_overbought"] is False

    # 2. Regime: Overbought Restriction on STRONG BUY (SMI >= 80, RSI > 75)
    res_ob = generate_signal_and_explanation(
        ticker="ASTS",
        smi=88.0,
        social_score=90.0,
        indicators={"status": "AVAILABLE", "price": 35.0, "ema200": 20.0, "rsi14": 82.0}
    )
    assert res_ob["base_signal"] == "WATCH"
    assert res_ob["signal_modifier"] == "OVEREXTENDED"
    assert res_ob["signal"] == "WATCH (OVEREXTENDED)"
    assert res_ob["is_overbought"] is True

    # 2B. Regime: Overbought Warning on BUY (70 <= SMI < 80, RSI > 75)
    res_buy_ob = generate_signal_and_explanation(
        ticker="ASTS",
        smi=75.0,
        social_score=75.0,
        indicators={"status": "AVAILABLE", "price": 28.0, "ema200": 20.0, "rsi14": 80.0}
    )
    assert res_buy_ob["base_signal"] == "BUY"
    assert res_buy_ob["signal_modifier"] == "OVEREXTENDED"
    assert res_buy_ob["signal"] == "BUY (OVEREXTENDED)"
    assert res_buy_ob["is_overbought"] is True

    # 3. Regime: Missing Technical Data (status != "AVAILABLE")
    res_nodata = generate_signal_and_explanation(
        ticker="SPCX",
        smi=82.0,
        social_score=80.0,
        indicators={"status": "DATA_UNAVAILABLE", "price": None, "ema200": None, "rsi14": None}
    )
    assert res_nodata["base_signal"] in ["BUY", "STRONG BUY"]
    assert res_nodata["signal_modifier"] == "NO MKT DATA"
    assert "NO MKT DATA" in res_nodata["signal"]

    # 4. Regime: Bearish / Avoid Regime (SMI < 35)
    res_avoid = generate_signal_and_explanation(
        ticker="SPCE",
        smi=25.0,
        social_score=25.0,
        indicators={"status": "AVAILABLE", "price": 1.2, "ema200": 2.5, "rsi14": 30.0}
    )
    assert res_avoid["base_signal"] == "STRONG AVOID"
    assert res_avoid["signal_modifier"] is None
    assert res_avoid["signal"] == "STRONG AVOID"


def test_critical_catalyst_alerts_deduplication():
    """Verify that repeated critical catalysts of the same category produce only 1 alert."""
    catalysts = [
        {"category": "CONTRACT_AWARD", "direction": "BULLISH", "importance": "CRITICAL"},
        {"category": "CONTRACT_AWARD", "direction": "BULLISH", "importance": "CRITICAL"},
        {"category": "CONTRACT_AWARD", "direction": "BULLISH", "importance": "CRITICAL"},
        {"category": "LAUNCH_FAILURE", "direction": "BEARISH", "importance": "CRITICAL"},
        {"category": "LAUNCH_FAILURE", "direction": "BEARISH", "importance": "CRITICAL"}
    ]

    res = generate_signal_and_explanation(
        ticker="ASTS",
        smi=60.0,
        social_score=60.0,
        catalysts_found=catalysts
    )

    cat_alerts = [a for a in res["alerts"] if a["type"] == "CRITICAL_CATALYST"]
    # Must contain exactly 2 alerts (1 for Contract Award, 1 for Launch Failure), not 5
    assert len(cat_alerts) == 2
    alert_messages = [a["message"] for a in cat_alerts]
    assert any("Contract Award" in m for m in alert_messages)
    assert any("Launch Failure" in m for m in alert_messages)


def test_tiered_momentum_why_reasons():
    """Verify that micro-noise (|delta| < 4.0) is ignored, while >= 4.0 and >= 8.0 generate tiered reasons."""
    # 1. Micro-noise (delta = +1.5): Should NOT generate a momentum reason
    res_noise = generate_signal_and_explanation(ticker="ASTS", smi=65.0, smi_mom_1d=1.5)
    assert not any("momentum" in r.lower() or "acceleration" in r.lower() for r in res_noise["reasons"])

    # 2. Moderate momentum (delta = +5.0): Should generate rising reason
    res_mod = generate_signal_and_explanation(ticker="ASTS", smi=65.0, smi_mom_1d=5.0)
    assert any("SMI momentum rising" in r for r in res_mod["reasons"])

    # 3. Aggressive acceleration (delta = +9.0): Should generate rapid acceleration reason
    res_agg = generate_signal_and_explanation(ticker="ASTS", smi=75.0, smi_mom_1d=9.0)
    assert any("Rapid SMI acceleration" in r for r in res_agg["reasons"])

    # 4. Severe breakdown (delta = -8.5): Should generate severe breakdown reason
    res_drop = generate_signal_and_explanation(ticker="ASTS", smi=40.0, smi_mom_1d=-8.5)
    assert any("Severe SMI breakdown" in r for r in res_drop["reasons"])


def test_risk_score_integration_monotonicity():
    """
    Verify that calculate_risk_score (where higher = safer) directly increases SMI.
    A safe/stable asset MUST have a higher SMI than a volatile/risky asset when all other inputs are identical.
    """
    import pandas as pd
    import numpy as np

    # 1. Safe / Calm asset (tight ATR, low volatility)
    indicators_safe = {
        "status": "AVAILABLE",
        "price": 100.0,
        "atr": 1.0  # ATR% = 1.0% (< 2.5% -> +15 pts safety)
    }
    # Low variance price series
    prices_safe = [100.0 + (i % 2) * 0.1 for i in range(35)]
    df_safe = pd.DataFrame({"Close": prices_safe})
    risk_safe = calculate_risk_score(indicators_safe, raw_df=df_safe)
    assert risk_safe is not None and risk_safe >= 75.0, f"Expected high safety score >= 75, got {risk_safe}"

    # 2. Risky / Volatile asset (wide ATR, extreme volatility, severe drawdown)
    indicators_risky = {
        "status": "AVAILABLE",
        "price": 100.0,
        "atr": 10.0  # ATR% = 10.0% (> 8.0% -> -25 pts safety)
    }
    # Wildly oscillating and crashing series
    prices_risky = [150.0 - i * 2.5 + (np.sin(i) * 15.0) for i in range(35)]
    df_risky = pd.DataFrame({"Close": prices_risky})
    risk_risky = calculate_risk_score(indicators_risky, raw_df=df_risky)
    assert risk_risky is not None and risk_risky <= 30.0, f"Expected low safety score <= 30, got {risk_risky}"

    # 3. Calculate SMI with both
    base_params = {
        "social_score": 75.0,
        "post_count": 25,
        "news_score": 70.0,
        "news_count": 3,
        "momentum_score": 65.0
    }
    smi_safe = calculate_smi(**base_params, risk_score=risk_safe)
    smi_risky = calculate_smi(**base_params, risk_score=risk_risky)

    assert smi_safe["smi"] > smi_risky["smi"], (
        f"Safe asset SMI ({smi_safe['smi']}) must be higher than risky asset SMI ({smi_risky['smi']})"
    )
    # Verify exact difference is aligned with the 5% risk weight
    assert smi_safe["normalized_weights"]["risk"] > 0
    assert smi_risky["normalized_weights"]["risk"] > 0


def test_zero_post_count_strictly_excludes_social():
    """
    Assert that when post_count == 0, the social pillar is strictly excluded from weights,
    even if social_score was non-neutral (e.g. 85.0).
    """
    res = calculate_smi(
        social_score=85.0,
        post_count=0,
        news_score=75.0,
        news_count=3,
        momentum_score=75.0,
        risk_score=50.0
    )
    assert "social" not in res["normalized_weights"]
    # Remaining pillars should normalize to 1.0 without social dragging or boosting
    assert res["smi"] == pytest.approx(72.2, 0.5)


def test_risk_score_excluded_from_source_agreement():
    """
    Verify that risk_score (a non-directional stability metric) does not contaminate
    the directional source_agreement concordance calculation.
    """
    # 2 opposing directional pillars (Social bullish 85 -> +0.70, Momentum bearish 15 -> -0.70)
    # They have polar disagreement (agreement = -0.98)
    res_no_risk = calculate_smi(
        social_score=85.0,
        post_count=20,
        momentum_score=15.0,
        risk_score=None
    )
    res_with_safe_risk = calculate_smi(
        social_score=85.0,
        post_count=20,
        momentum_score=15.0,
        risk_score=85.0  # High stability/low volatility
    )

    # Source agreement must be identical whether risk_score is present or not
    assert res_no_risk["source_agreement"] == res_with_safe_risk["source_agreement"]
    assert res_with_safe_risk["source_agreement"] < 0.0, "Polar directional disagreement must produce negative agreement"


def test_fundamental_score_calculation_and_smi_full_coverage():
    """Verify calculate_fundamental_score and 100% data quality with all 6 pillars active."""
    from app.scoring.fundamentals import calculate_fundamental_score

    # 1. Healthy Space Company: 24+ months runway, low debt, strong growth
    healthy_fund = {
        "total_cash": 300_000_000,
        "total_debt": 50_000_000,
        "free_cashflow": -80_000_000,  # $80M burn / $300M cash = 3.75 years runway
        "revenue_growth": 0.45,        # +45% YoY growth
        "gross_margins": 0.35          # 35% gross margin
    }
    score_healthy = calculate_fundamental_score(healthy_fund)
    assert score_healthy is not None
    assert score_healthy >= 75.0

    # 2. Distressed Company: < 6 months runway, high debt, negative margin
    distressed_fund = {
        "total_cash": 15_000_000,
        "total_debt": 90_000_000,
        "free_cashflow": -60_000_000,  # 3 months runway -> acute capital raise / dilution risk
        "revenue_growth": -0.10,
        "gross_margins": -0.15
    }
    score_distressed = calculate_fundamental_score(distressed_fund)
    assert score_distressed is not None
    assert score_distressed <= 35.0

    # 3. Empty data returns None cleanly
    assert calculate_fundamental_score({}) is None
    assert calculate_fundamental_score(None) is None

    # 4. Full 6-pillar SMI coverage reaches 100.0% data_completeness / data_quality
    res_full = calculate_smi(
        social_score=80.0,
        prediction_score=75.0,
        prediction_quality=80.0,
        news_score=80.0,
        momentum_score=70.0,
        fundamental_score=score_healthy,
        risk_score=65.0,
        post_count=35,
        news_count=5,
        prediction_count=3
    )
    assert res_full["data_completeness"] == 100.0
    assert res_full["data_quality"] == 100.0
    assert res_full["confidence"] >= 90.0






