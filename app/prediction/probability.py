from typing import List, Tuple
from datetime import datetime, timedelta, timezone
from app.collectors.base import MarketProbabilityPoint


def calculate_probability_changes(
    current_yes_prob: float,
    history: List[MarketProbabilityPoint]
) -> Tuple[float, float, float]:
    """
    Calculate probability changes (in percentage points) over 1h, 6h, and 24h.
    
    Returns:
        (delta_1h_pp, delta_6h_pp, delta_24h_pp)
        e.g., if prob moved from 54% to 71%, delta is +17.0
    """
    if not history:
        return 0.0, 0.0, 0.0

    now = datetime.now(timezone.utc)
    
    target_1h = now - timedelta(hours=1)
    target_6h = now - timedelta(hours=6)
    target_24h = now - timedelta(hours=24)

    prob_1h = None
    prob_6h = None
    prob_24h = None

    sorted_history = sorted(history, key=lambda x: x.timestamp)

    for pt in sorted_history:
        ts = pt.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
            
        if ts <= target_1h:
            prob_1h = pt.yes_probability
        if ts <= target_6h:
            prob_6h = pt.yes_probability
        if ts <= target_24h:
            prob_24h = pt.yes_probability

    # Fallbacks if points not far enough
    if prob_1h is None and sorted_history:
        prob_1h = sorted_history[0].yes_probability
    if prob_6h is None:
        prob_6h = prob_1h
    if prob_24h is None:
        prob_24h = prob_6h

    delta_1h = round((current_yes_prob - (prob_1h if prob_1h is not None else current_yes_prob)) * 100.0, 2)
    delta_6h = round((current_yes_prob - (prob_6h if prob_6h is not None else current_yes_prob)) * 100.0, 2)
    delta_24h = round((current_yes_prob - (prob_24h if prob_24h is not None else current_yes_prob)) * 100.0, 2)

    return delta_1h, delta_6h, delta_24h


def calculate_prediction_momentum(
    probability_change_24h: float,
    volume_surge_ratio: float = 1.0
) -> float:
    """
    Calculate Prediction Market Momentum (0 to 100).
    Neutral momentum is 50.
    Positive acceleration (+20pp move) pushes towards 100.
    Negative collapse (-20pp move) pushes towards 0.
    """
    base = 50.0
    scaled_delta = probability_change_24h * 1.6
    vol_multiplier = min(1.5, max(0.8, volume_surge_ratio))
    momentum = base + (scaled_delta * vol_multiplier)
    
    return round(min(100.0, max(0.0, momentum)), 1)
