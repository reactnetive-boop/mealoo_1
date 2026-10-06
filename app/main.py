# ---------------------------------------------------------
# MAIN APPLICATION ENTRY POINT
# ---------------------------------------------------------

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.clock import BUSINESS_TZ
from app.core.config import APP_NAME, CORS_ORIGINS, ENABLE_API_DOCS, RUN_SCHEDULER, STORAGE_BACKEND, validate_settings
from app.core.database import engine
from app.core.errors import install_error_handlers
from app.core.middleware import install_middleware
from app.core.observability import RequestContextMiddleware, configure_logging, init_sentry
from app.api.v1.api import api_router
from app.schedulers import jobs
from app.utils.file_helper import BASE_DIR, PUBLIC_AREAS, public_url

configure_logging()
validate_settings()
init_sentry()

scheduler = BackgroundScheduler(timezone=BUSINESS_TZ)


def _schedule_jobs() -> None:
    scheduler.add_job(jobs.expire_subscriptions_job, CronTrigger(hour=0, minute=1), id="expire_subscriptions", replace_existing=True)
    scheduler.add_job(jobs.generate_meals_job, CronTrigger(hour=0, minute=5), id="generate_meals", replace_existing=True)
    scheduler.add_job(jobs.pickup_codes_job, CronTrigger(hour=0, minute=6), id="pickup_codes", replace_existing=True)
    scheduler.add_job(jobs.stale_sweep_job, CronTrigger(hour=0, minute=10), id="stale_sweep", replace_existing=True)
    scheduler.add_job(jobs.cutoff_sweep_job, IntervalTrigger(minutes=15), id="cutoff_sweep", replace_existing=True)
    scheduler.add_job(jobs.maintenance_job, CronTrigger(hour=3, minute=30), id="maintenance", replace_existing=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Only one process should run jobs (RUN_SCHEDULER=false on API replicas);
    # the jobs also take advisory locks, so an accidental second runner is harmless.
    if RUN_SCHEDULER:
        jobs.startup_catch_up()
        _schedule_jobs()
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown()


app = FastAPI(
    title=APP_NAME,
    lifespan=lifespan,
    docs_url="/docs" if ENABLE_API_DOCS else None,
    redoc_url="/redoc" if ENABLE_API_DOCS else None,
    openapi_url="/openapi.json" if ENABLE_API_DOCS else None,
)

install_error_handlers(app)
install_middleware(app)

# Mobile apps do not need CORS; this is for the admin web app. Tokens travel in
# the Authorization header, never cookies, so credentials stay disabled.
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    max_age=600,
    expose_headers=["X-Request-ID"],
)
# Outermost: every response (including CORS and size-limit rejections) carries a request id
app.add_middleware(RequestContextMiddleware)


@app.get("/")
def health_check():
    return {"success": True, "message": f"{APP_NAME} Running Successfully"}


@app.get("/health/live")
def liveness():
    """The process is up (no dependencies checked)."""
    return {"status": "ok"}


@app.get("/health")
def health():
    """Readiness: 503 when the database cannot be reached, so the platform stops routing here."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        database = "ok"
    except SQLAlchemyError:
        logging.getLogger("app.health").exception("database health check failed")
        database = "unavailable"
    body = {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "scheduler": "running" if scheduler.running else ("off" if not RUN_SCHEDULER else "stopped"),
    }
    return JSONResponse(body, status_code=200 if database == "ok" else 503)


app.include_router(api_router, prefix="/api/v1")

# Public images only. KYC documents (delivery_boys/documents) are private and
# served through authenticated endpoints.
if STORAGE_BACKEND == "local":
    for _area in PUBLIC_AREAS:
        app.mount(
            f"/uploads/{_area}",
            StaticFiles(directory=os.path.join(BASE_DIR, _area)),
            name=f"uploads:{_area}",
        )
else:
    @app.get("/uploads/{path:path}", include_in_schema=False)
    def uploaded_image(path: str):
        """Stored paths stay "uploads/...": send the apps on to the bucket / CDN."""
        url = public_url(f"uploads/{path}")
        if url is None:
            return JSONResponse({"success": False, "detail": "Not found"}, status_code=404)
        return RedirectResponse(url, status_code=307)
