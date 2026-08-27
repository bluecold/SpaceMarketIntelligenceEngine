from typing import Dict, Any, Optional
import pandas as pd
import numpy as np
from app.config import settings


def calculate_momentum_score(
    indicators: Dict[str, Any],
    raw_df: Optional[pd.DataFrame] = None,
    at_index: Optional[int] = None
) -> Optional[float]:
    """
    Computes Price Momentum Score (0 to 100).
    Evaluates short-term returns (1d, 3d, 5d), distance from EMA200, volume ratio,
    with penalties for extreme RSI / overextension.
    Supports `at_index` slicing for historical backtesting parity without lookahead bias.
    """
    if indicators.get("status") != "AVAILABLE" or indicators.get("price") is None:
        return None

    price = indicators.get("price", 0.0)
    ema200 = indicators.get("ema200")
    rsi = indicators.get("rsi14", 50.0)
    vol_ratio = indicators.get("volume_ratio", 1.0)

    # Base baseline momentum score
    score = 50.0

    # 1. EMA200 Distance
    if ema200 and ema200 > 0:
        dist_pct = ((price - ema200) / ema200) * 100.0
        if dist_pct > 0:
            score += min(20.0, dist_pct * 1.5)
        else:
            score += max(-20.0, dist_pct * 1.5)

    # 2. Short term price returns from dataframe
    if raw_df is not None:
        df_slice = raw_df.iloc[: at_index + 1] if at_index is not None else raw_df
        if len(df_slice) >= 6:
            close = df_slice['Close']
            ret_1d = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100.0
            ret_3d = ((close.iloc[-1] - close.iloc[-4]) / close.iloc[-4]) * 100.0
            ret_5d = ((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6]) * 100.0
            
            weighted_ret = (0.5 * ret_1d) + (0.3 * ret_3d) + (0.2 * ret_5d)
            score += np.clip(weighted_ret * 2.0, -25.0, 25.0)

    # 3. Volume confirmation (Option A: Institutional confirmation >= 1.2x, weakness penalty < 0.8x)
    if vol_ratio is not None:
        if vol_ratio >= settings.VOLUME_RATIO_INSTITUTIONAL_BUY:
            score += min(10.0, (vol_ratio - 1.0) * 8.0)
        elif vol_ratio < settings.VOLUME_RATIO_WEAKNESS:
            score -= 5.0

    # 4. Overbought Penalty (extreme RSI > 75 dampens momentum quality)
    if rsi and rsi > 75.0:
        overbought_excess = rsi - 75.0
        score -= overbought_excess * 1.5

    return round(float(np.clip(score, 0.0, 100.0)), 1)
