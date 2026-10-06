"""
Request ids, structured logs and optional error reporting.

Every request gets an id: the caller's X-Request-ID when it looks sane,
otherwise a new one. The id is returned in the X-Request-ID response header,
stamped on every log line written while serving the request, and used as the
"ref" in 500 responses. A user quoting that ref leads straight to the log
lines and to the Sentry event.

Logs are one JSON object per line when LOG_FORMAT=json (the production
default), plain text otherwise. Sentry is enabled only when SENTRY_DSN is set,
and never sends request bodies or personal data.
"""

import contextvars
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from starlette.datastructures import Headers, MutableHeaders

from app.core.config import APP_ENV, LOG_FORMAT, LOG_LEVEL, SENTRY_DSN, SENTRY_TRACES_SAMPLE_RATE
from app.core.rate_limit import ip_from

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_client_ip: contextvars.ContextVar[str | None] = contextvars.ContextVar("client_ip", default=None)

_SAFE_ID = re.compile(r"[A-Za-z0-9._-]{8,64}")
access_logger = logging.getLogger("app.access")
logger = logging.getLogger("app.errors")


def current_request_id() -> str | None:
    return _request_id.get()


def current_client_ip() -> str | None:
    return _client_ip.get()


def error_ref() -> str:
    """Reference shown to the user for an unexpected error."""
    return current_request_id() or uuid.uuid4().hex[:12]


# ── Logging ───────────────────────────────────────────────────

class _RequestIdFilter(logging.Filter):

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get() or "-"
        return True


_EXTRA_FIELDS = ("method", "path", "status", "duration_ms", "ip")


class JsonFormatter(logging.Formatter):

    def format(self, record: logging.LogRecord) -> str:
        body = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for field in _EXTRA_FIELDS:
            if hasattr(record, field):
                body[field] = getattr(record, field)
        if record.exc_info:
            body["exc"] = self.formatException(record.exc_info)
        return json.dumps(body, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if LOG_FORMAT == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(LOG_LEVEL)


def init_sentry() -> bool:
    if not SENTRY_DSN:
        return False
    import sentry_sdk  # optional; only needed when a DSN is configured

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=APP_ENV,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        send_default_pii=False,
        max_request_body_size="never",
    )
    return True


def _report(exc: BaseException, request_id: str) -> None:
    if not SENTRY_DSN:
        return
    import sentry_sdk

    with sentry_sdk.new_scope() as scope:
        scope.set_tag("request_id", request_id)
        sentry_sdk.capture_exception(exc)


# ── Middleware ────────────────────────────────────────────────

class RequestContextMiddleware:
    """
    Pure ASGI middleware (so the context variables reach the endpoint's thread)
    that assigns the request id, logs one access line per request and turns
    an exception nobody handled into the standard 500 body.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        rid = headers.get("x-request-id") or ""
        if not _SAFE_ID.fullmatch(rid):
            rid = uuid.uuid4().hex
        client = scope.get("client")
        ip = ip_from(headers, client[0] if client else None)
        rid_token = _request_id.set(rid)
        ip_token = _client_ip.set(ip)

        started = time.perf_counter()
        state = {"status": 500, "started": False}

        async def _send(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
                state["started"] = True
                MutableHeaders(scope=message).append("X-Request-ID", rid)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        except Exception as exc:
            logger.exception("unhandled error ref=%s path=%s", rid, scope.get("path"))
            _report(exc, rid)
            if state["started"]:
                raise
            body = json.dumps({
                "success": False,
                "detail": f"Internal server error (ref {rid}).",
                "message": f"Internal server error (ref {rid}).",
            }).encode()
            await _send({
                "type": "http.response.start",
                "status": 500,
                "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
            })
            await _send({"type": "http.response.body", "body": body})
        finally:
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            access_logger.info(
                "%s %s %s %sms", scope.get("method"), scope.get("path"), state["status"], elapsed,
                extra={"method": scope.get("method"), "path": scope.get("path"), "status": state["status"],
                       "duration_ms": elapsed, "ip": ip},
            )
            _request_id.reset(rid_token)
            _client_ip.reset(ip_token)
