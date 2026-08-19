from app.technical.scorer import calculate_technical_score


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
