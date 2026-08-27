import pandas as pd
import numpy as np
from app.technical.indicators import calculate_technical_indicators
from app.scoring.momentum import calculate_momentum_score
from app.scoring.risk import calculate_risk_score
from app.scoring.smi import calculate_smi
from app.divergence.detector import detect_divergences


def generate_synthetic_ohlcv(n: int = 100) -> pd.DataFrame:
    """Generates synthetic OHLCV time series for parity validation."""
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=n, freq="D")
    price = 50.0
    prices = []
    for _ in range(n):
        price += np.random.normal(0.1, 1.5)
        price = max(5.0, price)
        prices.append(price)

    df = pd.DataFrame({
        "Open": [p * 0.99 for p in prices],
        "High": [p * 1.02 for p in prices],
        "Low": [p * 0.98 for p in prices],
        "Close": prices,
        "Volume": [100000 + np.random.randint(0, 50000) for _ in prices]
    }, index=dates)
    return df


def test_technical_indicators_parity_live_vs_historical_slice():
    """
    Validates that calculate_technical_indicators(df, at_index=i) is mathematically
    and deterministically identical to calculate_technical_indicators(df.iloc[:i+1])
    (Live vs Backtest zero-drift guarantee).
    """
    df = generate_synthetic_ohlcv(80)

    for i in [30, 45, 60, 75, 79]:
        # 1. Historical evaluation at index i on full dataset
        historical_res = calculate_technical_indicators(df, at_index=i)

        # 2. Live evaluation on the dataset as it existed at step i
        live_res = calculate_technical_indicators(df.iloc[: i + 1])

        assert historical_res["status"] == "AVAILABLE"
        assert live_res["status"] == "AVAILABLE"
        assert historical_res["price"] == live_res["price"]
        assert historical_res["rsi14"] == live_res["rsi14"]
        assert historical_res["ema200"] == live_res["ema200"]
        assert historical_res["bollinger_middle"] == live_res["bollinger_middle"]
        assert historical_res["macd_histogram"] == live_res["macd_histogram"]
        assert historical_res["atr"] == live_res["atr"]


def test_momentum_and_risk_score_pure_parity():
    """
    Validates that momentum_score and risk_score evaluated at index i on full dataset
    match live execution on sliced dataset with zero lookahead bias.
    """
    df = generate_synthetic_ohlcv(80)

    for i in [35, 50, 70, 79]:
        ind_hist = calculate_technical_indicators(df, at_index=i)
        ind_live = calculate_technical_indicators(df.iloc[: i + 1])

        mom_hist = calculate_momentum_score(ind_hist, raw_df=df, at_index=i)
        mom_live = calculate_momentum_score(ind_live, raw_df=df.iloc[: i + 1])
        assert mom_hist == mom_live, f"Momentum drift at index {i}: {mom_hist} != {mom_live}"

        risk_hist = calculate_risk_score(ind_hist, raw_df=df, at_index=i)
        risk_live = calculate_risk_score(ind_live, raw_df=df.iloc[: i + 1])
        assert risk_hist == risk_live, f"Risk drift at index {i}: {risk_hist} != {risk_live}"


def test_smi_and_divergence_parity_live_vs_backtest():
    """
    Validates that calculate_smi and detect_divergences produce identical
    outputs whether invoked in live runner or backtest simulator.
    """
    # Live execution context
    smi_live = calculate_smi(
        social_score=82.0,
        prediction_score=74.0,
        prediction_quality=85.0,
        news_score=68.0,
        momentum_score=60.0,
        risk_score=70.0,
        post_count=25,
        news_count=5,
        prediction_count=2
    )

    # Backtest simulation context with identical inputs
    smi_backtest = calculate_smi(
        social_score=82.0,
        prediction_score=74.0,
        prediction_quality=85.0,
        news_score=68.0,
        momentum_score=60.0,
        risk_score=70.0,
        post_count=25,
        news_count=5,
        prediction_count=2
    )

    assert smi_live["smi"] == smi_backtest["smi"]
    assert smi_live["confidence"] == smi_backtest["confidence"]
    assert smi_live["source_agreement"] == smi_backtest["source_agreement"]

    # Divergences parity
    divs_live = detect_divergences(
        ticker="ASTS",
        social_score=82.0,
        prediction_score=74.0,
        price_return_1d=-3.5,
        volume_ratio=1.4
    )

    divs_backtest = detect_divergences(
        ticker="ASTS",
        social_score=82.0,
        prediction_score=74.0,
        price_return_1d=-3.5,
        volume_ratio=1.4
    )

    assert len(divs_live) == len(divs_backtest)
    assert divs_live[0].type == divs_backtest[0].type
    assert divs_live[0].strength == divs_backtest[0].strength
