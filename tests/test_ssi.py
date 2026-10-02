import pytest
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
    assert res["ssi"] is None
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

    # v2.2: 1-5 day returns no longer move the pillar (no predictive power on 2y of prices); only the
    # session direction signs the volume confirmation, and this series closes up on the last bar
    assert mom_with_df is not None and mom_with_df == mom_no_df

    falling_df = raw_df.copy()
    falling_df.loc[falling_df.index[-1], 'Close'] = prices[-2] - 1.0
    mom_falling = calculate_momentum_score(indicators, raw_df=falling_df)
    assert mom_falling < mom_with_df  # Heavy volume on a down day is distribution, not accumulation
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
        assert smi_zero_pred["prediction_score"] is None
    finally:
        db.close()


def test_social_score_relevance_filter_and_deduplication():
    """
    Verify that:
    1. Posts below SOCIAL_MIN_RELEVANCE (0.40) are dropped without fallback, returning None when all are noisy.
    2. Viral retweets / identical texts are deduplicated to 1 observation count while aggregating engagement.
    """
    from app.scoring.social import calculate_social_score
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    # 1. Noisy posts below relevance threshold (relevance = 0.10)
    noisy_posts = [
        SocialPostModel(
            tweet_id=f"noise_{i}",
            ticker="ASTS",
            username=f"user_{i}",
            text="Random tweet about something else entirely",
            created_at=now,
            sentiment_score=0.9,
            sentiment_label="BULLISH",
            relevance_score=0.10,
            recency_weight=1.0,
            engagement_score=1.0
        )
        for i in range(5)
    ]
    res_noisy = calculate_social_score(noisy_posts)
    assert res_noisy["social_score"] is None
    assert res_noisy["total_posts"] == 0

    # 2. 10 duplicate retweets of the same message (relevance = 0.85)
    duplicate_posts = [
        SocialPostModel(
            tweet_id=f"rt_{i}",
            ticker="ASTS",
            username=f"user_{i}",
            text="RT @investor_hub: ASTS commercial deployment reaches final operational testing! https://t.co/abc123",
            created_at=now,
            sentiment_score=0.8,
            sentiment_label="BULLISH",
            relevance_score=0.85,
            recency_weight=1.0,
            engagement_score=2.0
        )
        for i in range(10)
    ]
    res_dup = calculate_social_score(duplicate_posts)
    assert res_dup["social_score"] is not None
    # Must count as exactly 1 observation, not 10
    assert res_dup["total_posts"] == 1
    assert res_dup["relevant_posts"] == 1
    assert res_dup["social_score"] > 80.0


def test_social_score_respects_sentiment_confidence_weighting():
    """Verify that a high-confidence sentiment post (+0.8, conf 0.95) outweighs a low-confidence post (-0.8, conf 0.40)."""
    from app.scoring.social import calculate_social_score
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    posts = [
        # High confidence bullish post
        SocialPostModel(
            tweet_id="p1",
            ticker="RKLB",
            username="analyst_pro",
            text="Rocket Lab signs multi-launch contract, strong revenue expansion.",
            created_at=now,
            sentiment_score=0.8,
            sentiment_label="BULLISH",
            sentiment_confidence=0.95,
            relevance_score=1.0,
            recency_weight=1.0,
            engagement_score=1.0
        ),
        # Low confidence bearish post
        SocialPostModel(
            tweet_id="p2",
            ticker="RKLB",
            username="random_user",
            text="Stock drops slightly today.",
            created_at=now,
            sentiment_score=-0.8,
            sentiment_label="BEARISH",
            sentiment_confidence=0.40,
            relevance_score=1.0,
            recency_weight=1.0,
            engagement_score=1.0
        )
    ]
    res = calculate_social_score(posts)
    assert res["social_score"] is not None
    # Because conf 0.95 is > 2.3x higher than 0.40, the final score must lean clearly BULLISH (> 60)
    assert res["social_score"] > 60.0


def test_duplicate_spam_effective_sample_size_and_bounded_engagement():
    """
    Verify that 30 duplicate spammed copies of a bullish post from 1 author:
    1. Yields raw_post_count=30, unique_post_count=1, author_count=1, effective_sample_size=1.
    2. Bounds engagement accumulation so 30 duplicates do not produce 15x linear engagement growth.
    3. Feeds effective_sample_size=1 into calculate_smi, correctly shrinking the single-observation
       score from 100.0 towards 55.0 rather than keeping it at 100.0.
    """
    from datetime import datetime, timezone
    from app.scoring.social import calculate_social_score
    from app.scoring.smi import calculate_smi

    now = datetime.now(timezone.utc)
    spammed_posts = [
        SocialPostModel(
            tweet_id=f"spam_{i}",
            ticker="ASTS",
            username="spambot1",
            text="ASTS to the moon! Incredible satellite deployment!",
            created_at=now,
            sentiment_score=1.0,
            sentiment_label="BULLISH",
            sentiment_confidence=1.0,
            relevance_score=1.0,
            recency_weight=1.0,
            engagement_score=5.0
        )
        for i in range(30)
    ]

    res = calculate_social_score(spammed_posts)
    assert res["raw_post_count"] == 30
    assert res["relevant_post_count"] == 30
    assert res["unique_post_count"] == 1
    assert res["author_count"] == 1
    assert res["effective_sample_size"] == 1
    assert res["total_posts"] == 1

    # In the isolated social pillar, feeding N_eff=1 shrinks the 100.0 score to ~55.0
    smi_res_effective = calculate_smi(
        social_score=res["social_score"],
        post_count=res["effective_sample_size"]
    )
    # With N=1, Bayesian shrinkage maps 100.0 -> 50.0 + (100 - 50) * 0.1 = 55.0
    assert smi_res_effective["smi"] == pytest.approx(55.0, abs=1.0)

    # In contrast, if raw N=30 were erroneously passed, it would falsely report SMI 100.0
    smi_res_raw_erroneous = calculate_smi(
        social_score=res["social_score"],
        post_count=res["raw_post_count"]
    )
    assert smi_res_raw_erroneous["smi"] == 100.0


def test_dynamic_recency_decay_at_evaluation_time():
    """
    Verify that calculate_social_score dynamically computes recency decay from post.created_at
    against analysis_timestamp, rather than reusing static frozen DB recency_weight.
    """
    from datetime import datetime, timezone, timedelta
    from app.scoring.social import calculate_social_score

    now = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
    twelve_hours_ago = now - timedelta(hours=12)

    posts = [
        # Fresh bullish post (0 hours old) -> dynamic weight = 1.0
        SocialPostModel(
            tweet_id="fresh_1",
            ticker="RKLB",
            username="analyst1",
            text="Rocket Lab Neutron launch schedule accelerating on track!",
            created_at=now,
            sentiment_score=1.0,
            sentiment_label="BULLISH",
            sentiment_confidence=1.0,
            relevance_score=1.0,
            recency_weight=1.0,  # DB stored weight
            engagement_score=0.0
        ),
        # 12-hour-old bearish post -> dynamic weight = 0.50 with 12h half-life, despite DB recency_weight=1.0
        SocialPostModel(
            tweet_id="stale_1",
            ticker="RKLB",
            username="bear1",
            text="Temporary launch delay reported for test flight.",
            created_at=twelve_hours_ago,
            sentiment_score=-1.0,
            sentiment_label="BEARISH",
            sentiment_confidence=1.0,
            relevance_score=1.0,
            recency_weight=1.0,  # Frozen DB weight from 12 hours ago
            engagement_score=0.0
        )
    ]

    # Evaluated at 'now'
    res = calculate_social_score(posts, analysis_timestamp=now, half_life_hours=12.0)

    # If frozen weight 1.0 were used for both: weighted net = (+1.0*1.0 + -1.0*1.0)/2 = 0.0 -> score = 50.0
    # With dynamic decay: weight(fresh) = 1.0, weight(12h) = 0.50
    # Weighted sentiment sum = (+1.0*1.0 + -1.0*0.50) / 1.50 = +0.50 / 1.50 = +0.3333
    # Normalized social score = 50.0 + 50.0 * 0.3333 = 66.7
    assert res["social_score"] == pytest.approx(66.7, abs=0.5)
    assert res["weighted_bullish_pct"] == pytest.approx(66.7, abs=0.5)
    assert res["weighted_bearish_pct"] == pytest.approx(33.3, abs=0.5)


def test_multi_ticker_document_association_social_and_news():
    """
    Verify that a single multi-entity tweet or news article can be associated with multiple tickers
    (e.g. ASTS and RKLB), each preserving its ticker-specific sentiment score and relevance.
    """
    from datetime import datetime, timezone
    from app.database.connection import SessionLocal, init_db
    from app.database.repository import (
        save_social_posts, get_recent_social_posts,
        save_news_items, get_recent_news_items
    )

    import uuid
    init_db()
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        unique_suffix = uuid.uuid4().hex[:8]
        shared_tweet_id = f"shared_tweet_{unique_suffix}"

        # 1. Ingest shared tweet for ASTS (Bullish for ASTS)
        posts_asts = [{
            "tweet_id": shared_tweet_id,
            "ticker": "ASTS",
            "username": "space_insider",
            "text": "ASTS wins major satellite contract; Rocket Lab launch partnership remains uncertain.",
            "created_at": now,
            "sentiment_score": 1.0,
            "sentiment_label": "BULLISH",
            "sentiment_confidence": 0.95,
            "relevance_score": 1.0,
            "engagement_score": 10.0
        }]
        added_asts = save_social_posts(db, posts_asts)
        assert added_asts == 1

        # 2. Ingest same shared tweet for RKLB (Bearish/Uncertain for RKLB)
        posts_rklb = [{
            "tweet_id": shared_tweet_id,
            "ticker": "RKLB",
            "username": "space_insider",
            "text": "ASTS wins major satellite contract; Rocket Lab launch partnership remains uncertain.",
            "created_at": now,
            "sentiment_score": -0.60,
            "sentiment_label": "BEARISH",
            "sentiment_confidence": 0.85,
            "relevance_score": 0.80,
            "engagement_score": 10.0
        }]
        added_rklb = save_social_posts(db, posts_rklb)
        assert added_rklb == 1

        # Verify both tickers retrieve their respective document entries
        asts_posts = get_recent_social_posts(db, "ASTS", hours=24)
        rklb_posts = get_recent_social_posts(db, "RKLB", hours=24)

        asts_matches = [p for p in asts_posts if p.tweet_id == shared_tweet_id]
        rklb_matches = [p for p in rklb_posts if p.tweet_id == shared_tweet_id]

        assert len(asts_matches) == 1
        assert asts_matches[0].sentiment_score == 1.0
        assert asts_matches[0].sentiment_label == "BULLISH"

        assert len(rklb_matches) == 1
        assert rklb_matches[0].sentiment_score == -0.60
        assert rklb_matches[0].sentiment_label == "BEARISH"

        # 3. Ingest shared news item for ASTS and RKLB
        shared_url = f"https://spacenews.com/2026/asts-rklb-satellite-deployment-{unique_suffix}"
        news_asts = [{
            "ticker": "ASTS",
            "title": "Space Sector Weekly: ASTS and Rocket Lab Developments",
            "summary": "ASTS scales production while Rocket Lab expands launch manifest.",
            "source": "SpaceNews",
            "url": shared_url,
            "published_at": now,
            "sentiment_score": 0.80,
            "sentiment_label": "BULLISH",
            "relevance_score": 0.90
        }]
        news_rklb = [{
            "ticker": "RKLB",
            "title": "Space Sector Weekly: ASTS and Rocket Lab Developments",
            "summary": "ASTS scales production while Rocket Lab expands launch manifest.",
            "source": "SpaceNews",
            "url": shared_url,
            "published_at": now,
            "sentiment_score": 0.50,
            "sentiment_label": "BULLISH",
            "relevance_score": 0.85
        }]

        save_news_items(db, news_asts)
        save_news_items(db, news_rklb)

        asts_news = get_recent_news_items(db, "ASTS", days=3)
        rklb_news = get_recent_news_items(db, "RKLB", days=3)

        assert any(n.url == shared_url and n.sentiment_score == 0.80 for n in asts_news)
        assert any(n.url == shared_url and n.sentiment_score == 0.50 for n in rklb_news)

    finally:
        db.close()








