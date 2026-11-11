"""
Price chart payload: daily candles with objective overlays (EMA200, Bollinger 20/2, 52-week range).

Display context only. Nothing here feeds the SMI, the signal or the gates, and the module draws
no support/resistance levels of its own: those are left to the reader's eye.
"""
from bisect import bisect_left
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

EMA_SPAN = 200          # Same rule as app/technical/indicators.py: no EMA200 before 200 bars
BOLLINGER_WINDOW = 20
BOLLINGER_STD = 2.0
YEAR_BARS = 252         # Trading sessions in the 52-week range

BEARISH_BANDS = {"CAUTION", "AVOID", "STRONG_AVOID"}
BULLISH_BANDS = {"WATCH", "BUY", "STRONG_BUY"}


def _round(value: Any, digits: int = 4) -> Optional[float]:
    return None if value is None or pd.isna(value) else round(float(value), digits)


def build_candles(bars: Sequence[Any], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Candles (oldest first) with overlays computed over the full stored history, then trimmed
    to the last `limit` bars. Each overlay value at bar i uses bars 0..i only.
    The EMA200 runs over every stored bar, so it can differ slightly from the snapshot value,
    which the pipeline computes over the 1-year window it downloads.
    """
    if not bars:
        return []
    close = pd.Series([b.close for b in bars], dtype="float64")
    ema = close.ewm(span=EMA_SPAN, adjust=False).mean()
    mid = close.rolling(BOLLINGER_WINDOW).mean()
    std = close.rolling(BOLLINGER_WINDOW).std()

    candles = []
    for i, b in enumerate(bars):
        has_bands = not pd.isna(std.iloc[i])
        candles.append({
            "time": b.date,
            "open": _round(b.open), "high": _round(b.high), "low": _round(b.low), "close": _round(b.close),
            "volume": _round(b.volume, 0),
            "ema200": _round(ema.iloc[i]) if i >= EMA_SPAN - 1 else None,
            "bb_upper": _round(mid.iloc[i] + BOLLINGER_STD * std.iloc[i]) if has_bands else None,
            "bb_middle": _round(mid.iloc[i]) if has_bands else None,
            "bb_lower": _round(mid.iloc[i] - BOLLINGER_STD * std.iloc[i]) if has_bands else None,
        })
    return candles[-limit:] if limit else candles


def build_levels(bars: Sequence[Any]) -> Dict[str, Any]:
    """52-week high/low over the last YEAR_BARS sessions, and how many sessions back them."""
    window = list(bars)[-YEAR_BARS:]
    if not window:
        return {"high_52w": None, "low_52w": None, "range_sessions": 0}
    return {
        "high_52w": _round(max(b.high for b in window)),
        "low_52w": _round(min(b.low for b in window)),
        "range_sessions": len(window),
    }


def snap_to_session(day: str, session_dates: Sequence[str]) -> Optional[str]:
    """First session on or after `day` (a weekend headline lands on Monday's bar); None if there is none yet."""
    i = bisect_left(session_dates, day)
    return session_dates[i] if i < len(session_dates) else None


def build_markers(
    session_dates: Sequence[str],
    daily_bands: Sequence[tuple],
    catalyst_days: Sequence[Dict[str, Any]],
    earnings_dates: Sequence[str],
) -> List[Dict[str, Any]]:
    """
    Events to pin on the candles, oldest first:
    - SIGNAL: the day's closing band differs from the previous day's (`daily_bands` = [(day, band), ...]).
    - CATALYST: bearish catalyst headlines, one per session and category.
    - EARNINGS: report dates the pipeline recorded.
    Markers outside the visible sessions are dropped.
    """
    if not session_dates:
        return []
    first = session_dates[0]
    markers: List[Dict[str, Any]] = []

    prev_band = None
    for day, band in daily_bands:
        if band and prev_band and band != prev_band:
            when = snap_to_session(day, session_dates)
            if when and day >= first:
                direction = "BEARISH" if band in BEARISH_BANDS else "BULLISH" if band in BULLISH_BANDS else "NEUTRAL"
                markers.append({"time": when, "kind": "SIGNAL", "label": band, "direction": direction,
                                "text": f"Signal band {prev_band} -> {band}"})
        if band:
            prev_band = band

    seen = set()
    for item in catalyst_days:
        when = snap_to_session(item["day"], session_dates) if item["day"] >= first else None
        key = (when, item["catalyst"])
        if when and key not in seen:
            seen.add(key)
            markers.append({"time": when, "kind": "CATALYST", "label": item["catalyst"], "direction": "BEARISH",
                            "text": item.get("title") or item["catalyst"]})

    for day in sorted(set(earnings_dates)):
        if day in session_dates:
            markers.append({"time": day, "kind": "EARNINGS", "label": "EARNINGS", "direction": "NEUTRAL",
                            "text": "Earnings report date"})

    markers.sort(key=lambda m: m["time"])
    return markers
