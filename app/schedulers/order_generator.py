"""Kept for older scripts; meal generation lives in app.schedulers.jobs."""

from app.schedulers.jobs import generate_meals_job


def generate_subscription_orders():
    generate_meals_job()
