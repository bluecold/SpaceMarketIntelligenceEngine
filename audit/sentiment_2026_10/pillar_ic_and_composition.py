"""
Replays every stored snapshot with the current scoring code and reports, for the SMI and each pillar:
  1. its share of SMI movement (covariance contribution), i.e. what actually drives the index;
  2. the resulting signal-band distribution;
  3. a verdict per pillar and horizon (ALIVE / REVERSED / DEAD / INSUFFICIENT_DATA) from its IC against
     forward returns, with the rules in `_ic_stats.py`: entry at the first close after the snapshot,
     return in excess of the other tickers' basket, Newey-West t and block-bootstrap CI, sign stable
     across weeks and tickers, and no single ticker carrying the result.

Use it before rebalancing weights (pending task): a pillar deserves weight only if it comes out ALIVE in
both horizons. Social is rebuilt from stored posts (opinion-only polarity + 14-day baseline + filters);
momentum is rebuilt from daily yfinance bars at each snapshot date. Read-only on the database; the
verdict table (no post data) is also written to audit/output/.

    python -m audit.sentiment_2026_10.pillar_ic_and_composition [--min-rules-version 2.2.2] [--since 2026-10-24]
"""
import argparse
import json
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from audit.sentiment_2026_10._common import OUTPUT_DIR, TICKERS, connect_readonly
from audit.sentiment_2026_10._ic_stats import (
    build_panel, complete_bars, evaluate_ic, excess_forward_return, format_result, session_close_times,
)

import yfinance as yf
from app.database.models import SocialPostModel
from app.scoring.momentum import calculate_momentum_score
from app.scoring.signal import generate_signal_and_explanation
from app.scoring.smi import calculate_smi
from app.scoring.social import apply_social_baseline, calculate_social_baseline, calculate_social_score
from app.technical.indicators import calculate_technical_indicators

PILLARS = ("social", "news", "prediction", "momentum", "fundamental")
HORIZONS = (1, 3)  # trading sessions after the entry close (roughly the old 24h / 72h)
# Snapshots before 2.2.2 carry an SSI built from one ~20-tweet page per run (PROJECT_CONTEXT, section 5)
DEFAULT_MIN_RULES_VERSION = "2.2.2"


def version_tuple(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except ValueError:
        return (0,)


def load_posts(con):
    posts = defaultdict(list)
    for tk, text, user, created, s, lab, conf, rel, eng, tid, lang in con.execute(
            "select ticker, text, username, created_at, sentiment_score, sentiment_label, sentiment_confidence, "
            "relevance_score, engagement_score, tweet_id, lang from social_posts"):
        posts[tk].append(SocialPostModel(
            text=text, username=user, created_at=datetime.fromisoformat(created), sentiment_score=s,
            sentiment_label=lab, sentiment_confidence=conf, relevance_score=rel, engagement_score=eng,
            tweet_id=tid, lang=lang))
    return posts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="only snapshots from this date (YYYY-MM-DD), e.g. after a scoring change")
    ap.add_argument("--min-rules-version", default=DEFAULT_MIN_RULES_VERSION,
                    help=f"skip snapshots stored under older rules (default {DEFAULT_MIN_RULES_VERSION}; 'all' keeps every one)")
    args = ap.parse_args()

    con = connect_readonly()
    posts = load_posts(con)
    now_utc = datetime.now(timezone.utc)
    prices, closes, close_times = {}, {}, {}
    for tk in TICKERS:
        df = yf.Ticker(tk).history(period="2y", interval="1d")[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df.index = df.index.tz_localize(None)
        prices[tk] = df
        closes[tk] = complete_bars(df["Close"], now_utc)  # today's partial bar is not a close yet
        close_times[tk] = session_close_times(closes[tk].index)

    query = ("select ticker, timestamp, news_score, prediction_score, prediction_quality, fundamental_score, "
             "news_count, prediction_count, rsi14, price, rules_version from ssi_snapshots where smi is not null")
    params = []
    if args.since:
        query += " and timestamp >= ?"
        params.append(args.since)
    min_rules = None if args.min_rules_version == "all" else version_tuple(args.min_rules_version)
    out = []
    versions = Counter()
    for tk, ts, news, pms, pq, fund, nc, prc, rsi, price, rules in con.execute(query + " order by timestamp", params):
        if min_rules and version_tuple(rules) < min_rules:
            continue
        versions[rules] += 1
        ts = datetime.fromisoformat(ts)
        win = [p for p in posts[tk] if ts - timedelta(hours=24) <= p.created_at <= ts]
        hist = [p for p in posts[tk] if ts - timedelta(days=14) <= p.created_at <= ts]
        soc = apply_social_baseline(calculate_social_score(win, analysis_timestamp=ts),
                                    calculate_social_baseline(hist, ts - timedelta(days=14), ts - timedelta(hours=24)))
        df = prices[tk]
        idx = df.index.searchsorted(ts, side="right") - 1
        mom = None
        if idx >= 1:
            ind = calculate_technical_indicators(df, at_index=idx)
            ind["status"] = "AVAILABLE"
            mom = calculate_momentum_score(ind, raw_df=df, at_index=idx)
        d = calculate_smi(social_score=soc["social_score"], prediction_score=pms, prediction_quality=pq or 50.0,
                          news_score=news, momentum_score=mom, fundamental_score=fund,
                          post_count=soc["effective_sample_size"], news_count=nc, prediction_count=prc)
        if d["smi"] is None:
            continue
        sig = generate_signal_and_explanation(ticker=tk, smi=d["smi"],
                                              indicators={"status": "AVAILABLE", "price": price or 1.0, "rsi14": rsi})
        out.append({"tk": tk, "ts": ts, "price": price, "smi": d, "band": sig["base_signal"]})

    print(f"snapshots: {len(out)} | rules_version: {dict(versions)}")
    full = [o for o in out if len(o["smi"]["active_scores"]) >= 5]
    if len(full) > 10:
        fs = [o["smi"]["smi"] for o in full]
        ms, var = st.mean(fs), st.pvariance(fs)
        shares = []
        for k in PILLARS:
            c = [o["smi"]["normalized_weights"].get(k, 0) * o["smi"]["active_scores"].get(k, 0) for o in full]
            mc = st.mean(c)
            shares.append(f"{k}={100 * sum((x - mc) * (y - ms) for x, y in zip(c, fs)) / len(fs) / var:.0f}%")
        print(f"SMI std={st.pstdev(fs):.1f} | share of SMI movement: " + " ".join(shares))
    print("signal bands:", dict(Counter(o["band"] for o in out)))

    # Verdicts. Returns come from daily closes (entry at the first close after each snapshot, excess
    # over the other tickers), not from the snapshot's own price, which can be an after-hours quote.
    results = []
    for h in HORIZONS:
        obs = []
        for o in out:
            fr = excess_forward_return(closes, o["tk"], o["ts"], h, close_times=close_times)
            if fr is None:
                continue
            row = {"ticker": o["tk"], "ts": o["ts"], "entry_date": fr["entry_date"], "ret": fr["excess"],
                   "SMI": o["smi"]["smi"]}
            row.update({k: o["smi"]["active_scores"].get(k) for k in PILLARS})
            obs.append(row)
        print(f"\n--- {h}-session excess forward return: {len(obs)} snapshots with a complete window ---")
        for name in ("SMI",) + PILLARS:
            r = evaluate_ic(build_panel(obs, name), name, h)
            results.append(r)
            print(format_result(r))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"pillar_ic_verdicts_{now_utc:%Y%m%d}.json"
    path.write_text(json.dumps({
        "generated_at": now_utc.isoformat(), "since": args.since, "min_rules_version": args.min_rules_version,
        "rules_versions": dict(versions), "results": [r.as_dict() for r in results],
    }, indent=2, default=str), encoding="utf-8")
    print(f"\nverdicts written to {path}")

if __name__ == "__main__":
    main()
