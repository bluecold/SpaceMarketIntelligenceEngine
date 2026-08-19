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
        {"social_score": 80, "technical_score": 30, "smi": 85, "price": 10.0},
        {"social_score": 80, "technical_score": 30, "smi": 85, "price": 10.5},
        {"social_score": 80, "technical_score": 30, "smi": 85, "price": 11.0},
        {"social_score": 80, "technical_score": 30, "smi": 85, "price": 11.5},
        {"social_score": 80, "technical_score": 30, "smi": 85, "price": 12.0},
    ]

    res = evaluate_backtest_dataset(snapshots, holding_period_days=1)
    
    assert "model_a_baseline" in res
    assert "model_b_multisource" in res
    assert "hypothesis_analysis" in res
    assert res["model_a_baseline"]["metrics"]["total_trades"] == 4
    assert res["model_b_multisource"]["metrics"]["total_trades"] == 4
