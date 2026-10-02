"""
Scores the blind manual review (model_review_labels.csv) of FinBERT vs FinTwitBERT disagreements.

The 150 reviewed tweets were a stratified sample of the 5,682 relevant English tweets where the two models
disagreed (Oct 2026, 8,252 relevant English tweets). Accuracy is weighted by the real size of each stratum.
Tweets labelled NON_ENGLISH are excluded (the language filter drops them from the SSI).

    python -m audit.sentiment_2026_10.score_model_review
"""
import csv
from collections import Counter, defaultdict
from pathlib import Path

B, N, R = "BULLISH", "NEUTRAL", "BEARISH"
LABELS_CSV = Path(__file__).with_name("model_review_labels.csv")

# Disagreement population (FinBERT label, FinTwitBERT label) -> tweets, from compare_sentiment_models.py
POPULATION = {
    (N, B): 4454, (N, R): 811, (R, B): 162, (B, N): 122, (B, R): 75, (R, N): 58,
}


def fintwit_at(score: float, threshold: float) -> str:
    return B if score >= threshold else R if score <= -threshold else N


RULES = {
    "FinBERT (0.20)": lambda r: r["finbert_label"],
    "FinTwitBERT (0.20)": lambda r: r["fintwit_label"],
    "FinTwitBERT (0.60)": lambda r: fintwit_at(float(r["fintwit_score"]), 0.6),
    "FinTwitBERT (0.90)": lambda r: fintwit_at(float(r["fintwit_score"]), 0.9),
    "Hybrid: FinBERT gates, FinTwit directs": lambda r: N if r["finbert_label"] == N else (
        r["fintwit_label"] if r["fintwit_label"] != N else r["finbert_label"]),
}


def main():
    rows = [r for r in csv.DictReader(open(LABELS_CSV, encoding="utf-8")) if r["reviewer_label"] != "NON_ENGLISH"]
    strata = defaultdict(list)
    for r in rows:
        strata[(r["finbert_label"], r["fintwit_label"])].append(r)
    total = sum(POPULATION.values())

    print(f"reviewed English tweets: {len(rows)}")
    for k, rs in sorted(strata.items(), key=lambda kv: -POPULATION[kv[0]]):
        c = Counter(r["reviewer_label"] for r in rs)
        print(f"  FinBERT {k[0]:7s} / FinTwit {k[1]:7s}  population={POPULATION[k]:5d} n={len(rs):2d}  truth: "
              f"BULL {c[B]:2d} | NEU {c[N]:2d} | BEAR {c[R]:2d}")

    print(f"\n{'rule':42s} {'accuracy':>9s} {'flips':>7s} {'opinion precision':>18s}")
    for name, rule in RULES.items():
        acc = flips = op_pred = op_ok = 0.0
        for k, rs in strata.items():
            w = POPULATION[k] / len(rs)
            for r in rs:
                truth, pred = r["reviewer_label"], rule(r)
                acc += w * (truth == pred)
                flips += w * ({truth, pred} == {B, R})
                if pred != N:
                    op_pred += w
                    op_ok += w * (truth == pred)
        print(f"{name:42s} {100 * acc / total:8.0f}% {100 * flips / total:6.1f}% {100 * op_ok / max(op_pred, 1e-9):17.0f}%")


if __name__ == "__main__":
    main()
