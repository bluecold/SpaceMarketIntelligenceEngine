"""
Runs FinBERT and FinTwitBERT over every stored X post and compares their labels (~10 min per model on CPU).

Both models are labelled with the system rule: score = P(bullish) - P(bearish), opinion when |score| >= 0.20.
Writes audit/output/model_disagreements.csv (tweet_id, ticker, both labels and scores) for manual review.
Read-only on the database.

    python -m audit.sentiment_2026_10.compare_sentiment_models
"""
import csv
import time
from collections import Counter

from audit.sentiment_2026_10._common import OUTPUT_DIR, connect_readonly

from app.scoring.social import is_scorable_language

BATCH = 32
MODELS = [("ProsusAI/finbert", "positive", "negative"), ("StephanAkkerman/FinTwitBERT-sentiment", "bullish", "bearish")]


class _Post:
    def __init__(self, text, lang):
        self.text, self.lang = text, lang


def run_model(model_name, pos_key, neg_key, texts):
    from transformers import pipeline
    pipe = pipeline("text-classification", model=model_name, top_k=None)
    out, t0 = [], time.time()
    for i in range(0, len(texts), BATCH):
        batch = [t if t.strip() else "neutral" for t in texts[i:i + BATCH]]
        for preds in pipe(batch, truncation=True, max_length=128):
            scores = {p["label"].lower(): float(p["score"]) for p in preds}
            s = scores.get(pos_key, 0.0) - scores.get(neg_key, 0.0)
            out.append(("BULLISH" if s >= 0.20 else "BEARISH" if s <= -0.20 else "NEUTRAL", round(s, 3)))
    print(f"  {model_name}: {len(texts)} posts in {time.time() - t0:.0f}s")
    return out


def main():
    con = connect_readonly()
    rows = con.execute("select tweet_id, ticker, text, relevance_score, lang from social_posts").fetchall()
    texts = [r[2] or "" for r in rows]
    results = {name: run_model(name, pos, neg, texts) for name, pos, neg in MODELS}
    fb, ft = results[MODELS[0][0]], results[MODELS[1][0]]

    mask = [(r[3] or 0) >= 0.40 and is_scorable_language(_Post(r[2] or "", r[4])) for r in rows]
    for name, labels in (("FinBERT", fb), ("FinTwitBERT", ft)):
        c = Counter(l[0] for l, m in zip(labels, mask) if m)
        n = sum(c.values())
        print(f"{name:12s} relevant English: " + " | ".join(f"{k} {100 * c[k] / n:.1f}%" for k in ("BULLISH", "NEUTRAL", "BEARISH")))

    pairs = Counter((a[0], b[0]) for a, b, m in zip(fb, ft, mask) if m)
    agree = sum(v for (a, b), v in pairs.items() if a == b)
    print(f"agreement: {agree}/{sum(pairs.values())}")
    for (a, b), v in sorted(pairs.items(), key=lambda kv: -kv[1]):
        if a != b:
            print(f"  FinBERT {a:7s} / FinTwit {b:7s}: {v}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "model_disagreements.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tweet_id", "ticker", "finbert_label", "finbert_score", "fintwit_label", "fintwit_score"])
        for r, a, b, m in zip(rows, fb, ft, mask):
            if m and a[0] != b[0]:
                w.writerow([r[0], r[1], a[0], a[1], b[0], b[1]])
    print(f"disagreements -> {path}")


if __name__ == "__main__":
    main()
