import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.database.connection import get_db, SessionLocal
from app.database.models import JobRunModel
from app.database.repository import acquire_pipeline_job_lock, create_job_run, finish_job_run, utc_now
from app.jobs.runner import run_full_pipeline, PIPELINE_LOCK

logger = logging.getLogger("SMIE.JobsAPI")
router = APIRouter(tags=["Jobs"])


def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-KEY"),
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> bool:
    """
    Validates API Secret Key with constant-time comparison.
    1. Supports same-origin requests from the web dashboard safely without exposing keys in bundle.
    2. Enforces API_SECRET_KEY for external calls (cURL, scripts, automated webhooks).
    3. Fails secure in production if API_SECRET_KEY is missing.
    """
    headers = getattr(request, "headers", {}) or {}
    sec_fetch_site = headers.get("sec-fetch-site", "") if hasattr(headers, "get") else ""
    sec_fetch_site = sec_fetch_site.lower() if isinstance(sec_fetch_site, str) else ""
    origin = headers.get("origin", "") if hasattr(headers, "get") else ""
    host = headers.get("host", "") if hasattr(headers, "get") else ""
    
    is_same_origin = (
        sec_fetch_site == "same-origin" or
        (origin and host and (host in origin or "localhost" in origin or "127.0.0.1" in origin))
    )

    expected_key = getattr(settings, "API_SECRET_KEY", None)
    env = getattr(settings, "ENVIRONMENT", "development").lower()

    # Extract provided key from headers safely
    provided_key = x_api_key if isinstance(x_api_key, str) else None
    auth_str = authorization if isinstance(authorization, str) else None
    if not provided_key and auth_str:
        if auth_str.startswith("Bearer "):
            provided_key = auth_str[7:].strip()
        else:
            provided_key = auth_str.strip()

    # If key was explicitly provided, verify with constant-time comparison
    if provided_key:
        if not expected_key:
            return True
        if secrets.compare_digest(str(provided_key), str(expected_key)):
            return True
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid API key header (X-API-KEY)."
        )

    # Legitimate same-origin browser request from the dashboard
    if is_same_origin:
        return True

    # If no key was provided for an external request
    if not expected_key:
        if env == "production":
            raise HTTPException(
                status_code=503,
                detail="Server configuration error: API_SECRET_KEY must be set in production for external requests."
            )
        # Development / test mode bypass
        return True

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Missing API key header (X-API-KEY)."
    )


async def _execute_pipeline_task(job_id: int):
    """Worker task executed by BackgroundTasks."""
    try:
        logger.info(f"Starting background pipeline execution for job_id={job_id}...")
        await run_full_pipeline(existing_job_id=job_id, lock_already_acquired=True)
    except Exception as e:
        logger.exception(f"Fatal error in background pipeline task {job_id}: {e}")
        db = SessionLocal()
        try:
            finish_job_run(db, job_id, status="ERROR", error=str(e))
        finally:
            db.close()
    finally:
        if PIPELINE_LOCK.locked():
            PIPELINE_LOCK.release()


@router.post("/api/jobs/run", status_code=202)
async def trigger_full_pipeline_job(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    authorized: bool = Depends(verify_api_key)
) -> Dict[str, Any]:
    """
    Triggers the complete analysis pipeline asynchronously in the background.
    Returns HTTP 202 Accepted with job_id immediately to prevent proxy timeouts.
    Rejects overlapping concurrent requests with HTTP 409 Conflict.
    Enforces API Key authentication if API_SECRET_KEY is configured.
    """
    # 1. Process-level mutex check
    if PIPELINE_LOCK.locked():
        raise HTTPException(
            status_code=409,
            detail="A pipeline execution is already in progress in this process. Please wait for it to complete."
        )

    # 2. Atomic distributed lock check across all processes, workers, CLI, and Scheduler
    job_run, conflict_err = acquire_pipeline_job_lock(db, source="API")
    if not job_run:
        raise HTTPException(
            status_code=409,
            detail=conflict_err or "A pipeline execution is currently in progress. Please wait for it to complete."
        )

    await PIPELINE_LOCK.acquire()

    try:
        job_id = job_run.id
        # 3. Schedule background task
        background_tasks.add_task(_execute_pipeline_task, job_id)
    except Exception:
        if PIPELINE_LOCK.locked():
            PIPELINE_LOCK.release()
        finish_job_run(db, job_run.id, status="ERROR", error="Failed to launch background task")
        raise

    return JSONResponse(
        status_code=202,
        content={
            "status": "ACCEPTED",
            "message": "Pipeline execution scheduled in background.",
            "job_id": job_id
        }
    )


@router.get("/api/jobs/latest")
def get_latest_job(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Returns the most recent job run execution record."""
    job = db.query(JobRunModel).order_by(JobRunModel.started_at.desc()).first()
    if not job:
        return {"job": None}
    
    return {
        "job": {
            "id": job.id,
            "job_name": job.job_name,
            "status": job.status,
            "started_at": job.started_at.isoformat() + "Z" if job.started_at else None,
            "finished_at": job.finished_at.isoformat() + "Z" if job.finished_at else None,
            "records_processed": job.records_processed,
            "error_message": job.error_message
        }
    }


@router.get("/api/jobs/{job_id}")
def get_job_status(job_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Queries the status and telemetry of a specific job run by ID."""
    job = db.query(JobRunModel).filter(JobRunModel.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found.")

    return {
        "id": job.id,
        "job_name": job.job_name,
        "status": job.status,
        "started_at": job.started_at.isoformat() + "Z" if job.started_at else None,
        "finished_at": job.finished_at.isoformat() + "Z" if job.finished_at else None,
        "records_processed": job.records_processed,
        "error_message": job.error_message
    }
