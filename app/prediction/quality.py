import math
from typing import Optional
from datetime import datetime, timezone


def calculate_market_quality(
    liquidity: float,
    volume: float,
    spread: float = 0.0,
    end_date: Optional[datetime] = None,
    activity_score: float = 1.0
) -> float:
    """
    Calculate Market Quality Score (0 to 100) for a Prediction Market.
    
    Evaluates whether the market is sufficiently deep, liquid, tight, and active
    to be trusted as an informative quantitative signal.
    
    Components:
    1. Liquidity (35%): Logarithmic scaling up to $100k+ pool.
    2. Volume (30%): Cumulative traded volume up to $250k+.
    3. Spread (20%): Tightness of Bid-Ask spread (narrower = higher quality).
    4. Time to Resolution / Activity (15%): Imminent vs. reasonably near-term resolution.
    """
    # 1. Liquidity Score (0 to 35 pts)
    # $0 -> 0 pts, $1k -> 10 pts, $10k -> 20 pts, $100k+ -> 35 pts
    if liquidity <= 0:
        liquidity_pts = 0.0
    else:
        # log10(1 + liquidity) normalized against log10(1 + 100,000) = 5.0
        norm_liq = min(1.0, math.log10(1 + liquidity) / 5.0)
        liquidity_pts = norm_liq * 35.0

    # 2. Volume Score (0 to 30 pts)
    # $0 -> 0 pts, $5k -> 10 pts, $50k -> 20 pts, $250k+ -> 30 pts
    if volume <= 0:
        volume_pts = 0.0
    else:
        norm_vol = min(1.0, math.log10(1 + volume) / 5.4)
        volume_pts = norm_vol * 30.0

    # 3. Spread Score (0 to 20 pts)
    # Spread <= 0.01 (1 cent) -> 20 pts; Spread >= 0.15 (15 cents) -> 0 pts
    if spread <= 0:
        spread_pts = 18.0  # Assumed decent if spread not reported but liquid
    elif spread <= 0.01:
        spread_pts = 20.0
    elif spread >= 0.15:
        spread_pts = 0.0
    else:
        spread_pts = max(0.0, 20.0 * (1.0 - (spread - 0.01) / 0.14))

    # 4. Time to Resolution & Activity (0 to 15 pts)
    # Markets resolving within 3 to 180 days are ideal for near-term intelligence
    time_pts = 10.0
    if end_date:
        end_date_utc = end_date.replace(tzinfo=timezone.utc) if end_date.tzinfo is None else end_date.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)
        days_left = (end_date_utc - now_utc).total_seconds() / 86400.0
        if days_left < 0:
            time_pts = 5.0  # Already ended / in resolution
        elif days_left <= 1.0:
            time_pts = 15.0 # Imminent resolution (highest price discovery)
        elif days_left <= 30.0:
            time_pts = 13.0
        elif days_left <= 180.0:
            time_pts = 10.0
        else:
            time_pts = 6.0  # Distant speculative market (>6 months)

    total_score = liquidity_pts + volume_pts + spread_pts + (time_pts * activity_score)
    return round(min(100.0, max(0.0, total_score)), 1)
