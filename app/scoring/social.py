import math
import re
import statistics
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from app.database.models import SocialPostModel
from app.config import settings
from app.sentiment.weighting import calculate_recency_weight

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


# X language codes that carry no real language (cashtag/hashtag/mention/media-only posts): judged by script instead
X_UNDETERMINED_LANGS = {"und", "qme", "qht", "qam", "qct", "qst", "zxx", "art"}


def is_scorable_language(post: Any) -> bool:
    """
    True when a post is in a language the sentiment models understand (settings.SOCIAL_ALLOWED_LANGUAGES).

    Uses the language X detected when available. Posts without it (collected before it was stored, mocks)
    or with an undetermined code fall back to a script check: mostly non-Latin letters (Japanese, Korean,
    Arabic, Cyrillic...) means non-English. That fallback cannot catch Latin-script languages such as
    Spanish or Portuguese (~1.4% of relevant posts); X's own detection covers them for new posts.
    """
    allowed = {l.lower() for l in getattr(settings, "SOCIAL_ALLOWED_LANGUAGES", ["en"])}
    lang = (getattr(post, "lang", None) or "").lower()
    if lang and lang not in X_UNDETERMINED_LANGS:
        return lang in allowed

    text = getattr(post, "text", "") or ""
    letters = re.findall(r"[^\W\d_]", text)
    if not letters:
        return True
    ascii_share = sum(1 for ch in letters if ch.isascii()) / len(letters)
    return ascii_share >= 0.85


# Promotional / bot campaign patterns. Reviewed on 4,791 stored posts (Oct 2026): every opinion-labelled
# match (69, all BULLISH) was a group invite, paid-signal promo or a reach-hashtag campaign that appends
# unrelated cashtags ("...RYET quietly building an ecosystem #bb28 $SPCE").
SPAM_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    # Reality-TV hashtags hijacked for reach by stock-promo bot networks
    r"#(?:bbnaija|smno|bb28|brosis|blonde|candid)\b",
    # Chat group invites
    r"\b(?:whatsapp|telegram|discord)\b.{0,80}\b(?:group|channel|community|chat|link|join)\b",
    r"\b(?:join|joining)\b.{0,40}\b(?:whatsapp|telegram|discord)\b",
    r"\bjoin\b.{0,30}\b(?:our|my|the)\b.{0,20}\b(?:free\s+)?(?:group|community|signal|alerts?)\b",
    r"\breply\s+with\s+[\"“']?\w+[\"”']?\s+to\s+join\b",
    r"\bsend\s+[\"“']\w[\w\s]*[\"”']\s",
    # Paid signals, copy trading, testimonial and engagement bait
    r"\b(?:signal\s+group|copy\s+trad\w+|trading\s+signals?|real[- ]time\s+(?:trading\s+)?alerts?)\b",
    r"\bi\s+(?:made|earned|profited)\s+\$?[\d,.]+k?\b.{0,40}\b(?:following|thanks\s+to)\b",
    r"\b(?:turn(?:ed)?\s+on|notifications?\s+(?:on|turned\s+on))\b.{0,30}\bnotifications?\b",
    r"\bnext\s+alert\b",
    r"\b(?:accuracy\s+rate|win\s+rate)\s+of\s+\d{2,3}\s*%|\b\d{2,3}\s*%\s+(?:accuracy|win\s+rate)\b",
)]


def is_promotional_spam(post: Any) -> bool:
    """True for stock-promo bot posts (group invites, paid signals, hashtag-hijack campaigns)."""
    if not getattr(settings, "SOCIAL_EXCLUDE_SPAM", True):
        return False
    text = getattr(post, "text", "") or ""
    return any(p.search(text) for p in SPAM_PATTERNS)


def calculate_social_score(
    posts: List[SocialPostModel],
    analysis_timestamp: Optional[datetime] = None,
    half_life_hours: float = 12.0,
    post_details: Optional[Dict[int, Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Calculates the raw Social Sentiment Score (0 - 100) and sentiment distribution.
    Weight per post: relevance * recency * confidence * (1 + engagement_score / ENGAGEMENT_SCALE_DIVISOR).

    Opinion-only polarity: the score is the weighted mean sentiment of BULLISH/BEARISH posts only.
    NEUTRAL posts (news links, questions, chatter; ~80% of X traffic) carry no direction, so averaging
    them in would pull every ticker towards 50 regardless of the bull/bear balance. They still count in
    the distribution percentages and in total_posts (attention), but not in the polarity.
    Returns social_score = None when no opinionated post exists (no directional evidence).

    effective_sample_size counts opinionated posts (deduplicated and bounded by distinct authors);
    it drives Bayesian shrinkage in calculate_smi and the divergence engine.
    The ticker baseline adjustment is applied separately by apply_social_baseline().

    Deduplicates posts by normalized text and enforces settings.SOCIAL_MIN_RELEVANCE.
    Dynamically recalculates recency decay from post.created_at against analysis_timestamp.
    Limits engagement accumulation from duplicate spam messages to prevent artificial score manipulation.

    post_details: optional dict filled with one entry per input post, keyed by id(post), from this same
    pass (so a UI can never disagree with the score): {"status": "counted"|"excluded", "reason", "weight",
    "vote_share"}. reason is "low_relevance", "language", "spam" or "duplicate"; vote_share is the post's
    percentage of the opinion weight (0 for neutral posts, which do not vote).
    """
    def _note(post, status, reason=None, weight=0.0, vote_share=0.0):
        if post_details is not None:
            post_details[id(post)] = {"status": status, "reason": reason, "weight": round(weight, 4), "vote_share": round(vote_share, 1)}

    total_collected = len(posts) if posts else 0
    if not posts:
        return {
            "non_english_post_count": 0,
            "spam_post_count": 0,
            "social_score": None,
            "raw_post_count": 0,
            "relevant_post_count": 0,
            "unique_post_count": 0,
            "author_count": 0,
            "opinion_post_count": 0,
            "effective_sample_size": 0,
            "total_posts": 0,
            "relevant_posts": 0,
            "bullish_pct": 0.0,
            "neutral_pct": 0.0,
            "bearish_pct": 0.0,
            "weighted_bullish_pct": 0.0,
            "weighted_neutral_pct": 0.0,
            "weighted_bearish_pct": 0.0
        }

    # Reference evaluation timestamp (default to current UTC if not specified)
    if analysis_timestamp is None:
        analysis_timestamp = datetime.now(timezone.utc)

    min_rel = getattr(settings, "SOCIAL_MIN_RELEVANCE", 0.40)
    relevant_all = [
        p for p in posts
        if getattr(p, "relevance_score", 1.0) is not None and getattr(p, "relevance_score", 1.0) >= min_rel
    ]
    # Sentiment models are English-only: other languages are excluded rather than misread
    english_posts = [p for p in relevant_all if is_scorable_language(p)]
    non_english_count = len(relevant_all) - len(english_posts)
    # Promo bots carry no real opinion (and are uniformly bullish): excluded from polarity and attention
    relevant_posts = [p for p in english_posts if not is_promotional_spam(p)]
    spam_count = len(english_posts) - len(relevant_posts)
    relevant_count = len(relevant_posts)

    if post_details is not None:
        relevant_ids = {id(p) for p in relevant_all}
        english_ids = {id(p) for p in english_posts}
        for p in posts:
            if id(p) not in relevant_ids:
                _note(p, "excluded", "low_relevance")
            elif id(p) not in english_ids:
                _note(p, "excluded", "language")
        for p in english_posts:
            if is_promotional_spam(p):
                _note(p, "excluded", "spam")

    if not relevant_posts:
        return {
            "non_english_post_count": non_english_count,
            "spam_post_count": spam_count,
            "social_score": None,
            "raw_post_count": total_collected,
            "relevant_post_count": 0,
            "unique_post_count": 0,
            "author_count": 0,
            "opinion_post_count": 0,
            "effective_sample_size": 0,
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

        # Dynamically recalculate recency weight from created_at against analysis_timestamp
        p_created = getattr(p, "created_at", None)
        if p_created is not None:
            if isinstance(p_created, str):
                try:
                    p_created = datetime.fromisoformat(p_created)
                except Exception:
                    p_created = None
            if p_created is not None and isinstance(p_created, datetime):
                p_rec = calculate_recency_weight(p_created, reference_now=analysis_timestamp, half_life_hours=half_life_hours)
            else:
                p_rec = getattr(p, "recency_weight", 1.0) or 1.0
        else:
            p_rec = getattr(p, "recency_weight", 1.0) or 1.0

        p_rel = getattr(p, "relevance_score", 1.0) or 1.0
        p_sent = getattr(p, "sentiment_score", 0.0) or 0.0
        p_label = getattr(p, "sentiment_label", "NEUTRAL") or "NEUTRAL"
        p_conf = getattr(p, "sentiment_confidence", 0.70) or 0.70

        p_author = getattr(p, "username", "") or ""

        if norm_key not in unique_posts_map:
            unique_posts_map[norm_key] = {
                "sentiment_score": p_sent,
                "sentiment_label": p_label,
                "sentiment_confidence": p_conf,
                "relevance_score": p_rel,
                "recency_weight": p_rec,
                "engagement_score": p_eng,
                "duplicate_count": 1,
                "authors": {p_author} if p_author else set(),
                "post": p
            }
        else:
            entry = unique_posts_map[norm_key]
            entry["duplicate_count"] += 1
            _note(p, "excluded", "duplicate")
            if p_author:
                entry["authors"].add(p_author)
            # Bounded duplicate engagement accumulation:
            # Prevents linear inflation from spam/retweet bombardment.
            marginal_bonus = min(p_eng * 0.25, 2.0 / math.sqrt(entry["duplicate_count"]))
            entry["engagement_score"] = max(entry["engagement_score"], p_eng) + marginal_bonus
            entry["recency_weight"] = max(entry["recency_weight"], p_rec)
            entry["sentiment_confidence"] = max(entry.get("sentiment_confidence", 0.70), p_conf)

    deduped_items = list(unique_posts_map.values())
    unique_count = len(deduped_items)

    all_authors = set(
        getattr(p, "username", "")
        for p in relevant_posts
        if getattr(p, "username", "")
    )
    author_count = len(all_authors) if all_authors else unique_count

    # Post sample size (attention / display): cannot exceed unique distinct message contents or unique authors
    post_sample_size = min(unique_count, max(1, author_count)) if unique_count > 0 else 0
    rel_total = unique_count

    # Opinion sample size (directional evidence): same bound, restricted to BULLISH/BEARISH posts
    opinion_items = [item for item in deduped_items if item["sentiment_label"] in ("BULLISH", "BEARISH")]
    opinion_count = len(opinion_items)
    opinion_authors = set().union(*(item["authors"] for item in opinion_items)) if opinion_items else set()
    effective_sample_size = min(opinion_count, max(1, len(opinion_authors))) if opinion_count > 0 else 0

    bullish_cnt = sum(1 for item in deduped_items if item["sentiment_label"] == "BULLISH")
    bearish_cnt = sum(1 for item in deduped_items if item["sentiment_label"] == "BEARISH")
    neutral_cnt = sum(1 for item in deduped_items if item["sentiment_label"] == "NEUTRAL")

    bullish_pct = round(100.0 * bullish_cnt / rel_total, 1)
    bearish_pct = round(100.0 * bearish_cnt / rel_total, 1)
    neutral_pct = round(100.0 * neutral_cnt / rel_total, 1)

    # Weighted calculation: distribution over all posts, polarity over opinionated posts only
    weight_total = 0.0
    opinion_weighted_sum = 0.0
    opinion_weight_total = 0.0

    w_bull = 0.0
    w_bear = 0.0
    w_neu = 0.0

    for item in deduped_items:
        conf = item.get("sentiment_confidence", 0.70)
        w = item["relevance_score"] * item["recency_weight"] * conf * (1.0 + item["engagement_score"] / ENGAGEMENT_SCALE_DIVISOR)
        weight_total += w

        if item["sentiment_label"] == "BULLISH":
            w_bull += w
        elif item["sentiment_label"] == "BEARISH":
            w_bear += w
        else:
            w_neu += w

        if item["sentiment_label"] in ("BULLISH", "BEARISH"):
            opinion_weighted_sum += item["sentiment_score"] * w
            opinion_weight_total += w
        item["weight"] = w

    for item in deduped_items:
        is_opinion = item["sentiment_label"] in ("BULLISH", "BEARISH")
        share = 100.0 * item["weight"] / opinion_weight_total if (is_opinion and opinion_weight_total > 0) else 0.0
        _note(item["post"], "counted", weight=item["weight"], vote_share=share)

    if weight_total > 0:
        weighted_bull_pct = round(100.0 * w_bull / weight_total, 1)
        weighted_bear_pct = round(100.0 * w_bear / weight_total, 1)
        weighted_neu_pct = round(100.0 * w_neu / weight_total, 1)
    else:
        weighted_bull_pct = bullish_pct
        weighted_bear_pct = bearish_pct
        weighted_neu_pct = neutral_pct

    # Convert opinion polarity (-1..+1) to 0..100 score; no opinions -> no directional evidence
    if opinion_weight_total > 0:
        norm_sentiment = opinion_weighted_sum / opinion_weight_total
        social_score = max(0.0, min(100.0, round(50.0 + (50.0 * norm_sentiment), 1)))
    else:
        social_score = None

    return {
        "social_score": social_score,
        "raw_post_count": total_collected,
        "relevant_post_count": relevant_count,
        "unique_post_count": unique_count,
        "author_count": author_count,
        "opinion_post_count": opinion_count,
        "non_english_post_count": non_english_count,
        "spam_post_count": spam_count,
        "effective_sample_size": effective_sample_size,
        "total_posts": post_sample_size,
        "relevant_posts": post_sample_size,
        "bullish_pct": bullish_pct,
        "neutral_pct": neutral_pct,
        "bearish_pct": bearish_pct,
        "weighted_bullish_pct": weighted_bull_pct,
        "weighted_neutral_pct": weighted_neu_pct,
        "weighted_bearish_pct": weighted_bear_pct
    }


def _as_naive_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo is not None else dt


def calculate_social_baseline(
    history_posts: List[SocialPostModel],
    window_start: datetime,
    window_end: datetime
) -> Dict[str, Any]:
    """
    Computes a ticker's normal X sentiment and mention rate over [window_start, window_end).

    Retail X is structurally bullish (bullish opinions outnumber bearish ~2:1 for every covered ticker),
    so a raw polarity of 60 is the norm, not a signal. The baseline lets the SSI measure deviation from
    each ticker's own norm.

    - polarity: weighted opinion polarity (-1..+1) without recency decay, shrunk towards 0 by a
      pseudo-weight of settings.SOCIAL_BASELINE_PRIOR_WEIGHT so thin histories barely move the SSI.
    - daily_post_rate: median of unique relevant posts per 24h bucket (deduplicated within each bucket,
      exactly like the live lookback window). Empty buckets are collection gaps and are skipped.
    """
    start = _as_naive_utc(window_start)
    end = _as_naive_utc(window_end)
    min_rel = getattr(settings, "SOCIAL_MIN_RELEVANCE", 0.40)
    prior_weight = getattr(settings, "SOCIAL_BASELINE_PRIOR_WEIGHT", 10.0)

    unique: Dict[str, Any] = {}
    bucket_keys: Dict[int, set] = {}
    for p in history_posts or []:
        created = getattr(p, "created_at", None)
        if created is None or getattr(p, "relevance_score", None) is None:
            continue
        created = _as_naive_utc(created)
        if not (start <= created < end) or p.relevance_score < min_rel or not is_scorable_language(p) or is_promotional_spam(p):
            continue
        key = normalize_text_for_dedup(p.text) if getattr(p, "text", None) else ""
        key = key or str(getattr(p, "tweet_id", id(p)))
        bucket = int((end - created).total_seconds() // 86400)
        bucket_keys.setdefault(bucket, set()).add(key)
        if key not in unique:
            unique[key] = p

    weighted_sum = 0.0
    weight_total = 0.0
    opinion_count = 0
    for p in unique.values():
        if getattr(p, "sentiment_label", None) not in ("BULLISH", "BEARISH"):
            continue
        conf = getattr(p, "sentiment_confidence", 0.70) or 0.70
        eng = getattr(p, "engagement_score", 0.0) or 0.0
        w = (p.relevance_score or 1.0) * conf * (1.0 + eng / ENGAGEMENT_SCALE_DIVISOR)
        weighted_sum += (getattr(p, "sentiment_score", 0.0) or 0.0) * w
        weight_total += w
        opinion_count += 1

    polarity = weighted_sum / (weight_total + prior_weight) if (weight_total + prior_weight) > 0 else 0.0
    daily_counts = sorted(len(keys) for keys in bucket_keys.values())
    daily_post_rate = float(statistics.median(daily_counts)) if daily_counts else 0.0

    return {
        "polarity": round(polarity, 4),
        "opinion_post_count": opinion_count,
        "unique_post_count": len(unique),
        "days_covered": len(daily_counts),
        "daily_post_rate": round(daily_post_rate, 2)
    }


def apply_social_baseline(social_res: Dict[str, Any], baseline: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Re-centers the raw opinion polarity on the ticker's own baseline and adds attention metrics.

      social_score (SSI) = 50 + raw_score - baseline_score     (clamped to 0..100)
      mention_volume_ratio = unique relevant posts in the lookback window / baseline posts per window

    The ratio is None until the baseline covers settings.SOCIAL_BASELINE_MIN_DAYS, since a short history
    cannot tell a spike from normal traffic. Adds social_polarity_raw and social_baseline for transparency.
    """
    res = dict(social_res)
    raw = social_res.get("social_score")
    res["social_polarity_raw"] = raw
    res["social_baseline"] = None
    res["mention_volume_ratio"] = None
    if not baseline:
        return res

    baseline_score = round(50.0 + 50.0 * baseline.get("polarity", 0.0), 1)
    res["social_baseline"] = baseline_score
    if raw is not None:
        res["social_score"] = max(0.0, min(100.0, round(50.0 + raw - baseline_score, 1)))

    min_days = getattr(settings, "SOCIAL_BASELINE_MIN_DAYS", 3.0)
    rate = baseline.get("daily_post_rate") or 0.0
    if baseline.get("days_covered", 0.0) >= min_days and rate > 0:
        lookback_days = getattr(settings, "SOCIAL_LOOKBACK_HOURS", 24) / 24.0
        current = social_res.get("unique_post_count", 0) or 0
        res["mention_volume_ratio"] = round(current / (rate * lookback_days), 2)
    return res


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
