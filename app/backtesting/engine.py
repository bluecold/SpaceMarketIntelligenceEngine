import json
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
import numpy as np
from sqlalchemy.orm import Session
from app.database.models import SSISnapshotModel, MarketSnapshotModel, utc_now
from app.scoring.smi import calculate_smi
from app.scoring.signal import generate_signal_and_explanation
from app.config import INITIAL_TICKERS, settings


def calculate_financial_metrics(
    returns: List[float],
    risk_free_rate: float = 0.0,
    holding_period_days: int = 1
) -> Dict[str, Any]:
    """
    Computes standard quantitative trading and event-level backtesting metrics:
    Win Rate, Profit Factor, Expectancy, Max Drawdown, Sharpe Ratio, Sortino Ratio.
    Annualizes Sharpe and Sortino based on the actual holding horizon: sqrt(252 / holding_period_days).
    """
    if not returns:
        return {
            "total_trades": 0,
            "win_rate": 0.0,
            "avg_return": 0.0,
            "median_return": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0
        }

    arr_returns = np.array(returns, dtype=float)
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    
    win_rate = (len(wins) / len(returns)) * 100.0 if returns else 0.0
    avg_return = float(np.mean(arr_returns))
    median_return = float(np.median(arr_returns))
    
    total_gains = sum(wins) if wins else 0.0
    total_losses = abs(sum(losses)) if losses else 0.0
    profit_factor = (total_gains / total_losses) if total_losses > 0 else (99.0 if total_gains > 0 else 0.0)
    
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = abs(float(np.mean(losses))) if losses else 0.0
    loss_rate = (len(losses) / len(returns))
    expectancy = ((win_rate / 100.0) * avg_win) - (loss_rate * avg_loss)

    # Max Drawdown calculation from cumulative equity curve (incorporating initial capital 1.0)
    equity_curve = np.insert(np.cumprod(1.0 + arr_returns / 100.0), 0, 1.0)
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - peak) / peak
    max_drawdown = abs(float(np.min(drawdowns))) * 100.0 if len(drawdowns) > 0 else 0.0

    # Horizon-adjusted annualization factor: sqrt(252 / H)
    periods_per_year = max(1.0, 252.0 / float(max(1, holding_period_days)))
    annualization_factor = math.sqrt(periods_per_year)

    # Sharpe Ratio
    std_return = float(np.std(arr_returns)) if len(arr_returns) > 1 else 0.0
    excess_mean = avg_return - (risk_free_rate / periods_per_year)
    sharpe_ratio = (excess_mean / std_return * annualization_factor) if std_return > 0 else 0.0

    # Sortino Ratio: Target Downside Deviation (Lower Partial Moment 2 with target = MAR)
    target = risk_free_rate / periods_per_year
    downside_diffs = np.minimum(0.0, arr_returns - target)
    downside_variance = float(np.mean(downside_diffs ** 2))
    downside_std = math.sqrt(downside_variance)

    if downside_std > 0:
        sortino_ratio = (excess_mean / downside_std) * annualization_factor
    elif excess_mean > 0:
        sortino_ratio = 99.0  # Zero downside risk with positive excess returns
    else:
        sortino_ratio = 0.0

    return {
        "total_trades": len(returns),
        "win_rate": round(win_rate, 1),
        "avg_return": round(avg_return, 2),
        "median_return": round(median_return, 2),
        "profit_factor": round(profit_factor, 2),
        "expectancy": round(expectancy, 2),
        "max_drawdown": round(max_drawdown, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "sortino_ratio": round(sortino_ratio, 2)
    }


def _parse_timestamp(ts: Any) -> Optional[datetime]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None) if ts.tzinfo is not None else ts
    if isinstance(ts, str):
        try:
            clean_str = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean_str)
            return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt
        except Exception:
            return None
    return None


def simulate_portfolio_execution(
    trades: List[Dict[str, Any]],
    initial_capital: float = 100000.0,
    max_concurrent_positions: int = 5,
    transaction_cost_bps: float = 10.0,
    holding_period_days: int = 3
) -> Dict[str, Any]:
    """
    Simulates realistic portfolio execution across multiple simultaneous trade signals:
    - Capital allocation with position limits (e.g. 20% max per position for max_concurrent=5).
    - Prevents overlapping sequential leverage by tracking cash balance and active positions.
    - Applies realistic transaction costs and slippage on entries and exits (deducted from cash).
    - Computes portfolio-level equity curve, max drawdown, and capital utilization across all events.
    - Resolves holding_period_days when trade exit_time is unspecified.
    """
    if not trades:
        return {
            "initial_capital": initial_capital,
            "ending_capital": initial_capital,
            "total_net_return_pct": 0.0,
            "portfolio_max_drawdown_pct": 0.0,
            "max_concurrent_positions": 0,
            "avg_capital_invested_pct": 0.0,
            "total_transaction_costs": 0.0,
            "total_executed_trades": 0,
            "skipped_trades_no_cash": 0
        }

    # Normalize trades with parsed timestamps and holding_period_days fallback
    normalized_trades = []
    for t in trades:
        entry_dt = _parse_timestamp(t.get("entry_time"))
        exit_dt = _parse_timestamp(t.get("exit_time"))
        if exit_dt is None and entry_dt is not None and holding_period_days > 0:
            exit_dt = entry_dt + timedelta(days=holding_period_days)

        normalized_trades.append({
            "ticker": t.get("ticker", "UNKNOWN"),
            "entry_time": entry_dt,
            "exit_time": exit_dt,
            "return": float(t.get("return", 0.0))
        })

    # Sort trades chronologically by entry_time
    sorted_trades = sorted(
        normalized_trades,
        key=lambda t: t["entry_time"] if t["entry_time"] is not None else datetime.min
    )

    cost_multiplier = transaction_cost_bps / 10000.0
    cash = initial_capital
    max_pos_capital = initial_capital / float(max_concurrent_positions)

    active_positions: List[Dict[str, Any]] = []
    executed_trades = 0
    skipped_no_cash = 0
    total_costs = 0.0
    max_concurrent_seen = 0

    equity_points: List[float] = [initial_capital]
    invested_fractions: List[float] = [0.0]

    # Process events in chronological sequence
    for trade in sorted_trades:
        curr_entry = trade["entry_time"]
        curr_exit = trade["exit_time"]
        t_return = trade["return"]

        # 1. Close any positions that have reached their exit time before or at this entry
        if curr_entry is not None:
            closing_positions = []
            remaining_positions = []
            for pos in active_positions:
                pos_exit = pos.get("exit_time")
                if pos_exit is not None and pos_exit <= curr_entry:
                    closing_positions.append(pos)
                else:
                    remaining_positions.append(pos)

            # Sort closing positions chronologically by their exit time
            closing_positions.sort(key=lambda p: p.get("exit_time") or datetime.min)

            for pos in closing_positions:
                gross_proceeds = pos["allocated"] * (1.0 + pos["return"] / 100.0)
                exit_cost = gross_proceeds * cost_multiplier
                net_proceeds = gross_proceeds - exit_cost
                cash += net_proceeds
                total_costs += exit_cost

            if closing_positions:
                active_positions = remaining_positions
                active_val = sum(p["allocated"] for p in active_positions)
                curr_equity = cash + active_val
                equity_points.append(curr_equity)
                invested_fractions.append(active_val / curr_equity if curr_equity > 0 else 0.0)

        # 2. Check position limit and available cash (accounting for entry commission)
        max_affordable = cash / (1.0 + cost_multiplier)
        allocated = min(max_affordable, max_pos_capital)

        if len(active_positions) >= max_concurrent_positions or allocated < 10.0:
            skipped_no_cash += 1
            continue

        entry_cost = allocated * cost_multiplier
        total_costs += entry_cost
        cash -= (allocated + entry_cost)

        active_positions.append({
            "ticker": trade["ticker"],
            "allocated": allocated,
            "entry_time": curr_entry,
            "exit_time": curr_exit,
            "return": t_return
        })
        executed_trades += 1
        max_concurrent_seen = max(max_concurrent_seen, len(active_positions))

        # Current total portfolio equity after entry
        active_val = sum(p["allocated"] for p in active_positions)
        curr_equity = cash + active_val
        equity_points.append(curr_equity)
        invested_fractions.append(active_val / curr_equity if curr_equity > 0 else 0.0)

    # 3. Close all remaining open positions at the end of the simulation
    active_positions.sort(key=lambda p: p.get("exit_time") or datetime.max)
    while active_positions:
        pos = active_positions.pop(0)
        gross_proceeds = pos["allocated"] * (1.0 + pos["return"] / 100.0)
        exit_cost = gross_proceeds * cost_multiplier
        net_proceeds = gross_proceeds - exit_cost
        cash += net_proceeds
        total_costs += exit_cost

        active_val = sum(p["allocated"] for p in active_positions)
        curr_equity = cash + active_val
        equity_points.append(curr_equity)
        invested_fractions.append(active_val / curr_equity if curr_equity > 0 else 0.0)

    ending_capital = cash
    if len(equity_points) == 0 or equity_points[-1] != ending_capital:
        equity_points.append(ending_capital)
        invested_fractions.append(0.0)

    # Calculate portfolio max drawdown and periodic portfolio Sharpe from non-overlapping equity points
    eq_arr = np.array(equity_points, dtype=float)
    peak = np.maximum.accumulate(eq_arr)
    drawdowns = (eq_arr - peak) / peak
    port_max_dd = abs(float(np.min(drawdowns))) * 100.0 if len(drawdowns) > 0 else 0.0

    eq_returns = np.diff(eq_arr) / eq_arr[:-1] if len(eq_arr) > 1 else np.array([])
    rf_daily = (0.04 / 252.0)  # Standard 4% annual risk-free rate
    if len(eq_returns) > 1 and np.std(eq_returns) > 0:
        excess_daily = eq_returns - rf_daily
        port_sharpe = float(np.mean(excess_daily) / np.std(eq_returns) * math.sqrt(252.0))
    else:
        port_sharpe = 0.0

    total_net_return = ((ending_capital - initial_capital) / initial_capital) * 100.0
    avg_invested = float(np.mean(invested_fractions)) * 100.0

    return {
        "initial_capital": round(initial_capital, 2),
        "ending_capital": round(ending_capital, 2),
        "total_net_return_pct": round(total_net_return, 2),
        "portfolio_max_drawdown_pct": round(port_max_dd, 2),
        "portfolio_sharpe_ratio": round(port_sharpe, 2),
        "max_concurrent_positions": max_concurrent_seen,
        "avg_capital_invested_pct": round(avg_invested, 1),
        "total_transaction_costs": round(total_costs, 2),
        "total_executed_trades": executed_trades,
        "skipped_trades_no_cash": skipped_no_cash
    }


def compute_hypothesis_significance(
    model_a_trades: List[Dict[str, Any]],
    model_b_trades: List[Dict[str, Any]],
    min_required_trades: int = 30,
    n_bootstrap: int = 1000,
    random_seed: int = 42
) -> Dict[str, Any]:
    """
    Performs a non-parametric block / time-cluster bootstrap hypothesis test
    comparing Model B (Treatment: Multisource + Polymarket) against Model A (Control: Baseline).

    Tests:
    H0: Delta E(Return) <= 0  (Polymarket adds zero or negative incremental edge)
    H1: Delta E(Return) > 0   (Polymarket adds strictly positive alpha)

    Guarantees:
    - Does NOT assume normal returns or constant variance.
    - Preserves autocorrelation and cross-asset clustering by resampling contiguous blocks.
    - Reports 95% Bootstrap Confidence Interval and empirical one-sided p-value.
    - Distinguishes sample count threshold (min_sample_reached) from true statistical significance (is_statistically_significant).
    """
    n_a = len(model_a_trades)
    n_b = len(model_b_trades)
    min_sample = min(n_a, n_b)
    min_sample_reached = (min_sample >= min_required_trades)

    returns_a = np.array([t["return"] for t in model_a_trades], dtype=float) if n_a > 0 else np.array([], dtype=float)
    returns_b = np.array([t["return"] for t in model_b_trades], dtype=float) if n_b > 0 else np.array([], dtype=float)

    mean_delta = float(np.mean(returns_b) - np.mean(returns_a)) if (n_a > 0 and n_b > 0) else 0.0

    # Check calendar date synchrony when timestamps are present (R2-01 audit fix)
    has_dates_a = any(t.get("entry_time") is not None for t in model_a_trades)
    has_dates_b = any(t.get("entry_time") is not None for t in model_b_trades)
    is_date_paired = False
    paired_diffs = []
    common_dates_count = 0

    if has_dates_a and has_dates_b:
        def _get_trade_date(t):
            dt = _parse_timestamp(t.get("entry_time"))
            return dt.date().isoformat() if dt else None

        dates_a = {_get_trade_date(t) for t in model_a_trades if _get_trade_date(t)}
        dates_b = {_get_trade_date(t) for t in model_b_trades if _get_trade_date(t)}
        common_dates = dates_a.intersection(dates_b)
        common_dates_count = len(common_dates)

        if not common_dates or (common_dates_count / max(len(dates_a), len(dates_b)) < 0.5):
            return {
                "min_sample_size": min_sample,
                "min_sample_reached": False,
                "is_statistically_significant": False,
                "positive_edge_significant": False,
                "negative_edge_significant": False,
                "difference_significant": False,
                "p_value": 1.0,
                "confidence_interval_95": {"lower": 0.0, "upper": 0.0},
                "mean_return_delta_pct": round(mean_delta, 2),
                "date_overlap_count": common_dates_count,
                "test_method": f"Block Bootstrap (Insufficient calendar alignment: {common_dates_count} common dates < 50% overlap required)"
            }

        # Build date-and-ticker aligned pairs across the synchronized calendar timeline
        trade_key_a = {}
        for t in model_a_trades:
            d = _get_trade_date(t)
            sym = str(t.get("ticker", "")).upper()
            if d:
                trade_key_a[(d, sym)] = float(t.get("return", 0.0))

        trade_key_b = {}
        for t in model_b_trades:
            d = _get_trade_date(t)
            sym = str(t.get("ticker", "")).upper()
            if d:
                trade_key_b[(d, sym)] = float(t.get("return", 0.0))

        min_common_date = min(common_dates)
        max_common_date = max(common_dates)
        all_keys = sorted([
            k for k in (set(trade_key_a.keys()) | set(trade_key_b.keys()))
            if min_common_date <= k[0] <= max_common_date
        ])
        aligned_a = []
        aligned_b = []
        for key in all_keys:
            # If Model B took a trade that Model A did not, alternative return is 0.0% (cash / no trade)
            ret_a = trade_key_a.get(key, 0.0)
            ret_b = trade_key_b.get(key, 0.0)
            aligned_a.append(ret_a)
            aligned_b.append(ret_b)

        n_pairs = len(aligned_a)
        if n_pairs < min_required_trades:
            return {
                "min_sample_size": min_sample,
                "min_sample_reached": False,
                "is_statistically_significant": False,
                "positive_edge_significant": False,
                "negative_edge_significant": False,
                "difference_significant": False,
                "p_value": 1.0,
                "confidence_interval_95": {"lower": 0.0, "upper": 0.0},
                "mean_return_delta_pct": round(mean_delta, 2),
                "date_overlap_count": common_dates_count,
                "test_method": f"Block Bootstrap (Insufficient trade observations: {n_pairs} < {min_required_trades} required)"
            }

        paired_diffs = np.array(aligned_b, dtype=float) - np.array(aligned_a, dtype=float)
        is_date_paired = True
        min_sample = n_pairs
        min_sample_reached = (min_sample >= min_required_trades)
        mean_delta = float(np.mean(paired_diffs))

    if not min_sample_reached or n_a == 0 or n_b == 0:
        return {
            "min_sample_size": min_sample,
            "min_sample_reached": min_sample_reached,
            "is_statistically_significant": False,
            "positive_edge_significant": False,
            "negative_edge_significant": False,
            "difference_significant": False,
            "p_value": 1.0,
            "confidence_interval_95": {"lower": 0.0, "upper": 0.0},
            "mean_return_delta_pct": round(mean_delta, 2),
            "date_overlap_count": common_dates_count if (has_dates_a and has_dates_b) else None,
            "test_method": "Block Bootstrap (N < 30 insufficient sample)"
        }

    rng = np.random.default_rng(random_seed)

    # Contiguous block size to capture serial and cross-asset market dependencies
    block_size = max(1, min(5, min_sample // 10))
    n_blocks = max(1, min_sample // block_size)

    delta_means = np.empty(n_bootstrap, dtype=float)

    for b in range(n_bootstrap):
        if is_date_paired:
            # Resample paired differences directly across synchronized timeline
            idx = rng.integers(0, max(1, min_sample - block_size + 1), size=n_blocks)
            resampled_diffs = np.concatenate([paired_diffs[i : i + block_size] for i in idx])
            delta_means[b] = float(np.mean(resampled_diffs))
        elif n_a == n_b:
            # Fully synchronized paired block resampling
            idx = rng.integers(0, max(1, min_sample - block_size + 1), size=n_blocks)
            resampled_a = np.concatenate([returns_a[i : i + block_size] for i in idx])
            resampled_b = np.concatenate([returns_b[i : i + block_size] for i in idx])
            delta_means[b] = float(np.mean(resampled_b - resampled_a))
        else:
            # Synchronized timeline-aligned block resampling
            idx_rel = rng.random(size=n_blocks)
            idx_a = (idx_rel * max(1, n_a - block_size)).astype(int)
            idx_b = (idx_rel * max(1, n_b - block_size)).astype(int)
            resampled_a = np.concatenate([returns_a[i : i + block_size] for i in idx_a])
            resampled_b = np.concatenate([returns_b[i : i + block_size] for i in idx_b])
            delta_means[b] = float(np.mean(resampled_b) - np.mean(resampled_a))

    # 95% Confidence Interval (percentile method)
    ci_lower = float(np.percentile(delta_means, 2.5))
    ci_upper = float(np.percentile(delta_means, 97.5))

    # Empirical one-sided p-values:
    # p_value_pos: probability that Delta Mean <= 0 (testing for positive alpha B > A)
    # p_value_neg: probability that Delta Mean >= 0 (testing for negative alpha B < A)
    p_value_pos = float(np.mean(delta_means <= 0.0))
    p_value_neg = float(np.mean(delta_means >= 0.0))

    # Directional significance:
    # 1. Positive edge: Model B strictly outperforms Model A with 95% CI > 0
    positive_edge_significant = bool(min_sample_reached and p_value_pos < 0.05 and ci_lower > 0.0)

    # 2. Negative edge: Model B strictly underperforms Model A with 95% CI < 0
    negative_edge_significant = bool(min_sample_reached and p_value_neg < 0.05 and ci_upper < 0.0)

    # 3. Difference significance (two-sided): 95% CI strictly excludes 0 in either direction
    difference_significant = bool(positive_edge_significant or negative_edge_significant)

    reported_p_value = p_value_pos if mean_delta >= 0 else p_value_neg

    return {
        "min_sample_size": min_sample,
        "min_sample_reached": min_sample_reached,
        "is_statistically_significant": positive_edge_significant,
        "positive_edge_significant": positive_edge_significant,
        "negative_edge_significant": negative_edge_significant,
        "difference_significant": difference_significant,
        "p_value": round(reported_p_value, 4),
        "confidence_interval_95": {
            "lower": round(ci_lower, 2),
            "upper": round(ci_upper, 2)
        },
        "mean_return_delta_pct": round(mean_delta, 2),
        "date_overlap_count": common_dates_count if (has_dates_a and has_dates_b) else None,
        "test_method": f"Paired Block Bootstrap (B={n_bootstrap}, block_size={block_size}, 95% CI)"
    }


def evaluate_backtest_dataset(
    snapshots: List[Dict[str, Any]],
    holding_period_days: int = 3,
    buy_threshold: Optional[float] = None
) -> Dict[str, Any]:
    """
    Evaluates signal efficacy by comparing signals (STRONG BUY / BUY)
    against forward realized returns at specified holding periods (1D, 3D, 5D).
    
    Rigorous Apples-to-Apples Comparison:
    - Model A (Control): SMI computed WITHOUT Polymarket prediction markets.
    - Model B (Treatment): SMI computed WITH Polymarket prediction markets.
    Both models use the identical buy_threshold and identical multi-factor engine.
    
    Timestamp-Aware Horizon Matching:
    - Uses real physical timestamps (target_time = t_entry + holding_period_days)
      to avoid confusing N snapshots (e.g. 3 hours) with N real days.
    - Falls back to step-based index matching only for synthetic untimestamped tests.
    """
    if buy_threshold is None:
        buy_threshold = getattr(settings, "THRESHOLD_BUY", 65.0)

    model_a_trades: List[Dict[str, Any]] = [] # Model A: Without Polymarket
    model_b_trades: List[Dict[str, Any]] = [] # Model B: With Polymarket

    static_weights = {
        "social": settings.WEIGHT_SOCIAL,
        "prediction": settings.WEIGHT_PREDICTION,
        "news": settings.WEIGHT_NEWS,
        "momentum": settings.WEIGHT_MOMENTUM,
        "fundamental": settings.WEIGHT_FUNDAMENTALS,
        "risk": settings.WEIGHT_RISK
    }

    # Group snapshots by ticker for isolated trajectory analysis
    ticker_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in snapshots:
        ticker_groups[s.get("ticker", "UNKNOWN")].append(s)

    all_trades_a = []
    all_trades_b = []

    for sym, raw_snaps in ticker_groups.items():
        if len(raw_snaps) < 2:
            continue

        has_timestamps = any(s.get("timestamp") is not None for s in raw_snaps)
        if has_timestamps:
            ticker_snaps = sorted(
                raw_snaps,
                key=lambda s: _parse_timestamp(s.get("timestamp")) or datetime.min
            )
        else:
            ticker_snaps = raw_snaps

        locked_until_ts_a = None
        locked_until_idx_a = -1

        locked_until_ts_b = None
        locked_until_idx_b = -1

        for i, current in enumerate(ticker_snaps):
            curr_price = current.get("price")
            if curr_price is None or curr_price <= 0:
                continue

            curr_ts = _parse_timestamp(current.get("timestamp"))

            can_enter_a = (curr_ts >= locked_until_ts_a) if (curr_ts is not None and locked_until_ts_a is not None) else (locked_until_ts_a is None if curr_ts is not None else i >= locked_until_idx_a)
            can_enter_b = (curr_ts >= locked_until_ts_b) if (curr_ts is not None and locked_until_ts_b is not None) else (locked_until_ts_b is None if curr_ts is not None else i >= locked_until_idx_b)

            if not can_enter_a and not can_enter_b:
                continue

            soc = current.get("social_score")
            pred = current.get("prediction_score")
            news = current.get("news_score")
            mom = current.get("momentum_score")
            risk = current.get("risk_score")
            tech = current.get("technical_score")
            fund = current.get("fundamental_score")
            post_cnt = current.get("post_count")
            news_cnt = current.get("news_count")
            pred_cnt = current.get("prediction_count")
            pred_qual = current.get("prediction_quality", 50.0)

            # Model A: SMI computed WITHOUT Polymarket (prediction_score=None, weight redistributed)
            signal_a = False
            smi_a = None
            weights_a = current.get("effective_weights") or static_weights
            if can_enter_a:
                smi_a_res = calculate_smi(
                    social_score=soc,
                    prediction_score=None,
                    news_score=news,
                    momentum_score=mom,
                    risk_score=risk,
                    technical_score_raw=tech,
                    fundamental_score=fund,
                    post_count=post_cnt,
                    news_count=news_cnt,
                    prediction_count=0,
                    custom_weights=weights_a
                )
                smi_a = smi_a_res["smi"]
                sig_a_res = generate_signal_and_explanation(
                    ticker=sym,
                    smi=smi_a,
                    social_score=soc,
                    prediction_score=None,
                    news_score=news,
                    momentum_score=mom,
                    technical_score_raw=tech,
                    source_agreement=smi_a_res.get("source_agreement"),
                    data_quality=smi_a_res.get("data_quality"),
                    indicators=current.get("indicators") or {
                        "price": curr_price,
                        "rsi14": current.get("rsi14", current.get("rsi")),
                        "status": current.get("market_status", "AVAILABLE")
                    },
                    fundamentals=current.get("fundamentals"),
                    fundamental_score=fund,
                    risk_score=risk,
                    is_mom_comparable_1d=smi_a_res.get("is_mom_comparable_1d", True),
                    social_stats={"total_posts": post_cnt} if post_cnt is not None else None
                )
                if smi_a is not None and smi_a >= buy_threshold and sig_a_res.get("base_signal") in ["BUY", "STRONG BUY"]:
                    signal_a = True

            # Model B: SMI computed WITH Polymarket (incorporating prediction markets)
            signal_b = False
            smi_b = None
            if can_enter_b:
                if pred is None:
                    smi_b = smi_a
                    signal_b = signal_a
                else:
                    weights_b = current.get("effective_weights") or static_weights
                    smi_b_res = calculate_smi(
                        social_score=soc,
                        prediction_score=pred,
                        prediction_quality=pred_qual,
                        news_score=news,
                        momentum_score=mom,
                        risk_score=risk,
                        technical_score_raw=tech,
                        fundamental_score=fund,
                        post_count=post_cnt,
                        news_count=news_cnt,
                        prediction_count=pred_cnt,
                        custom_weights=weights_b
                    )
                    smi_b = smi_b_res["smi"]
                    sig_b_res = generate_signal_and_explanation(
                        ticker=sym,
                        smi=smi_b,
                        social_score=soc,
                        prediction_score=pred,
                        news_score=news,
                        momentum_score=mom,
                        technical_score_raw=tech,
                        source_agreement=smi_b_res.get("source_agreement"),
                        data_quality=smi_b_res.get("data_quality"),
                        indicators=current.get("indicators") or {
                            "price": curr_price,
                            "rsi14": current.get("rsi14", current.get("rsi")),
                            "status": current.get("market_status", "AVAILABLE")
                        },
                        fundamentals=current.get("fundamentals"),
                        fundamental_score=fund,
                        risk_score=risk,
                        is_mom_comparable_1d=smi_b_res.get("is_mom_comparable_1d", True),
                        social_stats={"total_posts": post_cnt} if post_cnt is not None else None
                    )
                    if smi_b is not None and smi_b >= buy_threshold and sig_b_res.get("base_signal") in ["BUY", "STRONG BUY"]:
                        signal_b = True

            if not signal_a and not signal_b:
                continue

            future = None
            exit_ts = None
            exit_idx = -1

            if curr_ts is not None:
                target_time = curr_ts + timedelta(days=holding_period_days)
                max_tolerance_time = target_time + timedelta(days=max(2, holding_period_days))

                # Search forward for the earliest snapshot satisfying target holding period
                for j in range(i + 1, len(ticker_snaps)):
                    cand_ts = _parse_timestamp(ticker_snaps[j].get("timestamp"))
                    if cand_ts is not None and cand_ts >= target_time:
                        if cand_ts <= max_tolerance_time:
                            future = ticker_snaps[j]
                            exit_ts = cand_ts
                        break
            else:
                # Fallback for synthetic/step-based test datasets without timestamps
                future_idx = i + holding_period_days
                if future_idx < len(ticker_snaps):
                    future = ticker_snaps[future_idx]
                    exit_idx = future_idx

            if future is None:
                continue

            fut_price = future.get("price")
            if fut_price is None or fut_price <= 0:
                continue

            realized_return = ((fut_price - curr_price) / curr_price) * 100.0

            if signal_a:
                model_a_trades.append({
                    "ticker": sym,
                    "entry_time": curr_ts,
                    "exit_time": exit_ts,
                    "entry_idx": i,
                    "exit_idx": exit_idx,
                    "return": realized_return
                })
                locked_until_ts_a = exit_ts
                locked_until_idx_a = exit_idx if exit_idx >= 0 else i + holding_period_days

            if signal_b:
                model_b_trades.append({
                    "ticker": sym,
                    "entry_time": curr_ts,
                    "exit_time": exit_ts,
                    "entry_idx": i,
                    "exit_idx": exit_idx,
                    "return": realized_return
                })
                locked_until_ts_b = exit_ts
                locked_until_idx_b = exit_idx if exit_idx >= 0 else i + holding_period_days

    # Sort all multi-ticker trades globally in true chronological order
    model_a_trades.sort(key=lambda t: t["exit_time"] or t["entry_time"] or datetime.min)
    model_b_trades.sort(key=lambda t: t["exit_time"] or t["entry_time"] or datetime.min)

    model_a_returns = [t["return"] for t in model_a_trades]
    model_b_returns = [t["return"] for t in model_b_trades]

    metrics_a = calculate_financial_metrics(model_a_returns, holding_period_days=holding_period_days)
    metrics_b = calculate_financial_metrics(model_b_returns, holding_period_days=holding_period_days)

    portfolio_a = simulate_portfolio_execution(model_a_trades, holding_period_days=holding_period_days)
    portfolio_b = simulate_portfolio_execution(model_b_trades, holding_period_days=holding_period_days)

    # Hypothesis conclusion with formal statistical significance test
    significance_res = compute_hypothesis_significance(
        model_a_trades=model_a_trades,
        model_b_trades=model_b_trades,
        min_required_trades=getattr(settings, "DYNAMIC_WEIGHT_MIN_TRADES", 30)
    )

    is_statistically_significant = significance_res["positive_edge_significant"]
    difference_significant = significance_res["difference_significant"]
    min_sample = significance_res["min_sample_size"]
    min_sample_reached = significance_res["min_sample_reached"]

    sharpe_diff = metrics_b["sharpe_ratio"] - metrics_a["sharpe_ratio"]
    pf_diff = metrics_b["profit_factor"] - metrics_a["profit_factor"]
    wr_diff = metrics_b["win_rate"] - metrics_a["win_rate"]

    edge_positive = (sharpe_diff > 0.05) or (pf_diff > 0.0 and wr_diff >= 0.0)
    polymarket_adds_value = is_statistically_significant and edge_positive

    return {
        "holding_period_days": holding_period_days,
        "buy_threshold": buy_threshold,
        "model_a_baseline": {
            "name": "Model A (X Social + Technical + News Baseline)",
            "metrics": metrics_a,
            "portfolio": portfolio_a
        },
        "model_b_multisource": {
            "name": "Model B (Multi-Source with Polymarket PMS)",
            "metrics": metrics_b,
            "portfolio": portfolio_b
        },
        "hypothesis_analysis": {
            "polymarket_incremental_value": polymarket_adds_value,
            "is_statistically_significant": is_statistically_significant,
            "positive_edge_significant": significance_res["positive_edge_significant"],
            "negative_edge_significant": significance_res["negative_edge_significant"],
            "difference_significant": difference_significant,
            "min_sample_reached": min_sample_reached,
            "min_sample_size": min_sample,
            "p_value": significance_res["p_value"],
            "confidence_interval_95": significance_res["confidence_interval_95"],
            "mean_return_delta_pct": significance_res["mean_return_delta_pct"],
            "test_method": significance_res["test_method"],
            "win_rate_delta_pp": round(wr_diff, 1),
            "profit_factor_delta": round(pf_diff, 2),
            "sharpe_delta": round(sharpe_diff, 2)
        }
    }


def calculate_calibrated_prediction_weight(
    backtest_data: Dict[str, Any],
    min_trades: Optional[int] = None,
    pred_min: Optional[float] = None,
    pred_max: Optional[float] = None
) -> Dict[str, Any]:
    """
    Computes closed-loop dynamic weight calibration for Polymarket (WEIGHT_PREDICTION)
    based on forward empirical backtest efficacy (Delta Sharpe on 3D horizon).
    
    Guarantees:
    1. Statistical Sample Gate: Requires >= min_trades (default 30) on both arms before departing from base prior.
    2. Statistical Significance Gate: Requires statistical significance (two-sided difference_significant with 95% CI != 0)
       so feedback is not activated merely by reaching N=30 on random noise.
    3. Strict Risk Bounds: Limits calibrated weight to [pred_min (5%), pred_max (25%)].
    4. Sum Conservation: Proportionally renormalizes the other 5 pillar weights so the sum is identically 1.0000.
    """
    from app.config import settings

    min_sample = min_trades if min_trades is not None else getattr(settings, "DYNAMIC_WEIGHT_MIN_TRADES", 30)
    p_min = pred_min if pred_min is not None else getattr(settings, "DYNAMIC_WEIGHT_PRED_MIN", 0.05)
    p_max = pred_max if pred_max is not None else getattr(settings, "DYNAMIC_WEIGHT_PRED_MAX", 0.25)
    base_pred_weight = getattr(settings, "WEIGHT_PREDICTION", 0.15)

    # Extract 3D horizon (or evaluate directly if single horizon dict passed)
    if "evaluation_horizons" in backtest_data:
        horizon = backtest_data["evaluation_horizons"].get("3D", {})
    elif "model_b_multisource" in backtest_data:
        horizon = backtest_data
    else:
        horizon = {}

    trades_a = horizon.get("model_a_baseline", {}).get("metrics", {}).get("total_trades", 0)
    trades_b = horizon.get("model_b_multisource", {}).get("metrics", {}).get("total_trades", 0)
    sample_size = min(trades_a, trades_b)
    
    hyp_analysis = horizon.get("hypothesis_analysis", {})
    delta_sharpe = float(hyp_analysis.get("sharpe_delta", 0.0))
    win_rate_delta = float(hyp_analysis.get("win_rate_delta_pp", 0.0))
    # Check difference_significant for two-directional calibration with conservative default False
    is_diff_significant = hyp_analysis.get(
        "difference_significant",
        hyp_analysis.get("is_statistically_significant", False)
    )

    base_weights = {
        "social": getattr(settings, "WEIGHT_SOCIAL", 0.30),
        "prediction": base_pred_weight,
        "news": getattr(settings, "WEIGHT_NEWS", 0.20),
        "momentum": getattr(settings, "WEIGHT_MOMENTUM", 0.25),
        "fundamental": getattr(settings, "WEIGHT_FUNDAMENTALS", 0.10),
        "risk": getattr(settings, "WEIGHT_RISK", 0.0)
    }

    if sample_size < min_sample:
        return {
            "is_calibrated": False,
            "status": f"PRIOR_BASELINE_INSUFFICIENT_SAMPLE (N={sample_size} < {min_sample})",
            "base_weight": base_pred_weight,
            "calibrated_weight": base_pred_weight,
            "multiplier": 1.0,
            "delta_sharpe": delta_sharpe,
            "win_rate_delta_pp": win_rate_delta,
            "sample_size": sample_size,
            "min_required_sample": min_sample,
            "effective_weights": base_weights
        }

    if not is_diff_significant:
        return {
            "is_calibrated": False,
            "status": f"PRIOR_BASELINE_NOT_STATISTICALLY_SIGNIFICANT (p={hyp_analysis.get('p_value', 'N/A')})",
            "base_weight": base_pred_weight,
            "calibrated_weight": base_pred_weight,
            "multiplier": 1.0,
            "delta_sharpe": delta_sharpe,
            "win_rate_delta_pp": win_rate_delta,
            "sample_size": sample_size,
            "min_required_sample": min_sample,
            "effective_weights": base_weights
        }

    # Proportional adjustment based on Delta Sharpe
    # Delta Sharpe +1.0 -> multiplier 1.5 -> weight = 0.15 * 1.5 = 0.225
    raw_multiplier = 1.0 + (delta_sharpe * 0.5)
    calibrated_pred_weight = max(p_min, min(p_max, base_pred_weight * raw_multiplier))
    actual_multiplier = calibrated_pred_weight / base_pred_weight if base_pred_weight > 0 else 1.0

    # Renormalize other weights to ensure sum == 1.0000
    other_sum_base = sum(w for k, w in base_weights.items() if k != "prediction")
    remaining_weight = 1.0 - calibrated_pred_weight
    scale_factor = remaining_weight / other_sum_base if other_sum_base > 0 else 1.0

    effective_weights = {}
    for k, w in base_weights.items():
        if k == "prediction":
            effective_weights[k] = round(calibrated_pred_weight, 4)
        else:
            effective_weights[k] = round(w * scale_factor, 4)

    # Correct rounding drift on largest component
    drift = 1.0 - sum(effective_weights.values())
    if abs(drift) > 1e-6:
        effective_weights["social"] = round(effective_weights["social"] + drift, 4)

    return {
        "is_calibrated": True,
        "status": "CALIBRATED_ACTIVE",
        "base_weight": base_pred_weight,
        "calibrated_weight": round(calibrated_pred_weight, 4),
        "multiplier": round(actual_multiplier, 3),
        "delta_sharpe": delta_sharpe,
        "win_rate_delta_pp": win_rate_delta,
        "sample_size": sample_size,
        "min_required_sample": min_sample,
        "effective_weights": effective_weights
    }


def run_historical_backtest(
    db: Session,
    lookback_days: int = 60,
    include_mock: bool = False
) -> Dict[str, Any]:
    """
    Runs full backtesting engine over database snapshot history.
    Filters snapshots within lookback_days window and excludes synthetic (MOCK) data by default.
    """
    cutoff = utc_now() - timedelta(days=lookback_days)
    query = (
        db.query(SSISnapshotModel)
        .filter(SSISnapshotModel.timestamp >= cutoff)
    )
    if not include_mock:
        query = query.filter(SSISnapshotModel.data_source != "MOCK")

    snaps_db = query.order_by(SSISnapshotModel.timestamp.asc()).all()
    
    snapshots_list = []
    for s in snaps_db:
        fund_dict = None
        if getattr(s, "fundamentals_data", None):
            try:
                fund_dict = json.loads(s.fundamentals_data)
            except Exception:
                fund_dict = None
        if fund_dict is None and getattr(s, "runway_months", None) is not None:
            fund_dict = {"runway_months": s.runway_months}

        weights_dict = None
        if getattr(s, "effective_weights", None):
            try:
                weights_dict = json.loads(s.effective_weights)
            except Exception:
                weights_dict = None

        mkt_status = getattr(s, "market_status", None) or "AVAILABLE"
        rsi_val = getattr(s, "rsi14", None)

        snapshots_list.append({
            "ticker": s.ticker,
            "timestamp": s.timestamp,
            "social_score": s.social_score,
            "prediction_score": s.prediction_score,
            "prediction_quality": getattr(s, "prediction_quality", 50.0),
            "news_score": s.news_score,
            "momentum_score": s.momentum_score,
            "risk_score": s.risk_score,
            "technical_score": s.technical_score,
            "fundamental_score": s.fundamental_score,
            "smi": s.smi if s.smi is not None else s.ssi,
            "post_count": getattr(s, "post_count", None),
            "news_count": getattr(s, "news_count", None),
            "prediction_count": getattr(s, "prediction_count", None),
            "data_quality": getattr(s, "data_quality", 100.0),
            "price": s.price,
            "volume": getattr(s, "volume", None),
            "signal": s.signal,
            "base_signal": getattr(s, "base_signal", None),
            "signal_modifier": getattr(s, "signal_modifier", None),
            "rsi14": rsi_val,
            "market_status": mkt_status,
            "fundamentals": fund_dict,
            "effective_weights": weights_dict,
            "rules_version": getattr(s, "rules_version", "2.0.0"),
            "indicators": {
                "price": s.price,
                "rsi14": rsi_val,
                "status": mkt_status,
                "technical_score": s.technical_score
            }
        })

    # Evaluate for 1D, 3D, 5D holding horizons
    horizon_1d = evaluate_backtest_dataset(snapshots_list, holding_period_days=1)
    horizon_3d = evaluate_backtest_dataset(snapshots_list, holding_period_days=3)
    horizon_5d = evaluate_backtest_dataset(snapshots_list, holding_period_days=5)

    evaluation_horizons = {
        "1D": horizon_1d,
        "3D": horizon_3d,
        "5D": horizon_5d
    }

    calibration_result = calculate_calibrated_prediction_weight({
        "evaluation_horizons": evaluation_horizons
    })

    from app.config import settings
    if getattr(settings, "ENABLE_DYNAMIC_WEIGHT_FEEDBACK", False) and calibration_result["is_calibrated"]:
        from app.scoring.smi import set_calibrated_weights
        set_calibrated_weights(calibration_result["effective_weights"])

    return {
        "total_snapshots_analyzed": len(snapshots_list),
        "evaluation_horizons": evaluation_horizons,
        "dynamic_weight_calibration": calibration_result,
        "primary_research_question": "Does adding Polymarket PMS provide incremental alpha over X + Market alone?",
        "summary_recommendation": (
            "Model B (Multi-Source with Polymarket) exhibits tighter risk mitigation and higher signal confidence."
            if horizon_3d["hypothesis_analysis"]["polymarket_incremental_value"]
            else "Accumulating more live snapshot history to reach statistical significance across market regimes."
        )
    }
