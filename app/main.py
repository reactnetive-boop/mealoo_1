# ---------------------------------------------------------
# MAIN APPLICATION ENTRY POINT
# ---------------------------------------------------------

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import APP_NAME
from app.api.v1.api import api_router
from app.schedulers.order_generator import generate_subscription_orders

logging.basicConfig(level=logging.INFO)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run once at startup to catch up on any missing orders
    generate_subscription_orders()

    # Then run daily at midnight
    scheduler.add_job(
        generate_subscription_orders,
        trigger=CronTrigger(hour=0, minute=0),
        id="generate_subscription_orders",
        replace_existing=True
    )
    scheduler.start()

    yield

    scheduler.shutdown()


app = FastAPI(
    title=APP_NAME,
    lifespan=lifespan
)


@app.get("/")
def health_check():

    return {
        "success": True,
        "message": f"{APP_NAME} Running Successfully"
    }

app.include_router(
    api_router,
    prefix="/api/v1"
)

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)