from typing import Dict, Any, Optional
import pandas as pd
import numpy as np


def calculate_risk_score(
    indicators: Dict[str, Any],
    raw_df: Optional[pd.DataFrame] = None,
    at_index: Optional[int] = None
) -> Optional[float]:
    """
    Computes Risk Score (0 to 100, where higher = safer/lower risk, lower = extreme risk/volatility).
    Evaluates ATR normalized by price, 30-day volatility, and rolling drawdown.
    Supports `at_index` slicing for historical backtesting parity without lookahead bias.
    """
    if indicators.get("status") != "AVAILABLE" or indicators.get("price") is None:
        return None

    price = indicators.get("price", 1.0)
    atr = indicators.get("atr", 0.0)

    # Base baseline risk score (50 = moderate risk)
    safety_score = 50.0

    # 1. Normalized ATR (ATR / Price)
    if price > 0 and atr is not None:
        atr_pct = (atr / price) * 100.0
        # If ATR% is high (> 6% daily move), safety drops
        if atr_pct > 8.0:
            safety_score -= 25.0
        elif atr_pct > 5.0:
            safety_score -= 15.0
        elif atr_pct < 2.5:
            safety_score += 15.0

    # 2. Historical 30-day Volatility & Drawdown
    if raw_df is not None:
        df_slice = raw_df.iloc[: at_index + 1] if at_index is not None else raw_df
        if len(df_slice) >= 30:
            close = df_slice['Close'].tail(30)
            daily_returns = close.pct_change().dropna()
            ann_vol = daily_returns.std() * np.sqrt(252) * 100.0
            
            # Volatility assessment
            if ann_vol > 80.0:
                safety_score -= 20.0
            elif ann_vol > 50.0:
                safety_score -= 10.0
            elif ann_vol < 30.0:
                safety_score += 15.0

            # Drawdown assessment from 30d high
            max_30d = close.max()
            current = close.iloc[-1]
            drawdown_pct = ((max_30d - current) / max_30d) * 100.0
            if drawdown_pct > 25.0:
                safety_score -= 15.0

    return round(float(np.clip(safety_score, 0.0, 100.0)), 1)
