from typing import List, Dict, Any
from app.database.models import SocialPostModel
from app.config import settings

# Scales log1p engagement: ln(1 + ~22,000) ≈ 10.0 maps high-engagement posts to ~2.0x weight
ENGAGEMENT_SCALE_DIVISOR = getattr(settings, "ENGAGEMENT_SCALE_DIVISOR", 10.0)


def calculate_social_score(posts: List[SocialPostModel]) -> Dict[str, Any]:
    """
    Calculates Social Sentiment Score (0 - 100) and sentiment distribution.
    Weight per post: relevance_score * recency_weight * (1 + engagement_score / ENGAGEMENT_SCALE_DIVISOR)
    """
    if not posts:
        return {
            "social_score": 50.0,
            "total_posts": 0,
            "relevant_posts": 0,
            "bullish_pct": 0.0,
            "neutral_pct": 0.0,
            "bearish_pct": 0.0,
            "weighted_bullish_pct": 0.0,
            "weighted_neutral_pct": 0.0,
            "weighted_bearish_pct": 0.0
        }

    total_count = len(posts)
    relevant_posts = [p for p in posts if p.relevance_score >= 0.40]
    
    if not relevant_posts:
        relevant_posts = posts  # Fallback to all if threshold filters all

    bullish_cnt = sum(1 for p in relevant_posts if p.sentiment_label == "BULLISH")
    bearish_cnt = sum(1 for p in relevant_posts if p.sentiment_label == "BEARISH")
    neutral_cnt = sum(1 for p in relevant_posts if p.sentiment_label == "NEUTRAL")

    rel_total = len(relevant_posts)
    bullish_pct = round(100.0 * bullish_cnt / rel_total, 1)
    bearish_pct = round(100.0 * bearish_cnt / rel_total, 1)
    neutral_pct = round(100.0 * neutral_cnt / rel_total, 1)

    # Weighted calculation
    weighted_sentiment_sum = 0.0
    weight_total = 0.0

    w_bull = 0.0
    w_bear = 0.0
    w_neu = 0.0

    for p in relevant_posts:
        w = p.relevance_score * p.recency_weight * (1.0 + (p.engagement_score or 0.0) / ENGAGEMENT_SCALE_DIVISOR)
        weight_total += w
        weighted_sentiment_sum += p.sentiment_score * w

        if p.sentiment_label == "BULLISH":
            w_bull += w
        elif p.sentiment_label == "BEARISH":
            w_bear += w
        else:
            w_neu += w

    if weight_total > 0:
        norm_sentiment = weighted_sentiment_sum / weight_total
        weighted_bull_pct = round(100.0 * w_bull / weight_total, 1)
        weighted_bear_pct = round(100.0 * w_bear / weight_total, 1)
        weighted_neu_pct = round(100.0 * w_neu / weight_total, 1)
    else:
        norm_sentiment = 0.0
        weighted_bull_pct = bullish_pct
        weighted_bear_pct = bearish_pct
        weighted_neu_pct = neutral_pct

    # Convert normalized sentiment (-1..+1) to 0..100 score
    raw_social_score = 50.0 + (50.0 * norm_sentiment)
    social_score = max(0.0, min(100.0, round(raw_social_score, 1)))

    return {
        "social_score": social_score,
        "total_posts": total_count,
        "relevant_posts": rel_total,
        "bullish_pct": bullish_pct,
        "neutral_pct": neutral_pct,
        "bearish_pct": bearish_pct,
        "weighted_bullish_pct": weighted_bull_pct,
        "weighted_neutral_pct": weighted_neu_pct,
        "weighted_bearish_pct": weighted_bear_pct
    }
