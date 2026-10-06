"""
Retired.

This job used to refund free skips at each meal cut-off. Skips are now
refunded at the moment the customer skips (SubscriptionService.skip_order,
idempotency key meal_refund:<order_id>), so running this job as well paid
the same skip twice. It is kept as a no-op so old scripts still import.
"""

import logging

logger = logging.getLogger(__name__)


def process_order_billing(meal_slot: str) -> None:
    logger.info("[billing:%s] retired job called; skips are refunded when they happen", meal_slot)
