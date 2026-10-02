"""Shared helpers for the October 2026 sentiment/momentum studies. Run every script from the repo root."""
import math
import os
import sqlite3
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "audit" / "output"
DB_PATH = ROOT / "data" / "space_sentiment.db"
TICKERS = ["ASTS", "RKLB", "SATL", "SPCE", "SPCX"]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("ENVIRONMENT", "testing")


def connect_readonly() -> sqlite3.Connection:
    """Opens the production database read-only; these studies never write to it."""
    return sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)


def rank(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    rk = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            rk[order[k]] = (i + j) / 2.0
        i = j + 1
    return rk


def spearman(a, b):
    """Rank correlation (information coefficient). Returns None for fewer than 10 pairs."""
    if len(a) < 10:
        return None
    ra, rb = rank(a), rank(b)
    ma, mb = st.mean(ra), st.mean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return num / den if den else None
