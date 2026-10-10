"""
Customers cannot cancel their own plans or one-time orders (business rule).

Admins still cancel through their own endpoints. The flag is read on every
call so it can be switched without a restart in tests.
"""

from app.core import config
from app.core.errors import DomainError


def customer_cancellation_enabled() -> bool:
    return bool(config.CUSTOMER_CANCELLATION_ENABLED)


def assert_customer_can_cancel(what: str) -> None:
    if not customer_cancellation_enabled():
        raise DomainError(
            f"{what} can't be cancelled from the app. Please contact support if you need help.",
            403,
            code="CANCELLATION_DISABLED",
        )
