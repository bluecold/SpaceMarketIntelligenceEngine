from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple, Any
from app.config import settings, DEFAULT_EVENT_COMPANY_MAPPINGS
from app.collectors.base import PredictionMarketData
from app.prediction.probability import calculate_prediction_momentum


def calculate_prediction_market_score(
    ticker: str,
    direct_markets: List[PredictionMarketData],
    sector_events: Optional[List[PredictionMarketData]] = None,
    event_mappings: Optional[Dict[str, Dict[str, float]]] = None,
    allow_sector_only: Optional[bool] = None
) -> Tuple[Optional[float], float, float, Dict[str, Any]]:
    """
    Calculate Prediction Market Score (PMS, 0-100) for a specific ticker.
    
    Formula (Strictly Directional, Centered at 50):
      - Probability Momentum (24h): 60% (real-time smart money alpha)
      - Probability Level: 40% (calibrated against milestone base rate P0=0.20 or custom baseline)
      
    Rules:
      - Only active, unresolved, unexpired markets contribute to prospective PMS.
      - If Market Quality < 30.0, the market's effective weight is 0.
      - If no valid markets exceed quality threshold, returns (None, 0.0, avg_quality, breakdown).
      - Quality and liquidity determine market weighting and confidence without biasing directional PMS.
      - Cross-company sector events are factored in via event impact mappings (-1.0 to +1.0), but only
        alongside at least one direct market unless allow_sector_only (default settings.PMS_ALLOW_SECTOR_ONLY).
      - Numeric range buckets of an exclusive event ('<5', '5-6', ...) are skipped: each one's YES has no
        direction of its own, and low-probability buckets used to read as bearish.
    
    Returns:
        (pms_score, pms_confidence, avg_quality, breakdown_dict)
    """
    mappings = event_mappings or DEFAULT_EVENT_COMPANY_MAPPINGS
    if allow_sector_only is None:
        allow_sector_only = getattr(settings, "PMS_ALLOW_SECTOR_ONLY", False)
    min_base_rate = getattr(settings, "PMS_MIN_BASE_RATE", 0.005)
    sector_events = sector_events or []
    now_utc = datetime.now(timezone.utc)
    
    valid_market_scores: List[Dict[str, Any]] = []
    seen_market_ids: set = set()
    range_bucket_count = 0
    
    # 1. Evaluate Direct Markets for this ticker
    for m in direct_markets:
        if m.ticker and m.ticker.upper() == ticker.upper():
            if m.external_id in seen_market_ids:
                continue

            # Check market status and expiration (P1.2 audit fix)
            if getattr(m, "status", "ACTIVE") != "ACTIVE":
                continue
            if getattr(m, "closed", False) or getattr(m, "resolved", False):
                continue
            if getattr(m, "resolution_date", None) is not None:
                continue
            if getattr(m, "end_date", None) is not None:
                end_dt = m.end_date
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
                if end_dt < now_utc:
                    continue

            # Check Quality Rule
            if m.quality_score < settings.POLYMARKET_MIN_QUALITY:
                continue  # Excluded by quality threshold
            if getattr(m, "is_range_bucket", False):
                range_bucket_count += 1
                continue
                
            seen_market_ids.add(m.external_id)
            # Base probability level (0 - 100) and effective delta adjusted by semantic polarity & base-rate anchor
            pol = getattr(m, "polarity", 1)
            delta_24h = m.probability_change_24h if m.probability_change_24h is not None else 0.0
            
            # Base-rate anchor (P0): default from settings (0.20 for aerospace milestones) or explicit market baseline
            base_rate = getattr(m, "baseline_probability", None)
            if base_rate is None or not (0.0 < base_rate < 1.0):
                base_rate = getattr(settings, "PMS_DEFAULT_BASE_RATE", 0.20)
            base_rate = min(1.0 - min_base_rate, max(min_base_rate, float(base_rate)))

            if pol < 0:
                # Negative event (e.g. failure, delay): high YES probability is bearish for stock
                # If risk of failure/delay <= base_rate, risk is at or below expected baseline (neutral to bullish)
                p_risk = m.yes_probability
                if p_risk <= base_rate:
                    prob_level = 50.0 + ((base_rate - p_risk) / base_rate) * 50.0
                else:
                    prob_level = 50.0 - ((p_risk - base_rate) / (1.0 - base_rate)) * 50.0
                prob_level = min(100.0, max(0.0, prob_level))
                effective_delta = -delta_24h
            else:
                # Positive event (e.g. launch milestone, contract):
                # If YES probability >= base_rate, milestone is meeting or exceeding baseline expectations
                p_milestone = m.yes_probability
                if p_milestone >= base_rate:
                    prob_level = 50.0 + ((p_milestone - base_rate) / (1.0 - base_rate)) * 50.0
                else:
                    prob_level = (p_milestone / base_rate) * 50.0
                prob_level = min(100.0, max(0.0, prob_level))
                effective_delta = delta_24h
            
            # Momentum (0 - 100)
            mom_score = calculate_prediction_momentum(effective_delta)
            
            # Pure directional PMS (0 - 100, neutral = 50.0)
            w_mom = getattr(settings, "PMS_WEIGHT_MOMENTUM", 0.60)
            w_level = getattr(settings, "PMS_WEIGHT_LEVEL", 0.40)
            market_pms = (
                w_level * prob_level +
                w_mom * mom_score
            )
            
            valid_market_scores.append({
                "market_id": m.external_id,
                "title": m.title,
                "type": "DIRECT",
                "polarity": pol,
                "probability": m.yes_probability,
                "raw_delta_24h": m.probability_change_24h,
                "adjusted_delta_24h": effective_delta,
                "delta_24h": effective_delta,
                "quality": m.quality_score,
                "pms": market_pms,
                "weight": m.quality_score / 100.0
            })
            
    # 2. Evaluate Sector / Global Event Markets that impact this ticker
    for ev in sector_events:
        if ev.external_id in seen_market_ids:
            continue  # Prevent double-counting if market was already evaluated directly

        # Check market status and expiration
        if getattr(ev, "status", "ACTIVE") != "ACTIVE":
            continue
        if getattr(ev, "closed", False) or getattr(ev, "resolved", False):
            continue
        if getattr(ev, "resolution_date", None) is not None:
            continue
        if getattr(ev, "end_date", None) is not None:
            end_dt = ev.end_date
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            if end_dt < now_utc:
                continue

        if ev.quality_score < settings.POLYMARKET_MIN_QUALITY:
            continue
        if getattr(ev, "is_range_bucket", False):
            range_bucket_count += 1
            continue
            
        event_key = ev.event_key or ev.external_id
        if event_key in mappings and ticker.upper() in mappings[event_key]:
            seen_market_ids.add(ev.external_id)
            impact_factor = mappings[event_key][ticker.upper()]  # e.g., +0.30 or -0.20
            
            # Combine declared ticker impact with question polarity
            effective_impact = impact_factor * getattr(ev, "polarity", 1)
            ev_delta = ev.probability_change_24h if ev.probability_change_24h is not None else 0.0
            
            # If event is favorable (effective_impact > 0), high probability is bullish.
            # If event is unfavorable (effective_impact < 0), high probability is bearish for this stock.
            if effective_impact >= 0:
                adjusted_prob = 50.0 + (ev.yes_probability - 0.50) * 100.0 * abs(effective_impact)
                adjusted_delta = ev_delta * abs(effective_impact)
            else:
                adjusted_prob = 50.0 - (ev.yes_probability - 0.50) * 100.0 * abs(effective_impact)
                adjusted_delta = -ev_delta * abs(effective_impact)
                
            adjusted_prob = min(100.0, max(0.0, adjusted_prob))
            mom_score = calculate_prediction_momentum(adjusted_delta)
            
            # Pure directional PMS for sector event
            w_mom = getattr(settings, "PMS_WEIGHT_MOMENTUM", 0.60)
            w_level = getattr(settings, "PMS_WEIGHT_LEVEL", 0.40)
            event_pms = (
                w_level * adjusted_prob +
                w_mom * mom_score
            )

            
            valid_market_scores.append({
                "market_id": ev.external_id,
                "title": ev.title,
                "type": "SECTOR_EVENT",
                "impact_factor": impact_factor,
                "polarity": getattr(ev, "polarity", 1),
                "probability": ev.yes_probability,
                "raw_delta_24h": ev.probability_change_24h,
                "adjusted_delta_24h": adjusted_delta,
                "delta_24h": adjusted_delta,
                "quality": ev.quality_score,
                "pms": event_pms,
                "weight": (ev.quality_score / 100.0) * abs(impact_factor)
            })

    has_direct = any(item["type"] == "DIRECT" for item in valid_market_scores)
    if valid_market_scores and not has_direct and not allow_sector_only:
        # Sector events alone are a weak, near-constant proxy: no PMS rather than an anchor around 48
        return None, 0.0, 0.0, {
            "status": "SECTOR_ONLY_EXCLUDED",
            "market_count": 0,
            "raw_market_count": len(direct_markets) + len(sector_events),
            "valid_count": 0,
            "sector_event_count": len(valid_market_scores),
            "range_bucket_count": range_bucket_count,
            "avg_quality": 0.0,
            "pms_delta_24h": None,
            "delta_24h": None,
            "markets": []
        }

    # If no valid markets meet the quality threshold
    if not valid_market_scores:
        all_markets = direct_markets + sector_events
        avg_qual = sum(m.quality_score for m in all_markets) / len(all_markets) if all_markets else 0.0
        return None, 0.0, round(avg_qual, 1), {
            "status": "UNAVAILABLE_OR_LOW_QUALITY",
            "market_count": 0,
            "raw_market_count": len(all_markets),
            "valid_count": 0,
            "range_bucket_count": range_bucket_count,
            "avg_quality": round(avg_qual, 1),
            "pms_delta_24h": None,
            "delta_24h": None,
            "markets": []
        }

    # Calculate weighted average PMS and 24h probability delta
    total_weight = sum(item["weight"] for item in valid_market_scores)
    if total_weight > 0:
        weighted_pms = sum(item["pms"] * item["weight"] for item in valid_market_scores) / total_weight
        weighted_delta = sum(item.get("adjusted_delta_24h", item.get("delta_24h", 0.0)) * item["weight"] for item in valid_market_scores) / total_weight
    else:
        weighted_pms = sum(item["pms"] for item in valid_market_scores) / len(valid_market_scores)
        weighted_delta = sum(item.get("adjusted_delta_24h", item.get("delta_24h", 0.0)) for item in valid_market_scores) / len(valid_market_scores)
        
    final_pms = round(min(100.0, max(0.0, weighted_pms)), 1)
    pms_delta_24h = round(weighted_delta, 2)
    avg_quality = round(sum(item["quality"] for item in valid_market_scores) / len(valid_market_scores), 1)
    
    # Calculate confidence based on market quality and depth of markets
    market_depth_factor = min(1.0, len(valid_market_scores) / 2.0)
    confidence = round(min(100.0, (avg_quality * 0.75 + market_depth_factor * 25.0)), 1)

    breakdown = {
        "status": "AVAILABLE",
        "market_count": len(valid_market_scores),
        "range_bucket_count": range_bucket_count,
        "avg_quality": avg_quality,
        "pms_delta_24h": pms_delta_24h,
        "delta_24h": pms_delta_24h,
        "markets": valid_market_scores
    }

    return final_pms, confidence, avg_quality, breakdown
