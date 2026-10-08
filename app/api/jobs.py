import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Annotated
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Header, Request, Path
from sqlalchemy.orm import Session
from app.config import settings
from app.database.connection import get_db, SessionLocal, DbSession
from app.database.models import JobRunModel
from app.database.repository import acquire_pipeline_job_lock, create_job_run, finish_job_run, utc_now
from app.jobs.runner import run_full_pipeline, PIPELINE_LOCK

logger = logging.getLogger("SMIE.JobsAPI")
router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


def verify_api_key(
    request: Request,
    x_api_key: Annotated[Optional[str], Header(alias="X-API-KEY")] = None,
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None
) -> bool:
    """
    Validates API Secret Key with constant-time comparison.
    1. Rejects spoofable browser origin headers (Sec-Fetch-Site, Origin).
    2. Enforces API_SECRET_KEY in production: fails secure (503) if unconfigured regardless of client input.
    3. Requires valid API key via X-API-KEY or Authorization: Bearer header.
    4. Allows unauthenticated access in development ONLY if API_SECRET_KEY is not configured.
    """
    expected_key = getattr(settings, "API_SECRET_KEY", None)
    env = getattr(settings, "ENVIRONMENT", "development").lower()

    # Production fail-secure: If API_SECRET_KEY is not configured in production, reject all requests
    if env == "production" and not expected_key:
        raise HTTPException(
            status_code=503,
            detail="Server configuration error: API_SECRET_KEY must be configured in production."
        )

    # In development/test mode without API_SECRET_KEY, allow unauthenticated access
    if not expected_key:
        return True

    # Extract provided key from headers safely
    provided_key = x_api_key if isinstance(x_api_key, str) else None
    auth_str = authorization if isinstance(authorization, str) else None
    if not provided_key and auth_str:
        if auth_str.startswith("Bearer "):
            provided_key = auth_str[7:].strip()
        else:
            provided_key = auth_str.strip()

    if not provided_key:
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing API key header (X-API-KEY or Authorization Bearer)."
        )

    # Constant-time comparison to protect against timing attacks
    if not secrets.compare_digest(str(provided_key), str(expected_key)):
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid API key header (X-API-KEY)."
        )

    return True


AuthDep = Annotated[bool, Depends(verify_api_key)]


async def _execute_pipeline_task(job_id: int):
    """Worker task executed by BackgroundTasks."""
    try:
        logger.info(f"Starting background pipeline execution for job_id={job_id}...")
        await run_full_pipeline(existing_job_id=job_id, lock_already_acquired=True)
    except Exception as e:
        logger.exception(f"Fatal error in background pipeline task {job_id}: {e}")
        def _record_error():
            with SessionLocal() as db_err:
                finish_job_run(db_err, job_id, status="ERROR", error=str(e))
        await asyncio.to_thread(_record_error)
    finally:
        if PIPELINE_LOCK.locked():
            PIPELINE_LOCK.release()


@router.post("/run", status_code=202)
async def trigger_full_pipeline_job(
    background_tasks: BackgroundTasks,
    db: DbSession,
    authorized: AuthDep
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
    # Executed via asyncio.to_thread to prevent blocking the async event loop during SQLite lock acquisition
    job_run, conflict_err = await asyncio.to_thread(acquire_pipeline_job_lock, db, source="API")
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
        await asyncio.to_thread(finish_job_run, db, job_run.id, status="ERROR", error="Failed to launch background task")
        raise

    return {
        "status": "ACCEPTED",
        "message": "Pipeline execution scheduled in background.",
        "job_id": job_id
    }


@router.get("/latest")
def get_latest_job(db: DbSession) -> Dict[str, Any]:
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


@router.get("/{job_id}")
def get_job_status(
    job_id: Annotated[int, Path(ge=1, description="Job run ID")],
    db: DbSession
) -> Dict[str, Any]:
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
