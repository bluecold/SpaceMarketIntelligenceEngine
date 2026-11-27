"""Event study: abnormal returns around SEC offering filings (dilution). Read-only; never writes to the database.

Question: does an OFFERING filing (424B1/2/4/5) predict a negative abnormal return? The answer decides phase 2
of the EDGAR monitor (turning the informational SEC OFFERING modifier into a gate). The criteria below were fixed
in PROJECT_CONTEXT.md (section 5, 27/11/2026) before the first run; change them only with a reason recorded there.

- Events: OFFERING filings per sec_forms.classify_filing. Filings of one ticker less than EPISODE_GAP sessions
  apart form one episode dated at the first (preliminary + final prospectus of one deal count once). An episode
  without a close before it (an IPO) is skipped. SHELF / UNREGISTERED_SALE / RESALE are reported as description.
- Timing: acceptanceDateTime is UTC (checked against EDGAR's 06:00-22:00 ET window). Day 0 is the first session
  whose 16:00 New York close comes after the acceptance; the reference price is the last close before it.
- Abnormal return: ticker return minus the mean return of the other tickers that trade on both dates.
- Decision: MIN_EPISODES episodes in MIN_TICKERS tickers; then mean CAR[0,+2] < 0 with the bootstrap 95% CI below
  zero, negative when dropping any single ticker, and a negative median -> SUPPORTS_GATE.

Events come from the full EDGAR submissions index when SEC_USER_AGENT is set (more history), otherwise from the
sec_filings table (about one year). Usage, from the repo root:
    python -m audit.sentiment_2026_10.event_study_sec [--source db|edgar]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from audit.sentiment_2026_10._common import OUTPUT_DIR, TICKERS, connect_readonly
from audit.sentiment_2026_10._ic_stats import complete_bars, session_close_times

EPISODE_GAP = 5            # sessions; closer filings of one ticker are the same deal
WINDOWS = {"CAR[-5,-1]": (-5, -1), "CAR[0]": (0, 0), "CAR[0,+2]": (0, 2), "CAR[0,+9]": (0, 9)}
PRIMARY = "CAR[0,+2]"
MIN_EPISODES = 20
MIN_TICKERS = 3
BOOTSTRAP_SAMPLES = 5000
SEED = 7
CATEGORIES = ("OFFERING", "SHELF", "UNREGISTERED_SALE", "RESALE")


# --- Data ---------------------------------------------------------------------------------------------

def load_filings_db() -> List[dict]:
    con = connect_readonly()
    try:
        rows = con.execute("SELECT ticker, form, items, category, filed_date, accepted_at FROM sec_filings "
                           "WHERE source = 'LIVE' OR source IS NULL").fetchall()
    finally:
        con.close()
    out = []
    for t, form, items, cat, filed, acc in rows:
        ts = pd.Timestamp(acc).to_pydatetime() if acc else pd.Timestamp(filed + " 21:00").to_pydatetime()
        out.append({"ticker": t, "form": form, "items": items, "category": cat, "accepted_at": ts})
    return out


def load_filings_edgar() -> List[dict]:
    from app.collectors.sec_edgar_provider import EdgarSecProvider
    from app.config import INITIAL_TICKERS, settings
    settings.SEC_HISTORY_DAYS = 3650  # whatever the submissions index still lists (~1,000 newest filings)
    provider = EdgarSecProvider()
    if not provider.enabled:
        raise SystemExit("SEC_USER_AGENT is not set: use --source db or set it in .env")

    async def _all():
        out = []
        for cfg in INITIAL_TICKERS:
            res = await provider.fetch_filings(cfg.symbol, cik=getattr(cfg, "sec_cik", None))
            for f in res.filings or []:
                ts = f.accepted_at or pd.Timestamp(f.filed_date + " 21:00").to_pydatetime()
                out.append({"ticker": f.ticker, "form": f.form, "items": f.items, "category": f.category,
                            "accepted_at": ts})
        return out
    return asyncio.run(_all())


def load_closes(now_utc: datetime) -> Dict[str, pd.Series]:
    import yfinance as yf
    closes = {}
    for tk in TICKERS:
        df = yf.Ticker(tk).history(period="5y", interval="1d")
        s = df["Close"].dropna()
        s.index = pd.DatetimeIndex([pd.Timestamp(d).tz_localize(None).normalize() for d in s.index])
        closes[tk] = complete_bars(s, now_utc)
    return closes


# --- Event math (pure) --------------------------------------------------------------------------------

def day_zero(close_times: np.ndarray, accepted_utc: datetime) -> Optional[int]:
    """Position of the first bar whose close is strictly after the acceptance; None if none or no prior bar."""
    pos = int(np.searchsorted(close_times, np.datetime64(accepted_utc, "us"), side="right"))
    return pos if 0 < pos < len(close_times) else None


def episodes(filings: List[dict], closes: Dict[str, pd.Series], category: str) -> List[dict]:
    """One event per deal: filings of one ticker less than EPISODE_GAP sessions apart collapse to the first."""
    out = []
    for tk, s in closes.items():
        if s is None or s.empty:
            continue
        ct = session_close_times(s.index)
        pts = sorted((f for f in filings if f["ticker"] == tk and f["category"] == category),
                     key=lambda f: f["accepted_at"])
        last_pos = None
        for f in pts:
            acc = f["accepted_at"]
            if acc.tzinfo is not None:
                acc = acc.astimezone(timezone.utc).replace(tzinfo=None)
            p = day_zero(ct, acc)
            raw_pos = int(np.searchsorted(ct, np.datetime64(acc, "us"), side="right"))
            if last_pos is not None and raw_pos - last_pos < EPISODE_GAP:
                continue
            last_pos = raw_pos
            if p is None:
                continue  # no close before it (IPO) or after it (too recent)
            out.append({"ticker": tk, "pos": p, "date": s.index[p].date().isoformat(), "form": f["form"],
                        "accepted_at": acc.isoformat()})
    return out


def car(closes: Dict[str, pd.Series], ticker: str, pos: int, a: int, b: int) -> Optional[float]:
    """Cumulative abnormal return from the close before session pos+a to the close of session pos+b."""
    s = closes[ticker]
    i0, i1 = pos + a - 1, pos + b
    if i0 < 0 or i1 >= len(s):
        return None
    d0, d1 = s.index[i0], s.index[i1]
    own = float(s.iloc[i1] / s.iloc[i0] - 1.0)
    basket = [float(o.loc[d1] / o.loc[d0] - 1.0) for t, o in closes.items()
              if t != ticker and d0 in o.index and d1 in o.index]
    if not basket:
        return None
    return own - float(np.mean(basket))


def bootstrap_ci(x: np.ndarray, samples: int = BOOTSTRAP_SAMPLES, seed: int = SEED) -> tuple:
    rng = np.random.default_rng(seed)
    means = rng.choice(x, size=(samples, len(x)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(events: List[dict], window: str) -> dict:
    vals = [(e["ticker"], e[window]) for e in events if e.get(window) is not None]
    x = np.array([v for _, v in vals])
    res = {"window": window, "n": int(len(x)), "tickers": sorted({t for t, _ in vals})}
    if len(x) < 2:
        return res
    lo, hi = bootstrap_ci(x)
    loo = {}
    for t in res["tickers"]:
        rest = np.array([v for tk, v in vals if tk != t])
        loo[t] = float(rest.mean()) if len(rest) else None
    res.update({"mean": float(x.mean()), "median": float(np.median(x)), "std": float(x.std(ddof=1)),
                "share_negative": float((x < 0).mean()), "ci95": [lo, hi], "leave_one_ticker_out_mean": loo})
    return res


def verdict(primary: dict) -> str:
    if primary["n"] < MIN_EPISODES or len(primary["tickers"]) < MIN_TICKERS:
        return "INSUFFICIENT_DATA"
    loo_ok = all(v is not None and v < 0 for v in primary["leave_one_ticker_out_mean"].values())
    if primary["mean"] < 0 and primary["ci95"][1] < 0 and loo_ok and primary["median"] < 0:
        return "SUPPORTS_GATE"
    if primary["ci95"][0] > 0:
        return "POSITIVE_REACTION"
    return "NOT_SIGNIFICANT"


def unconditional(closes: Dict[str, pd.Series], a: int, b: int, step: int = 3) -> dict:
    """Abnormal return over the same window on every `step`-th session of every ticker, as context."""
    vals = []
    for tk, s in closes.items():
        for p in range(max(1, -a + 1), len(s) - b, step):
            v = car(closes, tk, p, a, b)
            if v is not None:
                vals.append(v)
    x = np.array(vals)
    return {"n": int(len(x)), "mean": float(x.mean()), "std": float(x.std(ddof=1))} if len(x) > 1 else {"n": 0}


# --- Main ---------------------------------------------------------------------------------------------

def pct(v):
    return "   n/a" if v is None else f"{100 * v:+6.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["auto", "db", "edgar"], default="auto")
    args = ap.parse_args()
    from app.config import settings
    source = args.source
    if source == "auto":
        source = "edgar" if getattr(settings, "SEC_USER_AGENT", "") else "db"
    filings = load_filings_edgar() if source == "edgar" else load_filings_db()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    closes = load_closes(now)
    first = min(f["accepted_at"] for f in filings).date() if filings else None
    print(f"Filings: {len(filings)} from {source} (since {first}); prices to {max(s.index[-1] for s in closes.values()).date()}")

    report = {"generated_at": now.isoformat() + "Z", "source": source, "criteria": {
        "episode_gap_sessions": EPISODE_GAP, "primary_window": PRIMARY, "min_episodes": MIN_EPISODES,
        "min_tickers": MIN_TICKERS, "bootstrap_samples": BOOTSTRAP_SAMPLES}, "categories": {}}
    for cat in CATEGORIES:
        evs = episodes(filings, closes, cat)
        for e in evs:
            for w, (a, b) in WINDOWS.items():
                e[w] = car(closes, e["ticker"], e["pos"], a, b)
        sums = {w: summarize(evs, w) for w in WINDOWS}
        per_ticker = defaultdict(int)
        for e in evs:
            per_ticker[e["ticker"]] += 1
        entry = {"episodes": len(evs), "per_ticker": dict(per_ticker), "windows": sums,
                 "events": [{k: v for k, v in e.items() if k != "pos"} for e in evs]}
        if cat == "OFFERING":
            entry["verdict"] = verdict(sums[PRIMARY])
        report["categories"][cat] = entry

        print(f"\n== {cat}: {len(evs)} episodes {dict(per_ticker)}" + (f"  -> {entry['verdict']}" if cat == "OFFERING" else ""))
        for w, r in sums.items():
            if r["n"] < 2:
                print(f"  {w:11s} n={r['n']}")
                continue
            print(f"  {w:11s} n={r['n']:3d} mean {pct(r['mean'])} median {pct(r['median'])} "
                  f"neg {100 * r['share_negative']:4.0f}%  CI95 [{pct(r['ci95'][0])}, {pct(r['ci95'][1])}]"
                  + ("  LOO " + " ".join(f"{t}:{pct(v).strip()}" for t, v in r["leave_one_ticker_out_mean"].items())
                     if w == PRIMARY else ""))
        if cat == "OFFERING":
            for e in evs:
                print(f"    {e['ticker']} {e['date']} {e['form']:6s} " + " ".join(f"{w} {pct(e[w])}" for w in WINDOWS))

    report["unconditional"] = {w: unconditional(closes, a, b) for w, (a, b) in WINDOWS.items()}
    print("\nUnconditional abnormal return (every 3rd session, all tickers): " +
          "; ".join(f"{w} mean {pct(r.get('mean'))} sd {pct(r.get('std'))}" for w, r in report["unconditional"].items()))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"event_study_sec_{now.date().isoformat()}.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved {path.relative_to(OUTPUT_DIR.parents[1])}")


if __name__ == "__main__":
    main()
