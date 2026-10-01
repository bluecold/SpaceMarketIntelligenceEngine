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


def test_technical_scorer_price_below_ema200_no_name_error():
    """
    Validates that price < EMA200 (e.g. live RKLB at $72.14 vs EMA200 at $76.60)
    executes cleanly without NameError: name 'rsi' is not defined.
    """
    indicators = {
        "status": "AVAILABLE",
        "price": 72.14,
        "ema200": 76.60,
        "rsi14": 42.0,  # Below 45.0 with price < EMA200 triggers bearish distribution check
        "bollinger_upper": 85.0,
        "bollinger_middle": 75.0,
        "bollinger_lower": 65.0,
        "macd_histogram": -0.25,
        "volume_ratio": 1.4,  # High volume in bearish setup -> distribution (0 volume pts)
        "price_change_1d": -1.8
    }
    # Must NOT raise NameError
    score = calculate_technical_score(indicators)
    assert score is not None
    assert isinstance(score, float)
    assert 0.0 <= score <= 40.0


def test_price_change_1d_in_calculate_technical_indicators():
    """Validates that calculate_technical_indicators correctly calculates price_change_1d."""
    df = pd.DataFrame({
        'Close': [100.0, 105.0, 102.0, 107.1],
        'High': [101.0, 106.0, 103.0, 108.0],
        'Low': [99.0, 104.0, 101.0, 106.0],
        'Volume': [1000] * 4
    })
    # Fewer than 5 candles -> DATA_UNAVAILABLE with price_change_1d = None
    res_short = calculate_technical_indicators(df)
    assert res_short["price_change_1d"] is None

    # 6 candles -> AVAILABLE with price_change_1d = +5.0%
    df_valid = pd.DataFrame({
        'Close': [90.0, 92.0, 95.0, 98.0, 100.0, 105.0],
        'High': [91.0, 93.0, 96.0, 99.0, 101.0, 106.0],
        'Low': [89.0, 91.0, 94.0, 97.0, 99.0, 104.0],
        'Volume': [1000] * 6
    })
    res_valid = calculate_technical_indicators(df_valid)
    assert res_valid["status"] == "AVAILABLE"
    assert res_valid["price_change_1d"] == 5.0


def test_all_bearish_conditions_in_technical_scorer():
    """
    Validates each of the three bearish distribution branches:
    1. price_change_1d < -1.0
    2. price < ema200 and rsi14 < 45.0
    3. macd_hist < 0 and price_change_1d < 0
    In all cases, high volume (>= 1.2x) is penalized (0 volume pts awarded).
    """
    base_ind = {
        "status": "AVAILABLE",
        "price": 50.0,
        "ema200": 45.0,
        "rsi14": 55.0,
        "bollinger_upper": 55.0,
        "bollinger_middle": 50.0,
        "bollinger_lower": 45.0,
        "macd_histogram": 0.1,
        "volume_ratio": 1.5,
        "price_change_1d": 0.5
    }
    # In neutral/bullish, volume_ratio 1.5 gets 5 points
    score_bullish = calculate_technical_score(base_ind)

    # Branch 1: price_change_1d < -1.0
    ind_b1 = {**base_ind, "price_change_1d": -2.5}
    score_b1 = calculate_technical_score(ind_b1)
    assert score_b1 < score_bullish

    # Branch 2: price < ema200 and rsi14 < 45.0
    ind_b2 = {**base_ind, "price": 40.0, "ema200": 45.0, "rsi14": 40.0, "price_change_1d": 0.0}
    score_b2 = calculate_technical_score(ind_b2)
    assert score_b2 < score_bullish

    # Branch 3: macd_histogram < 0 and price_change_1d < 0
    ind_b3 = {**base_ind, "macd_histogram": -0.5, "price_change_1d": -0.2}
    score_b3 = calculate_technical_score(ind_b3)
    assert score_b3 < score_bullish


def test_intraday_metrics_in_calculate_technical_indicators():
    """Validates intraday_reversal_pct, range_location, and intraday_change calculations."""
    # Day high: 63.0, Day low: 58.0, Day open: 60.0, Close: 58.5
    # intraday_reversal_pct: (58.5 - 63.0) / 63.0 * 100 = -7.14%
    # range_location: (58.5 - 58.0) / (63.0 - 58.0) = 0.5 / 5.0 = 0.10
    # intraday_change: (58.5 - 60.0) / 60.0 * 100 = -2.5%
    df = pd.DataFrame({
        'Open': [55.0, 56.0, 57.0, 58.0, 59.0, 60.0],
        'Close': [56.0, 57.0, 58.0, 59.0, 59.5, 58.5],
        'High': [57.0, 58.0, 59.0, 60.0, 61.0, 63.0],
        'Low': [54.0, 55.0, 56.0, 57.0, 58.0, 58.0],
        'Volume': [1000] * 6
    })
    res = calculate_technical_indicators(df)
    assert res["status"] == "AVAILABLE"
    assert res["intraday_reversal_pct"] is not None
    assert round(res["intraday_reversal_pct"], 2) == -7.14
    assert res["range_location"] is not None
    assert round(res["range_location"], 2) == 0.10
    assert res["intraday_change"] is not None
    assert round(res["intraday_change"], 2) == -2.50


def test_intraday_reversal_alert_generation():
    """
    Validates that a sharp intraday drop from morning highs triggers
    INTRADAY_REVERSAL_EXHAUSTION alert even if 1-day change vs yesterday is small.
    """
    from app.scoring.signal import generate_signal_and_explanation

    tech_data = {
        "price": 58.86,
        "volume_ratio": 1.45,
        "intraday_reversal_pct": -6.65,
        "range_location": 0.05,
        "rsi14": 52.0,
        "ema200": 50.0,
        "bollinger_lower": 52.0
    }
    # Stock is -0.9% vs yesterday (flat/HOLD zone), but collapsed -6.65% from day's high
    sig_res = generate_signal_and_explanation(
        ticker="ASTS",
        smi=51.0,
        price_change_1d=-0.9,
        indicators=tech_data
    )
    alerts = sig_res.get("alerts", [])
    rev_alerts = [a for a in alerts if a.get("type") == "INTRADAY_REVERSAL_EXHAUSTION"]
    assert len(rev_alerts) == 1
    assert rev_alerts[0]["category"] == "TECHNICAL"
    assert rev_alerts[0]["level"] == "WARNING"
    assert "-6.6%" in rev_alerts[0]["message"] or "-6.7%" in rev_alerts[0]["message"]


def test_technical_alerts_rsi_ema_and_bollinger():
    """Validates technical alerts for RSI overbought/oversold, EMA breakdown, and Bollinger band breach."""
    from app.scoring.signal import generate_signal_and_explanation

    # 1. RSI Overbought
    res_ob = generate_signal_and_explanation(
        ticker="RKLB",
        smi=68.0,
        price_change_1d=2.0,
        indicators={"price": 75.0, "rsi14": 78.5}
    )
    ob_alerts = [a for a in res_ob.get("alerts", []) if a.get("type") == "RSI_OVERBOUGHT"]
    assert len(ob_alerts) == 1
    assert ob_alerts[0]["category"] == "TECHNICAL"
    assert ob_alerts[0]["level"] == "WARNING"

    # 2. RSI Oversold
    res_os = generate_signal_and_explanation(
        ticker="SPCE",
        smi=32.0,
        price_change_1d=-3.0,
        indicators={"price": 2.5, "rsi14": 26.0}
    )
    os_alerts = [a for a in res_os.get("alerts", []) if a.get("type") == "RSI_OVERSOLD"]
    assert len(os_alerts) == 1
    assert os_alerts[0]["category"] == "TECHNICAL"
    assert os_alerts[0]["level"] == "WARNING"

    # 3. EMA200 Breakdown
    res_ema = generate_signal_and_explanation(
        ticker="ASTS",
        smi=42.0,
        price_change_1d=-3.5,
        indicators={"price": 48.0, "ema200": 51.0, "volume_ratio": 1.4}
    )
    ema_alerts = [a for a in res_ema.get("alerts", []) if a.get("type") == "EMA200_BREAKDOWN"]
    assert len(ema_alerts) == 1
    assert ema_alerts[0]["category"] == "TECHNICAL"
    assert ema_alerts[0]["level"] == "HIGH"

    # 4. Bollinger Bands Lower Breach
    res_bb = generate_signal_and_explanation(
        ticker="LMT",
        smi=40.0,
        price_change_1d=-2.5,
        indicators={"price": 435.0, "bollinger_lower": 440.0}
    )
    bb_alerts = [a for a in res_bb.get("alerts", []) if a.get("type") == "BOLLINGER_LOWER_BREACH"]
    assert len(bb_alerts) == 1
    assert bb_alerts[0]["category"] == "TECHNICAL"
    assert bb_alerts[0]["level"] == "WARNING"





