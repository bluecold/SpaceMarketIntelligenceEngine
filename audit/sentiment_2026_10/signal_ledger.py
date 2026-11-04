"""
Settles every stored signal against what the price did next, idea taken from TradingAgents' decision log
(TauricResearch/TradingAgents: each decision is scored on realized alpha from the first close after it,
grouped by rating). Here it is deterministic and read-only, and it answers what the pillar IC study does
not: does the *final* signal the user sees work, and do the gates and modifiers mark worse outcomes?

Unlike `pillar_ic_and_composition.py`, nothing is replayed: it reads the `base_signal`, `signal_modifier`
and `smi` stored in each snapshot, i.e. exactly what the engine emitted at the time. Returns use the same
rules as the IC study (`_ic_stats.py`): entry at the first regular-session close after the snapshot, return
in excess of the other tickers' equal-weight basket, one observation per ticker and entry close.

Reports per horizon:
  1. band ordering: IC verdict of the band rank (STRONG AVOID=0 .. STRONG BUY=6) against excess return;
  2. per-band ledger: count, mean excess return, share positive, block-bootstrap CI (descriptive);
  3. per-modifier effect: LOWER / HIGHER / NO_DIFFERENCE / INSUFFICIENT_DATA (`evaluate_flag`): flagged vs
     unflagged snapshots of the same tickers. A bearish gate earns its place only with LOWER;
  4. binding gates: snapshots where a gate actually lowered the band the SMI alone would give.

    python -m audit.sentiment_2026_10.signal_ledger [--min-rules-version 2.2.3] [--since 2026-11-02]

Read-only on the database; the summary (no post data) is written to audit/output/signal_ledger_<date>.json.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from audit.sentiment_2026_10._common import OUTPUT_DIR, TICKERS, connect_readonly
from audit.sentiment_2026_10._ic_stats import (
    BOOTSTRAP_SAMPLES, CONFIDENCE, block_bootstrap_ci, complete_bars, evaluate_flag, evaluate_ic,
    excess_forward_return, format_flag, format_result, session_close_times,
)
from app.config import settings

HORIZONS = (1, 3)
# 2.2.3 changed CAPITAL_RAISE detection (feeds CATALYST RISK) and added the EARNINGS modifier
DEFAULT_MIN_RULES_VERSION = "2.2.3"
BANDS = ["STRONG AVOID", "AVOID", "CAUTION", "HOLD", "WATCH", "BUY", "STRONG BUY"]
BAND_RANK = {b: i for i, b in enumerate(BANDS)}
# Gates that cap the band, plus modifiers that only inform. EARNINGS IN nD is grouped as EARNINGS.
MODIFIERS = ["CATALYST RISK", "HIGH RISK", "DILUTION RISK", "CONFLICTING SOURCES", "LOW DATA QUALITY",
             "OVEREXTENDED", "NO MKT DATA", "EARNINGS"]
MIN_BAND_DATES_FOR_CI = 10


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def band_from_smi(smi: float) -> str:
    """Band the SMI alone maps to, before any gate. Mirrors step 1 of generate_signal_and_explanation."""
    if smi >= settings.THRESHOLD_STRONG_BUY:
        return "STRONG BUY"
    if smi >= settings.THRESHOLD_BUY:
        return "BUY"
    if smi >= settings.THRESHOLD_WATCH:
        return "WATCH"
    if smi > settings.THRESHOLD_HOLD:
        return "HOLD"
    if smi > settings.THRESHOLD_AVOID:
        return "CAUTION"
    if smi > settings.THRESHOLD_STRONG_AVOID:
        return "AVOID"
    return "STRONG AVOID"


def parse_modifiers(raw) -> set:
    out = set()
    for m in (raw or "").split("|"):
        m = m.strip()
        if m:
            out.add("EARNINGS" if m.startswith("EARNINGS") else m)
    return out


def latest_per_entry(rows: list) -> pd.DataFrame:
    """One row per (ticker, entry close): snapshots sharing an entry close share the forward return."""
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("ts").groupby(["ticker", "date"], as_index=False).last()


def band_ledger(df: pd.DataFrame, horizon: int) -> list:
    out = []
    for band in BANDS:
        b = df[df["band"] == band]
        if b.empty:
            continue
        daily = b.groupby("date")["ret"].mean().sort_index().to_numpy()
        row = {"band": band, "n": len(b), "dates": len(daily), "mean_excess": float(b["ret"].mean()),
               "share_positive": float((b["ret"] > 0).mean()), "ci_low": None, "ci_high": None}
        if len(daily) >= MIN_BAND_DATES_FOR_CI:
            lag = max(horizon, int(round(len(daily) ** (1 / 3))))
            row["ci_low"], row["ci_high"] = block_bootstrap_ci(daily, lag, BOOTSTRAP_SAMPLES, CONFIDENCE, seed=7)
        out.append(row)
    return out


def format_band(r: dict) -> str:
    ci = (f"CI95=[{r['ci_low']:+.2%}, {r['ci_high']:+.2%}]" if r["ci_low"] is not None
          else f"(no CI: {r['dates']} dates < {MIN_BAND_DATES_FOR_CI})")
    return (f"  {r['band']:13s} n={r['n']:4d} dates={r['dates']:3d}  mean={r['mean_excess']:+.2%}  "
            f">0: {r['share_positive']:.0%}  {ci}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="only snapshots from this date (YYYY-MM-DD)")
    ap.add_argument("--min-rules-version", default=DEFAULT_MIN_RULES_VERSION,
                    help=f"skip snapshots stored under older rules (default {DEFAULT_MIN_RULES_VERSION}; 'all' keeps every one)")
    args = ap.parse_args()

    con = connect_readonly()
    query = ("select ticker, timestamp, smi, base_signal, signal_modifier, rules_version, data_source "
             "from ssi_snapshots where smi is not null and base_signal is not null and data_source != 'MOCK'")
    params = []
    if args.since:
        query += " and timestamp >= ?"
        params.append(args.since)
    min_rules = None if args.min_rules_version == "all" else version_tuple(args.min_rules_version)
    snaps, versions = [], Counter()
    for tk, ts, smi, band, mods, rules, src in con.execute(query + " order by timestamp", params):
        if min_rules and version_tuple(rules) < min_rules:
            continue
        if band not in BAND_RANK:
            continue
        versions[rules] += 1
        snaps.append({"ticker": tk, "ts": datetime.fromisoformat(ts), "smi": smi, "band": band,
                      "pre_gate": band_from_smi(smi), "mods": parse_modifiers(mods), "source": src})

    print(f"snapshots: {len(snaps)} | rules_version: {dict(versions)} | "
          f"sources: {dict(Counter(s['source'] for s in snaps))}")
    print("bands:", dict(Counter(s["band"] for s in snaps)))
    print("modifiers:", dict(Counter(m for s in snaps for m in s["mods"])))
    if not snaps:
        return

    now_utc = datetime.now(timezone.utc)
    closes, close_times = {}, {}
    for tk in TICKERS:
        c = yf.Ticker(tk).history(period="6mo", interval="1d")["Close"].dropna()
        c.index = c.index.tz_localize(None)
        closes[tk] = complete_bars(c, now_utc)  # today's partial bar is not a close yet
        close_times[tk] = session_close_times(closes[tk].index)

    summary = {"generated_at": now_utc.isoformat(), "since": args.since,
               "min_rules_version": args.min_rules_version, "rules_versions": dict(versions), "horizons": {}}
    for h in HORIZONS:
        rows = []
        for s in snaps:
            fr = excess_forward_return(closes, s["ticker"], s["ts"], h, close_times=close_times)
            if fr is None:
                continue
            row = {"ticker": s["ticker"], "ts": s["ts"], "date": fr["entry_date"], "ret": fr["excess"],
                   "band": s["band"], "rank": BAND_RANK[s["band"]], "pre_gate": s["pre_gate"]}
            row.update({m: m in s["mods"] for m in MODIFIERS})
            rows.append(row)
        df = latest_per_entry(rows)
        print(f"\n=== {h}-session excess forward return: {len(df)} settled (ticker, entry close) "
              f"from {len(rows)} snapshots ===")
        if df.empty:
            summary["horizons"][h] = {"settled": 0}
            continue

        ordering = evaluate_ic(df.rename(columns={"rank": "score"})[["ticker", "date", "score", "ret"]],
                               "band order", h)
        print("1. Does a higher band precede a better return?")
        print("  " + format_result(ordering))

        print("2. Ledger per band (descriptive; excess return over the other tickers):")
        ledger = band_ledger(df, h)
        for r in ledger:
            print(format_band(r))

        print("3. Modifiers: flagged vs unflagged, same tickers (a bearish gate should come out LOWER):")
        flags = []
        for m in MODIFIERS:
            if not df[m].any():
                continue
            fr = evaluate_flag(df[["ticker", "date", "ret"]].assign(flag=df[m]), m, h)
            flags.append(fr)
            print("  " + format_flag(fr))

        bound = df[df["pre_gate"].map(BAND_RANK) > df["rank"]]
        print(f"4. Gates that lowered the band: {len(bound)} of {len(df)}"
              + (f", mean excess {bound['ret'].mean():+.2%} (a gate that helps sits on negative returns)"
                 if len(bound) else " (no BUY-level SMI in the sample: gates did not change any band)"))

        summary["horizons"][h] = {
            "settled": len(df), "band_order": ordering.as_dict(), "bands": ledger,
            "modifiers": [f.as_dict() for f in flags],
            "binding_gates": {"n": len(bound), "mean_excess": float(bound["ret"].mean()) if len(bound) else None,
                              "transitions": dict(Counter(f"{a}->{b}" for a, b in zip(bound["pre_gate"], bound["band"])))},
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"signal_ledger_{now_utc:%Y%m%d}.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nsummary written to {path}")


if __name__ == "__main__":
    main()
