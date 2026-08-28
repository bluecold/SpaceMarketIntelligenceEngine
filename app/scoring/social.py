import re
from typing import List, Dict, Any, Optional
from app.database.models import SocialPostModel
from app.config import settings

# Scales log1p engagement: ln(1 + ~22,000) ≈ 10.0 maps high-engagement posts to ~2.0x weight
ENGAGEMENT_SCALE_DIVISOR = getattr(settings, "ENGAGEMENT_SCALE_DIVISOR", 10.0)


def normalize_text_for_dedup(text: str) -> str:
    """Normalize text by stripping RT prefixes, URLs, user mentions, whitespace, and punctuation."""
    t = text.lower()
    t = re.sub(r'^rt\s+@[a-z0-9_]+:\s*', '', t)
    t = re.sub(r'https?://\S+', '', t)
    t = re.sub(r'@[a-z0-9_]+', '', t)
    t = re.sub(r'[^\w\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def calculate_social_score(posts: List[SocialPostModel]) -> Dict[str, Any]:
    """
    Calculates Social Sentiment Score (0 - 100) and sentiment distribution.
    Weight per post: relevance_score * recency_weight * (1 + engagement_score / ENGAGEMENT_SCALE_DIVISOR).
    Deduplicates posts by normalized text and enforces settings.SOCIAL_MIN_RELEVANCE.
    """
    if not posts:
        return {
            "social_score": None,
            "total_posts": 0,
            "relevant_posts": 0,
            "bullish_pct": 0.0,
            "neutral_pct": 0.0,
            "bearish_pct": 0.0,
            "weighted_bullish_pct": 0.0,
            "weighted_neutral_pct": 0.0,
            "weighted_bearish_pct": 0.0
        }

    min_rel = getattr(settings, "SOCIAL_MIN_RELEVANCE", 0.40)
    relevant_posts = [
        p for p in posts
        if getattr(p, "relevance_score", 1.0) is not None and getattr(p, "relevance_score", 1.0) >= min_rel
    ]
    
    if not relevant_posts:
        return {
            "social_score": None,
            "total_posts": 0,
            "relevant_posts": 0,
            "bullish_pct": 0.0,
            "neutral_pct": 0.0,
            "bearish_pct": 0.0,
            "weighted_bullish_pct": 0.0,
            "weighted_neutral_pct": 0.0,
            "weighted_bearish_pct": 0.0
        }

    # Group and deduplicate posts by normalized text while accumulating engagement
    unique_posts_map: Dict[str, Dict[str, Any]] = {}
    for p in relevant_posts:
        norm_key = normalize_text_for_dedup(p.text) if hasattr(p, "text") and p.text else ""
        if not norm_key:
            norm_key = str(getattr(p, "tweet_id", id(p)))

        p_eng = getattr(p, "engagement_score", 0.0) or 0.0
        p_rec = getattr(p, "recency_weight", 1.0) or 1.0
        p_rel = getattr(p, "relevance_score", 1.0) or 1.0
        p_sent = getattr(p, "sentiment_score", 0.0) or 0.0
        p_label = getattr(p, "sentiment_label", "NEUTRAL") or "NEUTRAL"
        p_conf = getattr(p, "sentiment_confidence", 0.70) or 0.70

        if norm_key not in unique_posts_map:
            unique_posts_map[norm_key] = {
                "sentiment_score": p_sent,
                "sentiment_label": p_label,
                "sentiment_confidence": p_conf,
                "relevance_score": p_rel,
                "recency_weight": p_rec,
                "engagement_score": p_eng,
                "duplicate_count": 1
            }
        else:
            entry = unique_posts_map[norm_key]
            entry["duplicate_count"] += 1
            entry["engagement_score"] = max(entry["engagement_score"], p_eng) + 0.5 * p_eng
            entry["recency_weight"] = max(entry["recency_weight"], p_rec)
            entry["sentiment_confidence"] = max(entry.get("sentiment_confidence", 0.70), p_conf)

    deduped_items = list(unique_posts_map.values())
    rel_total = len(deduped_items)

    bullish_cnt = sum(1 for item in deduped_items if item["sentiment_label"] == "BULLISH")
    bearish_cnt = sum(1 for item in deduped_items if item["sentiment_label"] == "BEARISH")
    neutral_cnt = sum(1 for item in deduped_items if item["sentiment_label"] == "NEUTRAL")

    bullish_pct = round(100.0 * bullish_cnt / rel_total, 1)
    bearish_pct = round(100.0 * bearish_cnt / rel_total, 1)
    neutral_pct = round(100.0 * neutral_cnt / rel_total, 1)

    # Weighted calculation
    weighted_sentiment_sum = 0.0
    weight_total = 0.0

    w_bull = 0.0
    w_bear = 0.0
    w_neu = 0.0

    for item in deduped_items:
        conf = item.get("sentiment_confidence", 0.70)
        w = item["relevance_score"] * item["recency_weight"] * conf * (1.0 + item["engagement_score"] / ENGAGEMENT_SCALE_DIVISOR)
        weight_total += w
        weighted_sentiment_sum += item["sentiment_score"] * w

        if item["sentiment_label"] == "BULLISH":
            w_bull += w
        elif item["sentiment_label"] == "BEARISH":
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
        "total_posts": rel_total,
        "relevant_posts": rel_total,
        "bullish_pct": bullish_pct,
        "neutral_pct": neutral_pct,
        "bearish_pct": bearish_pct,
        "weighted_bullish_pct": weighted_bull_pct,
        "weighted_neutral_pct": weighted_neu_pct,
        "weighted_bearish_pct": weighted_bear_pct
    }


def apply_bayesian_shrinkage(
    score: float,
    sample_size: Optional[int],
    prior: float = 50.0,
    min_reliable_sample: int = 10
) -> float:
    """
    Applies Bayesian credibility shrinkage towards a neutral prior (default 50.0)
    for small sample sizes (< min_reliable_sample).
    Formula:
        effective_score = prior + (score - prior) * min(1.0, max(0.1, N / min_reliable_sample))
    """
    if sample_size is None or sample_size >= min_reliable_sample:
        return score
    if sample_size <= 0:
        return prior
    credibility = min(1.0, max(0.1, sample_size / float(min_reliable_sample)))
    return round(prior + (score - prior) * credibility, 2)
