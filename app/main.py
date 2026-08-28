import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
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

# CORS middleware for frontend communication (W3C CORS compliant with credentials)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:[0-9]+)?",
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

from pathlib import Path

# Mount frontend static files if built
dist_dir = (Path(__file__).resolve().parent.parent / "frontend" / "dist").resolve()
if dist_dir.exists() and dist_dir.is_dir():
    assets_dir = dist_dir / "assets"
    if assets_dir.exists() and assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api" or full_path in ("docs", "redoc", "openapi.json"):
            raise HTTPException(status_code=404, detail="API endpoint not found")
        try:
            file_path = (dist_dir / full_path).resolve()
            if not file_path.is_relative_to(dist_dir):
                raise HTTPException(status_code=404, detail="Resource not found")
            if file_path.is_file():
                return FileResponse(str(file_path))
        except (ValueError, RuntimeError):
            raise HTTPException(status_code=404, detail="Resource not found")

        # If a specific file or dotfile was requested but does not exist, return 404
        last_segment = full_path.split("/")[-1]
        if "." in last_segment:
            raise HTTPException(status_code=404, detail="Resource not found")

        # Clean SPA navigation fallback
        index_file = dist_dir / "index.html"
        if index_file.is_file():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404, detail="Resource not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
