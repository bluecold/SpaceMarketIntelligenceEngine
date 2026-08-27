from datetime import datetime, timezone
from app.scoring.ssi import calculate_ssi
from app.scoring.signal import generate_signal_and_explanation
from app.scoring.momentum import calculate_momentum_score
from app.scoring.risk import calculate_risk_score
from app.database.models import SocialPostModel


def test_ssi_pure_social_calculation_from_posts():
    """Validates that SSI calculates pure social sentiment without external market data."""
    posts = [
        SocialPostModel(
            tweet_id="1",
            ticker="ASTS",
            username="analyst1",
            text="ASTS constellation deployment is revolutionary",
            created_at=datetime.now(timezone.utc),
            likes=100,
            reposts=20,
            replies=10,
            views=5000,
            sentiment_score=0.8,
            sentiment_label="BULLISH",
            relevance_score=0.9,
            recency_weight=1.0,
            engagement_score=5.0
        ),
        SocialPostModel(
            tweet_id="2",
            ticker="ASTS",
            username="analyst2",
            text="ASTS FCC approval update",
            created_at=datetime.now(timezone.utc),
            likes=50,
            reposts=5,
            replies=2,
            views=1000,
            sentiment_score=0.6,
            sentiment_label="BULLISH",
            relevance_score=0.85,
            recency_weight=0.9,
            engagement_score=3.0
        )
    ]
    res = calculate_ssi(posts=posts)
    assert res["ssi"] > 70.0
    assert res["total_posts"] == 2
    assert res["weighted_bullish_pct"] == 100.0
    assert "prediction" not in res
    assert "news" not in res


def test_ssi_from_raw_score_clamping():
    res = calculate_ssi(social_score=85.4)
    assert res["ssi"] == 85.4
    assert res["social_score"] == 85.4

    res_clamped_high = calculate_ssi(social_score=120.0)
    assert res_clamped_high["ssi"] == 100.0

    res_clamped_low = calculate_ssi(social_score=-20.0)
    assert res_clamped_low["ssi"] == 0.0


def test_ssi_empty_posts_fallback():
    res = calculate_ssi(posts=[])
    assert res["ssi"] == 50.0
    assert res["total_posts"] == 0
    assert res["bullish_pct"] == 0.0
    assert res["neutral_pct"] == 0.0
    assert res["bearish_pct"] == 0.0



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
    # Since RSI > 75, signal should be restricted from STRONG BUY to WATCH with modifier OVEREXTENDED
    assert res["base_signal"] == "WATCH"
    assert res["signal_modifier"] == "OVEREXTENDED"
    assert res["signal"] == "WATCH (OVEREXTENDED)"
    assert res["is_overbought"] is True


def test_momentum_and_risk_scores():
    import pandas as pd
    indicators = {
        "status": "AVAILABLE",
        "price": 25.0,
        "ema200": 20.0,
        "rsi14": 62.0,
        "volume_ratio": 1.5,
        "atr": 0.8
    }
    mom_no_df = calculate_momentum_score(indicators)
    risk_no_df = calculate_risk_score(indicators)
    
    assert mom_no_df is not None and 50.0 <= mom_no_df <= 100.0
    assert risk_no_df is not None and 0.0 <= risk_no_df <= 100.0

    # With historical dataframe (multiday returns + 30d volatility)
    prices = [20.0 + i * 0.2 for i in range(35)]
    raw_df = pd.DataFrame({
        'Close': prices,
        'High': [p + 0.5 for p in prices],
        'Low': [p - 0.5 for p in prices],
        'Volume': [500000] * 35
    })
    mom_with_df = calculate_momentum_score(indicators, raw_df=raw_df)
    risk_with_df = calculate_risk_score(indicators, raw_df=raw_df)

    assert mom_with_df is not None and mom_with_df > mom_no_df  # Positive short-term returns boost momentum
    assert risk_with_df is not None and 0.0 <= risk_with_df <= 100.0


def test_get_historical_ssi_snapshot_momentum_isolation():
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, SSISnapshotModel, TickerModel
    from app.database.repository import get_historical_ssi_snapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()

    try:
        ticker_record = TickerModel(symbol="ASTS", name="AST SpaceMobile", sector="Space", is_active=True)
        db.add(ticker_record)
        db.commit()

        now = datetime.now(timezone.utc).replace(tzinfo=None)

        # Snapshot 1: 25 hours ago (SMI: 60.0)
        s1 = SSISnapshotModel(
            ticker="ASTS", timestamp=now - timedelta(hours=25),
            social_score=60.0, ssi=60.0, smi=60.0, signal="HOLD", confidence=80.0, data_completeness=100.0
        )
        # Snapshot 2: 5 minutes ago (SMI: 80.0)
        s2 = SSISnapshotModel(
            ticker="ASTS", timestamp=now - timedelta(minutes=5),
            social_score=80.0, ssi=80.0, smi=80.0, signal="BUY", confidence=85.0, data_completeness=100.0
        )
        db.add_all([s1, s2])
        db.commit()

        # Target 24h ago should retrieve s1 (SMI: 60.0) instead of the 5-min-old s2 (SMI: 80.0)
        snap_24h = get_historical_ssi_snapshot(db, "ASTS", target_hours_ago=24.0, tolerance_hours=6.0)
        assert snap_24h is not None
        assert snap_24h.smi == 60.0

        # Current SMI is 82.0 -> Momentum 1D is 82.0 - 60.0 = +22.0 (not 82.0 - 80.0 = +2.0)
        smi_mom_1d = 82.0 - snap_24h.smi
        assert smi_mom_1d == 22.0

        # Snapshot 3: Stale gap test - snapshot from 30 days ago (720h)
        s_ancient = SSISnapshotModel(
            ticker="RKLB", timestamp=now - timedelta(days=30),
            social_score=50.0, ssi=50.0, smi=50.0, signal="HOLD", confidence=80.0, data_completeness=100.0
        )
        db.add(s_ancient)
        db.commit()

        # Querying 24h for RKLB must return None (not the 30-day-old record)
        snap_stale = get_historical_ssi_snapshot(db, "RKLB", target_hours_ago=24.0, tolerance_hours=6.0)
        assert snap_stale is None
    finally:
        db.close()


def test_ssi_snapshot_persists_post_news_prediction_counts():
    """Verify that SSISnapshotModel and repository accurately persist post_count, news_count, and prediction_count."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base
    from app.database.repository import save_ssi_snapshot, get_latest_ssi_snapshot
    from app.scoring.smi import calculate_smi

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        data = {
            "ticker": "ASTS",
            "social_score": 85.0,
            "prediction_score": 75.0,
            "news_score": 80.0,
            "ssi": 85.0,
            "smi": 82.0,
            "signal": "STRONG BUY",
            "confidence": 90.0,
            "data_completeness": 100.0,
            "post_count": 42,
            "news_count": 7,
            "prediction_count": 3
        }
        saved = save_ssi_snapshot(db, data)
        assert saved.post_count == 42
        assert saved.news_count == 7
        assert saved.prediction_count == 3

        latest = get_latest_ssi_snapshot(db, "ASTS")
        assert latest is not None
        assert latest.post_count == 42
        assert latest.news_count == 7
        assert latest.prediction_count == 3

        # Test calculate_smi excludes prediction when prediction_count=0
        smi_zero_pred = calculate_smi(
            social_score=80.0,
            prediction_score=90.0,
            prediction_count=0
        )
        # Prediction score was 90.0, but prediction_count=0 strictly excludes it, so SMI remains 80.0 (social only)
        assert smi_zero_pred["smi"] == 80.0
    finally:
        db.close()



