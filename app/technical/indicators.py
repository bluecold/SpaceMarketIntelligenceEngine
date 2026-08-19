from typing import Dict, Any, Optional
import pandas as pd
import numpy as np


def calculate_technical_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Computes technical indicators on daily OHLCV DataFrame:
    EMA200, RSI14, Bollinger Bands 20/2, MACD, Volume MA20, ATR14.
    """
    if df is None or df.empty or len(df) < 5 or 'Close' not in df.columns:
        return {
            "price": None, "volume": None, "ema200": None, "rsi14": None,
            "bollinger_upper": None, "bollinger_middle": None, "bollinger_lower": None,
            "macd_line": None, "macd_signal": None, "macd_histogram": None,
            "volume_ma20": None, "volume_ratio": None, "atr": None, "status": "DATA_UNAVAILABLE"
        }

    close = df['Close']
    volume = df['Volume']
    latest_price = float(close.iloc[-1])
    latest_volume = float(volume.iloc[-1])

    # 1. EMA200 (if insufficient periods, fall back to EMA of available periods)
    ema_period = min(200, len(df))
    ema200 = float(close.ewm(span=ema_period, adjust=False).mean().iloc[-1])

    # 2. RSI 14
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi_series = 100 - (100 / (1 + rs))
    rsi14 = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else 50.0

    # 3. Bollinger Bands (20, 2)
    bb_window = min(20, len(df))
    bollinger_middle = float(close.rolling(window=bb_window).mean().iloc[-1])
    std = float(close.rolling(window=bb_window).std().iloc[-1])
    bollinger_upper = bollinger_middle + 2.0 * std
    bollinger_lower = bollinger_middle - 2.0 * std

    # 4. MACD (12, 26, 9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    macd_histogram = macd_line - macd_signal
    
    latest_macd_line = float(macd_line.iloc[-1])
    latest_macd_signal = float(macd_signal.iloc[-1])
    latest_macd_hist = float(macd_histogram.iloc[-1])

    # 5. Volume MA20 & Ratio
    vol_window = min(20, len(df))
    volume_ma20 = float(volume.rolling(window=vol_window).mean().iloc[-1])
    volume_ratio = latest_volume / volume_ma20 if volume_ma20 > 0 else 1.0

    # 6. ATR 14
    high = df['High'] if 'High' in df.columns else close
    low = df['Low'] if 'Low' in df.columns else close
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = float(tr.rolling(window=min(14, len(df))).mean().iloc[-1])

    return {
        "price": round(latest_price, 2),
        "volume": latest_volume,
        "ema200": round(ema200, 2),
        "rsi14": round(rsi14, 2),
        "bollinger_upper": round(bollinger_upper, 2),
        "bollinger_middle": round(bollinger_middle, 2),
        "bollinger_lower": round(bollinger_lower, 2),
        "macd_line": round(latest_macd_line, 4),
        "macd_signal": round(latest_macd_signal, 4),
        "macd_histogram": round(latest_macd_hist, 4),
        "volume_ma20": round(volume_ma20, 2),
        "volume_ratio": round(volume_ratio, 2),
        "atr": round(atr14, 2),
        "status": "AVAILABLE"
    }
