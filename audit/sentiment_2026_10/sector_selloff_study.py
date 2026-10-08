"""
Measures whether a sector-wide selloff predicts the next days' returns, before adding a "SECTOR SELLOFF"
signal modifier (pending step 3 of the Oct 2026 review).

Basket: equal-weight daily return of the covered tickers trading that day (at least 3). For each ticker-day it
reports the rank correlation (IC) of the trailing basket return with the ticker's forward 1/3/5/10-day return,
and an event study on selloff episodes. Tickers fall together on the same dates, so the event study uses
episodes (first trigger day, then a cooldown as long as the horizon) and the basket's forward return per
episode, not ticker-days: otherwise one bad week would count as five to fifteen independent observations.

Features use closes up to day i only; forward returns start at the close of day i (no lookahead).
Downloads prices; never touches the database.

    python -m audit.sentiment_2026_10.sector_selloff_study [--period 5y]
"""
import argparse
import math
import random
import statistics as st

import pandas as pd

from audit.sentiment_2026_10._common import TICKERS, spearman

import yfinance as yf

HORIZONS = (1, 3, 5, 10)
VOL_WINDOW = 60
MIN_NAMES = 3
THRESHOLDS = (-5.0, -8.0, -12.0)  # basket 3-day return, %
Z_THRESHOLDS = (-1.5, -2.0)       # basket 3-day return in units of its trailing 3-day volatility


def load_closes(period: str) -> pd.DataFrame:
    closes = {}
    for tk in TICKERS + ["QQQ"]:
        df = yf.Ticker(tk).history(period=period, interval="1d")
        if df.empty:
            print(f"{tk}: no data")
            continue
        s = df["Close"].dropna()
        s.index = s.index.tz_localize(None).normalize()
        closes[tk] = s
        print(f"{tk}: {len(s)} bars from {s.index[0].date()}")
    return pd.DataFrame(closes).sort_index()


def build_frame(closes: pd.DataFrame) -> pd.DataFrame:
    names = [t for t in TICKERS if t in closes]
    rets = closes[names].pct_change(fill_method=None)
    n_names = rets.notna().sum(axis=1)
    basket_ret = rets.mean(axis=1).where(n_names >= MIN_NAMES)
    basket = (1 + basket_ret.fillna(0)).cumprod().where(basket_ret.notna())

    f = pd.DataFrame(index=closes.index)
    f["basket"] = basket
    f["b3"] = (basket / basket.shift(3) - 1) * 100
    f["b5"] = (basket / basket.shift(5) - 1) * 100
    vol3 = basket_ret.rolling(VOL_WINDOW).std() * math.sqrt(3) * 100
    f["b3z"] = f["b3"] / vol3
    qqq = closes["QQQ"]
    f["b3_ex_qqq"] = f["b3"] - (qqq / qqq.shift(3) - 1) * 100
    # Breadth: share of names down over 3 days
    f["breadth_down"] = (closes[names] / closes[names].shift(3) - 1).lt(0).sum(axis=1) / n_names
    for h in HORIZONS:
        f[f"bfwd{h}"] = (basket.shift(-h) / basket - 1) * 100
    return f, names


def ticker_records(closes: pd.DataFrame, f: pd.DataFrame, names):
    recs = []
    for tk in names:
        c = closes[tk]
        own3 = (c / c.shift(3) - 1) * 100
        for h in HORIZONS:
            f[f"{tk}_fwd{h}"] = (c.shift(-h) / c - 1) * 100
        for pos, d in enumerate(f.index):
            if pd.isna(c.loc[d]) or pd.isna(f.at[d, "b3"]) or pd.isna(f.at[d, "b3z"]):
                continue
            r = {
                "tk": tk, "pos": pos,
                "basket 3d return": f.at[d, "b3"],
                "basket 5d return": f.at[d, "b5"],
                "basket 3d (vol units)": f.at[d, "b3z"],
                "basket 3d minus QQQ": f.at[d, "b3_ex_qqq"],
                "own 3d minus basket": own3.loc[d] - f.at[d, "b3"] if not pd.isna(own3.loc[d]) else None,
            }
            for h in HORIZONS:
                v = f.at[d, f"{tk}_fwd{h}"]
                r[f"fwd{h}"] = None if pd.isna(v) else v
            recs.append(r)
    return recs


def report_ic(recs, names):
    features = [k for k in recs[0] if k not in ("tk", "pos") and not k.startswith("fwd")]
    print(f"\nticker-days: {len(recs)}")
    for h in HORIZONS:
        print(f"\n--- IC with ticker forward {h}d: pooled | mean within ticker | non-overlapping dates (t) ---")
        for feat in features:
            pairs = [(r[feat], r[f"fwd{h}"], r["tk"], r["pos"]) for r in recs if r[feat] is not None and r[f"fwd{h}"] is not None]
            pooled = spearman([p[0] for p in pairs], [p[1] for p in pairs])
            per = [spearman([p[0] for p in pairs if p[2] == t], [p[1] for p in pairs if p[2] == t]) for t in names]
            per = [x for x in per if x is not None]
            no = [p for p in pairs if p[3] % h == 0]
            ic_no = spearman([p[0] for p in no], [p[1] for p in no]) or 0.0
            # Same-date names are correlated: count distinct dates, not ticker-days, for the t-statistic
            n_dates = len({p[3] for p in no})
            t = ic_no * math.sqrt(max(0, n_dates - 2) / max(1e-9, 1 - ic_no ** 2))
            print(f"{feat:26s} {pooled:+.3f} | {st.mean(per):+.3f} | {ic_no:+.3f} (t={t:+.1f}, {n_dates} dates)")


def episodes(mask: pd.Series, cooldown: int):
    """First trigger day of each episode; a new episode needs `cooldown` trading days since the last start."""
    starts, last = [], -10**9
    for pos, flag in enumerate(mask.values):
        if flag and pos - last >= cooldown:
            starts.append(pos)
            last = pos
    return starts


def bootstrap_ci(xs, n=5000, seed=7):
    rnd = random.Random(seed)
    means = sorted(st.mean(rnd.choices(xs, k=len(xs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def report_events(f: pd.DataFrame):
    rules = [(f"basket 3d <= {t:.0f}%", f["b3"] <= t) for t in THRESHOLDS]
    rules += [(f"basket 3d <= {z:.1f} sd", f["b3z"] <= z) for z in Z_THRESHOLDS]
    rules += [("3d <= -8% and >=80% names down", (f["b3"] <= -8) & (f["breadth_down"] >= 0.8))]
    rules += [("3d <= -8% sector-specific (vs QQQ <= -6)", (f["b3"] <= -8) & (f["b3_ex_qqq"] <= -6))]
    valid = f["b3z"].notna()

    for h in HORIZONS:
        col = f[f"bfwd{h}"]
        base = col[valid & col.notna()].iloc[::h]  # non-overlapping unconditional windows
        b_mean = base.mean()
        print(f"\n--- basket forward {h}d after selloff episodes (cooldown {max(h, 3)}d) | unconditional mean {b_mean:+.2f}% "
              f"(n={len(base)}), share negative {100 * (base < 0).mean():.0f}% ---")
        print(f"{'rule':42s} {'n':>3s} {'mean':>7s} {'median':>7s} {'neg%':>5s}  95% CI of mean     excess vs uncond.")
        for label, mask in rules:
            starts = episodes((mask & valid).fillna(False), cooldown=max(h, 3))
            xs = [col.iloc[p] for p in starts if not pd.isna(col.iloc[p])]
            if len(xs) < 5:
                print(f"{label:42s} {len(xs):3d}  (too few episodes)")
                continue
            lo, hi = bootstrap_ci(xs)
            neg = 100 * sum(1 for x in xs if x < 0) / len(xs)
            print(f"{label:42s} {len(xs):3d} {st.mean(xs):+6.2f}% {st.median(xs):+6.2f}% {neg:4.0f}%  [{lo:+.2f}, {hi:+.2f}]   {st.mean(xs) - b_mean:+.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="5y", help="yfinance period (default 5y; SPCX has a short history)")
    args = ap.parse_args()

    closes = load_closes(args.period)
    f, names = build_frame(closes)
    print(f"basket days with >= {MIN_NAMES} names and {VOL_WINDOW}d vol: {int(f['b3z'].notna().sum())}")
    report_ic(ticker_records(closes, f, names), names)
    report_events(f)

    recent = f[["b3", "b3z", "b3_ex_qqq", "breadth_down"]].dropna().tail(8).round(2)
    print("\nrecent basket readings:\n" + recent.to_string())


if __name__ == "__main__":
    main()
