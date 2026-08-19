import asyncio
from fastapi import APIRouter, BackgroundTasks
from app.jobs.runner import run_full_pipeline

router = APIRouter(tags=["Jobs"])


@router.post("/api/jobs/run")
async def trigger_full_pipeline_job():
    """Trigger complete analysis pipeline asynchronously."""
    res = await run_full_pipeline()
    return res
