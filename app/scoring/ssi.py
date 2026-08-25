from typing import Dict, Any, Optional, List
from app.database.models import SocialPostModel
from app.scoring.social import calculate_social_score


def calculate_ssi(
    posts: Optional[List[SocialPostModel]] = None,
    social_score: Optional[float] = None
) -> Dict[str, Any]:
    """
    Computes the Space Sentiment Index (SSI, 0 - 100) representing pure social sentiment from X/Twitter.
    
    If raw posts are provided, applies log1p engagement weighting and exponential recency decay.
    If a pre-calculated social_score is provided, validates and encapsulates it.
    Does NOT include prediction markets, news catalysts, or technical price indicators (those belong to SMI).
    """
    if posts is not None:
        stats = calculate_social_score(posts)
        return {
            "ssi": stats["social_score"],
            "social_score": stats["social_score"],
            "total_posts": stats["total_posts"],
            "relevant_posts": stats["relevant_posts"],
            "bullish_pct": stats["bullish_pct"],
            "neutral_pct": stats["neutral_pct"],
            "bearish_pct": stats["bearish_pct"],
            "weighted_bullish_pct": stats["weighted_bullish_pct"],
            "weighted_neutral_pct": stats["weighted_neutral_pct"],
            "weighted_bearish_pct": stats["weighted_bearish_pct"]
        }

    raw = social_score if social_score is not None else 50.0
    clamped = max(0.0, min(100.0, round(raw, 1)))
    return {
        "ssi": clamped,
        "social_score": clamped,
        "total_posts": 0,
        "relevant_posts": 0,
        "bullish_pct": 0.0,
        "neutral_pct": 0.0,
        "bearish_pct": 0.0,
        "weighted_bullish_pct": 0.0,
        "weighted_neutral_pct": 0.0,
        "weighted_bearish_pct": 0.0
    }

