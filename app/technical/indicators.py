from typing import Dict, Any, Optional
import pandas as pd
import numpy as np


def calculate_technical_indicators(df: pd.DataFrame, at_index: Optional[int] = None) -> Dict[str, Any]:
    """
    Computes technical indicators on daily OHLCV DataFrame:
    EMA200, RSI14, Bollinger Bands 20/2, MACD, Volume MA20, ATR14.

    Supports slice-based evaluation at any historical index `at_index` (0-indexed)
    to guarantee 100% mathematical parity between live execution and backtesting
    without lookahead bias.
    """
    if df is None or df.empty or 'Close' not in df.columns:
        return {
            "price": None, "volume": None, "ema200": None, "rsi14": None,
            "bollinger_upper": None, "bollinger_middle": None, "bollinger_lower": None,
            "macd_line": None, "macd_signal": None, "macd_histogram": None,
            "volume_ma20": None, "volume_ratio": None, "atr": None, "status": "DATA_UNAVAILABLE"
        }

    # Slice DataFrame up to at_index (inclusive) to prevent lookahead bias
    if at_index is not None:
        if at_index < 0:
            at_index = len(df) + at_index
        if at_index < 0 or at_index >= len(df):
            return {
                "price": None, "volume": None, "ema200": None, "rsi14": None,
                "bollinger_upper": None, "bollinger_middle": None, "bollinger_lower": None,
                "macd_line": None, "macd_signal": None, "macd_histogram": None,
                "volume_ma20": None, "volume_ratio": None, "atr": None, "status": "DATA_UNAVAILABLE"
            }
        df_eval = df.iloc[: at_index + 1]
    else:
        df_eval = df

    if len(df_eval) < 5:
        return {
            "price": None, "volume": None, "ema200": None, "rsi14": None,
            "bollinger_upper": None, "bollinger_middle": None, "bollinger_lower": None,
            "macd_line": None, "macd_signal": None, "macd_histogram": None,
            "volume_ma20": None, "volume_ratio": None, "atr": None, "status": "DATA_UNAVAILABLE"
        }

    close = df_eval['Close']
    volume = df_eval['Volume']
    latest_price = float(close.iloc[-1])
    latest_volume = float(volume.iloc[-1])

    # 1. EMA200 (strictly requires at least 200 daily periods for statistical validity)
    if len(df_eval) >= 200:
        ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
        ema200_reliable = True
    else:
        ema200 = None
        ema200_reliable = False

    # 2. RSI 14 (Wilder's Smoothing Moving Average / RMA)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    
    rsi_period = min(14, max(2, len(df_eval) - 1))
    avg_gain = gain.ewm(alpha=1.0 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    
    last_gain = avg_gain.iloc[-1]
    last_loss = avg_loss.iloc[-1]
    
    if pd.isna(last_gain) or pd.isna(last_loss) or (last_gain == 0 and last_loss == 0):
        rsi14 = 50.0
    elif last_loss == 0:
        rsi14 = 100.0
    else:
        rs = last_gain / last_loss
        rsi14 = 100.0 - (100.0 / (1.0 + rs))

    # 3. Bollinger Bands (20, 2)
    bb_window = min(20, len(df_eval))
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
    vol_window = min(20, len(df_eval))
    volume_ma20 = float(volume.rolling(window=vol_window).mean().iloc[-1])
    volume_ratio = latest_volume / volume_ma20 if volume_ma20 > 0 else 1.0

    # 6. ATR 14 (Wilder's Smoothing)
    high = df_eval['High'] if 'High' in df_eval.columns else close
    low = df_eval['Low'] if 'Low' in df_eval.columns else close
    prev_close = close.shift(1)
    
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr_period = min(14, max(1, len(df_eval)))
    atr_series = tr.ewm(alpha=1.0 / atr_period, min_periods=atr_period, adjust=False).mean()
    atr14 = float(atr_series.iloc[-1]) if not pd.isna(atr_series.iloc[-1]) else float(tr.iloc[-1])

    # 7. Support & Resistance Pivots (Fixed 100-bar Lookback Window for 100% Live/Backtest Parity)
    sr_window = min(100, len(df_eval))
    recent_highs = high.tail(sr_window)
    recent_lows = low.tail(sr_window)
    
    resistance_levels = recent_highs[recent_highs > latest_price]
    nearest_resistance = float(resistance_levels.min()) if not resistance_levels.empty else round(latest_price * 1.05, 2)
    
    support_levels = recent_lows[recent_lows < latest_price]
    nearest_support = float(support_levels.max()) if not support_levels.empty else round(latest_price * 0.95, 2)

    # 8. Candlestick Anatomy & Conviction Scoring (Precedence: Doji first -> Strong +/-1.0 -> Moderate +/-0.5)
    open_p = float(df_eval['Open'].iloc[-1]) if 'Open' in df_eval.columns else latest_price
    candle_range = float(high.iloc[-1] - low.iloc[-1])
    candle_body = float(latest_price - open_p)
    pct_body = (abs(candle_body) / candle_range) if candle_range > 0 else 0.0
    
    if pct_body < 0.15 or candle_range == 0 or pd.isna(pct_body):
        candle_score = 0.0
        candle_label = "Doji / Indecisión neutra"
    elif candle_body > 0 and pct_body >= 0.55:
        candle_score = 1.0
        candle_label = "Alcista fuerte (impulso)"
    elif candle_body > 0:
        candle_score = 0.5
        candle_label = "Alcista moderada"
    elif candle_body < 0 and pct_body >= 0.55:
        candle_score = -1.0
        candle_label = "Bajista fuerte (impulso)"
    else:
        candle_score = -0.5
        candle_label = "Bajista moderada"

    # 9. Risk:Reward Ratio Gate (Reward to nearest resistance vs Risk to nearest support >= 1.5x)
    reward_room = nearest_resistance - latest_price
    sl_dist = latest_price - nearest_support
    passes_rr_gate = bool(reward_room >= sl_dist * 1.5) if sl_dist > 0 else True

    return {
        "price": round(latest_price, 2),
        "volume": latest_volume,
        "ema200": round(ema200, 2) if (ema200 is not None and not pd.isna(ema200)) else None,
        "ema200_reliable": ema200_reliable,
        "rsi14": round(rsi14, 2) if not pd.isna(rsi14) else 50.0,
        "bollinger_upper": round(bollinger_upper, 2) if not pd.isna(bollinger_upper) else None,
        "bollinger_middle": round(bollinger_middle, 2) if not pd.isna(bollinger_middle) else None,
        "bollinger_lower": round(bollinger_lower, 2) if not pd.isna(bollinger_lower) else None,
        "macd_line": round(latest_macd_line, 4) if not pd.isna(latest_macd_line) else 0.0,
        "macd_signal": round(latest_macd_signal, 4) if not pd.isna(latest_macd_signal) else 0.0,
        "macd_histogram": round(latest_macd_hist, 4) if not pd.isna(latest_macd_hist) else 0.0,
        "volume_ma20": round(volume_ma20, 2) if not pd.isna(volume_ma20) else latest_volume,
        "volume_ratio": round(volume_ratio, 2) if not pd.isna(volume_ratio) else 1.0,
        "atr": round(atr14, 2) if not pd.isna(atr14) else 0.0,
        "nearest_support": round(nearest_support, 2),
        "nearest_resistance": round(nearest_resistance, 2),
        "candle_score": candle_score,
        "candle_label": candle_label,
        "passes_rr_gate": passes_rr_gate,
        "status": "AVAILABLE"
    }
