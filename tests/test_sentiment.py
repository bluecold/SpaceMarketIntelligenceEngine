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
