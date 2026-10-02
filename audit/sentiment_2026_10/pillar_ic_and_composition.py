"""
Replays every stored snapshot with the current scoring code and reports, for the SMI and each pillar:
  1. its share of SMI movement (covariance contribution), i.e. what actually drives the index;
  2. its rank correlation (IC) with 24h / 72h forward price returns, pooled and within ticker;
  3. the resulting signal-band distribution.

Use it before rebalancing weights (pending task): a pillar deserves weight only if its IC is consistently
positive. Social is rebuilt from stored posts (opinion-only polarity + 14-day baseline + filters);
momentum is rebuilt from daily yfinance bars at each snapshot date. Read-only on the database.

    python -m audit.sentiment_2026_10.pillar_ic_and_composition [--since 2026-10-03]
"""
import argparse
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from audit.sentiment_2026_10._common import TICKERS, connect_readonly, spearman

import yfinance as yf
from app.database.models import SocialPostModel
from app.scoring.momentum import calculate_momentum_score
from app.scoring.signal import generate_signal_and_explanation
from app.scoring.smi import calculate_smi
from app.scoring.social import apply_social_baseline, calculate_social_baseline, calculate_social_score
from app.technical.indicators import calculate_technical_indicators

PILLARS = ("social", "news", "prediction", "momentum", "fundamental")


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
    args = ap.parse_args()

    con = connect_readonly()
    posts = load_posts(con)
    prices = {}
    for tk in TICKERS:
        df = yf.Ticker(tk).history(period="2y", interval="1d")[["Open", "High", "Low", "Close", "Volume"]].dropna()
        df.index = df.index.tz_localize(None)
        prices[tk] = df

    query = ("select ticker, timestamp, news_score, prediction_score, prediction_quality, fundamental_score, "
             "news_count, prediction_count, rsi14, price from ssi_snapshots where smi is not null")
    if args.since:
        query += f" and timestamp >= '{args.since}'"
    out = []
    for tk, ts, news, pms, pq, fund, nc, prc, rsi, price in con.execute(query + " order by timestamp"):
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

    print(f"snapshots: {len(out)}")
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

    for hours in (24, 72):
        print(f"\n--- IC vs {hours}h forward return: pooled | within ticker ---")
        feats = defaultdict(list)
        for tk in TICKERS:
            series = [o for o in out if o["tk"] == tk and o["price"]]
            for i, o in enumerate(series):
                fut = next((f for f in series[i + 1:] if f["ts"] >= o["ts"] + timedelta(hours=hours)), None)
                if not fut or fut["ts"] > o["ts"] + timedelta(hours=hours + 48):
                    continue
                ret = (fut["price"] - o["price"]) / o["price"]
                feats["SMI"].append((o["smi"]["smi"], ret, tk))
                for k in PILLARS:
                    v = o["smi"]["active_scores"].get(k)
                    if v is not None:
                        feats[k].append((v, ret, tk))
        for k, pairs in feats.items():
            pooled = spearman([p[0] for p in pairs], [p[1] for p in pairs])
            per = [spearman([p[0] for p in pairs if p[2] == t], [p[1] for p in pairs if p[2] == t]) for t in TICKERS]
            per = [x for x in per if x is not None]
            if pooled is not None and per:
                print(f"{k:12s} n={len(pairs):4d} {pooled:+.3f} | {st.mean(per):+.3f}")


if __name__ == "__main__":
    main()
