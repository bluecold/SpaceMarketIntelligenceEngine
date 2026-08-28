import asyncio
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.connection import get_db, SessionLocal
from app.database.models import JobRunModel
from app.database.repository import create_job_run, finish_job_run
from app.jobs.runner import run_full_pipeline

logger = logging.getLogger("SMIE.JobsAPI")
router = APIRouter(tags=["Jobs"])

# Concurrency Mutex Lock: prevents overlapping executions from racing against SQLite
_PIPELINE_LOCK = asyncio.Lock()


async def _execute_pipeline_task(job_id: int):
    """Worker task executed by BackgroundTasks; releases the exclusive lock on exit."""
    try:
        logger.info(f"Starting background pipeline execution for job_id={job_id}...")
        await run_full_pipeline(existing_job_id=job_id)
    except Exception as e:
        logger.exception(f"Fatal error in background pipeline task {job_id}: {e}")
        db = SessionLocal()
        try:
            finish_job_run(db, job_id, status="ERROR", error=str(e))
        finally:
            db.close()
    finally:
        if _PIPELINE_LOCK.locked():
            _PIPELINE_LOCK.release()


@router.post("/api/jobs/run", status_code=202)
async def trigger_full_pipeline_job(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Triggers the complete analysis pipeline asynchronously in the background.
    Returns HTTP 202 Accepted with job_id immediately to prevent proxy timeouts.
    Rejects overlapping concurrent requests with HTTP 409 Conflict.
    """
    if _PIPELINE_LOCK.locked():
        raise HTTPException(
            status_code=409,
            detail="A pipeline execution is already in progress. Please wait for it to complete."
        )

    # Acquire lock atomically in handler before responding
    await _PIPELINE_LOCK.acquire()

    try:
        # 1. Create Job record in database
        job_run = create_job_run(db, "smie_full_pipeline")
        job_id = job_run.id

        # 2. Schedule background task that releases the lock in finally
        background_tasks.add_task(_execute_pipeline_task, job_id)
    except Exception:
        if _PIPELINE_LOCK.locked():
            _PIPELINE_LOCK.release()
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
