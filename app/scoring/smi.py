from typing import Dict, Any, Optional, List
from app.config import settings


def calculate_source_agreement(active_directions: List[float]) -> float:
    """
    Calculate the Pairwise Directional Concordance (-1.0 to +1.0) among active information sources.
    
    Directions are in range [-1.0 (extreme bearish), +1.0 (extreme bullish)].
    - Unanimous concordant signals (+/+ or -/-) yield positive agreement approaching +1.0.
    - Contradictory signals (+/-) yield negative agreement (divergence) approaching -1.0.
    - Neutral sources (|d| < 0.10) contribute 0.0 (neutral impact).
    
    Guarantees strict bounds within [-1.0, +1.0].
    """
    if len(active_directions) <= 1:
        return 1.0  # Single source has trivial self-agreement

    pairs = 0
    total_concordance = 0.0

    for i in range(len(active_directions)):
        for j in range(i + 1, len(active_directions)):
            d_i = max(-1.0, min(1.0, active_directions[i]))
            d_j = max(-1.0, min(1.0, active_directions[j]))
            
            # Pairwise concordance:
            # If either source is neutral, pair contributes neutral 0.0
            if abs(d_i) < 0.10 or abs(d_j) < 0.10:
                pair_score = 0.0
            elif (d_i > 0 and d_j > 0) or (d_i < 0 and d_j < 0):
                pair_score = min(1.0, (abs(d_i) + abs(d_j)) / 1.5)
            else:
                pair_score = -min(1.0, (abs(d_i) + abs(d_j)) / 1.5)

            total_concordance += pair_score
            pairs += 1

    if pairs == 0:
        return 1.0

    avg_concordance = total_concordance / pairs
    return round(max(-1.0, min(1.0, avg_concordance)), 2)



def calculate_smi(
    social_score: float,
    prediction_score: Optional[float] = None,
    prediction_quality: float = 50.0,
    news_score: Optional[float] = None,
    momentum_score: Optional[float] = None,
    technical_score_raw: Optional[float] = None,
    fundamental_score: Optional[float] = None,
    risk_score: Optional[float] = None,
    previous_smi_1d: Optional[float] = None,
    previous_smi_3d: Optional[float] = None,
    previous_smi_5d: Optional[float] = None,
    post_count: int = 0,
    news_count: int = 0,
    prediction_count: int = 0
) -> Dict[str, Any]:
    """
    Computes Space Market Intelligence Index (SMI, 0 - 100) using SMIE v2.0 Architecture.
    
    Base Target Weights:
      - Social Sentiment (SSI): 30%
      - Prediction Markets (PMS): 15%
      - News / Catalysts: 20%
      - Market Momentum: 20%
      - Fundamentals: 10%
      - Risk / Safety: 5%
      
    Features:
      - Adaptive Weight Normalization (weights always sum to 1.0 without fabricating 50s)
      - Quality Gate: Polymarket weight = 0 if quality < POLYMARKET_MIN_QUALITY (30.0)
      - Decoupled Data Quality (%) vs Confidence (%)
      - Source Agreement (-1.0 to +1.0)
    """
    # 1. Base weights from configuration
    BASE_WEIGHTS = {
        "social": settings.WEIGHT_SOCIAL,
        "prediction": settings.WEIGHT_PREDICTION,
        "news": settings.WEIGHT_NEWS,
        "momentum": settings.WEIGHT_MOMENTUM,
        "fundamental": settings.WEIGHT_FUNDAMENTALS,
        "risk": settings.WEIGHT_RISK
    }

    active_scores: Dict[str, float] = {}
    effective_weights: Dict[str, float] = {}
    active_directions: List[float] = []

    # A. Social Sentiment (SSI) with Bayesian Credibility Shrinkage for small sample sizes (<10 posts)
    is_social_available = (social_score is not None) and (post_count > 0 or social_score != 50.0)
    if is_social_available:
        credibility = min(1.0, max(0.1, post_count / 10.0)) if post_count > 0 else 1.0
        effective_social = 50.0 + (social_score - 50.0) * credibility
        active_scores["social"] = effective_social
        effective_weights["social"] = BASE_WEIGHTS["social"]
        active_directions.append((effective_social - 50.0) / 50.0)

    # B. Prediction Market Score (PMS)
    if prediction_score is not None and prediction_quality >= settings.POLYMARKET_MIN_QUALITY:
        active_scores["prediction"] = prediction_score
        # Modulate prediction weight by quality score
        quality_factor = min(1.0, max(0.3, prediction_quality / 100.0))
        effective_weights["prediction"] = BASE_WEIGHTS["prediction"] * quality_factor
        active_directions.append((prediction_score - 50.0) / 50.0)
    else:
        # Effective weight is 0
        pass

    # C. News & Catalysts
    if news_score is not None and news_count > 0:
        active_scores["news"] = news_score
        effective_weights["news"] = BASE_WEIGHTS["news"]
        active_directions.append((news_score - 50.0) / 50.0)

    # D. Market Momentum (falls back to scaled technical score if raw momentum score is None)
    effective_mom = momentum_score
    if effective_mom is None and technical_score_raw is not None:
        effective_mom = (technical_score_raw / 40.0) * 100.0

    if effective_mom is not None:
        active_scores["momentum"] = effective_mom
        effective_weights["momentum"] = BASE_WEIGHTS["momentum"]
        active_directions.append((effective_mom - 50.0) / 50.0)

    # E. Fundamentals
    if fundamental_score is not None:
        active_scores["fundamental"] = fundamental_score
        effective_weights["fundamental"] = BASE_WEIGHTS["fundamental"]
        active_directions.append((fundamental_score - 50.0) / 50.0)

    # F. Risk / Safety (Inverted for score aggregation: higher safety = higher contribution)
    if risk_score is not None:
        # Risk score 0 (high safety) to 100 (high risk)
        # Convert to Safety index for addition: (100 - risk_score)
        active_scores["risk"] = (100.0 - risk_score)
        effective_weights["risk"] = BASE_WEIGHTS["risk"]

    # 2. Adaptive Weight Normalization
    total_effective_weight = sum(effective_weights.values())
    if total_effective_weight > 0:
        normalized_weights = {k: v / total_effective_weight for k, v in effective_weights.items()}
        weighted_smi = sum(active_scores[k] * normalized_weights[k] for k in active_scores.keys())
    else:
        normalized_weights = {}
        weighted_smi = social_score if social_score is not None else 50.0

    smi = max(0.0, min(100.0, round(weighted_smi, 1)))

    # 3. Source Agreement (-1.0 to +1.0)
    source_agreement = calculate_source_agreement(active_directions)

    # 4. Data Quality Score (0 to 100%)
    # Ratio of available pillars + depth
    total_pillars = len(BASE_WEIGHTS)
    active_pillars = len(active_scores)
    data_quality = round(100.0 * (active_pillars / float(total_pillars)), 1)

    # 5. Confidence Score (0 to 100%)
    # Combines Data Quality, source agreement, sample sizes
    base_conf = data_quality * 0.50  # Up to 50% from data completeness
    
    # Source agreement impact (+/- 15%)
    agreement_bonus = source_agreement * 15.0
    
    # Volume / Sample depth bonus (up to 35%)
    depth_bonus = 0.0
    if post_count >= 30:
        depth_bonus += 12.0
    elif post_count >= 10:
        depth_bonus += 6.0

    if news_count >= 3:
        depth_bonus += 10.0
    elif news_count >= 1:
        depth_bonus += 5.0

    if prediction_score is not None and prediction_quality >= 50.0:
        depth_bonus += 8.0
        
    if effective_mom is not None:
        depth_bonus += 5.0

    raw_confidence = base_conf + agreement_bonus + depth_bonus
    confidence = max(10.0, min(99.0, round(raw_confidence, 1)))

    # 6. Momentum del SMI
    smi_mom_1d = round(smi - previous_smi_1d, 1) if previous_smi_1d is not None else 0.0
    smi_mom_3d = round(smi - previous_smi_3d, 1) if previous_smi_3d is not None else 0.0
    smi_mom_5d = round(smi - previous_smi_5d, 1) if previous_smi_5d is not None else 0.0

    scaled_tech = round((technical_score_raw / 40.0) * 100.0, 1) if technical_score_raw is not None else None

    return {
        "smi": smi,
        "ssi": round(social_score, 1),
        "social_score": round(social_score, 1),
        "prediction_score": round(prediction_score, 1) if prediction_score is not None and prediction_quality >= settings.POLYMARKET_MIN_QUALITY else None,
        "prediction_quality": round(prediction_quality, 1),
        "news_score": round(news_score, 1) if news_score is not None and news_count > 0 else None,
        "momentum_score": round(momentum_score, 1) if momentum_score is not None else None,
        "scaled_technical": scaled_tech,
        "fundamental_score": round(fundamental_score, 1) if fundamental_score is not None else None,
        "risk_score": round(risk_score, 1) if risk_score is not None else None,
        "confidence": confidence,
        "data_quality": data_quality,
        "data_completeness": data_quality,
        "source_agreement": source_agreement,
        "smi_momentum_1d": smi_mom_1d,
        "smi_momentum_3d": smi_mom_3d,
        "smi_momentum_5d": smi_mom_5d,
        "normalized_weights": {k: round(v, 3) for k, v in normalized_weights.items()}
    }
