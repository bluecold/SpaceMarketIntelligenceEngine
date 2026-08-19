import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database.connection import init_db, SessionLocal
from app.database.repository import ensure_tickers_seeded
from app.api import health, dashboard, tickers, history, jobs, reports

logging.basicConfig(level=logging.INFO if settings.DEBUG else logging.WARNING)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Space Market Intelligence Engine database...")
    init_db()
    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
    finally:
        db.close()

    # Optional APScheduler startup
    scheduler = None
    if settings.ENABLE_SCHEDULER:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from app.jobs.runner import run_full_pipeline
            scheduler = AsyncIOScheduler()
            scheduler.add_job(run_full_pipeline, 'interval', minutes=settings.JOB_INTERVAL_MINUTES)
            scheduler.start()
            logger.info(f"APScheduler started. Job interval: {settings.JOB_INTERVAL_MINUTES} min.")
        except Exception as e:
            logger.error(f"Failed to start APScheduler: {e}")

    yield

    if scheduler:
        scheduler.shutdown()
        logger.info("APScheduler shut down.")


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description="Space Market Intelligence Engine (SMIE) Quantitative Backend",
    lifespan=lifespan
)

# CORS middleware for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(health.router)
app.include_router(dashboard.router)
app.include_router(tickers.router)
app.include_router(history.router)
app.include_router(jobs.router)
app.include_router(reports.router)

# Mount frontend static files if built
dist_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(dist_dir):
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_dir, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/"):
            return None
        file_path = os.path.join(dist_dir, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(dist_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
