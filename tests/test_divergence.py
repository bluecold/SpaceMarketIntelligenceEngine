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


def test_divergence_bayesian_shrinkage_suppresses_small_sample_noise():
    """
    Verify that Bayesian shrinkage properly protects divergence alerts:
    - 2 bullish posts (raw social_score = 90.0) are contracted to 58.0 and do NOT trigger BULLISH_DIVERGENCE.
    - 15 bullish posts (raw social_score = 90.0) maintain full conviction and DO trigger BULLISH_DIVERGENCE.
    """
    # Case 1: Small sample (N=2) -> Shrinkage pulls 90.0 towards 50.0 (effective = 58.0, dir_social = +0.16)
    small_sample_results = detect_divergences(
        ticker="ASTS",
        social_score=90.0,
        prediction_score=None,
        price_return_1d=-3.0,
        post_count=2
    )
    div_types_small = [r.type for r in small_sample_results]
    assert "BULLISH_DIVERGENCE" not in div_types_small, "Small sample of 2 posts should not trigger Bullish Divergence"

    # Case 2: Statistically reliable sample (N=15) -> full conviction (effective = 90.0, dir_social = +0.80)
    large_sample_results = detect_divergences(
        ticker="ASTS",
        social_score=90.0,
        prediction_score=None,
        price_return_1d=-3.0,
        post_count=15
    )
    div_types_large = [r.type for r in large_sample_results]
    assert "BULLISH_DIVERGENCE" in div_types_large, "Reliable sample of 15 posts should trigger Bullish Divergence"


def test_divergence_stateful_episode_lifecycle():
    """
    Verify stateful divergence episode management:
    1. First detection creates an active DivergenceModel row (resolved_at=None).
    2. Subsequent recurring detection updates last_seen without creating duplicate rows.
    3. When divergence condition ceases, episode is closed (resolved_at set to timestamp).
    """
    import time
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, DivergenceModel
    from app.database.repository import save_divergences, get_active_divergences, get_active_divergences_batch

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()

    try:
        div_data = [{
            "type": "BEARISH_DIVERGENCE",
            "source_a": "X_SOCIAL",
            "source_b": "PRICE",
            "source_c": None,
            "direction": "BEARISH",
            "strength": 0.85,
            "confidence": 0.80,
            "description": "Initial disconnect between social and price"
        }]

        # Run 1: Initial detection -> 1 active row created
        save_divergences(db, "ASTS", div_data)
        all_rows = db.query(DivergenceModel).all()
        assert len(all_rows) == 1
        ep1 = all_rows[0]
        assert ep1.resolved_at is None
        t_start = ep1.timestamp
        t_last1 = ep1.last_seen

        active_batch = get_active_divergences_batch(db, tickers=["ASTS"])
        assert len(active_batch["ASTS"]) == 1
        assert active_batch["ASTS"][0].id == ep1.id

        # Run 2: Recurring detection (same divergence type still active) -> updates last_seen without duplicate insert
        time.sleep(0.01)
        div_data_updated = [{
            "type": "BEARISH_DIVERGENCE",
            "source_a": "X_SOCIAL",
            "source_b": "PRICE",
            "source_c": None,
            "direction": "BEARISH",
            "strength": 0.90,
            "confidence": 0.85,
            "description": "Updated disconnect between social and price"
        }]
        save_divergences(db, "ASTS", div_data_updated)

        all_rows_run2 = db.query(DivergenceModel).all()
        assert len(all_rows_run2) == 1, "Recurring divergence must NOT create duplicate rows"
        ep_updated = all_rows_run2[0]
        assert ep_updated.timestamp == t_start  # Start time preserved
        assert ep_updated.last_seen >= t_last1  # Last seen updated
        assert ep_updated.strength == 0.90
        assert ep_updated.description == "Updated disconnect between social and price"
        assert ep_updated.resolved_at is None

        # Run 3: Condition ceased (empty active divergences list) -> closes the episode
        save_divergences(db, "ASTS", [])
        all_rows_run3 = db.query(DivergenceModel).all()
        assert len(all_rows_run3) == 1
        ep_closed = all_rows_run3[0]
        assert ep_closed.resolved_at is not None, "Ceased divergence must have resolved_at set"

        # Active queries must now return 0 active episodes
        active_after_close = get_active_divergences(db, "ASTS")
        assert len(active_after_close) == 0
        active_batch_after_close = get_active_divergences_batch(db, tickers=["ASTS"])
        assert len(active_batch_after_close["ASTS"]) == 0
    finally:
        db.close()




