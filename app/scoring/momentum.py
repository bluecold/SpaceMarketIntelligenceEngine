from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from app.config import settings

# Points added/removed by the EMA200 trend filter (price above/below the long-term trend)
TREND_FILTER_POINTS = 10.0


def calculate_momentum_score(
    indicators: Dict[str, Any],
    raw_df: Optional[pd.DataFrame] = None,
    at_index: Optional[int] = None
) -> Optional[float]:
    """
    Computes the Market Momentum pillar (0 to 100) as technical *context* for a sentiment-driven SMI.

    Components:
      - EMA200 trend filter: +/-10 for price above/below the EMA200 (binary, scale invariant), skipped
        when the EMA200 is not reliable (short price history).
      - Direction-aware volume confirmation: heavy volume adds up to +10 on up days and subtracts up to
        10 on down days; thin volume (< 0.8x) subtracts 5.
      - Overextension penalty: RSI above 75 subtracts 1.5 points per RSI point.

    Why not trend-following returns: on 2 years of daily prices for the covered tickers (1,756 bars,
    Oct 2026 review) the previous 1/3/5-day return term had ~0 rank correlation with forward 1-5 day
    returns, and the linear EMA200 distance had a negative one (-0.13 within ticker at 3 days). No variant
    showed positive predictive power, so the pillar is kept small (WEIGHT_MOMENTUM = 0.10) and
    low-variance (std ~9 points instead of ~22) so it frames the sentiment pillars instead of driving the SMI.

    Supports `at_index` slicing for historical backtesting parity without lookahead bias.
    """
    if indicators.get("status") != "AVAILABLE" or indicators.get("price") is None:
        return None

    price = indicators.get("price", 0.0)
    ema200 = indicators.get("ema200")
    rsi = indicators.get("rsi14", 50.0)
    vol_ratio = indicators.get("volume_ratio", 1.0)

    score = 50.0

    # 1. EMA200 trend filter (binary)
    if ema200 and ema200 > 0 and indicators.get("ema200_reliable", True):
        score += TREND_FILTER_POINTS if price >= ema200 else -TREND_FILTER_POINTS

    # 2. Direction of the latest session, used to sign the volume confirmation
    is_falling = False
    if raw_df is not None:
        df_slice = raw_df.iloc[: at_index + 1] if at_index is not None else raw_df
        if len(df_slice) >= 2:
            close = df_slice['Close']
            is_falling = bool(close.iloc[-1] < close.iloc[-2])
    else:
        p_chg = indicators.get("price_change_1d")
        if p_chg is not None and p_chg < 0:
            is_falling = True

    # 3. Volume confirmation: high volume confirms the day's direction (accumulation vs distribution)
    if vol_ratio is not None:
        if vol_ratio >= settings.VOLUME_RATIO_INSTITUTIONAL_BUY:
            vol_delta = min(10.0, (vol_ratio - 1.0) * 8.0)
            if is_falling:
                score -= vol_delta
            else:
                score += vol_delta
        elif vol_ratio < settings.VOLUME_RATIO_WEAKNESS:
            score -= 5.0

    # 4. Overbought penalty (extreme RSI > 75 dampens momentum quality)
    if rsi and rsi > 75.0:
        overbought_excess = rsi - 75.0
        score -= overbought_excess * 1.5

    return round(float(np.clip(score, 0.0, 100.0)), 1)
