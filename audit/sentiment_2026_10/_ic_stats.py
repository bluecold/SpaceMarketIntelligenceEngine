"""Information-coefficient statistics with a verdict per pillar: ALIVE / REVERSED / DEAD / INSUFFICIENT_DATA.

The verdict idea (IC level + sign consistency + significance) comes from Vibe-Trading's alpha bench
(HKUDS/Vibe-Trading, MIT). Its implementation does not fit this universe, so the math here differs:

- Vibe-Trading ranks hundreds of stocks against each other on each date. With 5 tickers a per-date rank
  correlation has 5 points, so this module measures the IC along time inside each ticker instead.
- Snapshots arrive every few hours while forward returns span days, so consecutive observations share
  most of their return window. A plain t-stat treats them as independent and inflates. Significance here
  uses a Newey-West standard error with lag >= horizon and a moving-block bootstrap over dates.
- A fixed |IC| > 0.02 bar suits thousands of observations; with dozens, the bootstrap CI must exclude 0.

Returns are measured from the first regular-session close after the snapshot (a snapshot taken overnight
cannot trade at the previous close) and in excess of the equal-weight basket of the other tickers, so a
pillar that only tracks the sector's common move does not count as predictive.

Pure functions (numpy/pandas only, no network, no database) so tests can drive them with synthetic data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, time, timezone
from typing import Dict, Iterable, List, Optional, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NEW_YORK = ZoneInfo("America/New_York")
SESSION_CLOSE = time(16, 0)  # regular close; half-days (13:00) are rare and counted as 16:00

# Verdict thresholds. Change them only with a reason recorded in PROJECT_CONTEXT.md.
MIN_INDEPENDENT_OBS = 20     # dates / horizon: below this nothing can be concluded
MIN_WEEKS = 4                # weekly sign consistency needs several weeks
MIN_T_STAT = 2.0             # |Newey-West t| required on top of the CI excluding 0
MIN_WEEK_CONSISTENCY = 0.60  # share of weeks whose IC has the overall sign
MIN_TICKER_AGREEMENT = 0.60  # share of tickers (with enough data) whose IC has the overall sign
MIN_OBS_PER_TICKER = 10      # a ticker votes on the sign only with this many observations
MIN_TICKERS = 3              # tickers whose score actually varies; fewer cannot show a stable sign
# Dropping any single ticker, the rest must keep |t| >= this in the same direction: with 5 tickers a
# share-of-signs rule alone is passed by one strong ticker plus two noisy ones that land on its side.
MIN_LEAVE_ONE_OUT_T = 2.0
BOOTSTRAP_SAMPLES = 2000
CONFIDENCE = 0.95

ALIVE, REVERSED, DEAD, INSUFFICIENT = "ALIVE", "REVERSED", "DEAD", "INSUFFICIENT_DATA"


# --- Forward returns ------------------------------------------------------------------------------

def session_close_times(dates: Iterable) -> np.ndarray:
    """UTC instant of each bar's 16:00 New York close, as naive UTC datetimes (the DB stores naive UTC)."""
    out = []
    for d in dates:
        d = pd.Timestamp(d).date()
        out.append(datetime.combine(d, SESSION_CLOSE, NEW_YORK).astimezone(timezone.utc).replace(tzinfo=None))
    return np.array(out, dtype="datetime64[us]")


def complete_bars(closes: pd.Series, now_utc: datetime) -> pd.Series:
    """Drop bars whose session has not closed yet: yfinance serves today's partial bar as a close."""
    if closes.empty:
        return closes
    ends = session_close_times(closes.index)
    return closes[ends <= np.datetime64(now_utc.replace(tzinfo=None), "us")]


def entry_position(close_times: np.ndarray, ts_utc: datetime) -> Optional[int]:
    """Index of the first bar whose close is strictly after the snapshot (naive UTC)."""
    pos = int(np.searchsorted(close_times, np.datetime64(ts_utc, "us"), side="right"))
    return pos if pos < len(close_times) else None


def excess_forward_return(
    closes: Dict[str, pd.Series], ticker: str, ts_utc: datetime, horizon: int,
    close_times: Optional[Dict[str, np.ndarray]] = None,
) -> Optional[dict]:
    """Return of `ticker` from the first close after `ts_utc` to `horizon` sessions later, minus the mean
    return of the other tickers over the same two dates. None when the ticker or the basket lacks a bar."""
    s = closes.get(ticker)
    if s is None or s.empty:
        return None
    ct = close_times[ticker] if close_times else session_close_times(s.index)
    i = entry_position(ct, ts_utc)
    if i is None or i + horizon >= len(s):
        return None
    d_in, d_out = s.index[i], s.index[i + horizon]
    own = float(s.iloc[i + horizon] / s.iloc[i] - 1.0)
    basket = []
    for other, o in closes.items():
        if other == ticker or d_in not in o.index or d_out not in o.index:
            continue
        basket.append(float(o.loc[d_out] / o.loc[d_in] - 1.0))
    if not basket:
        return None
    return {"entry_date": pd.Timestamp(d_in), "raw": own, "basket": float(np.mean(basket)),
            "excess": own - float(np.mean(basket))}


# --- IC statistics --------------------------------------------------------------------------------

def _pct_rank(values: pd.Series) -> pd.Series:
    return values.rank(method="average")


def _standardize(x: pd.Series) -> pd.Series:
    sd = x.std(ddof=0)
    return (x - x.mean()) / sd if sd > 0 else x * 0.0


def newey_west_se(x: np.ndarray, lag: int) -> float:
    """HAC standard error of the mean of x with Bartlett weights."""
    n = len(x)
    if n < 2:
        return float("nan")
    e = x - x.mean()
    var = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        w = 1.0 - k / (lag + 1.0)
        var += 2.0 * w * float(e[k:] @ e[:-k]) / n
    return math.sqrt(max(var, 0.0) / n)


def block_bootstrap_ci(x: np.ndarray, block: int, samples: int, confidence: float, seed: int) -> tuple:
    """Moving-block bootstrap CI of the mean of x (blocks keep the overlap between neighbouring dates)."""
    n = len(x)
    block = max(1, min(block, n))
    rng = np.random.default_rng(seed)
    n_blocks = math.ceil(n / block)
    starts = rng.integers(0, n - block + 1, size=(samples, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(samples, -1)[:, :n]
    means = x[idx].mean(axis=1)
    a = (1.0 - confidence) / 2.0
    return float(np.quantile(means, a)), float(np.quantile(means, 1.0 - a))


def _hac_t(x: np.ndarray, lag: int) -> Optional[float]:
    se = newey_west_se(x, lag)
    return float(x.mean() / se) if se and se > 0 and math.isfinite(se) else None


@dataclass
class ICResult:
    name: str
    horizon: int
    n_obs: int
    n_dates: int
    n_weeks: int
    independent_obs: float
    ic: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    t_nw: Optional[float] = None
    week_consistency: Optional[float] = None
    ticker_ic: Dict[str, float] = field(default_factory=dict)
    flat_tickers: List[str] = field(default_factory=list)  # score or return never varies: no information
    ticker_agreement: Optional[float] = None
    leave_one_out_t: Optional[float] = None  # weakest sign-adjusted t after dropping one ticker
    verdict: str = INSUFFICIENT
    reason: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def evaluate_ic(panel: pd.DataFrame, name: str, horizon: int, seed: int = 7) -> ICResult:
    """Verdict for one score column.

    `panel` has columns ticker, date (entry date), score, ret (excess forward return), one row per
    ticker and entry date. Score and return are rank-transformed and standardized inside each ticker,
    so the IC is (a date-weighted version of) the average of each ticker's own Spearman correlation, and
    a ticker that always scores high cannot fake predictive power across tickers.
    """
    df = panel.dropna(subset=["score", "ret"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    # A ticker whose score never moves (e.g. fundamentals between filings) carries no ranking information;
    # its standardized products are all 0 and it would vote against any sign, so it is left out entirely.
    varies = df.groupby("ticker").agg(s=("score", "nunique"), r=("ret", "nunique"))
    flat = sorted(varies.index[(varies["s"] < 2) | (varies["r"] < 2)])
    df = df[~df["ticker"].isin(flat)]
    n_dates = df["date"].nunique()
    weeks = df["date"].dt.to_period("W")
    res = ICResult(name=name, horizon=horizon, n_obs=len(df), n_dates=n_dates, n_weeks=weeks.nunique(),
                   independent_obs=n_dates / max(horizon, 1), flat_tickers=flat)

    short = []
    if res.independent_obs < MIN_INDEPENDENT_OBS:
        short.append(f"{n_dates} dates / horizon {horizon} = {res.independent_obs:.0f} independent obs "
                     f"(need {MIN_INDEPENDENT_OBS})")
    if res.n_weeks < MIN_WEEKS:
        short.append(f"{res.n_weeks} weeks (need {MIN_WEEKS})")
    n_tickers = df["ticker"].nunique()
    if n_tickers < MIN_TICKERS:
        short.append(f"{n_tickers} tickers with a varying score (need {MIN_TICKERS})"
                     + (f"; flat: {', '.join(flat)}" if flat else ""))
    if short:
        res.reason = "; ".join(short)
        return res

    g = df.groupby("ticker")
    df["zs"] = g["score"].transform(lambda v: _standardize(_pct_rank(v)))
    df["zr"] = g["ret"].transform(lambda v: _standardize(_pct_rank(v)))
    df["prod"] = df["zs"] * df["zr"]

    # One value per date (tickers on the same date share the market's shock): the unit of resampling.
    # IC, CI and t all come from this series so they describe the same estimate.
    daily = df.groupby("date")["prod"].mean().sort_index().to_numpy()
    lag = max(horizon, int(round(len(daily) ** (1 / 3))))
    res.ic = float(daily.mean())
    res.t_nw = _hac_t(daily, lag)
    res.ci_low, res.ci_high = block_bootstrap_ci(
        daily, block=lag, samples=BOOTSTRAP_SAMPLES, confidence=CONFIDENCE, seed=seed)

    sign = 1.0 if res.ic >= 0 else -1.0
    weekly = df.groupby(weeks)["prod"].mean()
    res.week_consistency = float((np.sign(weekly) == sign).mean())

    # Each ticker's own Spearman IC (mean of its standardized-rank products)
    res.ticker_ic = {tk: float(p["prod"].mean()) for tk, p in df.groupby("ticker") if len(p) >= MIN_OBS_PER_TICKER}
    votes = [np.sign(v) == sign for v in res.ticker_ic.values()]
    res.ticker_agreement = float(np.mean(votes)) if votes else None

    loo = []
    for tk in res.ticker_ic:
        rest = df[df["ticker"] != tk].groupby("date")["prod"].mean().sort_index().to_numpy()
        t = _hac_t(rest, lag)
        if t is None:  # the rest has no usable variation: the result hangs on this one ticker
            loo = None
            break
        loo.append(sign * t)
    res.leave_one_out_t = float(min(loo)) if loo and len(loo) >= 2 else None

    significant = (res.ci_low > 0 or res.ci_high < 0) and res.t_nw is not None and abs(res.t_nw) >= MIN_T_STAT
    stable = (res.week_consistency >= MIN_WEEK_CONSISTENCY
              and res.ticker_agreement is not None and res.ticker_agreement >= MIN_TICKER_AGREEMENT
              and res.leave_one_out_t is not None and res.leave_one_out_t >= MIN_LEAVE_ONE_OUT_T)
    if significant and stable:
        res.verdict = ALIVE if res.ic > 0 else REVERSED
        res.reason = "CI excludes 0, |t| >= 2, sign stable across weeks and tickers, no single ticker drives it"
    else:
        res.verdict = DEAD
        missing = []
        if not (res.ci_low > 0 or res.ci_high < 0):
            missing.append("CI includes 0")
        if res.t_nw is None or abs(res.t_nw) < MIN_T_STAT:
            missing.append(f"|t|={abs(res.t_nw or 0):.1f} < {MIN_T_STAT}")
        if res.week_consistency < MIN_WEEK_CONSISTENCY:
            missing.append(f"weeks with same sign {res.week_consistency:.0%} < {MIN_WEEK_CONSISTENCY:.0%}")
        if res.ticker_agreement is None or res.ticker_agreement < MIN_TICKER_AGREEMENT:
            agree = "n/a" if res.ticker_agreement is None else f"{res.ticker_agreement:.0%}"
            missing.append(f"tickers agreeing {agree} < {MIN_TICKER_AGREEMENT:.0%}")
        if res.leave_one_out_t is None or res.leave_one_out_t < MIN_LEAVE_ONE_OUT_T:
            loo_txt = "n/a" if res.leave_one_out_t is None else f"{res.leave_one_out_t:.1f}"
            missing.append(f"leave-one-ticker-out t {loo_txt} < {MIN_LEAVE_ONE_OUT_T}")
        res.reason = "; ".join(missing)
    return res


# --- Flag effect (does a modifier/gate mark worse forward returns?) ----------------------------------

MIN_FLAG_INDEPENDENT_OBS = 10  # flagged dates / horizon, and the same for unflagged dates
MIN_FLAG_TICKERS = 2           # tickers seen both with and without the flag

LOWER, HIGHER, NO_DIFFERENCE = "LOWER", "HIGHER", "NO_DIFFERENCE"


@dataclass
class FlagResult:
    name: str
    horizon: int
    n_flagged: int
    n_unflagged: int
    flagged_dates: int
    unflagged_dates: int
    mixed_tickers: List[str] = field(default_factory=list)
    always_flagged: List[str] = field(default_factory=list)  # carry no within-ticker contrast
    diff: Optional[float] = None       # mean excess return flagged - unflagged, within-ticker demeaned
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    leave_one_out_same_sign: Optional[bool] = None  # rest keeps the sign with a CI excluding 0
    verdict: str = INSUFFICIENT
    reason: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _flag_diff(df: pd.DataFrame) -> Optional[float]:
    f, u = df.loc[df["flag"], "dret"], df.loc[~df["flag"], "dret"]
    if f.empty or u.empty:
        return None
    return float(f.mean() - u.mean())


def _flag_diff_ci(df: pd.DataFrame, horizon: int, seed: int) -> tuple:
    """Moving-block bootstrap over dates of the flagged-minus-unflagged mean (rows of one date move together)."""
    dates = np.sort(df["date"].unique())
    n = len(dates)
    if n < 2:
        return None, None
    di = df["date"].map({d: i for i, d in enumerate(dates)}).to_numpy()
    fl = df["flag"].to_numpy()
    r = df["dret"].to_numpy()
    sf, nf = np.bincount(di[fl], r[fl], n), np.bincount(di[fl], minlength=n).astype(float)
    su, nu = np.bincount(di[~fl], r[~fl], n), np.bincount(di[~fl], minlength=n).astype(float)
    block = max(1, min(max(horizon, int(round(n ** (1 / 3)))), n))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(BOOTSTRAP_SAMPLES, math.ceil(n / block)))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(BOOTSTRAP_SAMPLES, -1)[:, :n]
    with np.errstate(invalid="ignore", divide="ignore"):
        diffs = sf[idx].sum(1) / nf[idx].sum(1) - su[idx].sum(1) / nu[idx].sum(1)
    diffs = diffs[np.isfinite(diffs)]
    if diffs.size == 0:
        return None, None
    a = (1.0 - CONFIDENCE) / 2.0
    return float(np.quantile(diffs, a)), float(np.quantile(diffs, 1.0 - a))


def evaluate_flag(panel: pd.DataFrame, name: str, horizon: int, seed: int = 7) -> FlagResult:
    """Do snapshots carrying a flag (e.g. CATALYST RISK) see a different excess forward return?

    `panel` has columns ticker, date, flag (bool), ret. Only tickers seen both with and without the flag
    count, and returns are demeaned inside each ticker: a flag that sits on one ticker for weeks while that
    ticker drifts down would otherwise look predictive just by naming the ticker. The CI comes from a
    moving-block bootstrap over dates (rows of one date move together), and the result must stay
    significant in the same direction after dropping any single ticker. LOWER means flagged snapshots were followed by worse returns: what a bearish gate
    is supposed to catch.
    """
    df = panel.dropna(subset=["ret"]).copy()
    df["date"] = pd.to_datetime(df["date"])
    df["flag"] = df["flag"].astype(bool)
    states = df.groupby("ticker")["flag"].agg(["any", "all"])
    mixed = sorted(states.index[states["any"] & ~states["all"]])
    always = sorted(states.index[states["all"]])
    df = df[df["ticker"].isin(mixed)]
    res = FlagResult(name=name, horizon=horizon, n_flagged=int(df["flag"].sum()),
                     n_unflagged=int((~df["flag"]).sum()),
                     flagged_dates=df.loc[df["flag"], "date"].nunique(),
                     unflagged_dates=df.loc[~df["flag"], "date"].nunique(),
                     mixed_tickers=mixed, always_flagged=always)
    short = []
    h = max(horizon, 1)
    if res.flagged_dates / h < MIN_FLAG_INDEPENDENT_OBS:
        short.append(f"{res.flagged_dates} flagged dates / horizon {horizon} (need {MIN_FLAG_INDEPENDENT_OBS})")
    if res.unflagged_dates / h < MIN_FLAG_INDEPENDENT_OBS:
        short.append(f"{res.unflagged_dates} unflagged dates / horizon {horizon} (need {MIN_FLAG_INDEPENDENT_OBS})")
    if len(mixed) < MIN_FLAG_TICKERS:
        short.append(f"{len(mixed)} tickers seen with and without the flag (need {MIN_FLAG_TICKERS})"
                     + (f"; always flagged: {', '.join(always)}" if always else ""))
    if short:
        res.reason = "; ".join(short)
        return res

    df["dret"] = df["ret"] - df.groupby("ticker")["ret"].transform("mean")
    res.diff = _flag_diff(df)

    res.ci_low, res.ci_high = _flag_diff_ci(df, horizon, seed)

    # Dropping any one ticker, the rest must still show a difference of the same sign whose CI excludes 0:
    # a sign-only check is passed half the time by noise once one strong ticker sets the direction.
    loo_ok = True
    for tk in mixed:
        rest = df[df["ticker"] != tk]
        d = _flag_diff(rest)
        lo, hi = _flag_diff_ci(rest, horizon, seed) if d is not None else (None, None)
        if d is None or lo is None or np.sign(d) != np.sign(res.diff) or not (lo > 0 or hi < 0):
            loo_ok = False
            break
    res.leave_one_out_same_sign = loo_ok

    significant = res.ci_low > 0 or res.ci_high < 0
    if significant and res.leave_one_out_same_sign:
        res.verdict = LOWER if res.diff < 0 else HIGHER
        res.reason = "CI excludes 0 and no single ticker carries the sign"
    else:
        res.verdict = NO_DIFFERENCE
        res.reason = "; ".join(m for m, bad in (
            ("CI includes 0", not significant),
            ("not significant once one ticker is dropped", not res.leave_one_out_same_sign)) if bad)
    return res


def format_flag(r: FlagResult) -> str:
    if r.diff is None:
        return f"{r.name:18s} {r.horizon}d  flagged={r.n_flagged:3d}/{r.n_flagged + r.n_unflagged:3d}  {r.verdict}: {r.reason}"
    extra = f"  (always flagged, excluded: {', '.join(r.always_flagged)})" if r.always_flagged else ""
    return (f"{r.name:18s} {r.horizon}d  flagged={r.n_flagged:3d}/{r.n_flagged + r.n_unflagged:3d}  "
            f"diff={r.diff:+.2%} CI95=[{r.ci_low:+.2%}, {r.ci_high:+.2%}]  {r.verdict}"
            + (f" ({r.reason})" if r.verdict == NO_DIFFERENCE else "") + extra)


def build_panel(observations: Sequence[dict], score_key: str) -> pd.DataFrame:
    """One row per (ticker, entry date): the latest snapshot before that close. Snapshots sharing an entry
    close share the same forward return, so keeping all of them would multiply identical observations."""
    rows = [o for o in observations if o.get(score_key) is not None and o.get("ret") is not None]
    if not rows:
        return pd.DataFrame(columns=["ticker", "date", "score", "ret"])
    df = pd.DataFrame([{"ticker": o["ticker"], "date": o["entry_date"], "ts": o["ts"],
                        "score": o[score_key], "ret": o["ret"]} for o in rows])
    df = df.sort_values("ts").groupby(["ticker", "date"], as_index=False).last()
    return df[["ticker", "date", "score", "ret"]]


def format_result(r: ICResult) -> str:
    if r.ic is None:
        return f"{r.name:12s} {r.horizon}d  n={r.n_obs:4d}  {r.verdict}: {r.reason}"
    tickers = " ".join(f"{k}={v:+.2f}" for k, v in sorted(r.ticker_ic.items()))
    if r.flat_tickers:
        tickers += f"  (flat, excluded: {', '.join(r.flat_tickers)})"
    return (f"{r.name:12s} {r.horizon}d  n={r.n_obs:4d} dates={r.n_dates:3d}  IC={r.ic:+.3f} "
            f"CI95=[{r.ci_low:+.3f}, {r.ci_high:+.3f}] t_NW={r.t_nw if r.t_nw is None else round(r.t_nw, 2)} "
            f"weeks={r.week_consistency:.0%} tickers={'n/a' if r.ticker_agreement is None else f'{r.ticker_agreement:.0%}'} "
            f"LOO_t={'n/a' if r.leave_one_out_t is None else f'{r.leave_one_out_t:.1f}'}"
            f"  {r.verdict}" + (f" ({r.reason})" if r.verdict == DEAD else "") + f"\n{'':16s}{tickers}")
