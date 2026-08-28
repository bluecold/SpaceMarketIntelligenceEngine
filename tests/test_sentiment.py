from app.sentiment.classifier import HeuristicSentimentClassifier
from app.sentiment.weighting import calculate_engagement_score, calculate_recency_weight, calculate_relevance_score


def test_heuristic_classifier_bullish():
    classifier = HeuristicSentimentClassifier()
    res = classifier.analyze("ASTSpaceMobile $ASTS satellite milestone launch contract win!")
    assert res.label == "BULLISH"
    assert res.score > 0.20


def test_heuristic_classifier_bearish():
    classifier = HeuristicSentimentClassifier()
    res = classifier.analyze("$SPCE stock price dropping after cash burn dilution risk warning")
    assert res.label == "BEARISH"
    assert res.score < -0.20


def test_engagement_log_scaling():
    # Test log scaling prevents viral post dominance
    eng1 = calculate_engagement_score(likes=10, reposts=2, replies=1, views=500)
    eng2 = calculate_engagement_score(likes=1000, reposts=500, replies=200, views=50000)
    
    assert eng1 > 0
    assert eng2 > eng1
    assert eng2 < 10.0  # Log scale dampens gigantic viral numbers


def test_relevance_score():
    rel_exact = calculate_relevance_score("$ASTS BlueBird satellite launch", "ASTS", ["$ASTS", "AST SpaceMobile"])
    assert rel_exact == 1.0

    rel_standalone = calculate_relevance_score("ASTS satellite launch", "ASTS", ["$ASTS", "AST SpaceMobile"])
    assert rel_standalone == 0.75

    rel_unrelated = calculate_relevance_score("Random tweet about coffee and weather", "ASTS", ["$ASTS"])
    assert rel_unrelated <= 0.10


def test_calculate_news_score_empty_returns_none():
    """Validates that empty news items returns None for news_score (no fake 50s)."""
    from app.sentiment.weighting import calculate_news_score
    res = calculate_news_score([])
    assert res["news_score"] is None
    assert res["total_news"] == 0
    assert res["bullish_news_pct"] == 0.0
    assert res["bearish_news_pct"] == 0.0


def test_calculate_news_score_with_bullish_items():
    from datetime import datetime, timezone
    from app.sentiment.weighting import calculate_news_score
    from app.database.models import NewsItemModel

    news = [
        NewsItemModel(
            ticker="ASTS",
            title="AST SpaceMobile Receives Landmark FCC License",
            url="https://example.com/news1",
            source="SpaceNews",
            published_at=datetime.now(timezone.utc),
            sentiment_score=0.8,
            sentiment_label="BULLISH",
            relevance_score=1.0,
            catalyst_importance="CRITICAL"
        )
    ]
    res = calculate_news_score(news)
    assert res["news_score"] is not None
    assert res["news_score"] > 70.0
    assert res["total_news"] == 1
    assert res["bullish_news_pct"] == 100.0


def test_detect_multiple_catalysts_concurrent():
    from app.sentiment.weighting import detect_catalysts
    text = "ASTS announces capital raise dilution after payload launch delay"
    cats = detect_catalysts(text)
    
    cat_names = [c["category"] for c in cats]
    assert "CAPITAL_RAISE" in cat_names
    assert "LAUNCH_DELAY" in cat_names
    assert len(cats) >= 2


def test_detect_catalyst_importance_priority():
    from app.sentiment.weighting import detect_catalyst
    # Text contains both a MEDIUM milestone and a CRITICAL government contract
    text = "Rocket Lab completes hot fire engine test and wins landmark NASA government contract"
    cat_type, cat_dir, cat_imp = detect_catalyst(text)
    
    assert cat_type == "GOVERNMENT_CONTRACT"
    assert cat_imp == "CRITICAL"
    assert cat_dir == "BULLISH"


def test_heuristic_classifier_negation_inversion():
    classifier = HeuristicSentimentClassifier()

    # 1. Negated Bullish phrases should invert to BEARISH
    res1 = classifier.analyze("I am not bullish on this stock, no launch confirmation yet.")
    assert res1.label == "BEARISH"
    assert res1.score < 0.0

    res2 = classifier.analyze("Failed deployment and lack of revenue growth")
    assert res2.label == "BEARISH"
    assert res2.score < 0.0

    # 2. Negated Bearish phrases should invert to BULLISH
    res3 = classifier.analyze("Management confirms no dilution and not selling any shares.")
    assert res3.label == "BULLISH"
    assert res3.score > 0.0

    # 3. Affirmative idioms (e.g. 'no doubt') should NOT invert following bullish words
    res4 = classifier.analyze("No doubt about it, this is a great rocket launch and milestone contract!")
    assert res4.label == "BULLISH"
    assert res4.score > 0.0

    # 4. Punctuation boundary prevents distant negation crossing clauses
    res5 = classifier.analyze("This is no joke, massive launch success today.")
    assert res5.label == "BULLISH"
    assert res5.score > 0.0


def test_news_score_respects_relevance_weighting():
    from app.sentiment.weighting import calculate_news_score
    from datetime import datetime, timezone
    from collections import namedtuple

    MockNews = namedtuple("MockNews", ["sentiment_score", "sentiment_label", "published_at", "relevance_score", "catalyst_importance"])

    now = datetime.now(timezone.utc)
    # High relevance (+0.8 bullish with relevance 1.0) vs Low relevance (-0.8 bearish with relevance 0.2)
    news = [
        MockNews(sentiment_score=0.8, sentiment_label="BULLISH", published_at=now, relevance_score=1.0, catalyst_importance="MEDIUM"),
        MockNews(sentiment_score=-0.8, sentiment_label="BEARISH", published_at=now, relevance_score=0.2, catalyst_importance="MEDIUM"),
    ]

    res = calculate_news_score(news)
    assert res["news_score"] is not None
    # Score should be significantly bullish (> 70) because the bullish news had 5x higher relevance
    assert res["news_score"] > 70.0


def test_high_keyword_disambiguation_false_positives():
    """
    Verify that phrases like 'high risk', 'high cash burn', or 'all-time high short interest'
    are properly classified as BEARISH without false positive bullish hits from 'high'.
    """
    classifier = HeuristicSentimentClassifier()

    # 1. High risk & high cash burn (must be BEARISH)
    res_risk = classifier.analyze("ASTS faces high risk and high cash burn ahead of commercial service.")
    assert res_risk.label == "BEARISH"
    assert res_risk.score < 0.0

    # 2. Short interest at all-time high (must be BEARISH)
    res_short = classifier.analyze("RKLB short interest hits an all-time high amid market selloff.")
    assert res_short.label == "BEARISH"
    assert res_short.score < 0.0

    # 3. All-time high in price / stock context (must be BULLISH)
    res_ath = classifier.analyze("ASTS reaches an all-time high after successful commercial satellite launch milestone.")
    assert res_ath.label == "BULLISH"
    assert res_ath.score > 0.0


def test_neutral_domain_nouns_not_bullish():
    """
    Verify that domain nouns (rocket, satellite, launch, nasa, fcc) are NOT treated as bullish keywords,
    and factual descriptive sentences score NEUTRAL rather than degenerate +1.0.
    """
    classifier = HeuristicSentimentClassifier()

    # 1. Factual space activity post (must be NEUTRAL, score = 0.0)
    res_factual = classifier.analyze("SpaceX launches another Falcon 9 rocket with 20 Starlink satellites for NASA.")
    assert res_factual.label == "NEUTRAL"
    assert res_factual.score == 0.0

    # 2. Polar bullish post with tanh saturation (score ~ 0.46 for 1 hit, not 1.0)
    res_surge = classifier.analyze("Rocket Lab stock surges following earnings release.")
    assert res_surge.label == "BULLISH"
    assert 0.40 <= res_surge.score <= 0.60, f"Expected smooth tanh score ~0.46, got {res_surge.score}"

    # 3. Multi-hit bullish conviction
    res_multi = classifier.analyze("ASTS wins landmark contract, surges to all-time high with massive revenue growth.")
    assert res_multi.label == "BULLISH"
    assert res_multi.score >= 0.80


def test_detect_catalysts_word_boundaries_and_bearish_priority():
    """
    Verify that:
    1. Substrings like 'Seattle', 'battery', 'dodge' do NOT match 'att' or 'dod'.
    2. Exact word 'att' or 'dod' DOES match.
    3. 'launch abort' prioritizes BEARISH LAUNCH_DELAY over BULLISH LAUNCH.
    """
    from app.sentiment.weighting import detect_catalysts, detect_catalyst

    # 1. False substring matches must NOT trigger catalysts
    text_substrings = "The engineer from Seattle replaced the battery and attempted to dodge the obstacle in the carrier narrative."
    cats_false = detect_catalysts(text_substrings)
    assert len(cats_false) == 0, f"Expected 0 catalysts from false substrings, got {cats_false}"

    # 2. Legitimate acronyms with word boundaries DO trigger
    text_legit = "ASTS signs definitive partnership with AT&T and receives major DoD contract."
    cats_legit = detect_catalysts(text_legit)
    cat_names = [c["category"] for c in cats_legit]
    assert "GOVERNMENT_CONTRACT" in cat_names

    # 3. Anomaly / Launch Abort must prioritize BEARISH LAUNCH_DELAY over BULLISH LAUNCH
    text_abort = "Rocket Lab suffers launch abort after detecting engine anomaly during countdown."
    top_cat, top_dir, top_imp = detect_catalyst(text_abort)
    assert top_cat == "LAUNCH_DELAY"
    assert top_dir == "BEARISH"


def test_signal_reasons_deduplicates_and_ranks_catalysts():
    """
    Verify that generate_signal_and_explanation:
    1. Deduplicates multiple instances of the same catalyst category.
    2. Ranks CRITICAL catalysts from later items ahead of repetitive HIGH/MEDIUM items.
    3. Never prints duplicate lines for the same category.
    """
    from app.scoring.signal import generate_signal_and_explanation

    # Simulate 10 duplicate SATELLITE_DEPLOYMENT items from social posts followed by 1 CRITICAL GOVERNMENT_CONTRACT from news
    raw_catalysts = [{"category": "SATELLITE_DEPLOYMENT", "direction": "BULLISH", "importance": "HIGH"}] * 10
    raw_catalysts.append({"category": "GOVERNMENT_CONTRACT", "direction": "BULLISH", "importance": "CRITICAL"})
    raw_catalysts.append({"category": "CAPITAL_RAISE", "direction": "BEARISH", "importance": "HIGH"})

    res = generate_signal_and_explanation(
        ticker="ASTS",
        smi=75.0,
        social_score=75.0,
        catalysts_found=raw_catalysts
    )

    reasons = res["reasons"]
    catalyst_reasons = [r for r in reasons if "catalyst" in r.lower()]

    # 1. Must contain CRITICAL Government Contract at the top
    assert len(catalyst_reasons) == 3
    assert "[CRITICAL] Government Contract" in catalyst_reasons[0]

    # 2. Must not repeat Satellite Deployment multiple times
    sat_reasons = [r for r in catalyst_reasons if "Satellite Deployment" in r]
    assert len(sat_reasons) == 1

    # 3. Must contain Capital Raise
    cap_reasons = [r for r in catalyst_reasons if "Capital Raise" in r]
    assert len(cap_reasons) == 1


def test_news_score_below_relevance_threshold_returns_none():
    """Verify that calculate_news_score returns None when all news items are below NEWS_MIN_RELEVANCE."""
    from datetime import datetime, timezone
    from collections import namedtuple
    from app.sentiment.weighting import calculate_news_score

    MockNews = namedtuple("MockNews", ["sentiment_score", "sentiment_label", "published_at", "relevance_score", "catalyst_importance"])
    now = datetime.now(timezone.utc)

    # 3 news items with low relevance (relevance = 0.10, threshold is 0.40)
    low_rel_news = [
        MockNews(sentiment_score=0.9, sentiment_label="BULLISH", published_at=now, relevance_score=0.10, catalyst_importance="LOW"),
        MockNews(sentiment_score=-0.8, sentiment_label="BEARISH", published_at=now, relevance_score=0.15, catalyst_importance="LOW"),
    ]

    res = calculate_news_score(low_rel_news)
    assert res["news_score"] is None
    assert res["total_news"] == 0


def test_rss_news_pubdate_timezone_conversion():
    """Verify that RSS pubDate strings with timezones are converted to naive UTC correctly."""
    from email.utils import parsedate_to_datetime
    from datetime import timezone

    # 1. PubDate with Eastern Daylight Time (-0400)
    pub_str_edt = "Fri, 28 Aug 2026 10:00:00 -0400"
    dt_edt = parsedate_to_datetime(pub_str_edt)
    utc_dt = dt_edt.astimezone(timezone.utc).replace(tzinfo=None)
    # 10:00:00 -0400 is 14:00:00 UTC
    assert utc_dt.hour == 14
    assert utc_dt.day == 28

    # 2. PubDate with Tokyo Time (+0900)
    pub_str_jst = "Fri, 28 Aug 2026 05:00:00 +0900"
    dt_jst = parsedate_to_datetime(pub_str_jst)
    utc_jst = dt_jst.astimezone(timezone.utc).replace(tzinfo=None)
    # 05:00:00 +0900 on Aug 28 is 20:00:00 UTC on Aug 27
    assert utc_jst.hour == 20
    assert utc_jst.day == 27










