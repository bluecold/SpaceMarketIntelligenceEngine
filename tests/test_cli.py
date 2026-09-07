import pytest
from click.testing import CliRunner
from app.cli.commands import cli
from app.database.connection import SessionLocal, init_db
from app.database.repository import (
    ensure_tickers_seeded, get_recent_social_posts,
    get_recent_news_items, get_recent_prediction_markets,
    get_latest_market_snapshot, save_ssi_snapshot
)


@pytest.fixture(autouse=True)
def setup_cli_db():
    init_db()
    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
    finally:
        db.close()


def test_cli_collect_social():
    runner = CliRunner()
    result = runner.invoke(cli, ["collect-social"])
    assert result.exit_code == 0, f"Error: {result.output}"
    assert "Social posts collected" in result.output

    db = SessionLocal()
    try:
        posts = get_recent_social_posts(db, "ASTS", hours=48)
        assert len(posts) > 0, "Expected at least 1 ingested social post in database"
    finally:
        db.close()


def test_cli_collect_news():
    runner = CliRunner()
    result = runner.invoke(cli, ["collect-news"])
    assert result.exit_code == 0, f"Error: {result.output}"
    assert "News collection completed" in result.output

    db = SessionLocal()
    try:
        news = get_recent_news_items(db, "ASTS", days=2)
        assert len(news) > 0, "Expected at least 1 ingested news item in database"
    finally:
        db.close()


def test_cli_collect_polymarket():
    runner = CliRunner()
    result = runner.invoke(cli, ["collect-polymarket"])
    assert result.exit_code == 0, f"Error: {result.output}"
    assert "Retrieved and saved" in result.output

    db = SessionLocal()
    try:
        markets = get_recent_prediction_markets(db, "ASTS")
        assert len(markets) > 0, "Expected at least 1 ingested prediction market in database"
    finally:
        db.close()


def test_cli_collect_market():
    runner = CliRunner()
    result = runner.invoke(cli, ["collect-market"])
    assert result.exit_code == 0, f"Error: {result.output}"
    assert "Market indicators updated" in result.output

    db = SessionLocal()
    try:
        mkt = get_latest_market_snapshot(db, "ASTS")
        assert mkt is not None, "Expected market snapshot for ASTS to be created"
    finally:
        db.close()


def test_cli_calculate_divergences():
    runner = CliRunner()
    result = runner.invoke(cli, ["calculate-divergences"])
    assert result.exit_code == 0, f"Error: {result.output}"
    assert "active divergences across sector" in result.output


def test_cli_daily_report():
    runner = CliRunner()
    result = runner.invoke(cli, ["daily-report"])
    assert result.exit_code == 0, f"Error: {result.output}"
    assert "SPACE MARKET INTELLIGENCE DAILY REPORT" in result.output


def test_cli_backtest():
    runner = CliRunner()
    result = runner.invoke(cli, ["backtest"])
    assert result.exit_code == 0, f"Error: {result.output}"
    assert "MODEL COMPARISON" in result.output
    assert "Total Snapshots Evaluated" in result.output


def test_cli_analyze_with_data():
    from unittest.mock import patch, AsyncMock

    db = SessionLocal()
    try:
        snap = {
            "ticker": "ASTS",
            "social_score": 85.0,
            "prediction_score": 80.0,
            "news_score": 82.0,
            "momentum_score": 75.0,
            "fundamental_score": 70.0,
            "risk_score": 20.0,
            "technical_score": 32.0,
            "ssi": 85.0,
            "smi": 83.5,
            "signal": "STRONG_BUY",
            "base_signal": "STRONG_BUY",
            "signal_modifier": None,
            "confidence": 90.0,
            "data_completeness": 100.0,
            "data_quality": 100.0,
            "post_count": 25,
            "news_count": 10,
            "prediction_count": 3,
            "data_source": "LIVE",
            "social_source": "LIVE",
            "prediction_source": "LIVE",
            "news_source": "LIVE",
            "market_source": "LIVE",
            "price": 22.50
        }
        save_ssi_snapshot(db, snap)
    finally:
        db.close()

    runner = CliRunner()
    with patch("app.cli.commands.run_full_pipeline", new=AsyncMock(return_value={"status": "SUCCESS"})):
        result = runner.invoke(cli, ["analyze", "ASTS"])
        assert result.exit_code == 0, f"Error: {result.output}"
        assert "SPACE MARKET INTELLIGENCE ENGINE --- ASTS" in result.output
        assert "SMI (Market Intelligence Index): 83.5 / 100" in result.output
        assert "SSI (Social Sentiment Index):    85.0 / 100" in result.output
        assert "PMS (Prediction Market Score):   80.0 / 100" in result.output
        assert "Signal:                          STRONG_BUY" in result.output


def test_cli_analyze_with_null_scores():
    """Verify analyze handles null scores without TypeError."""
    from unittest.mock import patch, AsyncMock

    db = SessionLocal()
    try:
        null_snap = {
            "ticker": "SPCE",
            "social_score": None,
            "prediction_score": None,
            "news_score": None,
            "momentum_score": None,
            "fundamental_score": None,
            "risk_score": None,
            "technical_score": None,
            "ssi": None,
            "smi": None,
            "signal": "HOLD (DATA_UNAVAILABLE)",
            "base_signal": "HOLD",
            "signal_modifier": "DATA_UNAVAILABLE",
            "confidence": 0.0,
            "data_completeness": 0.0,
            "data_quality": 0.0,
            "post_count": 0,
            "news_count": 0,
            "prediction_count": 0,
            "data_source": "DEGRADED",
            "social_source": "EXCLUDED",
            "prediction_source": "EXCLUDED",
            "news_source": "EXCLUDED",
            "market_source": "DEGRADED",
            "price": None
        }
        save_ssi_snapshot(db, null_snap)
    finally:
        db.close()

    runner = CliRunner()
    with patch("app.cli.commands.run_full_pipeline", new=AsyncMock(return_value={"status": "SUCCESS"})):
        result = runner.invoke(cli, ["analyze", "SPCE"])
        assert result.exit_code == 0, f"Error: {result.output}"
        assert "SPACE MARKET INTELLIGENCE ENGINE --- SPCE" in result.output
        assert "Signal:                          HOLD (DATA_UNAVAILABLE)" in result.output
        assert "SMI (Market Intelligence Index): -- / 100" in result.output
        assert "SSI (Social Sentiment Index):    -- / 100" in result.output


def test_cli_error_exit_codes():
    """Verify that run-all and calculate-smi return non-zero exit codes when pipeline returns ERROR."""
    from unittest.mock import patch, AsyncMock

    runner = CliRunner()
    with patch("app.cli.commands.run_full_pipeline", new=AsyncMock(return_value={"status": "ERROR", "error": "Simulated Pipeline Error"})):
        res_run_all = runner.invoke(cli, ["run-all"])
        assert res_run_all.exit_code != 0, "run-all must return non-zero exit code on failure"
        assert "Simulated Pipeline Error" in res_run_all.output

        res_smi = runner.invoke(cli, ["calculate-smi"])
        assert res_smi.exit_code != 0, "calculate-smi must return non-zero exit code on failure"
        assert "Simulated Pipeline Error" in res_smi.output


def test_cli_clean_schema_autonomy(tmp_path, monkeypatch):
    """Verify that commands initialize schema autonomously and execute without errors on a fresh database."""
    import tempfile
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    temp_db_path = tmp_path / "clean_test.db"
    clean_db_url = f"sqlite:///{temp_db_path.as_posix()}"
    clean_engine = create_engine(clean_db_url)
    CleanSession = sessionmaker(bind=clean_engine)

    monkeypatch.setattr("app.database.connection.engine", clean_engine)
    monkeypatch.setattr("app.database.connection.SessionLocal", CleanSession)
    monkeypatch.setattr("app.cli.commands.SessionLocal", CleanSession)

    runner = CliRunner()

    # Commands must initialize DB themselves without crashing on missing tables
    res_div = runner.invoke(cli, ["calculate-divergences"])
    assert res_div.exit_code == 0, f"calculate-divergences failed on clean DB: {res_div.output}"

    res_rep = runner.invoke(cli, ["daily-report"])
    assert res_rep.exit_code == 0, f"daily-report failed on clean DB: {res_rep.output}"

    res_bt = runner.invoke(cli, ["backtest"])
    assert res_bt.exit_code == 0, f"backtest failed on clean DB: {res_bt.output}"

