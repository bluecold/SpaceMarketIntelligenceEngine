"""
Measures app.scoring.social.SPAM_PATTERNS on stored X posts: how much traffic and how many opinions they drop,
per ticker, and the opinion-labelled matches (what the filter removes from the SSI) for review.
Prints post texts locally; nothing is written. Read-only on the database.

    python -m audit.sentiment_2026_10.spam_pattern_check [--days 14] [--show 40]
"""
import argparse
from collections import Counter

from audit.sentiment_2026_10._common import connect_readonly

from app.scoring.social import SPAM_PATTERNS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--show", type=int, default=40)
    args = ap.parse_args()

    con = connect_readonly()
    rows = con.execute(
        "select ticker, text, sentiment_label from social_posts "
        f"where relevance_score >= 0.40 and created_at >= datetime('now', '-{int(args.days)} days')"
    ).fetchall()
    matched = [(tk, lab, text) for tk, text, lab in rows if any(p.search(text or "") for p in SPAM_PATTERNS)]
    opinions = Counter(tk for tk, _, lab in rows if lab != "NEUTRAL")
    spam_opinions = Counter(tk for tk, lab, _ in matched if lab != "NEUTRAL")

    print(f"posts: {len(rows)} | spam matches: {len(matched)} ({100 * len(matched) / max(1, len(rows)):.1f}%)")
    for tk in sorted(opinions):
        print(f"  {tk}: spam opinions {spam_opinions[tk]}/{opinions[tk]} ({100 * spam_opinions[tk] / opinions[tk]:.0f}%)")
    print("\nopinion-labelled matches (removed from the SSI):")
    for tk, lab, text in [m for m in matched if m[1] != "NEUTRAL"][:args.show]:
        print(f"  [{tk} {lab}] {' '.join((text or '').split())[:180]}")


if __name__ == "__main__":
    main()
