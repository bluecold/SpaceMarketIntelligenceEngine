"""
Measures whether the momentum pillar predicts forward returns, on 2 years of daily yfinance prices.

Rebuilds the live pillar bar by bar with at_index slicing (no lookahead) and reports the rank correlation (IC)
of the pillar and of its building blocks with 1/3/5-day forward returns: pooled, averaged within ticker, and
on non-overlapping windows with a t-statistic. Downloads prices; never touches the database.

    python -m audit.sentiment_2026_10.momentum_study
"""
import math
import statistics as st

from audit.sentiment_2026_10._common import TICKERS, spearman

import yfinance as yf
from app.scoring.momentum import calculate_momentum_score
from app.technical.indicators import calculate_technical_indicators

HORIZONS = (1, 3, 5)
WARMUP = 60


def main():
    recs = []
    for tk in TICKERS:
        df = yf.Ticker(tk).history(period="2y", interval="1d")[["Open", "High", "Low", "Close", "Volume"]].dropna()
        close = df["Close"].values
        print(f"{tk}: {len(df)} daily bars")
        for i in range(WARMUP, len(df) - max(HORIZONS)):
            ind = calculate_technical_indicators(df, at_index=i)
            if ind.get("price") is None:
                continue
            ind["status"] = "AVAILABLE"
            c = close[: i + 1]
            ema, atr = ind.get("ema200"), ind.get("atr")
            recs.append({
                "tk": tk, "i": i,
                "momentum pillar (live)": calculate_momentum_score(ind, raw_df=df, at_index=i),
                "return 1-5d (weighted)": 0.5 * (c[-1] / c[-2] - 1) + 0.3 * (c[-1] / c[-4] - 1) + 0.2 * (c[-1] / c[-6] - 1),
                "EMA200 distance (ATR units)": (c[-1] - ema) / atr if (ema and atr) else None,
                "above EMA200 (binary)": (1.0 if c[-1] >= ema else 0.0) if ema else None,
                "return 20d": (c[-1] / c[-21] - 1) if i >= 21 else None,
                "rsi14": ind.get("rsi14"),
                **{f"fwd{h}": (close[i + h] / close[i] - 1) * 100 for h in HORIZONS},
            })

    features = [k for k in recs[0] if k not in ("tk", "i") and not k.startswith("fwd")]
    print(f"\nobservations: {len(recs)}")
    for h in HORIZONS:
        print(f"\n--- forward {h}d: IC pooled | mean within ticker | non-overlapping (t) ---")
        for f in features:
            pairs = [(r[f], r[f"fwd{h}"], r["tk"], r["i"]) for r in recs if r[f] is not None]
            pooled = spearman([p[0] for p in pairs], [p[1] for p in pairs])
            per = [spearman([p[0] for p in pairs if p[2] == t], [p[1] for p in pairs if p[2] == t]) for t in TICKERS]
            per = [x for x in per if x is not None]
            no = [p for p in pairs if p[3] % h == 0]
            ic_no = spearman([p[0] for p in no], [p[1] for p in no]) or 0.0
            t = ic_no * math.sqrt((len(no) - 2) / max(1e-9, 1 - ic_no ** 2))
            print(f"{f:30s} {pooled:+.3f} | {st.mean(per):+.3f} | {ic_no:+.3f} (t={t:+.1f})")


if __name__ == "__main__":
    main()
