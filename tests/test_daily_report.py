import pytest
from app.reports.daily_report import generate_daily_report
from app.database.connection import SessionLocal, init_db


def test_generate_daily_report_structure():
    init_db()
    db = SessionLocal()
    try:
        report = generate_daily_report(db)
        
        assert "date" in report
        assert "sector_sentiment" in report
        assert "average_smi" in report
        assert "top_bullish" in report
        assert "top_bearish" in report
        assert "ticker_summaries" in report
        assert "markdown_report" in report
        assert len(report["ticker_summaries"]) >= 5
        
        # Check text report structure
        text = report["markdown_report"]
        assert "SPACE MARKET INTELLIGENCE DAILY REPORT" in text
        assert "SECTOR REGIME:" in text
        assert "ASSET SIGNALS & MULTIVARIATE BREAKDOWN:" in text
    finally:
        db.close()


def test_ensure_tickers_seeded_fresh_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.connection import Base
    from app.database.repository import ensure_tickers_seeded
    from app.database.models import TickerModel

    # Fresh in-memory sqlite database
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    db = TestSession()

    try:
        assert db.query(TickerModel).count() == 0
        ensure_tickers_seeded(db)
        
        tickers = db.query(TickerModel).all()
        assert len(tickers) == 5
        
        asts = db.query(TickerModel).filter(TickerModel.symbol == "ASTS").first()
        assert asts is not None
        assert asts.sector == "Direct-to-Cell / Satellite Telecom"
        assert asts.is_private_or_test is False

        # Calling it again is a no-op and preserves count
        ensure_tickers_seeded(db)
        assert db.query(TickerModel).count() == 5
    finally:
        db.close()


def test_api_404_on_nonexistent_route():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/nonexistent_route_123")
    assert response.status_code == 404
    assert response.json()["detail"] == "API endpoint not found"


def test_dashboard_endpoint_batch_retrieval():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import init_db

    init_db()
    client = TestClient(app)
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "rankings" in data
    assert "alerts" in data
    assert len(data["rankings"]) == 5
    for item in data["rankings"]:
        assert "data_age_hours" in item
        assert "is_stale" in item
        assert isinstance(item["is_stale"], bool)
        assert "base_signal" in item
        assert "signal_modifier" in item


def test_ssi_snapshot_model_base_signal_persistence():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, SSISnapshotModel, TickerModel
    from app.database.repository import save_ssi_snapshot

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()

    try:
        ticker_record = TickerModel(
            symbol="ASTS",
            name="AST SpaceMobile",
            sector="Direct-to-Cell",
            is_active=True
        )
        db.add(ticker_record)
        db.commit()

        snap_data = {
            "ticker": "ASTS",
            "social_score": 85.0,
            "prediction_score": 75.0,
            "news_score": 80.0,
            "momentum_score": 70.0,
            "risk_score": 30.0,
            "technical_score": 35.0,
            "ssi": 85.0,
            "smi": 82.0,
            "signal": "WATCH (OVEREXTENDED)",
            "base_signal": "WATCH",
            "signal_modifier": "OVEREXTENDED",
            "confidence": 90.0,
            "data_completeness": 100.0,
            "data_quality": 95.0,
            "price": 25.5,
            "volume": 1000000.0,
            "explanation": "Test explanation"
        }

        saved_snap = save_ssi_snapshot(db, snap_data)
        assert saved_snap.id is not None
        assert saved_snap.signal == "WATCH (OVEREXTENDED)"
        assert saved_snap.base_signal == "WATCH"
        assert saved_snap.signal_modifier == "OVEREXTENDED"

        # Verify SQL filtering by base_signal works seamlessly
        queried = db.query(SSISnapshotModel).filter(SSISnapshotModel.base_signal == "WATCH").first()
        assert queried is not None
        assert queried.ticker == "ASTS"
    finally:
        db.close()


def test_dashboard_returns_null_when_no_data_and_no_imputation():
    """
    Test Rule in Spec & Architecture:
    If no snapshot data exists for a ticker, SMI, SSI, and subscores MUST be null / None.
    Fake imputation (e.g. 50.0) is strictly forbidden.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.main import app
    from app.database.connection import get_db
    from app.database.models import Base

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        client = TestClient(app)
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert len(data["rankings"]) == 5
        for item in data["rankings"]:
            assert item["smi"] is None, f"Expected None for smi without data, got {item['smi']}"
            assert item["ssi"] is None, f"Expected None for ssi without data, got {item['ssi']}"
            assert item["social_score"] is None
            assert item["delta_1d"] is None
            assert item["pms"] is None
            assert item["signal"] == "N/A"
            assert item["market_status"] == "DATA_UNAVAILABLE"
    finally:
        app.dependency_overrides.clear()


def test_init_db_auto_migration_idempotent():
    """Verify that init_db safely introspects and migrates database columns without errors."""
    from app.database.connection import init_db
    # First execution creates tables and runs migrations
    init_db()
    # Second execution must be strictly idempotent and not throw errors
    init_db()


def test_ticker_detail_and_prediction_markets_api_endpoints():
    """Verify that /api/tickers/{ticker} and /api/tickers/{ticker}/prediction-markets return 200 with direct vs sector metadata."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import init_db

    init_db()
    client = TestClient(app)
    for ticker in ["ASTS", "RKLB", "SPCE", "SATL", "SPCX"]:
        # Test Detail endpoint
        res_detail = client.get(f"/api/tickers/{ticker}")
        assert res_detail.status_code == 200
        detail_data = res_detail.json()
        assert detail_data["ticker"] == ticker
        assert "prediction_markets" in detail_data
        assert "sample_counts" in detail_data

        # If prediction markets exist, direct contracts must have is_direct == True
        for m in detail_data["prediction_markets"]:
            assert "is_direct" in m
            assert "event_role" in m
            if m.get("ticker") and m["ticker"].upper() == ticker:
                assert m["is_direct"] is True
                assert m["event_role"] == "DIRECT"

        # Test prediction markets standalone endpoint
        res_pm = client.get(f"/api/tickers/{ticker}/prediction-markets")
        assert res_pm.status_code == 200
        pm_data = res_pm.json()
        assert isinstance(pm_data, list)


def test_get_history_series_returns_latest_bounded_chronological():
    """
    Verify that when more than limit snapshots exist in DB (e.g. 150 snapshots),
    get_history_series(limit=100) returns the latest 100 snapshots in chronological ascending order.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database.models import Base, SSISnapshotModel
    from app.database.repository import get_history_series

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()

    try:
        now = datetime.now(timezone.utc)
        # Create 150 hourly snapshots for ASTS
        snaps = [
            SSISnapshotModel(
                ticker="ASTS",
                timestamp=now - timedelta(hours=150 - i),
                price=10.0 + i * 0.1,
                smi=50.0 + (i % 20),
                ssi=50.0,
                social_score=50.0,
                signal="HOLD",
                confidence=80.0,
                data_completeness=100.0
            )
            for i in range(150)
        ]
        db.add_all(snaps)
        db.commit()

        # Query history series with default limit=100
        history = get_history_series(db, "ASTS", limit=100)

        # 1. Must return exactly 100 snapshots
        assert len(history) == 100

        # 2. Must contain the LATEST snapshots (#50 to #149), not the oldest (#0 to #49)
        # Snapshot #149 had price = 10.0 + 149*0.1 = 24.9
        assert history[-1]["price"] == pytest.approx(24.9, 0.01)
        # Snapshot #50 had price = 10.0 + 50*0.1 = 15.0
        assert history[0]["price"] == pytest.approx(15.0, 0.01)

        # 3. Must be strictly ascending in timestamp
        timestamps = [h["timestamp"] for h in history]
        assert timestamps == sorted(timestamps)
    finally:
        db.close()


def test_dashboard_semantic_state_alert_ids():
    """Verify that /api/dashboard produces semantic state-based alert IDs."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import init_db

    init_db()
    client = TestClient(app)
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    alerts = data.get("alerts", [])
    
    for al in alerts:
        # Alert IDs should follow state patterns, not auto-incrementing snapshot numbers
        assert al["id"].startswith(f"{al['ticker']}:")
        if al["type"] in ["STRONG_BUY", "STRONG_AVOID"]:
            assert al["id"] == f"{al['ticker']}:SIGNAL:{al['type']}"
        elif al["type"] == "STALE_DATA":
            assert al["id"] == f"{al['ticker']}:SYSTEM:STALE_DATA"


def test_database_alerts_persistence_and_dashboard_serving():
    """Verify that save_alerts persists CRITICAL_CATALYST and MOMENTUM_BUY and /api/dashboard returns them."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import SessionLocal, init_db
    from app.database.repository import save_alerts

    init_db()
    db = SessionLocal()
    try:
        # Save a critical catalyst and momentum buy alert for ASTS
        alerts_to_save = [
            {
                "ticker": "ASTS",
                "type": "CRITICAL_CATALYST",
                "category": "CATALYST",
                "level": "CRITICAL",
                "message": "⚡ Critical Catalyst detected on ASTS: Government Contract"
            },
            {
                "ticker": "ASTS",
                "type": "MOMENTUM_BUY",
                "category": "SIGNAL",
                "level": "HIGH",
                "message": "📈 ASTS BUY signal confirmed with accelerating SMI (+4.5 1D)"
            }
        ]
        save_alerts(db, "ASTS", alerts_to_save)
    finally:
        db.close()

    client = TestClient(app)
    res = client.get("/api/dashboard")
    assert res.status_code == 200
    data = res.json()
    alerts = data.get("alerts", [])

    types = [a["type"] for a in alerts if a["ticker"] == "ASTS"]
    assert "CRITICAL_CATALYST" in types
    assert "MOMENTUM_BUY" in types

    cat_alert = next(a for a in alerts if a["type"] == "CRITICAL_CATALYST")
    assert cat_alert["level"] == "CRITICAL"
    assert cat_alert["category"] == "CATALYST"
    assert "⚡ Critical Catalyst" in cat_alert["message"]


def test_health_and_dashboard_data_provenance_governance():
    """Verify that /api/health audits provider modes and /api/dashboard returns data_source."""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.connection import SessionLocal, init_db
    from app.database.repository import save_ssi_snapshot

    init_db()
    db = SessionLocal()
    try:
        snap_data = {
            "ticker": "RKLB",
            "social_score": 75.0,
            "prediction_score": 65.0,
            "news_score": 70.0,
            "momentum_score": 60.0,
            "risk_score": 70.0,
            "technical_score": 28.0,
            "ssi": 75.0,
            "smi": 71.5,
            "signal": "BUY",
            "confidence": 85.0,
            "data_completeness": 100.0,
            "data_quality": 100.0,
            "post_count": 25,
            "news_count": 5,
            "prediction_count": 2,
            "data_source": "LIVE",
            "social_source": "LIVE",
            "prediction_source": "LIVE",
            "news_source": "LIVE",
            "market_source": "LIVE",
            "price": 45.5
        }
        save_ssi_snapshot(db, snap_data)
    finally:
        db.close()

    client = TestClient(app)

    # 1. Verify /api/health
    res_health = client.get("/api/health")
    assert res_health.status_code == 200
    h_data = res_health.json()
    assert "allow_mock_fallback" in h_data
    assert "engine_data_source" in h_data
    assert "x_provider" in h_data
    assert "polymarket_provider" in h_data

    # 2. Verify /api/dashboard contains data_source tags
    res_dash = client.get("/api/dashboard")
    assert res_dash.status_code == 200
    d_data = res_dash.json()
    rklb_rank = next((r for r in d_data.get("rankings", []) if r["ticker"] == "RKLB"), None)
    assert rklb_rank is not None
    assert rklb_rank["data_source"] == "LIVE"
    assert rklb_rank["social_source"] == "LIVE"
    assert rklb_rank["prediction_source"] == "LIVE"


def test_jobs_async_execution_and_status_endpoints():
    """Verify POST /api/jobs/run returns 202 Accepted and GET /api/jobs/{id} tracks execution."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # 1. Trigger background job execution
    res_run = client.post("/api/jobs/run")
    assert res_run.status_code == 202
    run_data = res_run.json()
    assert run_data["status"] == "ACCEPTED"
    job_id = run_data["job_id"]
    assert job_id is not None

    # 2. Query specific job status
    res_status = client.get(f"/api/jobs/{job_id}")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["id"] == job_id
    assert status_data["status"] in ["RUNNING", "SUCCESS", "ERROR"]

    # 3. Query latest job
    res_latest = client.get("/api/jobs/latest")
    assert res_latest.status_code == 200
    latest_data = res_latest.json()
    assert latest_data["job"] is not None
    assert latest_data["job"]["id"] >= job_id













