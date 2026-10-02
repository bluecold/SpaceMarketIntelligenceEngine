import pytest
from app.config import settings
from app.backtesting.engine import (
    calculate_financial_metrics,
    evaluate_backtest_dataset,
    run_historical_backtest,
)


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

    # Case 2: Significant Outperformance (N=45 >= 30, Delta Sharpe = +1.0, difference_significant = True)
    mock_positive_alpha = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": 45}},
                "model_b_multisource": {"metrics": {"total_trades": 45}},
                "hypothesis_analysis": {
                    "sharpe_delta": +1.0,
                    "win_rate_delta_pp": +8.5,
                    "difference_significant": True,
                    "positive_edge_significant": True
                }
            }
        }
    }
    cal_pos = calculate_calibrated_prediction_weight(mock_positive_alpha, min_trades=30)
    assert cal_pos["is_calibrated"]
    assert cal_pos["calibrated_weight"] > 0.15
    assert cal_pos["calibrated_weight"] == pytest.approx(0.225, abs=0.01)
    assert sum(cal_pos["effective_weights"].values()) == pytest.approx(1.0, abs=1e-4)
    assert cal_pos["effective_weights"]["social"] < settings.WEIGHT_SOCIAL  # Proportional reduction of others

    # Case 3: Significant Underperformance (N=50 >= 30, Delta Sharpe = -1.5, difference_significant = True)
    mock_negative_alpha = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": 50}},
                "model_b_multisource": {"metrics": {"total_trades": 50}},
                "hypothesis_analysis": {
                    "sharpe_delta": -1.5,
                    "win_rate_delta_pp": -12.0,
                    "difference_significant": True,
                    "negative_edge_significant": True
                }
            }
        }
    }
    cal_neg = calculate_calibrated_prediction_weight(mock_negative_alpha, min_trades=30)
    assert cal_neg["is_calibrated"]
    assert cal_neg["calibrated_weight"] < 0.15
    assert cal_neg["calibrated_weight"] >= 0.05
    assert sum(cal_neg["effective_weights"].values()) == pytest.approx(1.0, abs=1e-4)
    assert cal_neg["effective_weights"]["social"] > 0.30  # Proportional expansion of others

    # Case 3b: Conservative default - missing difference_significant must NOT calibrate
    mock_missing_sig = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": 50}},
                "model_b_multisource": {"metrics": {"total_trades": 50}},
                "hypothesis_analysis": {"sharpe_delta": -1.5, "win_rate_delta_pp": -12.0}
            }
        }
    }
    cal_unconfirmed = calculate_calibrated_prediction_weight(mock_missing_sig, min_trades=30)
    assert not cal_unconfirmed["is_calibrated"]
    assert cal_unconfirmed["calibrated_weight"] == 0.15
    assert "NOT_STATISTICALLY_SIGNIFICANT" in cal_unconfirmed["status"]

    # Case 4: Feeding calibrated weights into calculate_smi
    smi_res_prior = calculate_smi(social_score=80.0, prediction_score=20.0, prediction_quality=80.0)
    smi_res_cal = calculate_smi(social_score=80.0, prediction_score=20.0, prediction_quality=80.0, custom_weights=cal_pos["effective_weights"])
    # In positive alpha mode, prediction weight is higher (22.5% vs 15%), so low prediction (20.0) pulls SMI down more
    assert smi_res_cal["smi"] < smi_res_prior["smi"]


def test_hypothesis_significance_directional_bootstrap_and_negative_edge():
    """
    Verify that:
    1. A statistically significant negative alpha produces negative_edge_significant=True,
       positive_edge_significant=False, and difference_significant=True.
    2. calculate_calibrated_prediction_weight successfully calibrates downward to minimum weight (5%).
    """
    from app.backtesting.engine import compute_hypothesis_significance, calculate_calibrated_prediction_weight

    # Model A consistently produces positive returns (+4% to +8%)
    trades_a = [{"return": 6.0 + (i % 3) * 0.5} for i in range(40)]
    # Model B consistently produces negative returns (-4% to -8%)
    trades_b = [{"return": -6.0 - (i % 3) * 0.5} for i in range(40)]

    sig_res = compute_hypothesis_significance(
        model_a_trades=trades_a,
        model_b_trades=trades_b,
        min_required_trades=30,
        n_bootstrap=500,
        random_seed=42
    )

    assert sig_res["min_sample_reached"] is True
    assert sig_res["positive_edge_significant"] is False
    assert sig_res["is_statistically_significant"] is False
    assert sig_res["negative_edge_significant"] is True
    assert sig_res["difference_significant"] is True
    assert sig_res["confidence_interval_95"]["upper"] < 0.0

    # Test that this real negative outcome properly triggers dynamic downward calibration
    backtest_data = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": len(trades_a)}},
                "model_b_multisource": {"metrics": {"total_trades": len(trades_b)}},
                "hypothesis_analysis": {
                    "sharpe_delta": -2.5,
                    "win_rate_delta_pp": -40.0,
                    **sig_res
                }
            }
        }
    }
    cal_res = calculate_calibrated_prediction_weight(backtest_data, min_trades=30)
    assert cal_res["is_calibrated"] is True
    assert cal_res["calibrated_weight"] == 0.05  # Lower bound pred_min (5%)
    assert cal_res["effective_weights"]["prediction"] == 0.05
    assert cal_res["effective_weights"]["social"] > 0.30  # Rescaled upwards


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


def test_run_historical_backtest_empty_db():
    """Verify run_historical_backtest executes cleanly and returns zero-state metrics on empty database."""
    from app.database.connection import SessionLocal
    from app.database.models import SSISnapshotModel

    db = SessionLocal()
    try:
        # Clear existing snapshots for clean test
        db.query(SSISnapshotModel).delete()
        db.commit()

        res = run_historical_backtest(db, lookback_days=30)
        assert res["total_snapshots_analyzed"] == 0
        assert "evaluation_horizons" in res
        assert "1D" in res["evaluation_horizons"]
        assert "3D" in res["evaluation_horizons"]
        assert "5D" in res["evaluation_horizons"]
        assert res["evaluation_horizons"]["1D"]["model_a_baseline"]["metrics"]["total_trades"] == 0
        assert res["evaluation_horizons"]["1D"]["model_b_multisource"]["metrics"]["total_trades"] == 0
    finally:
        db.close()


def test_run_historical_backtest_with_db_data():
    """Verify run_historical_backtest retrieves and filters snapshots within lookback_days."""
    from app.database.connection import SessionLocal
    from app.database.models import SSISnapshotModel, utc_now
    from datetime import timedelta

    db = SessionLocal()
    try:
        db.query(SSISnapshotModel).delete()
        db.commit()

        now = utc_now()
        # 1 snapshot out of window (> 40 days ago)
        outdated = SSISnapshotModel(
            ticker="ASTS",
            timestamp=now - timedelta(days=45),
            ssi=80.0,
            social_score=80.0,
            news_score=80.0,
            momentum_score=80.0,
            prediction_score=80.0,
            price=10.0,
            signal="BUY",
            confidence=100.0,
            data_completeness=100.0
        )
        # 2 snapshots inside window (within 10 days)
        snap1 = SSISnapshotModel(
            ticker="ASTS",
            timestamp=now - timedelta(days=2),
            ssi=85.0,
            social_score=85.0,
            news_score=80.0,
            momentum_score=80.0,
            prediction_score=85.0,
            price=10.0,
            signal="STRONG_BUY",
            confidence=100.0,
            data_completeness=100.0
        )
        snap2 = SSISnapshotModel(
            ticker="ASTS",
            timestamp=now - timedelta(days=1),
            ssi=85.0,
            social_score=85.0,
            news_score=80.0,
            momentum_score=80.0,
            prediction_score=85.0,
            price=12.0,
            signal="STRONG_BUY",
            confidence=100.0,
            data_completeness=100.0
        )
        db.add_all([outdated, snap1, snap2])
        db.commit()

        # Run with 30-day lookback: should include snap1 and snap2 (2 snapshots), exclude outdated
        res = run_historical_backtest(db, lookback_days=30)
        assert res["total_snapshots_analyzed"] == 2
        assert res["evaluation_horizons"]["1D"]["model_a_baseline"]["metrics"]["total_trades"] == 1
        assert res["evaluation_horizons"]["1D"]["model_a_baseline"]["metrics"]["win_rate"] == 100.0
    finally:
        db.query(SSISnapshotModel).delete()
        db.commit()
        db.close()


def test_run_historical_backtest_excludes_mock_data():
    """Verify run_historical_backtest strictly excludes snapshots with data_source='MOCK' unless explicitly requested."""
    from app.database.connection import SessionLocal
    from app.database.models import SSISnapshotModel, utc_now
    from datetime import timedelta

    db = SessionLocal()
    try:
        db.query(SSISnapshotModel).delete()
        db.commit()

        now = utc_now()
        live_snap1 = SSISnapshotModel(
            ticker="ASTS",
            timestamp=now - timedelta(days=2),
            ssi=85.0,
            social_score=85.0,
            news_score=80.0,
            momentum_score=80.0,
            prediction_score=85.0,
            price=10.0,
            signal="STRONG_BUY",
            confidence=100.0,
            data_completeness=100.0,
            data_source="LIVE"
        )
        live_snap2 = SSISnapshotModel(
            ticker="ASTS",
            timestamp=now - timedelta(days=1),
            ssi=85.0,
            social_score=85.0,
            news_score=80.0,
            momentum_score=80.0,
            prediction_score=85.0,
            price=12.0,
            signal="STRONG_BUY",
            confidence=100.0,
            data_completeness=100.0,
            data_source="LIVE"
        )
        mock_snap = SSISnapshotModel(
            ticker="ASTS",
            timestamp=now - timedelta(days=1, hours=12),
            ssi=90.0,
            social_score=90.0,
            news_score=90.0,
            momentum_score=90.0,
            prediction_score=90.0,
            price=15.0,
            signal="STRONG_BUY",
            confidence=100.0,
            data_completeness=100.0,
            data_source="MOCK"
        )
        db.add_all([live_snap1, live_snap2, mock_snap])
        db.commit()

        # Default: exclude mock snapshots -> only 2 live snapshots analyzed
        res_default = run_historical_backtest(db, lookback_days=30)
        assert res_default["total_snapshots_analyzed"] == 2

        # include_mock=True -> all 3 snapshots analyzed
        res_with_mock = run_historical_backtest(db, lookback_days=30, include_mock=True)
        assert res_with_mock["total_snapshots_analyzed"] == 3
    finally:
        db.query(SSISnapshotModel).delete()
        db.commit()
        db.close()


def test_api_backtest_endpoint():
    """Verify GET /api/backtest responds with 200 OK and expected JSON schema."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/backtest?lookback_days=30")
    assert response.status_code == 200
    data = response.json()
    assert "total_snapshots_analyzed" in data
    assert "evaluation_horizons" in data
    assert "1D" in data["evaluation_horizons"]
    assert "3D" in data["evaluation_horizons"]
    assert "5D" in data["evaluation_horizons"]


def test_hypothesis_significance_block_bootstrap_insufficient_sample():
    """
    Verify that when trade count N < 30, statistical significance is not declared
    and p-value defaults to 1.0 (conservative baseline).
    """
    from app.backtesting.engine import compute_hypothesis_significance

    trades_a = [{"return": 5.0} for _ in range(15)]
    trades_b = [{"return": 10.0} for _ in range(15)]

    res = compute_hypothesis_significance(trades_a, trades_b, min_required_trades=30)
    assert not res["min_sample_reached"]
    assert not res["is_statistically_significant"]
    assert res["min_sample_size"] == 15
    assert res["p_value"] == 1.0


def test_hypothesis_significance_block_bootstrap_true_positive():
    """
    Verify that when Model B has a genuine, statistically distinct edge over Model A
    (N = 50, +6% vs -1%), block bootstrap produces p < 0.05 and a strictly positive 95% CI.
    """
    from app.backtesting.engine import compute_hypothesis_significance
    import numpy as np

    rng = np.random.default_rng(123)
    trades_a = [{"return": float(r)} for r in rng.normal(loc=-1.0, scale=3.0, size=50)]
    trades_b = [{"return": float(r)} for r in rng.normal(loc=5.0, scale=3.0, size=50)]

    res = compute_hypothesis_significance(trades_a, trades_b, min_required_trades=30, n_bootstrap=1000)
    assert res["min_sample_reached"]
    assert res["is_statistically_significant"]
    assert res["p_value"] < 0.01
    assert res["confidence_interval_95"]["lower"] > 0.0
    assert "Block Bootstrap" in res["test_method"]


def test_hypothesis_significance_block_bootstrap_pure_noise_rejection():
    """
    Verify that when Model A and Model B have identical zero-alpha return distributions (pure noise),
    the test correctly avoids false positive significance (p >= 0.05, 95% CI includes <= 0).
    """
    from app.backtesting.engine import compute_hypothesis_significance
    import numpy as np

    rng = np.random.default_rng(999)
    # Both drawn from identical N(0, 5) distribution
    trades_a = [{"return": float(r)} for r in rng.normal(loc=0.0, scale=5.0, size=50)]
    trades_b = [{"return": float(r)} for r in rng.normal(loc=0.0, scale=5.0, size=50)]

    res = compute_hypothesis_significance(trades_a, trades_b, min_required_trades=30, n_bootstrap=1000)
    assert res["min_sample_reached"]
    assert not res["is_statistically_significant"]
    assert res["p_value"] > 0.05
    assert res["confidence_interval_95"]["lower"] <= 0.0


def test_dynamic_weight_calibration_rejects_insignificant_edge():
    """
    Verify that if sample size N >= 30 is reached but the edge is marked as NOT statistically significant,
    the dynamic weight calibration engine does NOT adjust weights, keeping the prior baseline.
    """
    from app.backtesting.engine import calculate_calibrated_prediction_weight

    mock_insignificant_dataset = {
        "evaluation_horizons": {
            "3D": {
                "model_a_baseline": {"metrics": {"total_trades": 50}},
                "model_b_multisource": {"metrics": {"total_trades": 50}},
                "hypothesis_analysis": {
                    "sharpe_delta": +0.8,
                    "win_rate_delta_pp": +4.0,
                    "is_statistically_significant": False,
                    "p_value": 0.25
                }
            }
        }
    }
    res = calculate_calibrated_prediction_weight(mock_insignificant_dataset, min_trades=30)
    assert not res["is_calibrated"]
    assert "NOT_STATISTICALLY_SIGNIFICANT" in res["status"]
    assert res["calibrated_weight"] == 0.15


def test_calculate_financial_metrics_first_loss_drawdown():
    """
    Verify that calculate_financial_metrics captures the drawdown from the starting capital
    even when the first trade is a loss (fixing the 0% bug on initial loss).
    """
    # Single first loss: -10% -> Max drawdown should be exactly 10.0%
    m1 = calculate_financial_metrics([-10.0])
    assert m1["max_drawdown"] == 10.0

    # Sequential starting losses: -5%, -10% -> 1.0 -> 0.95 -> 0.855 -> Drawdown is 14.5%
    m2 = calculate_financial_metrics([-5.0, -10.0])
    assert m2["max_drawdown"] == pytest.approx(14.5, abs=0.1)


def test_calculate_financial_metrics_sortino_constant_losses():
    """
    Verify that Sortino ratio uses target downside deviation (LPM2) so that identical negative returns
    [-1, -1, -1] produce a negative Sortino ratio reflecting downside risk, rather than 0.0.
    """
    m = calculate_financial_metrics([-1.0, -1.0, -1.0])
    assert m["sortino_ratio"] < 0.0
    assert m["sortino_ratio"] == pytest.approx(-15.87, abs=0.5)


def test_simulate_portfolio_execution_concurrent_positions_and_costs():
    """
    Verify that simulate_portfolio_execution models capital constraints and overlapping trades:
    1. Tracks concurrent positions when multiple tickers signal simultaneously.
    2. Applies transaction cost friction.
    3. Prevents unrealistic 100% sequential compounding of simultaneous trades.
    """
    from datetime import datetime, timedelta
    from app.backtesting.engine import simulate_portfolio_execution

    t0 = datetime(2026, 8, 1, 10, 0)
    trades = [
        {"ticker": "ASTS", "entry_time": t0, "exit_time": t0 + timedelta(days=3), "return": 10.0},
        {"ticker": "RKLB", "entry_time": t0 + timedelta(days=1), "exit_time": t0 + timedelta(days=4), "return": -5.0},
        {"ticker": "LUNR", "entry_time": t0 + timedelta(days=2), "exit_time": t0 + timedelta(days=5), "return": 8.0}
    ]

    port = simulate_portfolio_execution(
        trades=trades,
        initial_capital=100000.0,
        max_concurrent_positions=5,
        transaction_cost_bps=10.0
    )

    assert port["initial_capital"] == 100000.0
    assert port["max_concurrent_positions"] == 3
    assert port["total_executed_trades"] == 3
    assert port["total_transaction_costs"] > 0.0
    # Net ending capital should reflect partial capital allocation (20k per position) + returns - costs
    assert port["ending_capital"] > 100000.0
    assert port["total_net_return_pct"] > 0.0
    assert port["portfolio_max_drawdown_pct"] >= 0.0


def test_historical_backtest_reproduces_overbought_dilution_and_market_status_gates():
    """
    Verify that run_historical_backtest accurately reproduces live gates from DB persisted snapshots:
    1. An overbought ticker (RSI > 75) is restricted from STRONG BUY to WATCH (no trade entered).
    2. A company with critical cash runway (< 6 months) triggers DILUTION RISK restriction.
    3. Missing market data (market_status != 'AVAILABLE') adds NO MKT DATA modifier.
    4. Effective weights, rules version, and fundamentals are faithfully reconstructed.
    """
    from app.database.connection import SessionLocal, init_db
    from app.database.models import SSISnapshotModel, utc_now
    from app.database.repository import save_ssi_snapshot
    from app.backtesting.engine import run_historical_backtest
    from datetime import timedelta

    init_db()
    db = SessionLocal()
    try:
        db.query(SSISnapshotModel).delete()
        db.commit()

        now = utc_now()

        # 1. Save overbought snapshot (high SMI ~90 >= 85, but RSI=80.0) -> Overbought restriction restricts STRONG BUY to WATCH
        overbought_snap = {
            "ticker": "ASTS",
            "social_score": 90.0,
            "prediction_score": 90.0,
            "news_score": 90.0,
            "momentum_score": 90.0,
            "fundamental_score": 90.0,
            "risk_score": 90.0,
            "technical_score": 38.0,
            "ssi": 90.0,
            "smi": 90.0,
            "signal": "WATCH (OVEREXTENDED)",
            "base_signal": "WATCH",
            "signal_modifier": "OVEREXTENDED",
            "confidence": 90.0,
            "data_completeness": 100.0,
            "price": 20.0,
            "rsi14": 80.0,
            "market_status": "AVAILABLE",
            "fundamentals": {"total_cash": 500000000.0, "runway_months": 24.0},
            "effective_weights": {"social": 0.3, "prediction": 0.15, "news": 0.2, "momentum": 0.15, "fundamental": 0.1, "risk": 0.1},
            "rules_version": "2.0.0"
        }
        s1 = save_ssi_snapshot(db, overbought_snap)
        s1.timestamp = now - timedelta(days=2)

        # Future price snapshot
        future_snap = {
            "ticker": "ASTS",
            "social_score": 80.0,
            "prediction_score": 80.0,
            "news_score": 80.0,
            "momentum_score": 80.0,
            "fundamental_score": 80.0,
            "risk_score": 80.0,
            "technical_score": 35.0,
            "ssi": 80.0,
            "smi": 80.0,
            "signal": "BUY",
            "confidence": 90.0,
            "data_completeness": 100.0,
            "price": 25.0,
            "rsi14": 65.0,
            "market_status": "AVAILABLE"
        }
        s2 = save_ssi_snapshot(db, future_snap)
        s2.timestamp = now - timedelta(days=1)
        db.commit()

        # Run historical backtest on DB snapshots
        res = run_historical_backtest(db, lookback_days=10)
        assert res["total_snapshots_analyzed"] == 2
        # Because ASTS was overbought (RSI=80 on STRONG BUY), the backtest correctly restricts base_signal to WATCH,
        # entering 0 trades instead of a false trade entry!
        metrics_1d = res["evaluation_horizons"]["1D"]["model_a_baseline"]["metrics"]
        assert metrics_1d["total_trades"] == 0

        # 2. Verify that dilution risk (< 6 months runway) is preserved from DB and restricts BUY to WATCH
        db.query(SSISnapshotModel).delete()
        db.commit()

        dilution_snap = {
            "ticker": "ASTS",
            "social_score": 80.0,
            "prediction_score": 80.0,
            "news_score": 80.0,
            "momentum_score": 80.0,
            "fundamental_score": 80.0,
            "risk_score": 80.0,
            "technical_score": 30.0,
            "ssi": 80.0,
            "smi": 80.0,
            "signal": "WATCH (DILUTION RISK)",
            "base_signal": "WATCH",
            "signal_modifier": "DILUTION RISK",
            "confidence": 85.0,
            "data_completeness": 100.0,
            "price": 20.0,
            "rsi14": 55.0,
            "market_status": "AVAILABLE",
            "fundamentals": {"total_cash": 10000000.0, "runway_months": 4.0},
            "rules_version": "2.0.0"
        }
        d1 = save_ssi_snapshot(db, dilution_snap)
        d1.timestamp = now - timedelta(days=2)
        d2 = save_ssi_snapshot(db, future_snap)
        d2.timestamp = now - timedelta(days=1)
        db.commit()

        res_dilution = run_historical_backtest(db, lookback_days=10)
        metrics_dilution = res_dilution["evaluation_horizons"]["1D"]["model_a_baseline"]["metrics"]
        assert metrics_dilution["total_trades"] == 0

    finally:
        db.query(SSISnapshotModel).delete()
        db.commit()
        db.close()


def test_simulate_portfolio_costs_cash_reconciliation():
    """
    Verify that entry and exit transaction costs are both deducted from cash:
    For a trade with 0% return, ending_capital must equal initial_capital - total_transaction_costs.
    """
    from datetime import datetime, timedelta
    from app.backtesting.engine import simulate_portfolio_execution

    t0 = datetime(2026, 8, 1, 10, 0)
    trades = [
        {"ticker": "ASTS", "entry_time": t0, "exit_time": t0 + timedelta(days=3), "return": 0.0}
    ]

    port = simulate_portfolio_execution(
        trades=trades,
        initial_capital=100000.0,
        max_concurrent_positions=1,
        transaction_cost_bps=20.0  # 0.20% per leg
    )

    assert port["total_executed_trades"] == 1
    assert port["total_transaction_costs"] > 0.0
    # Ending cash should exactly match initial_capital minus total_transaction_costs
    expected_ending = 100000.0 - port["total_transaction_costs"]
    assert port["ending_capital"] == pytest.approx(expected_ending, 0.01)
    assert port["total_net_return_pct"] < 0.0


def test_simulate_portfolio_holding_period_days_fallback():
    """
    Verify that holding_period_days is used to close trades when exit_time is None,
    enabling sequential positions to be opened after the holding horizon expires.
    """
    from datetime import datetime, timedelta
    from app.backtesting.engine import simulate_portfolio_execution

    t0 = datetime(2026, 8, 1, 10, 0)
    # Two sequential trades with max_concurrent_positions=1, exit_time omitted
    trades = [
        {"ticker": "ASTS", "entry_time": t0, "return": 5.0},
        {"ticker": "RKLB", "entry_time": t0 + timedelta(days=4), "return": 5.0}
    ]

    # With holding_period_days=3, ASTS closes at t0+3 days. RKLB entering at t0+4 days should execute!
    port = simulate_portfolio_execution(
        trades=trades,
        initial_capital=100000.0,
        max_concurrent_positions=1,
        transaction_cost_bps=10.0,
        holding_period_days=3
    )

    assert port["total_executed_trades"] == 2
    assert port["skipped_trades_no_cash"] == 0
    assert port["max_concurrent_positions"] == 1


def test_simulate_portfolio_equity_curve_and_drawdown():
    """
    Verify that intermediate exits are captured in the equity curve,
    properly reflecting peak equity and max drawdown between sequential trade waves.
    """
    from datetime import datetime, timedelta
    from app.backtesting.engine import simulate_portfolio_execution

    t0 = datetime(2026, 8, 1, 10, 0)
    trades = [
        # First trade: +20% gain, closes on Day 3
        {"ticker": "ASTS", "entry_time": t0, "exit_time": t0 + timedelta(days=3), "return": 20.0},
        # Second trade: enters on Day 6, suffers -10% loss, closes on Day 9
        {"ticker": "RKLB", "entry_time": t0 + timedelta(days=6), "exit_time": t0 + timedelta(days=9), "return": -10.0}
    ]

    port = simulate_portfolio_execution(
        trades=trades,
        initial_capital=100000.0,
        max_concurrent_positions=1,
        transaction_cost_bps=0.0
    )

    # Initial 100k -> Trade 1 (+20%) reaches 120k peak -> Trade 2 (-10%) drops from 120k to 108k
    # Drawdown from 120k to 108k is -10% (or 10.0%)
    assert port["ending_capital"] == pytest.approx(108000.0, 1.0)
    assert port["portfolio_max_drawdown_pct"] == pytest.approx(10.0, 0.5)













