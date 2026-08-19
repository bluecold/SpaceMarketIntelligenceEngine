from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.connection import get_db
from app.database.models import JobRunModel
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

    # Get last job run
    last_job = db.query(JobRunModel).order_by(JobRunModel.started_at.desc()).first()
    last_update_str = last_job.finished_at.isoformat() + "Z" if last_job and last_job.finished_at else datetime.now(timezone.utc).isoformat()

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "database": db_status,
        "x_provider": "ok",
        "polymarket_provider": "ok" if settings.POLYMARKET_ENABLED else "disabled",
        "market_provider": "ok",
        "news_provider": "ok",
        "last_update": last_update_str
    }
