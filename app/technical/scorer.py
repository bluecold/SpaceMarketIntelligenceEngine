from typing import Dict, Any, Optional


def calculate_technical_score(indicators: Dict[str, Any]) -> Optional[float]:
    """
    Evaluates technical indicators and calculates Technical Score (0 to 40 points).
    Returns None if market data is unavailable.
    """
    if not indicators or indicators.get("status") != "AVAILABLE":
        return None

    price = indicators.get("price")
    ema200 = indicators.get("ema200")
    rsi14 = indicators.get("rsi14")
    b_upper = indicators.get("bollinger_upper")
    b_middle = indicators.get("bollinger_middle")
    b_lower = indicators.get("bollinger_lower")
    macd_hist = indicators.get("macd_histogram")
    vol_ratio = indicators.get("volume_ratio")

    if price is None:
        return None

    total_score = 0.0

    # 1. EMA200 (Max 10 points)
    if ema200 is not None:
        if price >= ema200:
            total_score += 10.0
        else:
            total_score += 0.0

    # 2. RSI (Max 10 points)
    if rsi14 is not None:
        if 50.0 <= rsi14 <= 70.0:
            total_score += 10.0
        elif 45.0 <= rsi14 < 50.0:
            total_score += 6.0
        elif 70.0 < rsi14 <= 75.0:
            total_score += 5.0
        elif rsi14 < 45.0:
            total_score += 2.0
        else:  # Overbought > 75
            total_score += 0.0

    # 3. Bollinger Bands (Max 10 points)
    if b_middle is not None and b_upper is not None and b_lower is not None:
        if b_middle <= price <= b_upper:
            total_score += 10.0
        elif b_lower <= price < b_middle:
            total_score += 6.0
        elif price < b_lower:  # Oversold rebound opportunity
            total_score += 4.0
        else:  # Overextended above upper band
            total_score += 2.0

    # 4. MACD (Max 5 points)
    if macd_hist is not None:
        if macd_hist > 0:
            total_score += 5.0
        else:
            # Price / Volatility normalized near-zero consolidation threshold
            atr = indicators.get("atr")
            if atr is not None and atr > 0:
                is_near_zero = (abs(macd_hist) / atr) <= 0.08
            elif price > 0:
                is_near_zero = (abs(macd_hist) / price) <= 0.002  # <= 0.20% of price
            else:
                is_near_zero = abs(macd_hist) <= 0.05

            if is_near_zero:
                total_score += 2.0
            else:
                total_score += 0.0

    # 5. Volume Ratio (Max 5 points)
    if vol_ratio is not None:
        if vol_ratio >= 1.5:
            total_score += 5.0
        elif 1.2 <= vol_ratio < 1.5:
            total_score += 3.0
        else:
            total_score += 1.0

    return min(40.0, round(total_score, 1))
