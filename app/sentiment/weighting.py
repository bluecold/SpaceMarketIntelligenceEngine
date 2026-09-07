import math
import re
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
from app.config import settings

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
    "FAA_APPROVAL": {
        "keywords": ["faa license", "faa approval", "environmental review", "launch license", "cleared for launch"],
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
    "LAUNCH_FAILURE": {
        "keywords": [
            "launch failure", "failed launch", "explosion", "exploded", "exploding",
            "rud", "rapid unscheduled disassembly", "lost vehicle", "mission failure",
            "payload lost", "booster lost", "crash", "crashed", "engine failure"
        ],
        "direction": "BEARISH",
        "importance": "CRITICAL"
    },
    "LAUNCH_DELAY": {
        "keywords": ["delay", "delayed", "rescheduled", "postponed", "launch abort", "anomaly", "scrubbed", "scrub", "grounded", "hold"],
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

# Semantic entity and action lexicons for contextual catalyst resolution
GOV_AGENCIES = ["nasa", "space force", "dod", "pentagon", "sda", "usaf", "darpa", "defense"]
CONTRACT_TERMS = ["contract", "contracts", "agreement", "agreements", "task order", "award", "awards", "awarded", "procurement", "grant", "deal"]

CANCELLATION_PATTERNS = [
    r"\bcancel(s|ed|led|ing|ling|lation)?\b",
    r"\bterminate(s|d|ing|tion)?\b",
    r"\brevoke(s|d|ing)?\b",
    r"\bloss\b",
    r"\blost\b",
    r"\bloses\b",
    r"\bdrop(s|ped|ping)?\b",
    r"\bscrap(s|ped|ping)?\b",
    r"\breject(s|ed|ing)?\b",
    r"\bdeni(es|ed)\b",
    r"\bgrounds?\b"
]

HYPOTHETICAL_PATTERNS = [
    r"^\s*(?:what\s+if|could|would|might|hypothetically)\b",
    r"\b(?:what\s+if|speculation:|rumor:|unconfirmed:|hypothetical)\b"
]

HISTORICAL_PATTERNS = [
    r"\b(?:in\s+(?:19\d\d|20[01]\d|202[0-3])|years\s+ago|historically|in\s+the\s+past|back\s+in\s+(?:19\d\d|20\d\d)|anniversary\s+of)\b"
]


def detect_catalysts(
    text: str,
    ticker: Optional[str] = None,
    include_hypothetical: bool = True,
    include_historical: bool = True
) -> List[Dict[str, Any]]:
    """
    Detects all matching market catalysts, decoupling entity mentions from event predicates,
    resolving negation, cancellation, competitor rivalry, and filtering out hypothetical/historical noise.
    Returns a list of dicts sorted by importance hierarchy:
    [{"category": cat, "direction": dir, "importance": imp, "keyword": kw, ...}, ...]
    """
    clean_text = text.lower()
    matches: List[Dict[str, Any]] = []
    seen_categories = set()

    # 1. Detect if the text represents a purely speculative/hypothetical question
    is_hypo = any(re.search(p, clean_text) for p in HYPOTHETICAL_PATTERNS) or (
        clean_text.endswith("?") and any(re.search(rf"\b{w}\b", clean_text) for w in ["what if", "could", "might", "would", "is it possible"])
    )

    # 2. Detect if the text is historical retrospect (e.g. event from years ago)
    is_hist = any(re.search(p, clean_text) for p in HISTORICAL_PATTERNS)

    # 3. Detect cancellation, revocation, denial, or termination action verbs
    has_cancellation = any(re.search(p, clean_text) for p in CANCELLATION_PATTERNS)

    # 4. Detect inter-company competitor rivalry (e.g. "NASA selects SpaceX over Rocket Lab")
    m_rival = (
        re.search(r'\b(?:wins?|awarded|selects?|selected|picks?|picked|choos(?:es|ing)|chosen)\s+(?:[a-z0-9\s]+?\s+)?(?:over|instead of|against|beating)\s+([a-z0-9\s]+?)(?:\s+(?:for|on|in|to|with)\b|[.,;]|$)', clean_text)
        or re.search(r'\b([a-z0-9\s]+?)\s+(?:beats?|defeats?|outcompetes?)\s+([a-z0-9\s]+?)(?:\s+(?:for|on|in|to|with)\b|[.,;]|$)', clean_text)
    )
    if m_rival:
        defeated = m_rival.group(1).strip()
        is_target_defeated = False
        if ticker:
            tick_clean = ticker.lower()
            if tick_clean in defeated or (tick_clean == "rklb" and "rocket lab" in defeated) or (tick_clean == "asts" and ("ast" in defeated or "spacemobile" in defeated)):
                is_target_defeated = True
        else:
            # Without explicit ticker, the defeated party in the rivalry experienced a contract/award loss
            is_target_defeated = True

        if is_target_defeated:
            matches.append({
                "category": "GOVERNMENT_CONTRACT",
                "direction": "BEARISH",
                "importance": "CRITICAL",
                "keyword": f"competitor selected over {defeated}"
            })
            seen_categories.add("GOVERNMENT_CONTRACT")

    # 5. Government contract detection with contextual entity & cancellation decoupling
    has_gov_entity = any(re.search(rf"\b{re.escape(g)}\b", clean_text) for g in GOV_AGENCIES)
    has_contract_noun = any(re.search(rf"\b{re.escape(c)}\b", clean_text) for c in CONTRACT_TERMS)
    has_direct_gov_phrase = any(re.search(rf"\b{re.escape(p)}\b", clean_text) for p in ["government contract", "defense contract", "sda contract"])

    has_partner_kw = any(re.search(rf"\b{re.escape(kw)}\b", clean_text) for kw in CATALYST_CONFIG["PARTNERSHIP"]["keywords"])

    if "GOVERNMENT_CONTRACT" not in seen_categories:
        is_gov = (
            has_direct_gov_phrase
            or (has_gov_entity and (has_contract_noun or has_cancellation))
            or (has_contract_noun and has_cancellation and not has_partner_kw)
        )
        if is_gov:
            if has_cancellation:
                matches.append({
                    "category": "GOVERNMENT_CONTRACT",
                    "direction": "BEARISH",
                    "importance": "CRITICAL",
                    "keyword": "cancels contract"
                })
                seen_categories.add("GOVERNMENT_CONTRACT")
            else:
                matches.append({
                    "category": "GOVERNMENT_CONTRACT",
                    "direction": "BULLISH",
                    "importance": "CRITICAL",
                    "keyword": "government contract"
                })
                seen_categories.add("GOVERNMENT_CONTRACT")

    # 6. Partnership detection with cancellation handling
    if "PARTNERSHIP" not in seen_categories:
        has_partnership_kw = any(re.search(rf"\b{re.escape(kw)}\b", clean_text) for kw in CATALYST_CONFIG["PARTNERSHIP"]["keywords"])
        if has_partnership_kw:
            if has_cancellation:
                matches.append({
                    "category": "PARTNERSHIP",
                    "direction": "BEARISH",
                    "importance": "HIGH",
                    "keyword": "partnership cancelled/terminated"
                })
                seen_categories.add("PARTNERSHIP")
            else:
                matches.append({
                    "category": "PARTNERSHIP",
                    "direction": "BULLISH",
                    "importance": "HIGH",
                    "keyword": "partnership"
                })
                seen_categories.add("PARTNERSHIP")

    # 7. FAA Approval detection with denial/grounding handling
    if "FAA_APPROVAL" not in seen_categories:
        has_faa_kw = any(re.search(rf"\b{re.escape(kw)}\b", clean_text) for kw in CATALYST_CONFIG["FAA_APPROVAL"]["keywords"])
        if has_faa_kw:
            if has_cancellation or any(re.search(p, clean_text) for p in [r"\bdeni(es|ed)\b", r"\breject(s|ed)?\b", r"\bgrounds?\b"]):
                matches.append({
                    "category": "FAA_APPROVAL",
                    "direction": "BEARISH",
                    "importance": "HIGH",
                    "keyword": "faa denial/grounding"
                })
                seen_categories.add("FAA_APPROVAL")
            else:
                matches.append({
                    "category": "FAA_APPROVAL",
                    "direction": "BULLISH",
                    "importance": "HIGH",
                    "keyword": "faa approval"
                })
                seen_categories.add("FAA_APPROVAL")

    # 8. Technical Milestone detection with test failure handling
    if "TECHNICAL_MILESTONE" not in seen_categories:
        has_milestone_kw = any(re.search(rf"\b{re.escape(kw)}\b", clean_text) for kw in CATALYST_CONFIG["TECHNICAL_MILESTONE"]["keywords"])
        if has_milestone_kw:
            if any(re.search(p, clean_text) for p in [r"\bfail(ed|ure|s)?\b", r"\banomaly\b", r"\bexplosion\b", r"\bexplod(ed|ing)\b"]):
                matches.append({
                    "category": "TECHNICAL_MILESTONE",
                    "direction": "BEARISH",
                    "importance": "HIGH",
                    "keyword": "milestone test failure"
                })
                seen_categories.add("TECHNICAL_MILESTONE")
            else:
                matches.append({
                    "category": "TECHNICAL_MILESTONE",
                    "direction": "BULLISH",
                    "importance": "MEDIUM",
                    "keyword": "technical milestone"
                })
                seen_categories.add("TECHNICAL_MILESTONE")

    # 9. Match remaining categories from CATALYST_CONFIG
    # Prioritize risk-critical categories (LAUNCH_FAILURE, LAUNCH_DELAY) ahead of generic categories (LAUNCH)
    remaining_categories = [
        cat for cat in ["LAUNCH_FAILURE", "LAUNCH_DELAY", "CAPITAL_RAISE", "ANALYST_DOWNGRADE", "SATELLITE_DEPLOYMENT", "REVENUE", "LAUNCH"]
        if cat in CATALYST_CONFIG and cat not in seen_categories
    ]
    for cat in CATALYST_CONFIG:
        if cat not in seen_categories and cat not in remaining_categories and cat not in ["GOVERNMENT_CONTRACT", "PARTNERSHIP", "FAA_APPROVAL", "TECHNICAL_MILESTONE"]:
            remaining_categories.append(cat)

    for category in remaining_categories:
        if category in seen_categories:
            continue
        # If launch failure or delay was detected, suppress generic bullish LAUNCH
        if category == "LAUNCH" and ("LAUNCH_FAILURE" in seen_categories or "LAUNCH_DELAY" in seen_categories):
            continue

        config = CATALYST_CONFIG[category]
        for kw in config["keywords"]:
            kw_pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(kw_pattern, clean_text):
                matches.append({
                    "category": category,
                    "direction": config["direction"],
                    "importance": config["importance"],
                    "keyword": kw
                })
                seen_categories.add(category)
                break

    # Ensure mutually exclusive launch events: LAUNCH_FAILURE and LAUNCH_DELAY supersede generic LAUNCH
    if any(m["category"] in ("LAUNCH_FAILURE", "LAUNCH_DELAY") for m in matches):
        matches = [m for m in matches if m["category"] != "LAUNCH"]

    # 10. Apply hypothetical and historical qualifiers
    final_matches = []
    for m in matches:
        m_copy = dict(m)
        if is_hypo:
            m_copy["is_hypothetical"] = True
            m_copy["importance"] = "LOW"
        if is_hist:
            m_copy["is_historical"] = True
            m_copy["importance"] = "LOW"

        if is_hypo and not include_hypothetical:
            continue
        if is_hist and not include_historical:
            continue
        final_matches.append(m_copy)

    # 11. Sort by:
    # 1) Importance hierarchy (CRITICAL first, then HIGH, etc.)
    # 2) Polar risk on tie (BEARISH before BULLISH)
    # 3) Specificity on tie (longer keyword first)
    final_matches.sort(
        key=lambda c: (
            IMPORTANCE_RANK.get(c["importance"], 99),
            0 if c["direction"] == "BEARISH" else 1,
            -len(c.get("keyword", ""))
        )
    )
    return final_matches


def detect_catalyst(text: str, ticker: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Detect highest-priority market catalyst in the text based on importance hierarchy.
    Excludes hypothetical or historical retrospective statements from actionable alerts.
    Returns (catalyst_category, direction, importance)
    """
    all_cats = detect_catalysts(text, ticker=ticker, include_hypothetical=False, include_historical=False)
    if not all_cats:
        return None, None, None
    top = all_cats[0]
    return top["category"], top["direction"], top["importance"]


def calculate_news_score(
    news_items: List[Any],
    analysis_timestamp: Optional[datetime] = None,
    half_life_hours: float = 24.0
) -> Dict[str, Any]:
    """
    Computes aggregated News Score (0 to 100) from recent news articles.
    Filters articles by settings.NEWS_MIN_RELEVANCE (default 0.40).
    Dynamically recalculates recency weight relative to analysis_timestamp.
    Returns news_score = None when no relevant news items exist (Adaptive weight normalization).
    """
    if not news_items:
        return {
            "news_score": None,
            "total_news": 0,
            "bullish_news_pct": 0.0,
            "bearish_news_pct": 0.0
        }

    if analysis_timestamp is None:
        analysis_timestamp = datetime.now(timezone.utc)

    min_rel = getattr(settings, "NEWS_MIN_RELEVANCE", 0.40)
    relevant_items = [
        item for item in news_items
        if getattr(item, "relevance_score", 1.0) is None or getattr(item, "relevance_score", 1.0) >= min_rel
    ]

    if not relevant_items:
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

    for item in relevant_items:
        # Importance weighting multiplier
        imp_mult = 1.0
        if getattr(item, 'catalyst_importance', None) == "CRITICAL":
            imp_mult = 2.0
        elif getattr(item, 'catalyst_importance', None) == "HIGH":
            imp_mult = 1.5

        # Recency decay for news (half-life 24 hours, dynamic from analysis_timestamp)
        pub_at = getattr(item, "published_at", None)
        if pub_at is not None:
            rec_w = calculate_recency_weight(pub_at, reference_now=analysis_timestamp, half_life_hours=half_life_hours)
        else:
            rec_w = getattr(item, "recency_weight", 1.0) or 1.0

        rel_score = getattr(item, 'relevance_score', 1.0) if getattr(item, 'relevance_score', 1.0) is not None else 1.0
        conf_score = getattr(item, 'sentiment_confidence', 1.0) if getattr(item, 'sentiment_confidence', 1.0) is not None else 1.0
        w = rel_score * rec_w * conf_score * imp_mult
        
        total_weight += w
        weighted_sentiment_sum += getattr(item, 'sentiment_score', 0.0) * w

        if getattr(item, 'sentiment_label', None) == "BULLISH":
            bull_cnt += 1
        elif getattr(item, 'sentiment_label', None) == "BEARISH":
            bear_cnt += 1

    if total_weight <= 0:
        return {
            "news_score": None,
            "total_news": len(relevant_items),
            "bullish_news_pct": 0.0,
            "bearish_news_pct": 0.0
        }

    norm_sent = weighted_sentiment_sum / total_weight
    raw_news_score = 50.0 + (50.0 * norm_sent)
    news_score = max(0.0, min(100.0, round(raw_news_score, 1)))

    n_total = len(relevant_items)
    return {
        "news_score": news_score,
        "total_news": n_total,
        "bullish_news_pct": round(100.0 * bull_cnt / n_total, 1),
        "bearish_news_pct": round(100.0 * bear_cnt / n_total, 1)
    }
