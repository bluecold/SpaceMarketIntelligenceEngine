from app.scoring.ssi import calculate_ssi
from app.scoring.signal import generate_signal_and_explanation
from app.scoring.momentum import calculate_momentum_score
from app.scoring.risk import calculate_risk_score


def test_ssi_calculation_v11():
    # 30% Social (80) + 20% News (70) + 20% Momentum (60) + 5% Risk (50) -> Normalized weights
    res = calculate_ssi(
        social_score=80.0,
        news_score=70.0,
        momentum_score=60.0,
        risk_score=50.0,
        post_count=30,
        news_count=5
    )
    assert 65.0 <= res["smi"] <= 75.0
    assert res["ssi"] == 80.0  # SSI is pure social
    assert res["data_completeness"] >= 60.0


def test_ssi_calculation_missing_market_data():
    res = calculate_ssi(social_score=80.0, technical_score_raw=None, post_count=30)
    assert res["smi"] == 80.0
    assert res["ssi"] == 80.0
    assert res["data_completeness"] == 16.7  # 1 out of 6 pillars active
    assert res["confidence"] < 80.0


def test_signal_overbought_restriction():
    indicators = {"status": "AVAILABLE", "price": 30.0, "ema200": 20.0, "rsi14": 82.0}
    res = generate_signal_and_explanation(
        ticker="ASTS",
        smi=88.0,
        social_score=85.0,
        technical_score_raw=36.0,
        indicators=indicators,
        social_stats={"weighted_bullish_pct": 70.0},
        catalysts_found=[]
    )
    # Since RSI > 75, signal should be restricted from STRONG BUY to WATCH (OVEREXTENDED)
    assert "WATCH" in res["signal"] or "OVEREXTENDED" in res["signal"]
    assert res["is_overbought"] is True


def test_momentum_and_risk_scores():
    indicators = {
        "status": "AVAILABLE",
        "price": 25.0,
        "ema200": 20.0,
        "rsi14": 62.0,
        "volume_ratio": 1.5,
        "atr": 0.8
    }
    mom = calculate_momentum_score(indicators)
    risk = calculate_risk_score(indicators)
    
    assert mom is not None and 50.0 <= mom <= 100.0
    assert risk is not None and 0.0 <= risk <= 100.0
