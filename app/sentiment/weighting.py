import math
import re
from datetime import datetime
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
    now = reference_now or datetime.utcnow()
    age_seconds = max(0.0, (now - created_at).total_seconds())
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


def detect_catalyst(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Detect potential market catalysts, direction and importance.
    Returns (catalyst_category, direction, importance)
    """
    clean_text = text.lower()
    
    for category, config in CATALYST_CONFIG.items():
        for kw in config["keywords"]:
            if kw in clean_text:
                return category, config["direction"], config["importance"]
                    
    return None, None, None


def calculate_news_score(news_items: List[Any]) -> Dict[str, Any]:
    """
    Computes aggregated News Score (0 to 100) from recent news articles.
    """
    if not news_items:
        return {
            "news_score": 50.0,
            "total_news": 0,
            "bullish_news_pct": 33.3,
            "bearish_news_pct": 33.3
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
        w = item.relevance_score * rec_w * imp_mult
        
        total_weight += w
        weighted_sentiment_sum += item.sentiment_score * w

        if item.sentiment_label == "BULLISH":
            bull_cnt += 1
        elif item.sentiment_label == "BEARISH":
            bear_cnt += 1

    if total_weight > 0:
        norm_sent = weighted_sentiment_sum / total_weight
    else:
        norm_sent = 0.0

    raw_news_score = 50.0 + (50.0 * norm_sent)
    news_score = max(0.0, min(100.0, round(raw_news_score, 1)))

    n_total = len(news_items)
    return {
        "news_score": news_score,
        "total_news": n_total,
        "bullish_news_pct": round(100.0 * bull_cnt / n_total, 1),
        "bearish_news_pct": round(100.0 * bear_cnt / n_total, 1)
    }
