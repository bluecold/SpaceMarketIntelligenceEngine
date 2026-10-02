import pytest
from datetime import datetime, timedelta, timezone

from app.database.models import SocialPostModel
from app.scoring.social import calculate_social_score, calculate_social_baseline, apply_social_baseline
from app.scoring.smi import calculate_smi
from app.scoring.signal import generate_signal_and_explanation

NOW = datetime(2026, 10, 1, 12, 0, 0)


def _post(i, label, score, author=None, created=NOW, text=None, conf=1.0, rel=1.0):
    return SocialPostModel(
        tweet_id=f"t{i}",
        ticker="ASTS",
        username=author or f"user_{i}",
        text=text or f"post number {i} about $ASTS",
        created_at=created,
        sentiment_score=score,
        sentiment_label=label,
        sentiment_confidence=conf,
        relevance_score=rel,
        engagement_score=0.0
    )


def test_neutral_posts_do_not_dilute_polarity():
    """
    2 bullish (+0.6) and 8 neutral posts: the old all-post mean gave 50 + 50*0.12 = 56.
    Opinion-only polarity keeps the bull/bear balance: 50 + 50*0.6 = 80.
    Neutral posts still show up in the distribution and in total_posts.
    """
    posts = [_post(i, "BULLISH", 0.6) for i in range(2)] + [_post(10 + i, "NEUTRAL", 0.0) for i in range(8)]
    res = calculate_social_score(posts, analysis_timestamp=NOW)
    assert res["social_score"] == pytest.approx(80.0, abs=0.1)
    assert res["neutral_pct"] == 80.0
    assert res["opinion_post_count"] == 2
    assert res["effective_sample_size"] == 2
    assert res["total_posts"] == 10


def test_all_neutral_posts_yield_no_directional_evidence():
    """Only neutral chatter: no SSI (None) and zero opinion sample, so the SMI excludes the social pillar."""
    posts = [_post(i, "NEUTRAL", 0.0) for i in range(12)]
    res = calculate_social_score(posts, analysis_timestamp=NOW)
    assert res["social_score"] is None
    assert res["effective_sample_size"] == 0
    assert res["total_posts"] == 12

    smi = calculate_smi(social_score=res["social_score"], news_score=60.0, post_count=res["effective_sample_size"], news_count=3)
    assert "social" not in smi["active_pillars"]


def test_opinion_sample_bounded_by_distinct_authors():
    """5 distinct bullish texts from a single author count as one independent opinion."""
    posts = [_post(i, "BULLISH", 0.8, author="same_user") for i in range(5)] + [_post(20, "NEUTRAL", 0.0)]
    res = calculate_social_score(posts, analysis_timestamp=NOW)
    assert res["opinion_post_count"] == 5
    assert res["effective_sample_size"] == 1


def _history(days, per_day, label="BULLISH", score=0.4):
    """per_day unique posts per 24h bucket, for `days` buckets ending 24h before NOW."""
    posts = []
    n = 0
    for d in range(days):
        for k in range(per_day):
            created = NOW - timedelta(hours=24 + 24 * d + 1 + k * 0.1)
            posts.append(_post(1000 + n, label, score, created=created, text=f"history post {n}"))
            n += 1
    return posts


def test_baseline_recenters_structurally_bullish_ticker():
    """
    A ticker whose community is always +0.4 bullish (raw SSI 70) has a baseline near 70,
    so a normal day maps to ~50 and only a deviation from that norm moves the SSI.
    """
    history = _history(days=10, per_day=20)
    base = calculate_social_baseline(history, NOW - timedelta(days=14), NOW - timedelta(hours=24))
    # 200 opinions with weight 1.0 vs prior weight 10: polarity = 0.4 * 200 / 210
    assert base["polarity"] == pytest.approx(0.4 * 200 / 210, abs=1e-3)
    assert base["days_covered"] == 10
    assert base["daily_post_rate"] == 20.0

    normal_day = calculate_social_score([_post(i, "BULLISH", 0.4) for i in range(20)], analysis_timestamp=NOW)
    adjusted = apply_social_baseline(normal_day, base)
    assert adjusted["social_polarity_raw"] == pytest.approx(70.0, abs=0.1)
    assert adjusted["social_baseline"] == pytest.approx(69.0, abs=0.1)
    assert adjusted["social_score"] == pytest.approx(51.0, abs=0.2)

    bearish_turn = calculate_social_score(
        [_post(i, "BULLISH", 0.4) for i in range(10)] + [_post(50 + i, "BEARISH", -0.6) for i in range(10)],
        analysis_timestamp=NOW
    )
    assert apply_social_baseline(bearish_turn, base)["social_score"] < 35.0


def test_thin_baseline_is_shrunk_towards_neutral():
    """Three opinionated posts of history barely move the baseline (prior pseudo-weight of 10)."""
    base = calculate_social_baseline(_history(days=1, per_day=3, score=0.9), NOW - timedelta(days=14), NOW - timedelta(hours=24))
    assert base["polarity"] == pytest.approx(0.9 * 3 / 13, abs=1e-3)
    assert base["days_covered"] == 1


def test_mention_volume_ratio_uses_daily_median_and_needs_history():
    """
    Baseline rate is the median of per-day unique counts (duplicates collapse only within a day).
    The ratio stays None until SOCIAL_BASELINE_MIN_DAYS of history exist.
    """
    history = _history(days=5, per_day=10)
    # The same text repeated on another day is still one post per day
    history += [_post(9000 + d, "NEUTRAL", 0.0, created=NOW - timedelta(hours=30 + 24 * d), text="same daily text") for d in range(5)]
    base = calculate_social_baseline(history, NOW - timedelta(days=14), NOW - timedelta(hours=24))
    assert base["daily_post_rate"] == 11.0

    spike_day = calculate_social_score([_post(i, "BULLISH", 0.5) for i in range(33)], analysis_timestamp=NOW)
    adjusted = apply_social_baseline(spike_day, base)
    assert adjusted["mention_volume_ratio"] == pytest.approx(3.0, abs=0.01)

    short = calculate_social_baseline(_history(days=2, per_day=10), NOW - timedelta(days=14), NOW - timedelta(hours=24))
    assert apply_social_baseline(spike_day, short)["mention_volume_ratio"] is None


def test_baseline_ignores_current_window_and_low_relevance():
    """Posts inside the live lookback window or below relevance do not feed the baseline."""
    history = _history(days=4, per_day=5)
    history.append(_post(7000, "BEARISH", -1.0, created=NOW - timedelta(hours=2)))
    history.append(_post(7001, "BEARISH", -1.0, created=NOW - timedelta(hours=48), rel=0.1))
    base = calculate_social_baseline(history, NOW - timedelta(days=14), NOW - timedelta(hours=24))
    assert base["opinion_post_count"] == 20
    assert base["polarity"] > 0


def test_attention_spike_alert_and_reasons():
    """Mention volume >= 2x normal raises ATTENTION_SPIKE with the direction X is leaning."""
    stats = {"mention_volume_ratio": 2.6, "effective_sample_size": 25, "social_baseline": 58.0, "social_polarity_raw": 72.0}
    res = generate_signal_and_explanation(ticker="SPCE", smi=52.0, social_score=64.0, social_stats=stats)
    spike = next(a for a in res["alerts"] if a["type"] == "ATTENTION_SPIKE")
    assert spike["id"] == "SPCE:SIGNAL:ATTENTION_SPIKE"
    assert spike["level"] == "HIGH"
    assert "bullish" in spike["message"]
    assert any("more bullish than this ticker's norm" in r and "raw 72 vs norm 58" in r for r in res["reasons"])
    assert any("mention volume 2.6x" in r for r in res["reasons"])

    mixed = generate_signal_and_explanation(ticker="SPCE", smi=50.0, social_score=50.0,
                                            social_stats={"mention_volume_ratio": 3.0, "effective_sample_size": 25})
    spike_mixed = next(a for a in mixed["alerts"] if a["type"] == "ATTENTION_SPIKE")
    assert spike_mixed["level"] == "WARNING" and "mixed" in spike_mixed["message"]

    calm = generate_signal_and_explanation(ticker="SPCE", smi=50.0, social_score=64.0,
                                           social_stats={"mention_volume_ratio": 1.3, "effective_sample_size": 25})
    assert not any(a["type"] == "ATTENTION_SPIKE" for a in calm["alerts"])


def test_language_filter_uses_x_lang_then_script_fallback():
    """X's detected language decides when present; undetermined or missing codes fall back to the script check."""
    from app.scoring.social import is_scorable_language

    assert is_scorable_language(SocialPostModel(text="$ASTS looks strong", lang="en"))
    assert not is_scorable_language(SocialPostModel(text="Eu acho muito legal a SpaceX", lang="pt"))
    assert not is_scorable_language(SocialPostModel(text="RKLB is great", lang="ja"))
    # Undetermined / missing language: judged by script
    assert is_scorable_language(SocialPostModel(text="$RKLB \U0001F680\U0001F680", lang="und"))
    assert not is_scorable_language(SocialPostModel(text="RKLB 상승 시장이 ATM 완료를 긍정적으로 받아들이기", lang=None))
    assert not is_scorable_language(SocialPostModel(text="半導体・メモリに資金集中 SpaceX", lang="qme"))
    assert is_scorable_language(SocialPostModel(text="Rocket Lab Neutron update", lang=None))


def test_non_english_posts_excluded_from_ssi_and_baseline():
    """Non-English posts are counted as excluded and never vote in the polarity or the baseline."""
    english = [_post(i, "BULLISH", 0.5) for i in range(3)]
    korean = []
    for i in range(5):
        p = _post(100 + i, "BEARISH", -0.9)
        p.lang = "ko"
        korean.append(p)
    res = calculate_social_score(english + korean, analysis_timestamp=NOW)
    assert res["opinion_post_count"] == 3
    assert res["non_english_post_count"] == 5
    assert res["social_score"] == pytest.approx(75.0, abs=0.1)

    only_foreign = calculate_social_score(korean, analysis_timestamp=NOW)
    assert only_foreign["social_score"] is None
    assert only_foreign["non_english_post_count"] == 5

    history = _history(days=4, per_day=5)
    for p in history[:10]:
        p.lang = "ja"
    base = calculate_social_baseline(history, NOW - timedelta(days=14), NOW - timedelta(hours=24))
    assert base["opinion_post_count"] == 10


def test_promotional_spam_patterns():
    """Bot promos are flagged; genuine trading opinions that mention profits or platforms are not."""
    from app.scoring.social import is_promotional_spam

    spam = [
        "I' created a dedicated WhatsApp group for $SATL $SPCE $JOBY shareholders. Reply with \"stock\" to join for free.",
        "$OSRH $ASTS $HTZ . If you hold any of these, pay attention to him; I made $80,000 by following his trades.",
        "Stacking revenue streams across AI education is the move. $RYET quietly building here #blonde $RKLB $SLB",
        "Here are 5 stocks poised for 5x growth: $ASTS $RKLB $SATL. Save this post. Follow me and turn on notifications.",
        "$SPCX BIG LONG Entry Zone: 155 Stop loss: 150 TP: 166 Join Our Official Telegram & Get VIP Access",
        "Watching $ORBS $SATL closely. Real-time market alerts and key levels. WhatsApp https://t.co/x Send \"Hot Stocks\" now",
    ]
    genuine = [
        "I made $4k on $RKLB calls today, Neutron news is a big deal",
        "$ASTS looks strong into the BlueBird launch, adding more shares",
        "Rocket Lab joins the SDA tranche with a new award, huge for $RKLB",
        "Telegram from AT&T: the beta of $ASTS service starts next month",
        "$SPCE turned on the afterburners today, up 12%",
    ]
    for t in spam:
        assert is_promotional_spam(SocialPostModel(text=t)), t
    for t in genuine:
        assert not is_promotional_spam(SocialPostModel(text=t)), t


def test_spam_excluded_from_ssi_attention_and_baseline(monkeypatch):
    """Spam neither votes in the polarity nor counts as mentions; the exclusion can be switched off."""
    from app.config import settings

    genuine = [_post(i, "BEARISH", -0.5) for i in range(3)]
    bots = [_post(50 + i, "BULLISH", 0.95, text=f"Formind ties the AI stack together {i} #bb28 $ASTS $UNH") for i in range(6)]
    res = calculate_social_score(genuine + bots, analysis_timestamp=NOW)
    assert res["spam_post_count"] == 6
    assert res["opinion_post_count"] == 3
    assert res["unique_post_count"] == 3
    assert res["social_score"] == pytest.approx(25.0, abs=0.1)

    history = _history(days=4, per_day=5)
    for p in history[:8]:
        p.text = f"Join our free WhatsApp group for $ASTS alerts {p.tweet_id}"
    base = calculate_social_baseline(history, NOW - timedelta(days=14), NOW - timedelta(hours=24))
    assert base["opinion_post_count"] == 12

    monkeypatch.setattr(settings, "SOCIAL_EXCLUDE_SPAM", False)
    assert calculate_social_score(genuine + bots, analysis_timestamp=NOW)["spam_post_count"] == 0


def test_post_details_match_the_ssi_pass():
    """Every input post gets a status from the same pass that computes the SSI; vote shares of opinions sum to 100."""
    bull = _post(1, "BULLISH", 0.8)
    bear = _post(2, "BEARISH", -0.6, conf=0.5)
    neutral = _post(3, "NEUTRAL", 0.0)
    dup = _post(4, "BULLISH", 0.8, text=bull.text)
    foreign = _post(5, "BULLISH", 0.9, text="RKLB 상승 시장이 ATM 완료를 긍정적으로")
    spam = _post(6, "BULLISH", 0.9, text="Join our free WhatsApp group for $ASTS alerts")
    noise = _post(7, "BULLISH", 0.9, rel=0.1)
    posts = [bull, bear, neutral, dup, foreign, spam, noise]

    details = {}
    res = calculate_social_score(posts, analysis_timestamp=NOW, post_details=details)
    assert len(details) == len(posts)
    assert [details[id(p)]["reason"] for p in (dup, foreign, spam, noise)] == ["duplicate", "language", "spam", "low_relevance"]
    assert all(details[id(p)]["status"] == "counted" for p in (bull, bear, neutral))
    assert details[id(neutral)]["vote_share"] == 0.0
    assert details[id(bull)]["vote_share"] + details[id(bear)]["vote_share"] == pytest.approx(100.0, abs=0.2)
    assert details[id(bull)]["vote_share"] > details[id(bear)]["vote_share"]
    # Passing the dict does not change the score
    assert res["social_score"] == calculate_social_score(posts, analysis_timestamp=NOW)["social_score"]


def test_ticker_api_feed_ranks_by_ssi_weight_and_tags_exclusions():
    """The ticker detail feed lists opinions by SSI weight first, then neutral posts, then excluded posts with reasons."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import SessionLocal
    from app.database.repository import save_social_posts

    now = datetime.now(timezone.utc)
    rows = [
        ("feed_big", "$SATL loading more shares, huge contract coming", "BULLISH", 0.95, 5.0, None),
        ("feed_small", "$SATL looks fine I guess, holding", "BULLISH", 0.92, 0.0, None),
        ("feed_neutral", "$SATL earnings call is on Thursday", "NEUTRAL", 0.1, 0.0, None),
        ("feed_spam", "Join our free WhatsApp group for $SATL alerts", "BULLISH", 0.95, 9.0, None),
        ("feed_ko", "$SATL 오늘 대풀롱으로 마지막 탈출", "BULLISH", 0.95, 0.0, "ko"),
    ]
    db = SessionLocal()
    try:
        db.query(SocialPostModel).filter(SocialPostModel.tweet_id.like("feed_%")).delete(synchronize_session=False)
        db.commit()
        save_social_posts(db, [{
            "tweet_id": tid, "ticker": "SATL", "username": tid, "text": text, "created_at": now - timedelta(minutes=10),
            "sentiment_score": score if label != "NEUTRAL" else 0.0, "sentiment_label": label, "sentiment_confidence": 0.95,
            "relevance_score": 1.0, "engagement_score": eng, "lang": lang, "source": "LIVE"
        } for tid, text, label, score, eng, lang in rows])

        body = TestClient(app).get("/api/tickers/SATL").json()
        feed = [p for p in body["recent_posts"] if p["id"].startswith("feed_")]
        ids = [p["id"] for p in feed]
        assert ids.index("feed_big") < ids.index("feed_small") < ids.index("feed_neutral")
        assert ids.index("feed_neutral") < min(ids.index("feed_spam"), ids.index("feed_ko"))
        by_id = {p["id"]: p for p in feed}
        assert by_id["feed_spam"]["status"] == "excluded" and by_id["feed_spam"]["excluded_reason"] == "spam"
        assert by_id["feed_ko"]["excluded_reason"] == "language"
        assert by_id["feed_big"]["vote_share"] > by_id["feed_small"]["vote_share"] > 0
        assert body["social_stats"]["excluded_post_counts"].get("spam", 0) >= 1
    finally:
        db.query(SocialPostModel).filter(SocialPostModel.tweet_id.like("feed_%")).delete(synchronize_session=False)
        db.commit()
        db.close()
