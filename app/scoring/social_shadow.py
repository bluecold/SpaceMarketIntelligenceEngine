"""
Shadow social score from daily aggregate rows (Adanos X API). Measured only: never part of the SMI.

It mirrors the live SSI as closely as daily aggregates allow:
  - raw_score: opinion-only polarity on 0..100, 50 + 50 * (bull - bear) / (bull + bear), so neutral posts
    carry no direction, as in calculate_social_score.
  - baseline_score: the ticker's trailing SOCIAL_BASELINE_DAYS norm (days strictly before the scored day),
    opinion-weighted and shrunk towards neutral by SOCIAL_BASELINE_PRIOR_WEIGHT, as in calculate_social_baseline.
    None until SOCIAL_BASELINE_MIN_DAYS days with opinions exist.
  - shadow_ssi: 50 + raw - baseline (clamped 0..100), as in apply_social_baseline, then the same Bayesian shrinkage towards 50 that calculate_smi applies to the live SSI, with the day's
    opinion count as the sample size (a day with one bearish post is not a 0).
  - volume_ratio: mentions / median mentions of the baseline days.
Differences from the live SSI to keep in mind when measuring: the provider's own classifier (not FinTwitBERT),
no spam or language filter on our side, no engagement or recency weights, and one value per UTC day (the
current day is partial until it ends).
"""
import statistics
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from app.config import settings
from app.scoring.social import apply_bayesian_shrinkage


def _polarity(row: Dict[str, Any]) -> Optional[float]:
    bull, bear = row.get("bullish_pct"), row.get("bearish_pct")
    if bull is None or bear is None or (bull + bear) <= 0:
        return None
    return (bull - bear) / (bull + bear)


def _opinions(row: Dict[str, Any]) -> float:
    bull, bear, n = row.get("bullish_pct") or 0.0, row.get("bearish_pct") or 0.0, row.get("mentions") or 0
    return n * (bull + bear) / 100.0


def compute_shadow_scores(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Copies of the daily rows (oldest first) with raw_score, baseline_score, shadow_ssi, opinion_count and
    volume_ratio. Each day only looks at earlier days, so a value never changes when later days arrive."""
    days = int(getattr(settings, "SOCIAL_BASELINE_DAYS", 14))
    prior = float(getattr(settings, "SOCIAL_BASELINE_PRIOR_WEIGHT", 10.0))
    min_days = float(getattr(settings, "SOCIAL_BASELINE_MIN_DAYS", 3.0))
    by_date = {r["date"]: r for r in rows}
    out = []
    for r in sorted(rows, key=lambda x: x["date"]):
        d = date.fromisoformat(r["date"])
        res = dict(r)
        p = _polarity(r)
        res["raw_score"] = round(50.0 + 50.0 * p, 1) if p is not None else None
        res["opinion_count"] = round(_opinions(r), 1)

        hist = [by_date[k] for k in ((d - timedelta(days=i)).isoformat() for i in range(1, days + 1)) if k in by_date]
        weighted = [(_polarity(h), _opinions(h)) for h in hist]
        weighted = [(pol, w) for pol, w in weighted if pol is not None and w > 0]
        total_w = sum(w for _, w in weighted)
        base_pol = sum(pol * w for pol, w in weighted) / (total_w + prior) if (total_w + prior) > 0 else 0.0
        res["baseline_score"] = round(50.0 + 50.0 * base_pol, 1) if len(weighted) >= min_days else None
        if res["raw_score"] is not None and res["baseline_score"] is not None:
            unshrunk = max(0.0, min(100.0, round(50.0 + res["raw_score"] - res["baseline_score"], 1)))
            res["shadow_ssi"] = round(apply_bayesian_shrinkage(unshrunk, int(round(res["opinion_count"]))), 1)
        else:
            res["shadow_ssi"] = None

        hist_mentions = [h["mentions"] for h in hist if h.get("mentions")]
        if len(hist_mentions) >= min_days and r.get("mentions") is not None:
            med = statistics.median(hist_mentions)
            res["volume_ratio"] = round(r["mentions"] / med, 2) if med > 0 else None
        else:
            res["volume_ratio"] = None
        out.append(res)
    return out
