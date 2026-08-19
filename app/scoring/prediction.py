from typing import List, Optional, Dict, Tuple, Any
from app.config import settings, DEFAULT_EVENT_COMPANY_MAPPINGS
from app.collectors.base import PredictionMarketData
from app.prediction.probability import calculate_prediction_momentum


def calculate_prediction_market_score(
    ticker: str,
    direct_markets: List[PredictionMarketData],
    sector_events: Optional[List[PredictionMarketData]] = None,
    event_mappings: Optional[Dict[str, Dict[str, float]]] = None
) -> Tuple[Optional[float], float, float, Dict[str, Any]]:
    """
    Calculate Prediction Market Score (PMS, 0-100) for a specific ticker.
    
    Formula:
      - Probability Level: 40%
      - Probability Momentum: 35%
      - Market Quality: 15%
      - Volume/Liquidity: 10%
      
    Rules:
      - If Market Quality < 30.0, the market's effective weight is 0.
      - If no valid markets exceed quality threshold, returns (None, 0.0, avg_quality, breakdown).
      - Cross-company sector events are factored in via event impact mappings (-1.0 to +1.0).
    
    Returns:
        (pms_score, pms_confidence, avg_quality, breakdown_dict)
    """
    mappings = event_mappings or DEFAULT_EVENT_COMPANY_MAPPINGS
    sector_events = sector_events or []
    
    valid_market_scores: List[Dict[str, Any]] = []
    
    # 1. Evaluate Direct Markets for this ticker
    for m in direct_markets:
        if m.ticker and m.ticker.upper() == ticker.upper():
            # Check Quality Rule
            if m.quality_score < settings.POLYMARKET_MIN_QUALITY:
                continue  # Excluded by quality threshold
                
            # Base probability level (0 - 100)
            prob_level = m.yes_probability * 100.0
            
            # Momentum (0 - 100)
            mom_score = calculate_prediction_momentum(m.probability_change_24h)
            
            # Normalized Liquidity/Volume score (0 - 100)
            liq_vol_score = min(100.0, (m.quality_score * 0.7 + (min(100000.0, m.volume) / 1000.0) * 0.3))
            
            # Single Market PMS Component breakdown
            market_pms = (
                0.40 * prob_level +
                0.35 * mom_score +
                0.15 * m.quality_score +
                0.10 * liq_vol_score
            )
            
            valid_market_scores.append({
                "market_id": m.external_id,
                "title": m.title,
                "type": "DIRECT",
                "probability": m.yes_probability,
                "delta_24h": m.probability_change_24h,
                "quality": m.quality_score,
                "pms": market_pms,
                "weight": m.quality_score / 100.0
            })
            
    # 2. Evaluate Sector / Global Event Markets that impact this ticker
    for ev in sector_events:
        if ev.quality_score < settings.POLYMARKET_MIN_QUALITY:
            continue
            
        event_key = ev.event_key or ev.external_id
        if event_key in mappings and ticker.upper() in mappings[event_key]:
            impact_factor = mappings[event_key][ticker.upper()]  # e.g., +0.30 or -0.20
            
            # If event is favorable (impact > 0), high probability is bullish.
            # If event is unfavorable (impact < 0), high probability is bearish for this stock.
            if impact_factor >= 0:
                adjusted_prob = 50.0 + (ev.yes_probability - 0.50) * 100.0 * abs(impact_factor)
                adjusted_delta = ev.probability_change_24h * abs(impact_factor)
            else:
                adjusted_prob = 50.0 - (ev.yes_probability - 0.50) * 100.0 * abs(impact_factor)
                adjusted_delta = -ev.probability_change_24h * abs(impact_factor)
                
            adjusted_prob = min(100.0, max(0.0, adjusted_prob))
            mom_score = calculate_prediction_momentum(adjusted_delta)
            
            event_pms = (
                0.40 * adjusted_prob +
                0.35 * mom_score +
                0.15 * ev.quality_score +
                0.10 * 50.0
            )
            
            valid_market_scores.append({
                "market_id": ev.external_id,
                "title": ev.title,
                "type": "SECTOR_EVENT",
                "impact_factor": impact_factor,
                "probability": ev.yes_probability,
                "delta_24h": ev.probability_change_24h,
                "quality": ev.quality_score,
                "pms": event_pms,
                "weight": (ev.quality_score / 100.0) * abs(impact_factor)
            })

    # If no valid markets meet the quality threshold
    if not valid_market_scores:
        all_markets = direct_markets + sector_events
        avg_qual = sum(m.quality_score for m in all_markets) / len(all_markets) if all_markets else 0.0
        return None, 0.0, round(avg_qual, 1), {
            "status": "UNAVAILABLE_OR_LOW_QUALITY",
            "market_count": len(all_markets),
            "valid_count": 0,
            "markets": []
        }

    # Calculate weighted average PMS
    total_weight = sum(item["weight"] for item in valid_market_scores)
    if total_weight > 0:
        weighted_pms = sum(item["pms"] * item["weight"] for item in valid_market_scores) / total_weight
    else:
        weighted_pms = sum(item["pms"] for item in valid_market_scores) / len(valid_market_scores)
        
    final_pms = round(min(100.0, max(0.0, weighted_pms)), 1)
    avg_quality = round(sum(item["quality"] for item in valid_market_scores) / len(valid_market_scores), 1)
    
    # Calculate confidence based on market quality and depth of markets
    market_depth_factor = min(1.0, len(valid_market_scores) / 2.0)
    confidence = round(min(100.0, (avg_quality * 0.75 + market_depth_factor * 25.0)), 1)

    breakdown = {
        "status": "AVAILABLE",
        "market_count": len(valid_market_scores),
        "avg_quality": avg_quality,
        "markets": valid_market_scores
    }

    return final_pms, confidence, avg_quality, breakdown
