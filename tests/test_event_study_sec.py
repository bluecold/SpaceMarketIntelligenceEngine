"""Event-study math (audit/sentiment_2026_10/event_study_sec.py) on synthetic prices: no network, no database."""
from datetime import datetime

import numpy as np
import pandas as pd

from audit.sentiment_2026_10 import event_study_sec as es
from audit.sentiment_2026_10._ic_stats import session_close_times

DATES = pd.bdate_range("2026-03-02", periods=30)


def _closes():
    flat = pd.Series(100.0, index=DATES)
    a = flat.copy()
    a.iloc[10:] = 90.0  # -10% on session 10, then flat
    return {"AAA": a, "BBB": flat.copy(), "CCC": flat.copy() * 2}


def test_day_zero_uses_the_first_close_after_acceptance():
    ct = session_close_times(DATES)
    # 2026-03-16 is session 10. 19:00 UTC = 15:00 New York (before the close) -> day 0 is that session
    assert es.day_zero(ct, datetime(2026, 3, 16, 19, 0)) == 10
    # 21:30 UTC = 17:30 New York (after the close) -> the next session
    assert es.day_zero(ct, datetime(2026, 3, 16, 21, 30)) == 11
    assert es.day_zero(ct, datetime(2026, 2, 1)) is None  # no close before it (e.g. an IPO)


def test_car_is_relative_to_the_other_tickers():
    closes = _closes()
    assert abs(es.car(closes, "AAA", 10, 0, 0) - (-0.10)) < 1e-12
    assert abs(es.car(closes, "AAA", 10, 0, 2) - (-0.10)) < 1e-12
    assert abs(es.car(closes, "AAA", 11, 0, 2)) < 1e-12           # after the drop there is nothing abnormal
    closes["BBB"].iloc[10:] = 90.0                                 # the basket falls with it
    assert abs(es.car(closes, "AAA", 10, 0, 0) - (-0.05)) < 1e-12


def test_filings_of_one_deal_collapse_into_one_episode():
    closes = _closes()
    f = lambda d: {"ticker": "AAA", "form": "424B5", "items": None, "category": "OFFERING", "accepted_at": d}
    filings = [f(datetime(2026, 3, 16, 21, 30)), f(datetime(2026, 3, 17, 12, 0)),   # preliminary + final
               f(datetime(2026, 4, 1, 15, 0))]                                       # a later, separate deal
    eps = es.episodes(filings, closes, "OFFERING")
    assert [e["date"] for e in eps] == ["2026-03-17", "2026-04-01"]


def test_verdict_needs_enough_episodes_and_tickers():
    base = {"window": es.PRIMARY, "tickers": ["A", "B", "C"], "mean": -0.1, "median": -0.05,
            "ci95": [-0.2, -0.01], "leave_one_ticker_out_mean": {"A": -0.1, "B": -0.1, "C": -0.08}}
    assert es.verdict({**base, "n": es.MIN_EPISODES - 1}) == "INSUFFICIENT_DATA"
    assert es.verdict({**base, "n": es.MIN_EPISODES}) == "SUPPORTS_GATE"
    assert es.verdict({**base, "n": 30, "ci95": [-0.2, 0.02]}) == "NOT_SIGNIFICANT"
    assert es.verdict({**base, "n": 30, "leave_one_ticker_out_mean": {"A": 0.01, "B": -0.1, "C": -0.1}}) == "NOT_SIGNIFICANT"
    assert es.verdict({**base, "n": 30, "mean": 0.1, "median": 0.1, "ci95": [0.01, 0.2]}) == "POSITIVE_REACTION"
    assert es.verdict({**base, "n": 30, "tickers": ["A", "B"]}) == "INSUFFICIENT_DATA"


def test_bootstrap_ci_brackets_the_mean():
    x = np.array([-0.1, -0.05, -0.2, 0.02, -0.08, -0.12])
    lo, hi = es.bootstrap_ci(x)
    assert lo < x.mean() < hi
