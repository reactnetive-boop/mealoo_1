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
from app.schedulers.order_billing import process_order_billing

logging.basicConfig(level=logging.INFO)

scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run once at startup to catch up on any missing orders
    generate_subscription_orders()

    # Generate all subscription orders daily at midnight
    scheduler.add_job(
        generate_subscription_orders,
        trigger=CronTrigger(hour=0, minute=0),
        id="generate_subscription_orders",
        replace_existing=True,
    )

    # Billing jobs: deduct wallet per meal slot at delivery time
    for meal_slot, hour in (("breakfast", 6), ("lunch", 9), ("dinner", 15)):
        scheduler.add_job(
            process_order_billing,
            trigger=CronTrigger(hour=hour, minute=0),
            id=f"billing_{meal_slot}",
            args=[meal_slot],
            replace_existing=True,
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