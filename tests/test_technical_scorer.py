import pandas as pd
import numpy as np
from app.technical.scorer import calculate_technical_score
from app.technical.indicators import calculate_technical_indicators


def test_technical_scorer_bullish():
    indicators = {
        "status": "AVAILABLE",
        "price": 25.0,
        "ema200": 20.0,  # +10 (Price > EMA200)
        "rsi14": 62.0,   # +10 (RSI 50-70)
        "bollinger_upper": 28.0,
        "bollinger_middle": 24.0,  # +10 (Price in upper band)
        "bollinger_lower": 20.0,
        "macd_histogram": 0.15,   # +5 (Histogram > 0)
        "volume_ratio": 1.6        # +5 (Ratio >= 1.5)
    }
    score = calculate_technical_score(indicators)
    assert score == 40.0


def test_technical_scorer_unavailable():
    indicators = {"status": "DATA_UNAVAILABLE"}
    score = calculate_technical_score(indicators)
    assert score is None


def test_rsi_wilder_smoothing_monotonic_series():
    """Validates Wilder's RSI on strictly rising and strictly falling series."""
    # 1. Strictly rising series -> RSI should reach 100
    prices_up = [10.0 + i * 0.5 for i in range(25)]
    df_up = pd.DataFrame({
        'Close': prices_up,
        'High': [p + 0.2 for p in prices_up],
        'Low': [p - 0.2 for p in prices_up],
        'Volume': [100000] * 25
    })
    res_up = calculate_technical_indicators(df_up)
    assert res_up["status"] == "AVAILABLE"
    assert res_up["rsi14"] == 100.0
    assert res_up["atr"] > 0.0

    # 2. Strictly falling series -> RSI should reach 0
    prices_down = [30.0 - i * 0.5 for i in range(25)]
    df_down = pd.DataFrame({
        'Close': prices_down,
        'High': [p + 0.2 for p in prices_down],
        'Low': [p - 0.2 for p in prices_down],
        'Volume': [100000] * 25
    })
    res_down = calculate_technical_indicators(df_down)
    assert res_down["rsi14"] == 0.0


def test_rsi_wilder_smoothing_realistic_series():
    """Validates realistic price oscillating series yields smooth bounded RSI and valid ATR."""
    np.random.seed(42)
    base = 20.0
    returns = np.random.normal(0.001, 0.02, 50)
    prices = [base]
    for r in returns:
        prices.append(prices[-1] * (1.0 + r))

    df = pd.DataFrame({
        'Close': prices,
        'High': [p * 1.01 for p in prices],
        'Low': [p * 0.99 for p in prices],
        'Volume': [500000] * len(prices)
    })
    res = calculate_technical_indicators(df)
    assert res["status"] == "AVAILABLE"
    assert 20.0 <= res["rsi14"] <= 80.0
    assert res["ema200"] is None  # 51 candles < 200 periods
    assert res["ema200_reliable"] is False
    assert res["bollinger_upper"] > res["bollinger_middle"] > res["bollinger_lower"]
    assert res["atr"] > 0.0


def test_macd_price_and_atr_normalization_scale_invariance():
    """
    Validates scale invariance for MACD near-zero consolidation:
    - Low priced stock ($2, e.g. SPCE): -0.04 is a 2% negative move (NOT near zero -> 0 pts).
      -0.002 is 0.1% negative move (near zero -> +2 pts).
    - High priced stock ($400, e.g. LMT): -0.20 is a 0.05% move (near zero -> +2 pts).
    """
    # 1. Penny/Micro-cap ($2.00) with -0.04 MACD (2% drop from price)
    ind_spce_negative = {
        "status": "AVAILABLE",
        "price": 2.00,
        "atr": 0.15,
        "macd_histogram": -0.04  # Was getting +2 in old code due to <= 0.05, now should get 0.0
    }
    score_spce_neg = calculate_technical_score(ind_spce_negative)
    assert score_spce_neg == 0.0, f"Expected 0.0 for 2% negative MACD move, got {score_spce_neg}"

    # 1b. Penny/Micro-cap ($2.00) with genuine tight consolidation (-0.002)
    # Available points: MACD (5.0). Scored: 2.0 -> (2.0 / 5.0) * 40.0 = 16.0
    ind_spce_flat = {
        "status": "AVAILABLE",
        "price": 2.00,
        "atr": 0.15,
        "macd_histogram": -0.002
    }
    score_spce_flat = calculate_technical_score(ind_spce_flat)
    assert score_spce_flat == 16.0, f"Expected 16.0 for scaled near-zero MACD, got {score_spce_flat}"

    # 2. Large-cap ($400.00) with -0.20 MACD (0.05% drop from price, within ATR)
    # Available points: MACD (5.0). Scored: 2.0 -> (2.0 / 5.0) * 40.0 = 16.0
    ind_lmt_flat = {
        "status": "AVAILABLE",
        "price": 400.00,
        "atr": 5.0,
        "macd_histogram": -0.20  # -0.20 / 5.0 = 0.04 ATR (well within 0.08 ATR threshold)
    }
    score_lmt_flat = calculate_technical_score(ind_lmt_flat)
    assert score_lmt_flat == 16.0, f"Expected 16.0 for high priced stock near-zero MACD, got {score_lmt_flat}"


def test_ema200_depth_gate_and_adaptive_normalization():
    """Validates that len(df) < 200 yields ema200=None, ema200_reliable=False, and scales adaptively."""
    # 1. Series with 80 candles (< 200)
    df_short = pd.DataFrame({
        'Close': [20.0 + i * 0.1 for i in range(80)],
        'High': [20.2 + i * 0.1 for i in range(80)],
        'Low': [19.8 + i * 0.1 for i in range(80)],
        'Volume': [50000] * 80
    })
    res_short = calculate_technical_indicators(df_short)
    assert res_short["ema200"] is None
    assert res_short["ema200_reliable"] is False

    # Scorer on short history: 30 max points available (RSI=10, BB=10, MACD=5, Vol=5)
    # If all 30 points are won, scaled score is 40.0
    ind_short_bullish = {
        "status": "AVAILABLE",
        "price": 28.0,
        "ema200": None,             # Omitted
        "rsi14": 60.0,              # +10
        "bollinger_middle": 26.0,
        "bollinger_upper": 30.0,
        "bollinger_lower": 22.0,    # +10
        "macd_histogram": 0.5,      # +5
        "volume_ratio": 1.6         # +5
    }
    score_short = calculate_technical_score(ind_short_bullish)
    assert score_short == 40.0, f"Expected 40.0 scaled score, got {score_short}"

    # 2. Series with 220 candles (>= 200)
    df_long = pd.DataFrame({
        'Close': [20.0 + i * 0.05 for i in range(220)],
        'High': [20.2 + i * 0.05 for i in range(220)],
        'Low': [19.8 + i * 0.05 for i in range(220)],
        'Volume': [50000] * 220
    })
    res_long = calculate_technical_indicators(df_long)
    assert res_long["ema200"] is not None
    assert res_long["ema200_reliable"] is True
    assert res_long["ema200"] > 20.0



