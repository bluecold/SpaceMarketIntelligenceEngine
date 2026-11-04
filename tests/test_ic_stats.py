"""Verdict logic of audit/sentiment_2026_10/_ic_stats.py on synthetic data (no network, no database)."""
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from audit.sentiment_2026_10 import _ic_stats as ics


def _panel(beta: float, n_dates: int = 120, tickers=("ASTS", "RKLB", "SATL", "SPCE", "SPCX"), seed: int = 1):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2026-01-05", periods=n_dates)
    rows = []
    for tk in tickers:
        level = rng.normal(50, 20)  # per-ticker score level must not matter
        for d in dates:
            s = rng.normal()
            rows.append({"ticker": tk, "date": d, "score": level + 10 * s, "ret": beta * s + rng.normal()})
    return pd.DataFrame(rows)


def test_predictive_score_is_alive():
    r = ics.evaluate_ic(_panel(beta=0.6), "pillar", horizon=1)
    assert r.verdict == ics.ALIVE, r.reason
    assert r.ic > 0.3 and r.ci_low > 0 and r.t_nw > 2
    assert set(r.ticker_ic) == {"ASTS", "RKLB", "SATL", "SPCE", "SPCX"}


def test_inverted_score_is_reversed():
    r = ics.evaluate_ic(_panel(beta=-0.6), "pillar", horizon=1)
    assert r.verdict == ics.REVERSED, r.reason
    assert r.ic < -0.3 and r.ci_high < 0


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_pure_noise_is_dead(seed):
    r = ics.evaluate_ic(_panel(beta=0.0, seed=seed), "pillar", horizon=1)
    assert r.verdict == ics.DEAD, f"{r.ic} {r.reason}"
    assert abs(r.ic) < 0.1


def test_short_history_is_insufficient():
    # 30 dates at a 3-session horizon are only 10 independent observations
    r = ics.evaluate_ic(_panel(beta=0.6, n_dates=30), "pillar", horizon=3)
    assert r.verdict == ics.INSUFFICIENT
    assert r.ic is None and "independent obs" in r.reason


def test_signal_in_one_ticker_only_is_not_alive():
    """A strong IC driven by one ticker while the rest are noise fails the ticker-agreement rule."""
    strong = _panel(beta=3.0, tickers=("ASTS",), seed=11)
    noise = _panel(beta=0.0, tickers=("RKLB", "SATL", "SPCE", "SPCX"), seed=12)
    r = ics.evaluate_ic(pd.concat([strong, noise]), "pillar", horizon=1)
    assert r.verdict != ics.ALIVE


def _persistent_overlapping_panel(seed, n=90, h=3, phi=0.9):
    """No real signal, but a slow-moving score (like the SSI) against overlapping h-session returns:
    the setting where a naive t-stat flags noise as significant (~18% of seeds at |t| >= 2)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2026-01-05", periods=n)
    rows = []
    for tk in ("ASTS", "RKLB", "SATL", "SPCE", "SPCX"):
        s = np.zeros(n)
        for i in range(1, n):
            s[i] = phi * s[i - 1] + rng.normal()
        e = rng.normal(size=n + h)
        r = [e[i + 1:i + 1 + h].sum() for i in range(n)]
        rows += [{"ticker": tk, "date": d, "score": s[i], "ret": r[i]} for i, d in enumerate(dates)]
    return pd.DataFrame(rows)


def test_persistent_score_with_overlapping_returns_is_not_flagged(monkeypatch):
    monkeypatch.setattr(ics, "BOOTSTRAP_SAMPLES", 500)
    verdicts = [ics.evaluate_ic(_persistent_overlapping_panel(s), "x", horizon=3, seed=s).verdict for s in range(15)]
    assert verdicts.count(ics.DEAD) == len(verdicts), verdicts


def test_overlap_widens_uncertainty():
    """Overlapping multi-day returns repeat information: the HAC t must be smaller than a naive t."""
    rng = np.random.default_rng(3)
    x = np.convolve(rng.normal(size=300), np.ones(5) / 5, mode="valid") + 0.05  # MA(4) like 5-day overlap
    naive_se = x.std(ddof=0) / np.sqrt(len(x))
    assert ics.newey_west_se(x, lag=5) > 1.5 * naive_se


def test_bootstrap_ci_is_seeded_and_contains_mean():
    x = np.random.default_rng(0).normal(0.1, 1.0, 200)
    a = ics.block_bootstrap_ci(x, block=5, samples=500, confidence=0.95, seed=9)
    assert a == ics.block_bootstrap_ci(x, block=5, samples=500, confidence=0.95, seed=9)
    assert a[0] < x.mean() < a[1]


# --- Entry at the first close after the snapshot -----------------------------------------------------

def _closes(values, start="2026-10-26"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


@pytest.mark.parametrize("ts, expected", [
    (datetime(2026, 11, 2, 14, 0), "2026-11-02"),   # Monday 09:00 New York: same-day close (21:00 UTC, EST)
    (datetime(2026, 11, 2, 21, 30), "2026-11-03"),  # after Monday's close: Tuesday
    (datetime(2026, 10, 30, 20, 30), "2026-11-02"), # Friday 16:30 EDT (close was 20:00 UTC): Monday
    (datetime(2026, 10, 31, 12, 0), "2026-11-02"),  # weekend: Monday
])
def test_entry_is_first_close_after_snapshot(ts, expected):
    s = _closes(range(1, 11))
    i = ics.entry_position(ics.session_close_times(s.index), ts)
    assert str(s.index[i].date()) == expected


def test_excess_return_subtracts_other_tickers_basket():
    closes = {
        "ASTS": _closes([100, 110, 121, 130]),
        "RKLB": _closes([50, 55, 50, 50]),
        "SATL": _closes([10, 10, 11, 11]),
    }
    # Monday 26/10 before the close: entry 26/10, exit one session later (27/10)
    r = ics.excess_forward_return(closes, "ASTS", datetime(2026, 10, 26, 15, 0), horizon=1)
    assert r["entry_date"] == pd.Timestamp("2026-10-26")
    assert r["raw"] == pytest.approx(0.10)
    assert r["basket"] == pytest.approx((0.10 + 0.0) / 2)
    assert r["excess"] == pytest.approx(0.05)


def test_excess_return_none_without_exit_bar_or_basket():
    closes = {"ASTS": _closes([100, 110]), "RKLB": _closes([50, 55])}
    assert ics.excess_forward_return(closes, "ASTS", datetime(2026, 10, 27, 15, 0), horizon=1) is None
    assert ics.excess_forward_return({"ASTS": closes["ASTS"]}, "ASTS", datetime(2026, 10, 26, 15, 0), 1) is None


def test_partial_bar_of_today_is_dropped():
    s = _closes([1, 2, 3], start="2026-11-02")  # Mon..Wed
    kept = ics.complete_bars(s, now_utc=datetime(2026, 11, 4, 18, 0))  # Wednesday 13:00 New York
    assert list(kept.index.strftime("%Y-%m-%d")) == ["2026-11-02", "2026-11-03"]


def test_panel_keeps_latest_snapshot_per_entry_close():
    obs = [
        {"ticker": "ASTS", "entry_date": pd.Timestamp("2026-11-02"), "ts": datetime(2026, 11, 2, 10), "social": 40, "ret": 0.01},
        {"ticker": "ASTS", "entry_date": pd.Timestamp("2026-11-02"), "ts": datetime(2026, 11, 2, 18), "social": 60, "ret": 0.01},
        {"ticker": "ASTS", "entry_date": pd.Timestamp("2026-11-03"), "ts": datetime(2026, 11, 3, 10), "social": None, "ret": 0.02},
    ]
    p = ics.build_panel(obs, "social")
    assert len(p) == 1 and p.iloc[0]["score"] == 60


def test_flat_ticker_is_excluded_not_counted_against():
    """A ticker whose score never varies carries no information: it neither votes nor dilutes the IC."""
    live = _panel(beta=0.6, tickers=("ASTS", "RKLB", "SATL", "SPCE"), seed=21)
    flat = _panel(beta=0.0, tickers=("SPCX",), seed=22).assign(score=50.0)
    r = ics.evaluate_ic(pd.concat([live, flat]), "fundamental", horizon=1)
    assert r.flat_tickers == ["SPCX"]
    assert "SPCX" not in r.ticker_ic
    assert r.verdict == ics.ALIVE, r.reason


def test_too_few_varying_tickers_is_insufficient():
    one = _panel(beta=0.6, tickers=("SPCX",), seed=31)
    flat = _panel(beta=0.0, tickers=("ASTS", "RKLB", "SATL", "SPCE"), seed=32).assign(score=70.0)
    r = ics.evaluate_ic(pd.concat([one, flat]), "fundamental", horizon=1)
    assert r.verdict == ics.INSUFFICIENT
    assert "1 tickers with a varying score" in r.reason and "independent obs" not in r.reason


# --- Flag effect (signal ledger) ---------------------------------------------------------------------

def _flag_panel(effect: float, n_dates: int = 120, tickers=("ASTS", "RKLB", "SATL", "SPCE"), p: float = 0.3,
                seed: int = 1):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2026-01-05", periods=n_dates)
    rows = []
    for tk in tickers:
        drift = rng.normal(0, 0.01)  # per-ticker drift must not matter
        for d in dates:
            f = bool(rng.random() < p)
            rows.append({"ticker": tk, "date": d, "flag": f, "ret": drift + effect * f + rng.normal(0, 0.03)})
    return pd.DataFrame(rows)


def test_flag_followed_by_worse_returns_is_lower():
    r = ics.evaluate_flag(_flag_panel(effect=-0.03), "CATALYST RISK", horizon=1)
    assert r.verdict == ics.LOWER, r.reason
    assert r.diff < 0 and r.ci_high < 0 and r.leave_one_out_same_sign


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_uninformative_flag_shows_no_difference(seed):
    r = ics.evaluate_flag(_flag_panel(effect=0.0, seed=seed), "HIGH RISK", horizon=1)
    assert r.verdict == ics.NO_DIFFERENCE, f"{r.diff} {r.reason}"


def test_flag_always_on_for_a_drifting_ticker_is_not_evidence():
    """A flag stuck on one underperforming ticker says nothing within ticker: that ticker is excluded."""
    df = _flag_panel(effect=0.0, tickers=("RKLB", "SATL"), p=0.0, seed=3)
    stuck = _flag_panel(effect=0.0, tickers=("SPCE",), p=1.0, seed=4).assign(ret=lambda d: d["ret"] - 0.05)
    r = ics.evaluate_flag(pd.concat([df, stuck]), "CATALYST RISK", horizon=1)
    assert r.verdict == ics.INSUFFICIENT
    assert r.always_flagged == ["SPCE"] and r.mixed_tickers == []


def test_few_flagged_dates_is_insufficient():
    r = ics.evaluate_flag(_flag_panel(effect=-0.03, n_dates=40, p=0.05), "DILUTION RISK", horizon=3)
    assert r.verdict == ics.INSUFFICIENT and r.diff is None
    assert "flagged dates" in r.reason


def test_flag_effect_from_one_ticker_is_not_lower():
    strong = _flag_panel(effect=-0.10, tickers=("ASTS",), seed=7)
    noise = _flag_panel(effect=0.0, tickers=("RKLB", "SATL", "SPCE"), seed=8)
    r = ics.evaluate_flag(pd.concat([strong, noise]), "CATALYST RISK", horizon=1)
    assert r.diff < 0 and r.verdict == ics.NO_DIFFERENCE, r.reason
    assert not r.leave_one_out_same_sign
