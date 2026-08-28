import os
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.connection import get_db
from app.database.models import JobRunModel, SSISnapshotModel
from app.config import settings

router = APIRouter(tags=["Health"])


@router.get("/api/health")
def health_check(db: Session = Depends(get_db)) -> Dict[str, Any]:
    # Check DB
    db_status = "ok"
    try:
        db.execute(text("SELECT 1;"))
    except Exception:
        db_status = "error"

    # Check X / Social Provider Status
    if settings.X_PROVIDER.lower() == "mock":
        x_status = "mock"
    elif settings.X_PROVIDER.lower() == "twikit":
        has_cookies = os.path.exists(settings.X_COOKIES_FILE) and os.path.getsize(settings.X_COOKIES_FILE) > 0
        has_credentials = bool(settings.X_AUTH_INFO_1 and settings.X_PASSWORD)
        x_status = "live" if (has_cookies or has_credentials) else "unauthenticated"
    else:
        x_status = "configured"

    # Check Polymarket Provider Status
    if not settings.POLYMARKET_ENABLED:
        poly_status = "disabled"
    elif settings.POLYMARKET_PROVIDER.lower() == "mock":
        poly_status = "mock"
    else:
        poly_status = "live"

    # Get last snapshot to check data provenance
    last_snap = db.query(SSISnapshotModel).order_by(SSISnapshotModel.timestamp.desc()).first()
    engine_data_source = getattr(last_snap, "data_source", "LIVE") if last_snap else ("MOCK" if (x_status == "mock" or poly_status == "mock") else "LIVE")

    # Get last job run
    last_job = db.query(JobRunModel).order_by(JobRunModel.started_at.desc()).first()
    last_update_str = last_job.finished_at.isoformat() + "Z" if last_job and last_job.finished_at else datetime.now(timezone.utc).isoformat()
    last_job_data = None
    if last_job:
        last_job_data = {
            "id": last_job.id,
            "status": last_job.status,
            "started_at": last_job.started_at.isoformat() + "Z" if last_job.started_at else None,
            "finished_at": last_job.finished_at.isoformat() + "Z" if last_job.finished_at else None,
            "records_processed": last_job.records_processed,
            "error_message": last_job.error_message
        }

    is_last_job_ok = last_job is None or last_job.status in ["SUCCESS", "RUNNING"]
    overall_status = "ok" if (db_status == "ok" and is_last_job_ok and x_status in ["live", "mock"] and poly_status in ["live", "mock", "disabled"]) else "degraded"

    return {
        "status": overall_status,
        "database": db_status,
        "engine_data_source": engine_data_source,
        "allow_mock_fallback": settings.ALLOW_MOCK_FALLBACK,
        "last_job": last_job_data,
        "x_provider": {
            "name": settings.X_PROVIDER,
            "status": x_status
        },
        "polymarket_provider": {
            "name": settings.POLYMARKET_PROVIDER,
            "status": poly_status
        },
        "market_provider": {
            "name": "yfinance",
            "status": "live"
        },
        "news_provider": {
            "name": "google_rss",
            "status": "live"
        },
        "last_update": last_update_str
    }
