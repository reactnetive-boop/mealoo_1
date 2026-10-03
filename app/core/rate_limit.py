"""
In-process sliding-window rate limiter.

This throttles abusive bursts per client IP and per identifier (mobile
number, email). It is per-process: with several API replicas each replica
counts separately, so the durable protections (per-account login lockout,
per-OTP attempt counter, OTP send quota) live in the database instead.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.core.config import TRUST_PROXY_HEADERS

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def hit(bucket: str, key: str, limit: int, window_seconds: int) -> None:
    """Record one hit; raise 429 when `limit` is exceeded inside the window."""

    now = time.monotonic()
    with _lock:
        q = _hits[(bucket, key)]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            retry_after = max(1, int(window_seconds - (now - q[0])))
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please wait and try again.",
                headers={"Retry-After": str(retry_after)},
            )
        q.append(now)


def reset_all() -> None:
    with _lock:
        _hits.clear()


def limit_by_ip(bucket: str, limit: int, window_seconds: int):
    """FastAPI dependency: throttle an endpoint per client IP."""

    def _dependency(request: Request):
        hit(bucket, client_ip(request), limit, window_seconds)

    return _dependency
