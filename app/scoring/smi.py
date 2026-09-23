from typing import Dict, Any, Optional, List
from app.config import settings
from app.scoring.social import apply_bayesian_shrinkage


def calculate_source_agreement(active_directions: List[float]) -> Optional[float]:
    """
    Calculate the Pairwise Directional Concordance (-1.0 to +1.0) among active information sources.
    
    Directions are in range [-1.0 (extreme bearish), +1.0 (extreme bullish)].
    - Unanimous concordant signals (+/+ or -/-) yield positive agreement approaching +1.0.
    - Contradictory signals (+/-) yield negative agreement (divergence) approaching -1.0.
    - Neutral sources (|d| < 0.10) contribute 0.0 (neutral impact).
    
    Returns None if fewer than 2 active sources exist (no cross-source corroboration possible).
    Guarantees strict bounds within [-1.0, +1.0].
    """
    if len(active_directions) <= 1:
        return None

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
        return 0.0

    avg_concordance = total_concordance / pairs
    return round(max(-1.0, min(1.0, avg_concordance)), 2)


# Global in-memory cache for dynamically calibrated weights
_calibrated_weights_cache: Optional[Dict[str, float]] = None


def set_calibrated_weights(weights: Optional[Dict[str, float]]) -> None:
    """Store dynamically calibrated weights from backtesting engine."""
    global _calibrated_weights_cache
    _calibrated_weights_cache = dict(weights) if weights else None


def get_active_weights() -> Dict[str, float]:
    """
    Retrieve active base scoring weights:
    Returns calibrated weights if dynamic feedback is enabled and available,
    otherwise returns static configuration weights.
    """
    global _calibrated_weights_cache
    if getattr(settings, "ENABLE_DYNAMIC_WEIGHT_FEEDBACK", False) and _calibrated_weights_cache:
        return dict(_calibrated_weights_cache)
    return {
        "social": settings.WEIGHT_SOCIAL,
        "prediction": settings.WEIGHT_PREDICTION,
        "news": settings.WEIGHT_NEWS,
        "momentum": settings.WEIGHT_MOMENTUM,
        "fundamental": settings.WEIGHT_FUNDAMENTALS,
        "risk": settings.WEIGHT_RISK
    }


def calculate_smi(
    social_score: Optional[float] = None,
    prediction_score: Optional[float] = None,
    prediction_quality: float = 50.0,
    news_score: Optional[float] = None,
    momentum_score: Optional[float] = None,
    fundamental_score: Optional[float] = None,
    risk_score: Optional[float] = None,
    technical_score_raw: Optional[float] = None,
    previous_smi_1d: Optional[Any] = None,
    previous_smi_3d: Optional[Any] = None,
    previous_smi_5d: Optional[Any] = None,
    previous_active_pillars: Optional[List[str]] = None,
    previous_scores: Optional[Dict[str, float]] = None,
    post_count: Optional[int] = None,
    news_count: Optional[int] = None,
    prediction_count: Optional[int] = None,
    custom_weights: Optional[Dict[str, float]] = None
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
      - Bayesian Credibility Shrinkage for small social samples (N < 10 posts)
      - Quality Gate: Polymarket weight = 0 if quality < POLYMARKET_MIN_QUALITY (30.0)
      - Decoupled Data Quality (%) vs Confidence (%)
      - Source Agreement (-1.0 to +1.0)
    """
    # 1. Base weights from configuration or dynamic calibration
    active_base = get_active_weights()
    if custom_weights:
        BASE_WEIGHTS = {k: custom_weights.get(k, active_base.get(k, 0.0)) for k in ["social", "prediction", "news", "momentum", "fundamental", "risk"]}
        for k, v in custom_weights.items():
            if k not in BASE_WEIGHTS:
                BASE_WEIGHTS[k] = v
    else:
        BASE_WEIGHTS = active_base

    active_scores: Dict[str, float] = {}
    effective_weights: Dict[str, float] = {}
    active_directions: List[float] = []

    # A. Social Sentiment (SSI) with Bayesian Credibility Shrinkage for small sample sizes (<10 posts)
    if social_score is not None:
        if post_count is None:
            # Sample size unspecified: treat signal as observed
            is_social_available = True
            effective_social = social_score
        elif post_count == 0:
            # 0 posts collected: strictly exclude social pillar from active weights
            is_social_available = False
            effective_social = 50.0
        else:
            # Bayesian shrinkage towards neutral prior 50.0: effective = 50.0 + (social - 50.0) * (N / 10)
            is_social_available = True
            effective_social = apply_bayesian_shrinkage(social_score, post_count)

        if is_social_available:
            w = BASE_WEIGHTS.get("social", 0.0)
            if w > 0:
                active_scores["social"] = effective_social
                effective_weights["social"] = w
                active_directions.append((effective_social - 50.0) / 50.0)

    # B. Prediction Market Score (PMS)
    if prediction_score is not None and prediction_quality >= settings.POLYMARKET_MIN_QUALITY:
        if prediction_count is None or prediction_count > 0:
            w = BASE_WEIGHTS.get("prediction", 0.0)
            if w > 0:
                active_scores["prediction"] = prediction_score
                # If custom_weights is provided, caller supplied exact target/effective weights; do not re-multiply quality (R2-03)
                if custom_weights:
                    effective_weights["prediction"] = w
                else:
                    quality_factor = min(1.0, max(0.3, prediction_quality / 100.0))
                    effective_weights["prediction"] = w * quality_factor
                active_directions.append((prediction_score - 50.0) / 50.0)

    # C. News & Catalysts
    if news_score is not None:
        if news_count is None or news_count > 0:
            w = BASE_WEIGHTS.get("news", 0.0)
            if w > 0:
                active_scores["news"] = news_score
                effective_weights["news"] = w
                active_directions.append((news_score - 50.0) / 50.0)

    # D. Market Momentum (falls back to scaled technical score if raw momentum score is None)
    effective_mom = momentum_score
    if effective_mom is None and technical_score_raw is not None:
        effective_mom = (technical_score_raw / 40.0) * 100.0

    if effective_mom is not None:
        w = BASE_WEIGHTS.get("momentum", 0.0)
        if w > 0:
            active_scores["momentum"] = effective_mom
            effective_weights["momentum"] = w
            active_directions.append((effective_mom - 50.0) / 50.0)

    # E. Fundamentals
    if fundamental_score is not None:
        w = BASE_WEIGHTS.get("fundamental", 0.0)
        if w > 0:
            active_scores["fundamental"] = fundamental_score
            effective_weights["fundamental"] = w
            active_directions.append((fundamental_score - 50.0) / 50.0)

    # F. Risk / Safety (calculate_risk_score already yields 0-100 where higher = safer/lower risk)
    if risk_score is not None:
        w = BASE_WEIGHTS.get("risk", 0.0)
        if w > 0:
            active_scores["risk"] = risk_score
            effective_weights["risk"] = w
        # Note: risk_score is a non-directional stability/safety metric and does not participate in active_directions

    # 2. Adaptive Weight Normalization
    total_effective_weight = sum(effective_weights.values())
    if total_effective_weight > 0:
        normalized_weights = {k: v / total_effective_weight for k, v in effective_weights.items()}
        weighted_smi = sum(active_scores[k] * normalized_weights[k] for k in normalized_weights.keys())
        smi = max(0.0, min(100.0, round(weighted_smi, 1)))
    else:
        normalized_weights = {}
        smi = None

    # 3. Source Agreement (-1.0 to +1.0)
    source_agreement = calculate_source_agreement(active_directions)

    # 4. Data Quality Score (0 to 100%)
    # Exclude non-directional zero-weight pillars (e.g. risk when decoupled) to reflect genuine source completeness
    eval_pillars = [k for k, v in BASE_WEIGHTS.items() if v > 0]
    total_pillars = len(eval_pillars) if eval_pillars else len(BASE_WEIGHTS)
    active_eval_pillars = [k for k in active_scores.keys() if k in eval_pillars]
    data_quality = round(100.0 * (len(active_eval_pillars) / float(total_pillars)), 1) if total_pillars > 0 else 0.0
    active_pillars = len(active_scores)
    total_data_sources = len(active_scores) + (1 if (risk_score is not None and "risk" not in active_scores) else 0)
    data_completeness = round(100.0 * (total_data_sources / 6.0), 1)

    # 5. Confidence Score (0 to 100%)
    if active_pillars == 0 or smi is None:
        confidence = 0.0
    else:
        base_conf = data_quality * 0.50
        agreement_bonus = (source_agreement * 15.0) if source_agreement is not None else 0.0
        
        depth_bonus = 0.0
        if post_count is not None:
            if post_count >= 30:
                depth_bonus += 12.0
            elif post_count >= 10:
                depth_bonus += 6.0
        elif social_score is not None:
            depth_bonus += 6.0

        if news_count is not None:
            if news_count >= 3:
                depth_bonus += 10.0
            elif news_count >= 1:
                depth_bonus += 5.0
        elif news_score is not None:
            depth_bonus += 5.0

        if prediction_score is not None and prediction_quality >= 50.0:
            depth_bonus += 8.0
            
        if effective_mom is not None:
            depth_bonus += 5.0

        raw_confidence = base_conf + agreement_bonus + depth_bonus
        confidence = max(10.0, min(99.0, round(raw_confidence, 1)))

    # 6. Momentum del SMI (R2-02 audit fix: decouple true evidence change from coverage changes across 1D, 3D, 5D)
    def _compute_horizon_momentum(prev_input, default_pillars=None, default_scores=None):
        if prev_input is None:
            return 0.0, True
        prev_val = prev_input.get("smi") if isinstance(prev_input, dict) else (prev_input.get("ssi") if isinstance(prev_input, dict) else prev_input)
        if prev_val is None:
            return 0.0, True
        prev_pillars = prev_input.get("active_pillars") if isinstance(prev_input, dict) else default_pillars
        prev_scores = prev_input.get("active_scores") if isinstance(prev_input, dict) else default_scores

        if prev_pillars is not None and set(prev_pillars) != set(active_scores.keys()):
            # Coverage changed: compute delta strictly on mutual intersection of pillars evaluated in both snapshots
            common_pillars = [p for p in active_scores.keys() if prev_scores and p in prev_scores and p in prev_pillars]
            if common_pillars:
                cw = {k: BASE_WEIGHTS.get(k, 1.0) for k in common_pillars}
                tot_cw = sum(cw.values())
                if tot_cw > 0:
                    curr_c = sum(active_scores[k] * cw[k] for k in common_pillars) / tot_cw
                    prev_c = sum(prev_scores[k] * cw[k] for k in common_pillars) / tot_cw
                    return round(curr_c - prev_c, 1), False
            return 0.0, False
        return round(smi - prev_val, 1), True

    if smi is not None:
        smi_mom_1d, is_mom_comparable_1d = _compute_horizon_momentum(
            previous_smi_1d, default_pillars=previous_active_pillars, default_scores=previous_scores
        )
        smi_mom_3d, is_mom_comparable_3d = _compute_horizon_momentum(previous_smi_3d)
        smi_mom_5d, is_mom_comparable_5d = _compute_horizon_momentum(previous_smi_5d)
    else:
        smi_mom_1d = smi_mom_3d = smi_mom_5d = None
        is_mom_comparable_1d = is_mom_comparable_3d = is_mom_comparable_5d = True

    scaled_tech = round((technical_score_raw / 40.0) * 100.0, 1) if technical_score_raw is not None else None

    return {
        "smi": smi,
        "ssi": round(social_score, 1) if social_score is not None and (post_count is None or post_count > 0) else None,
        "social_score": round(social_score, 1) if social_score is not None and (post_count is None or post_count > 0) else None,
        "prediction_score": round(prediction_score, 1) if prediction_score is not None and prediction_quality >= settings.POLYMARKET_MIN_QUALITY and (prediction_count is None or prediction_count > 0) else None,
        "prediction_quality": round(prediction_quality, 1),
        "news_score": round(news_score, 1) if news_score is not None and (news_count is None or news_count > 0) else None,
        "momentum_score": round(momentum_score, 1) if momentum_score is not None else None,
        "scaled_technical": scaled_tech,
        "fundamental_score": round(fundamental_score, 1) if fundamental_score is not None else None,
        "risk_score": round(risk_score, 1) if risk_score is not None else None,
        "confidence": confidence,
        "data_quality": data_quality,
        "data_completeness": data_completeness,
        "source_agreement": source_agreement,
        "active_pillars": list(active_scores.keys()),
        "active_scores": {k: round(v, 1) for k, v in active_scores.items()},
        "is_mom_comparable_1d": is_mom_comparable_1d,
        "is_mom_comparable_3d": is_mom_comparable_3d,
        "is_mom_comparable_5d": is_mom_comparable_5d,
        "smi_momentum_1d": smi_mom_1d,
        "smi_momentum_3d": smi_mom_3d,
        "smi_momentum_5d": smi_mom_5d,
        "normalized_weights": {k: round(v, 3) for k, v in normalized_weights.items()},
        "effective_weights": {k: round(v, 4) for k, v in normalized_weights.items()}
    }
