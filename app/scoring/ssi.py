from typing import Dict, Any, Optional
from app.scoring.smi import calculate_smi


def calculate_ssi(
    social_score: float,
    news_score: Optional[float] = None,
    momentum_score: Optional[float] = None,
    technical_score_raw: Optional[float] = None,
    fundamental_score: Optional[float] = None,
    risk_score: Optional[float] = None,
    prediction_score: Optional[float] = None,
    prediction_quality: float = 50.0,
    previous_ssi_1d: Optional[float] = None,
    previous_ssi_3d: Optional[float] = None,
    previous_ssi_5d: Optional[float] = None,
    post_count: int = 0,
    news_count: int = 0
) -> Dict[str, Any]:
    """
    Backward-compatible wrapper forwarding to calculate_smi in SMIE v2.0.
    """
    res = calculate_smi(
        social_score=social_score,
        prediction_score=prediction_score,
        prediction_quality=prediction_quality,
        news_score=news_score,
        momentum_score=momentum_score,
        technical_score_raw=technical_score_raw,
        fundamental_score=fundamental_score,
        risk_score=risk_score,
        previous_smi_1d=previous_ssi_1d,
        previous_smi_3d=previous_ssi_3d,
        previous_smi_5d=previous_ssi_5d,
        post_count=post_count,
        news_count=news_count
    )
    # Ensure backward compatible keys
    res["ssi_momentum_1d"] = res.get("smi_momentum_1d", 0.0)
    res["ssi_momentum_3d"] = res.get("smi_momentum_3d", 0.0)
    res["ssi_momentum_5d"] = res.get("smi_momentum_5d", 0.0)
    return res
