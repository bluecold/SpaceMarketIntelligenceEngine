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




