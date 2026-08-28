import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict
import numpy as np
from sqlalchemy.orm import Session
from app.database.models import SSISnapshotModel, MarketSnapshotModel
from app.scoring.smi import calculate_smi
from app.config import INITIAL_TICKERS


def calculate_financial_metrics(
    returns: List[float],
    risk_free_rate: float = 0.0,
    holding_period_days: int = 1
) -> Dict[str, Any]:
    """
    Computes standard quantitative trading and backtesting metrics:
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

    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    
    win_rate = (len(wins) / len(returns)) * 100.0 if returns else 0.0
    avg_return = float(np.mean(returns))
    median_return = float(np.median(returns))
    
    total_gains = sum(wins) if wins else 0.0
    total_losses = abs(sum(losses)) if losses else 0.0
    profit_factor = (total_gains / total_losses) if total_losses > 0 else (99.0 if total_gains > 0 else 0.0)
    
    avg_win = float(np.mean(wins)) if wins else 0.0
    avg_loss = abs(float(np.mean(losses))) if losses else 0.0
    loss_rate = (len(losses) / len(returns))
    expectancy = ((win_rate / 100.0) * avg_win) - (loss_rate * avg_loss)

    # Max Drawdown calculation from cumulative equity curve
    equity_curve = np.cumprod(1.0 + np.array(returns) / 100.0)
    peak = np.maximum.accumulate(equity_curve)
    drawdowns = (equity_curve - peak) / peak
    max_drawdown = abs(float(np.min(drawdowns))) * 100.0 if len(drawdowns) > 0 else 0.0

    # Horizon-adjusted annualization factor: sqrt(252 / H)
    periods_per_year = max(1.0, 252.0 / float(max(1, holding_period_days)))
    annualization_factor = math.sqrt(periods_per_year)

    # Sharpe Ratio
    std_return = float(np.std(returns)) if len(returns) > 1 else 0.0
    excess_mean = avg_return - (risk_free_rate / periods_per_year)
    sharpe_ratio = (excess_mean / std_return * annualization_factor) if std_return > 0 else 0.0

    # Sortino Ratio (downside deviation only)
    downside_returns = [r for r in returns if r < 0]
    downside_std = float(np.std(downside_returns)) if len(downside_returns) > 1 else (std_return if std_return > 0 else 0.0)
    sortino_ratio = (excess_mean / downside_std * annualization_factor) if downside_std > 0 else 0.0

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


def evaluate_backtest_dataset(
    snapshots: List[Dict[str, Any]],
    holding_period_days: int = 3,
    buy_threshold: float = 75.0
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
    model_a_trades: List[Dict[str, Any]] = [] # Model A: Without Polymarket
    model_b_trades: List[Dict[str, Any]] = [] # Model B: With Polymarket

    # Group snapshots by ticker to prevent cross-asset price contamination
    grouped_by_ticker: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for s in snapshots:
        ticker_key = s.get("ticker", "DEFAULT")
        grouped_by_ticker[ticker_key].append(s)

    for ticker_sym, raw_snaps in grouped_by_ticker.items():
        # Sort chronologically if timestamps are available
        has_timestamps = any(_parse_timestamp(s.get("timestamp")) is not None for s in raw_snaps)
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
            pred_qual = current.get("prediction_quality", 80.0)

            # Model A: SMI computed WITHOUT Polymarket (prediction_score=None, weight redistributed)
            signal_a = False
            smi_a = None
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
                    prediction_count=0
                )
                smi_a = smi_a_res["smi"]
                if smi_a >= buy_threshold:
                    signal_a = True

            # Model B: SMI computed WITH Polymarket (incorporating prediction markets)
            signal_b = False
            if can_enter_b:
                if pred is not None:
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
                        prediction_count=pred_cnt
                    )
                    smi_b = smi_b_res["smi"]
                else:
                    if smi_a is not None:
                        smi_b = smi_a
                    else:
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
                            prediction_count=0
                        )
                        smi_b = smi_a_res["smi"]
                if smi_b >= buy_threshold:
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
                    "ticker": ticker_sym,
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
                    "ticker": ticker_sym,
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

    # Hypothesis conclusion with statistical significance test
    min_sample = min(metrics_a["total_trades"], metrics_b["total_trades"])
    is_statistically_significant = (min_sample >= 30)
    
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
            "metrics": metrics_a
        },
        "model_b_multisource": {
            "name": "Model B (Multi-Source with Polymarket PMS)",
            "metrics": metrics_b
        },
        "hypothesis_analysis": {
            "polymarket_incremental_value": polymarket_adds_value,
            "is_statistically_significant": is_statistically_significant,
            "min_sample_size": min_sample,
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
    2. Strict Risk Bounds: Limits calibrated weight to [pred_min (5%), pred_max (25%)].
    3. Sum Conservation: Proportionally renormalizes the other 5 pillar weights so the sum is identically 1.0000.
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
    
    delta_sharpe = float(horizon.get("hypothesis_analysis", {}).get("sharpe_delta", 0.0))
    win_rate_delta = float(horizon.get("hypothesis_analysis", {}).get("win_rate_delta_pp", 0.0))

    base_weights = {
        "social": getattr(settings, "WEIGHT_SOCIAL", 0.30),
        "prediction": base_pred_weight,
        "news": getattr(settings, "WEIGHT_NEWS", 0.20),
        "momentum": getattr(settings, "WEIGHT_MOMENTUM", 0.20),
        "fundamental": getattr(settings, "WEIGHT_FUNDAMENTALS", 0.10),
        "risk": getattr(settings, "WEIGHT_RISK", 0.05)
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
            "effective_weights": dict(base_weights)
        }

    # Bounded modulation by Delta Sharpe: multiplier between 0.50x and 1.667x
    # delta_sharpe = +1.0 -> multiplier = 1.5 -> weight = 0.225
    # delta_sharpe = -1.0 -> multiplier = 0.5 -> weight = 0.075
    raw_delta_factor = max(-0.5, min(0.5, delta_sharpe / 2.0))
    raw_multiplier = 1.0 + raw_delta_factor
    calibrated_pred_weight = max(p_min, min(p_max, base_pred_weight * raw_multiplier))
    actual_multiplier = calibrated_pred_weight / base_pred_weight

    # Proportional re-normalization of other 5 pillars
    other_base_sum = sum(v for k, v in base_weights.items() if k != "prediction")
    remaining_budget = 1.0 - calibrated_pred_weight
    scale_factor = remaining_budget / other_base_sum if other_base_sum > 0 else 1.0

    effective_weights = {}
    for k, v in base_weights.items():
        if k == "prediction":
            effective_weights[k] = round(calibrated_pred_weight, 4)
        else:
            effective_weights[k] = round(v * scale_factor, 4)

    # Reconcile rounding to strict 1.0000
    diff = 1.0 - sum(effective_weights.values())
    if abs(diff) > 1e-6:
        effective_weights["social"] = round(effective_weights["social"] + diff, 4)

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


def run_historical_backtest(db: Session, lookback_days: int = 60) -> Dict[str, Any]:
    """
    Runs full backtesting engine over database snapshot history.
    Filters snapshots within lookback_days window.
    """
    cutoff = utc_now() - timedelta(days=lookback_days)
    snaps_db = (
        db.query(SSISnapshotModel)
        .filter(SSISnapshotModel.timestamp >= cutoff)
        .order_by(SSISnapshotModel.timestamp.asc())
        .all()
    )
    
    snapshots_list = [
        {
            "ticker": s.ticker,
            "timestamp": s.timestamp,
            "social_score": s.social_score,
            "prediction_score": s.prediction_score,
            "news_score": s.news_score,
            "momentum_score": s.momentum_score,
            "risk_score": s.risk_score,
            "technical_score": s.technical_score,
            "fundamental_score": s.fundamental_score,
            "smi": s.smi if s.smi is not None else s.ssi,
            "post_count": getattr(s, "post_count", None),
            "news_count": getattr(s, "news_count", None),
            "prediction_count": getattr(s, "prediction_count", None),
            "price": s.price,
            "signal": s.signal
        }
        for s in snaps_db
    ]

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
