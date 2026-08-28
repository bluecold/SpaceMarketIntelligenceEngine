import pytest
from app.backtesting.engine import calculate_financial_metrics, evaluate_backtest_dataset


def test_calculate_financial_metrics_all_positive():
    returns = [5.0, 10.0, 3.0, 8.0]
    metrics = calculate_financial_metrics(returns)
    
    assert metrics["total_trades"] == 4
    assert metrics["win_rate"] == 100.0
    assert metrics["avg_return"] == 6.5
    assert metrics["profit_factor"] == 99.0
    assert metrics["expectancy"] > 0
    assert metrics["max_drawdown"] == 0.0
    assert metrics["sharpe_ratio"] > 0


def test_calculate_financial_metrics_mixed_trades():
    returns = [10.0, -5.0, 15.0, -10.0]
    metrics = calculate_financial_metrics(returns)
    
    assert metrics["total_trades"] == 4
    assert metrics["win_rate"] == 50.0
    # Total gains = 25, Total losses = 15 => Profit Factor = 25/15 = 1.67
    assert metrics["profit_factor"] == 1.67
    assert metrics["avg_return"] == 2.5


def test_evaluate_backtest_dataset_hypothesis_comparison():
    # Construct synthetic snapshot trajectory
    snapshots = [
        {"social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "technical_score": 30.0, "price": 10.0},
        {"social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "technical_score": 30.0, "price": 10.5},
        {"social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "technical_score": 30.0, "price": 11.0},
        {"social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "technical_score": 30.0, "price": 11.5},
        {"social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "technical_score": 30.0, "price": 12.0},
    ]

    res = evaluate_backtest_dataset(snapshots, holding_period_days=1, buy_threshold=70.0)
    
    assert "model_a_baseline" in res
    assert "model_b_multisource" in res
    assert res["model_a_baseline"]["name"] == "Model A (X Social + Technical + News Baseline)"
    assert res["model_b_multisource"]["name"] == "Model B (Multi-Source with Polymarket PMS)"
    assert "hypothesis_analysis" in res
    assert res["model_a_baseline"]["metrics"]["total_trades"] == 4
    assert res["model_b_multisource"]["metrics"]["total_trades"] == 4


def test_evaluate_backtest_dataset_multi_ticker_isolation():
    # Interleaved snapshots for ASTS ($10 -> $11) and RKLB ($100 -> $110)
    interleaved_snapshots = [
        {"ticker": "ASTS", "social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "price": 10.0},
        {"ticker": "RKLB", "social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "price": 100.0},
        {"ticker": "ASTS", "social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "price": 11.0},
        {"ticker": "RKLB", "social_score": 80.0, "news_score": 80.0, "momentum_score": 75.0, "prediction_score": 85.0, "price": 110.0},
    ]

    res = evaluate_backtest_dataset(interleaved_snapshots, holding_period_days=1, buy_threshold=70.0)

    # Both ASTS ($10 -> $11 = +10%) and RKLB ($100 -> $110 = +10%) should yield +10% returns
    # Total trades = 2 (1 for ASTS, 1 for RKLB), avg_return = 10.0%
    metrics_a = res["model_a_baseline"]["metrics"]
    assert metrics_a["total_trades"] == 2
    assert metrics_a["avg_return"] == 10.0
    assert metrics_a["win_rate"] == 100.0


def test_backtest_with_bayesian_shrinkage_parity():
    """
    Verify that backtest engine honors Bayesian shrinkage when sample sizes are small.
    Noisy social score (85.0) with post_count=2 should shrink to 57.0, staying BELOW buy_threshold (75.0),
    whereas post_count=20 should keep 85.0 and trigger trades.
    """
    snaps_small_sample = [
        {"ticker": "ASTS", "social_score": 85.0, "post_count": 2, "momentum_score": 60.0, "news_score": 60.0, "price": 10.0},
        {"ticker": "ASTS", "social_score": 85.0, "post_count": 2, "momentum_score": 60.0, "news_score": 60.0, "price": 12.0},
    ]
    res_shrunk = evaluate_backtest_dataset(snaps_small_sample, holding_period_days=1, buy_threshold=75.0)
    # Shrunk SMI is ~58.2 (< 75.0), so 0 trades should be taken
    assert res_shrunk["model_a_baseline"]["metrics"]["total_trades"] == 0

    snaps_large_sample = [
        {"ticker": "ASTS", "social_score": 85.0, "post_count": 20, "momentum_score": 75.0, "news_score": 75.0, "price": 10.0},
        {"ticker": "ASTS", "social_score": 85.0, "post_count": 20, "momentum_score": 75.0, "news_score": 75.0, "price": 12.0},
    ]
    res_full = evaluate_backtest_dataset(snaps_large_sample, holding_period_days=1, buy_threshold=75.0)
    # Un-shrunk SMI is >= 75.0, so 1 trade should be taken
    assert res_full["model_a_baseline"]["metrics"]["total_trades"] == 1


def test_backtest_timestamp_physical_holding_period_vs_index_offset():
    """
    Verify that an hourly dataset evaluated at holding_period_days=3 matches the snapshot
    at t + 72h (3 real days), NOT the snapshot at index i + 3 (3 hours later).
    """
    from datetime import datetime, timedelta

    base_time = datetime(2026, 8, 1, 10, 0, 0)
    hourly_snaps = []

    # 100 hourly snapshots (from hour 0 to hour 99)
    for h in range(100):
        # Price starts at 10.0, moves up gradually to 10.3 at hour 3, and to 15.0 at hour 72
        if h == 0:
            price = 10.0
        elif h == 3:
            price = 10.3  # (+3% at 3 hours)
        elif h == 72:
            price = 15.0  # (+50% at 72 hours / 3 days)
        else:
            price = 10.0 + h * 0.05

        hourly_snaps.append({
            "ticker": "ASTS",
            "timestamp": base_time + timedelta(hours=h),
            "social_score": 85.0,
            "post_count": 20,
            "momentum_score": 80.0,
            "news_score": 80.0,
            "price": price
        })

    # Evaluate for 3-day holding period
    res = evaluate_backtest_dataset(hourly_snaps, holding_period_days=3, buy_threshold=75.0)
    metrics = res["model_a_baseline"]["metrics"]

    # Entry at hour 0 (Price 10.0) matches exit at hour 72 (Price 15.0) -> realized return is +50.0%
    # If the bug were present (matching i + 3), realized return would be +3.0%
    assert metrics["total_trades"] > 0
    # Average return must be consistent with multi-day growth (~50%), not intraday 3-hour micro-noise (<5%)
    assert metrics["avg_return"] > 30.0


def test_dynamic_weight_calibration_closed_loop():
    """
    Validates empirical closed-loop weight calibration:
    1. Low sample size (N < 30) -> preserves baseline prior (w_pred = 0.15).
    2. Significant positive Delta Sharpe -> safely scales prediction weight upward.
    3. Significant negative Delta Sharpe -> safely scales prediction weight downward.
    4. Exact sum conservation (sum of all 6 weights == 1.0000).
    """
    from app.backtesting.engine import calculate_calibrated_prediction_weight
    from app.scoring.smi import calculate_smi, set_calibrated_weights
    from app.config import settings

    # Case 1: Insufficient sample size (N=10 < 30)
    mock_small_dataset = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": 10}},
                "model_b_multisource": {"metrics": {"total_trades": 10}},
                "hypothesis_analysis": {"sharpe_delta": +1.5, "win_rate_delta_pp": +10.0}
            }
        }
    }
    cal_small = calculate_calibrated_prediction_weight(mock_small_dataset, min_trades=30)
    assert not cal_small["is_calibrated"]
    assert cal_small["sample_size"] == 10
    assert cal_small["calibrated_weight"] == 0.15
    assert sum(cal_small["effective_weights"].values()) == pytest.approx(1.0, abs=1e-4)

    # Case 1b: Asymmetric sample size (Model A = 40, Model B = 12 < 30) -> min gate must block calibration
    mock_asym_dataset = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": 40}},
                "model_b_multisource": {"metrics": {"total_trades": 12}},
                "hypothesis_analysis": {"sharpe_delta": +1.5, "win_rate_delta_pp": +10.0}
            }
        }
    }
    cal_asym = calculate_calibrated_prediction_weight(mock_asym_dataset, min_trades=30)
    assert not cal_asym["is_calibrated"]
    assert cal_asym["sample_size"] == 12

    # Case 2: Significant Outperformance (N=45 >= 30, Delta Sharpe = +1.0)
    mock_positive_alpha = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": 45}},
                "model_b_multisource": {"metrics": {"total_trades": 45}},
                "hypothesis_analysis": {"sharpe_delta": +1.0, "win_rate_delta_pp": +8.5}
            }
        }
    }
    cal_pos = calculate_calibrated_prediction_weight(mock_positive_alpha, min_trades=30)
    assert cal_pos["is_calibrated"]
    assert cal_pos["calibrated_weight"] > 0.15
    assert cal_pos["calibrated_weight"] == pytest.approx(0.225, abs=0.01)
    assert sum(cal_pos["effective_weights"].values()) == pytest.approx(1.0, abs=1e-4)
    assert cal_pos["effective_weights"]["social"] < 0.30  # Proportional reduction of others

    # Case 3: Significant Underperformance (N=50 >= 30, Delta Sharpe = -1.5)
    mock_negative_alpha = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": 50}},
                "model_b_multisource": {"metrics": {"total_trades": 50}},
                "hypothesis_analysis": {"sharpe_delta": -1.5, "win_rate_delta_pp": -12.0}
            }
        }
    }
    cal_neg = calculate_calibrated_prediction_weight(mock_negative_alpha, min_trades=30)
    assert cal_neg["is_calibrated"]
    assert cal_neg["calibrated_weight"] < 0.15
    assert cal_neg["calibrated_weight"] >= 0.05
    assert sum(cal_neg["effective_weights"].values()) == pytest.approx(1.0, abs=1e-4)
    assert cal_neg["effective_weights"]["social"] > 0.30  # Proportional expansion of others

    # Case 4: Feeding calibrated weights into calculate_smi
    smi_res_prior = calculate_smi(social_score=80.0, prediction_score=20.0, prediction_quality=80.0)
    smi_res_cal = calculate_smi(social_score=80.0, prediction_score=20.0, prediction_quality=80.0, custom_weights=cal_pos["effective_weights"])
    # In positive alpha mode, prediction weight is higher (22.5% vs 15%), so low prediction (20.0) pulls SMI down more
    assert smi_res_cal["smi"] < smi_res_prior["smi"]


def test_backtest_non_overlapping_trade_lockout():
    """
    Verify that 100 consecutive hourly buy signals evaluated with holding_period_days=3 (72 hours):
    1. Opens exactly 1 trade at hour 0, locking until hour 72.
    2. Opens exactly 1 subsequent trade at hour 72 (if data reaches hour 144) or only 1 trade in 100 hours.
    3. Prevents trade count inflation from 100 overlapping snapshots.
    """
    from datetime import datetime, timedelta

    base_time = datetime(2026, 8, 1, 10, 0, 0)
    hourly_snaps = []

    # 100 hourly snapshots with continuous BUY signals (SMI = 85.0)
    for h in range(100):
        hourly_snaps.append({
            "ticker": "ASTS",
            "timestamp": base_time + timedelta(hours=h),
            "social_score": 85.0,
            "post_count": 20,
            "momentum_score": 80.0,
            "news_score": 80.0,
            "price": 10.0 + h * 0.1
        })

    res = evaluate_backtest_dataset(hourly_snaps, holding_period_days=3, buy_threshold=75.0)
    metrics = res["model_a_baseline"]["metrics"]

    # In 100 hours with a 72-hour lockout, only 1 non-overlapping trade can complete (entry at 0h, exit at 72h)
    assert metrics["total_trades"] == 1
    # Exit price at 72h is 10.0 + 72*0.1 = 17.2 -> return is +72.0%
    assert metrics["avg_return"] == pytest.approx(72.0, abs=0.1)


def test_calculate_financial_metrics_horizon_annualization():
    """Verify that 3D and 5D holding periods scale Sharpe by sqrt(252/H), not sqrt(252)."""
    import math
    returns = [5.0, -2.0, 4.0, 6.0, -1.0, 3.0]

    m1 = calculate_financial_metrics(returns, holding_period_days=1)
    m3 = calculate_financial_metrics(returns, holding_period_days=3)
    m5 = calculate_financial_metrics(returns, holding_period_days=5)

    # Sharpe for 3D should be exactly Sharpe(1D) * sqrt(84) / sqrt(252) = Sharpe(1D) / sqrt(3)
    ratio_3d = m3["sharpe_ratio"] / m1["sharpe_ratio"]
    assert ratio_3d == pytest.approx(1.0 / math.sqrt(3), abs=0.02)

    # Sharpe for 5D should be exactly Sharpe(1D) * sqrt(50.4) / sqrt(252) = Sharpe(1D) / sqrt(5)
    ratio_5d = m5["sharpe_ratio"] / m1["sharpe_ratio"]
    assert ratio_5d == pytest.approx(1.0 / math.sqrt(5), abs=0.02)


def test_backtest_multi_ticker_chronological_equity_ordering():
    """
    Verify that trades from multiple tickers (e.g. ASTS in Jan, RKLB in Feb)
    are ordered strictly chronologically before computing the equity curve and drawdown,
    rather than grouping all ASTS trades then all RKLB trades.
    """
    from datetime import datetime, timedelta

    t1 = datetime(2026, 1, 1, 10, 0, 0)
    t2 = datetime(2026, 2, 1, 10, 0, 0)

    # Interleaved multi-ticker trajectory across two distinct months
    snapshots = [
        # Month 1: ASTS (+20% gain)
        {"ticker": "ASTS", "timestamp": t1, "social_score": 85.0, "news_score": 80.0, "momentum_score": 80.0, "price": 10.0},
        {"ticker": "ASTS", "timestamp": t1 + timedelta(days=1), "social_score": 85.0, "news_score": 80.0, "momentum_score": 80.0, "price": 12.0},
        # Month 2: RKLB (-10% loss)
        {"ticker": "RKLB", "timestamp": t2, "social_score": 85.0, "news_score": 80.0, "momentum_score": 80.0, "price": 100.0},
        {"ticker": "RKLB", "timestamp": t2 + timedelta(days=1), "social_score": 85.0, "news_score": 80.0, "momentum_score": 80.0, "price": 90.0},
    ]

    res = evaluate_backtest_dataset(snapshots, holding_period_days=1, buy_threshold=75.0)
    metrics = res["model_a_baseline"]["metrics"]

    assert metrics["total_trades"] == 2
    assert metrics["win_rate"] == 50.0
    # Chronological sequence: +20% (equity goes to 1.20), then -10% (equity goes to 1.20 * 0.9 = 1.08)
    # Peak is 1.20, trough is 1.08 -> Max Drawdown is exactly (1.20 - 1.08)/1.20 = 10.0%
    assert metrics["max_drawdown"] == 10.0








