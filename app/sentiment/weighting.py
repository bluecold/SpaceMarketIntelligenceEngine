import math
import re
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any

CATALYST_CONFIG = {
    "SATELLITE_DEPLOYMENT": {
        "keywords": ["satellite deployment", "orbit", "deployed", "constellation", "fcc license", "direct to cell"],
        "direction": "BULLISH",
        "importance": "HIGH"
    },
    "LAUNCH": {
        "keywords": ["launch", "test launch", "boca chica", "electron rocket", "neutron rocket", "starship", "lift off"],
        "direction": "BULLISH",
        "importance": "HIGH"
    },
    "GOVERNMENT_CONTRACT": {
        "keywords": ["government contract", "nasa", "space force", "dod", "pentagon", "defense contract", "sda contract"],
        "direction": "BULLISH",
        "importance": "CRITICAL"
    },
    "PARTNERSHIP": {
        "keywords": ["partnership", "mno", "partner", "agreement", "collaboration", "verizon", "att"],
        "direction": "BULLISH",
        "importance": "HIGH"
    },
    "REVENUE": {
        "keywords": ["revenue", "earnings", "quarterly", "sales", "arr", "guidance beat"],
        "direction": "BULLISH",
        "importance": "MEDIUM"
    },
    "TECHNICAL_MILESTONE": {
        "keywords": ["hot fire", "engine test", "fairing", "stage 1", "milestone", "payload", "qualification"],
        "direction": "BULLISH",
        "importance": "MEDIUM"
    },
    "CAPITAL_RAISE": {
        "keywords": ["dilution", "offering", "cash burn", "capital raise", "debt", "shares offering", "direct offering"],
        "direction": "BEARISH",
        "importance": "HIGH"
    },
    "LAUNCH_DELAY": {
        "keywords": ["delay", "delayed", "rescheduled", "postponed", "launch abort", "anomaly"],
        "direction": "BEARISH",
        "importance": "HIGH"
    },
    "ANALYST_DOWNGRADE": {
        "keywords": ["downgrade", "underweight", "sell rating", "price target cut"],
        "direction": "BEARISH",
        "importance": "MEDIUM"
    }
}


def calculate_engagement_score(likes: int, reposts: int, replies: int, views: int) -> float:
    """
    Calculate log-scaled engagement score:
    engagement = log1p(likes + 2*reposts + 1.5*replies + views/1000)
    """
    normalized_views = float(views) / 1000.0 if views else 0.0
    weighted_sum = float(likes) + 2.0 * float(reposts) + 1.5 * float(replies) + normalized_views
    return math.log1p(weighted_sum)


def calculate_recency_weight(created_at: datetime, reference_now: Optional[datetime] = None, half_life_hours: float = 12.0) -> float:
    """
    Exponential decay weight based on age in hours.
    weight = exp(-lambda * age_hours)
    """
    created_at_utc = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at.astimezone(timezone.utc)
    
    if reference_now is not None:
        now_utc = reference_now.replace(tzinfo=timezone.utc) if reference_now.tzinfo is None else reference_now.astimezone(timezone.utc)
    else:
        now_utc = datetime.now(timezone.utc)

    age_seconds = max(0.0, (now_utc - created_at_utc).total_seconds())
    age_hours = age_seconds / 3600.0
    
    decay_lambda = math.log(2.0) / half_life_hours
    weight = math.exp(-decay_lambda * age_hours)
    return round(weight, 4)


def calculate_relevance_score(text: str, symbol: str, aliases: List[str]) -> float:
    """
    Calculates relevance score from 0.0 to 1.0 based on keyword match.
    """
    clean_text = text.lower()
    
    # Exact ticker match with $ prefix
    if f"${symbol.lower()}" in clean_text:
        return 1.0
        
    # Check aliases
    for alias in aliases:
        if alias.lower() in clean_text:
            return 0.85
            
    # Standalone symbol match
    if re.search(r'\b' + re.escape(symbol.lower()) + r'\b', clean_text):
        return 0.75

    # Secondary space terms
    space_generic = ["satellite", "orbit", "space", "launch", "rocket"]
    if any(g in clean_text for g in space_generic):
        return 0.40

    return 0.10


IMPORTANCE_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def detect_catalysts(text: str) -> List[Dict[str, str]]:
    """
    Detect all matching market catalysts, their directions and importances in the text.
    Returns a list of dicts sorted by importance: [{"category": cat, "direction": dir, "importance": imp, "keyword": kw}, ...]
    """
    clean_text = text.lower()
    matches: List[Dict[str, str]] = []
    seen_categories = set()

    for category, config in CATALYST_CONFIG.items():
        for kw in config["keywords"]:
            if kw in clean_text:
                if category not in seen_categories:
                    matches.append({
                        "category": category,
                        "direction": config["direction"],
                        "importance": config["importance"],
                        "keyword": kw
                    })
                    seen_categories.add(category)
                break

    # Sort matches by importance hierarchy (CRITICAL first, then HIGH, etc.)
    matches.sort(key=lambda c: IMPORTANCE_RANK.get(c["importance"], 99))
    return matches


def detect_catalyst(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Detect highest-priority market catalyst in the text based on importance hierarchy.
    Returns (catalyst_category, direction, importance)
    """
    all_cats = detect_catalysts(text)
    if not all_cats:
        return None, None, None
    top = all_cats[0]
    return top["category"], top["direction"], top["importance"]


def calculate_news_score(news_items: List[Any]) -> Dict[str, Any]:
    """
    Computes aggregated News Score (0 to 100) from recent news articles.
    Returns news_score = None when no news items exist (Adaptive weight normalization).
    """
    if not news_items:
        return {
            "news_score": None,
            "total_news": 0,
            "bullish_news_pct": 0.0,
            "bearish_news_pct": 0.0
        }

    total_weight = 0.0
    weighted_sentiment_sum = 0.0
    bull_cnt = 0
    bear_cnt = 0

    for item in news_items:
        # Importance weighting multiplier
        imp_mult = 1.0
        if getattr(item, 'catalyst_importance', None) == "CRITICAL":
            imp_mult = 2.0
        elif getattr(item, 'catalyst_importance', None) == "HIGH":
            imp_mult = 1.5

        # Recency decay for news (half-life 24 hours)
        rec_w = calculate_recency_weight(item.published_at, half_life_hours=24.0)
        rel_score = getattr(item, 'relevance_score', 1.0)
        w = rel_score * rec_w * imp_mult
        
        total_weight += w
        weighted_sentiment_sum += getattr(item, 'sentiment_score', 0.0) * w

        if getattr(item, 'sentiment_label', None) == "BULLISH":
            bull_cnt += 1
        elif getattr(item, 'sentiment_label', None) == "BEARISH":
            bear_cnt += 1

    if total_weight <= 0:
        return {
            "news_score": None,
            "total_news": len(news_items),
            "bullish_news_pct": 0.0,
            "bearish_news_pct": 0.0
        }

    norm_sent = weighted_sentiment_sum / total_weight
    raw_news_score = 50.0 + (50.0 * norm_sent)
    news_score = max(0.0, min(100.0, round(raw_news_score, 1)))

    n_total = len(news_items)
    return {
        "news_score": news_score,
        "total_news": n_total,
        "bullish_news_pct": round(100.0 * bull_cnt / n_total, 1),
        "bearish_news_pct": round(100.0 * bear_cnt / n_total, 1)
    }
