"""
Rate limiting and short-lived counters (login back-off, burst throttles).

Two backends behind one small interface:
  * memory (default): per process. Fine for a single API instance and tests.
  * Redis (REDIS_URL set): shared by every replica and survives restarts.

If Redis is configured but unreachable, calls fall back to the in-memory store
and log an error: a Redis outage must not take login and ordering down. The
durable protections (OTP attempt counters, OTP send quota, account-wide lock)
live in the database either way.
"""

import logging
import threading
import time
import uuid
from collections import deque

from fastapi import HTTPException, Request

from app.core.config import REDIS_URL, TRUST_PROXY_HEADERS

logger = logging.getLogger("app.rate_limit")


def ip_from(headers, client_host: str | None) -> str:
    """Client IP; X-Forwarded-For is honoured only behind a trusted proxy."""
    if TRUST_PROXY_HEADERS:
        forwarded = headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return client_host or "unknown"


def client_ip(request: Request) -> str:
    return ip_from(request.headers, request.client.host if request.client else None)


# ── Stores ────────────────────────────────────────────────────

class MemoryStore:
    """Thread-safe in-process store. Expired keys are swept periodically."""

    SWEEP_EVERY = 1000

    def __init__(self):
        self._lock = threading.Lock()
        self._windows: dict[str, tuple[deque, int]] = {}
        self._values: dict[str, tuple[int, float]] = {}
        self._ops = 0

    def _tick(self, now: float) -> None:
        self._ops += 1
        if self._ops % self.SWEEP_EVERY:
            return
        for key, (q, window) in list(self._windows.items()):
            if not q or now - q[-1] > window:
                del self._windows[key]
        for key, (_, expires) in list(self._values.items()):
            if expires <= now:
                del self._values[key]

    def hit(self, key: str, limit: int, window: int) -> int | None:
        now = time.monotonic()
        with self._lock:
            self._tick(now)
            q, _ = self._windows.setdefault(key, (deque(), window))
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return max(1, int(window - (now - q[0])))
            q.append(now)
            return None

    def _live(self, key: str, now: float):
        entry = self._values.get(key)
        if entry and entry[1] > now:
            return entry
        self._values.pop(key, None)
        return None

    def incr(self, key: str, ttl: int) -> int:
        now = time.monotonic()
        with self._lock:
            self._tick(now)
            entry = self._live(key, now)
            value, expires = (entry[0] + 1, entry[1]) if entry else (1, now + ttl)
            self._values[key] = (value, expires)
            return value

    def block(self, key: str, seconds: int) -> None:
        with self._lock:
            self._values[key] = (1, time.monotonic() + max(1, int(seconds)))

    def blocked_for(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            entry = self._live(key, now)
            return max(1, int(entry[1] - now)) if entry else 0

    def delete(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._values.pop(key, None)
                self._windows.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
            self._values.clear()


class RedisStore:
    """Same interface on Redis: sorted sets for windows, TTL keys for counters."""

    def __init__(self, client, prefix: str = "rl:"):
        self.r = client
        self.prefix = prefix

    def _k(self, key: str) -> str:
        return self.prefix + key

    def hit(self, key: str, limit: int, window: int) -> int | None:
        k = self._k(key)
        now = time.time()
        member = f"{now:.6f}:{uuid.uuid4().hex[:8]}"
        pipe = self.r.pipeline()
        pipe.zremrangebyscore(k, 0, now - window)
        pipe.zadd(k, {member: now})
        pipe.zcard(k)
        pipe.expire(k, window + 1)
        count = pipe.execute()[2]
        if count <= limit:
            return None
        self.r.zrem(k, member)
        oldest = self.r.zrange(k, 0, 0, withscores=True)
        retry = window - (now - oldest[0][1]) if oldest else window
        return max(1, int(retry))

    def incr(self, key: str, ttl: int) -> int:
        k = self._k(key)
        pipe = self.r.pipeline()
        pipe.set(k, 0, ex=ttl, nx=True)
        pipe.incr(k)
        return int(pipe.execute()[1])

    def block(self, key: str, seconds: int) -> None:
        self.r.set(self._k(key), 1, ex=max(1, int(seconds)))

    def blocked_for(self, key: str) -> int:
        ttl = self.r.ttl(self._k(key))
        return ttl if ttl and ttl > 0 else 0

    def delete(self, *keys: str) -> None:
        if keys:
            self.r.delete(*(self._k(k) for k in keys))

    def reset(self) -> None:
        for k in self.r.scan_iter(match=self.prefix + "*"):
            self.r.delete(k)


_memory = MemoryStore()
_store = _memory
_last_redis_error = 0.0


def _make_default_store():
    if not REDIS_URL:
        return _memory
    import redis  # optional dependency, only needed when REDIS_URL is set

    client = redis.Redis.from_url(REDIS_URL, socket_timeout=0.5, socket_connect_timeout=0.5)
    return RedisStore(client)


def configure(store=None) -> None:
    """Swap the backing store (tests pass a fakeredis-backed RedisStore)."""
    global _store
    _store = store if store is not None else _make_default_store()


def _call(method: str, *args):
    global _last_redis_error
    try:
        return getattr(_store, method)(*args)
    except Exception:
        if _store is _memory:
            raise
        now = time.monotonic()
        if now - _last_redis_error > 60:
            _last_redis_error = now
            logger.exception("rate limit store unavailable, using in-process fallback")
        return getattr(_memory, method)(*args)


def incr(key: str, ttl: int) -> int:
    return _call("incr", key, ttl)


def block(key: str, seconds: int) -> None:
    _call("block", key, seconds)


def blocked_for(key: str) -> int:
    return _call("blocked_for", key)


def delete(*keys: str) -> None:
    _call("delete", *keys)


def hit(bucket: str, key: str, limit: int, window_seconds: int) -> None:
    """Record one hit; raise 429 when `limit` is exceeded inside the window."""
    retry_after = _call("hit", f"{bucket}:{key}", limit, window_seconds)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait and try again.",
            headers={"Retry-After": str(retry_after)},
        )


def reset_all() -> None:
    _memory.reset()
    if _store is not _memory:
        _call("reset")


def limit_by_ip(bucket: str, limit: int, window_seconds: int):
    """FastAPI dependency: throttle an endpoint per client IP."""

    def _dependency(request: Request):
        hit(bucket, client_ip(request), limit, window_seconds)

    return _dependency


configure()
