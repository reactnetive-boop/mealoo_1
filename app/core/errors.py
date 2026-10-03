"""
Error handling.

Business-rule failures raise DomainError (or HTTPException) with a message
that is safe to show to the user. Anything unexpected becomes a generic 500:
stack traces, SQL and exception text stay in the server log only.
"""

import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = logging.getLogger("app.errors")


class DomainError(Exception):
    """A business rule was violated; `message` is shown to the caller."""

    def __init__(self, message: str, status_code: int = 400, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _body(detail, code: str | None = None):
    body = {"success": False, "detail": detail}
    if isinstance(detail, str):
        body["message"] = detail
    if code:
        body["code"] = code
    return body


def install_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content=_body(exc.message, exc.code))

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException):
        detail = exc.detail
        code = None
        if isinstance(detail, dict):
            code = detail.get("code")
            detail = detail.get("message") or detail.get("detail") or "Request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(detail, code),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        # Echo field locations and messages, never the submitted values
        # (they can contain passwords).
        errors = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", "Invalid value"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"success": False, "detail": errors})

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        ref = uuid.uuid4().hex[:12]
        logger.warning("integrity error ref=%s path=%s: %s", ref, request.url.path, exc.orig)
        return JSONResponse(
            status_code=409,
            content=_body(f"The request conflicts with existing data (ref {ref})."),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db(request: Request, exc: SQLAlchemyError):
        ref = uuid.uuid4().hex[:12]
        logger.exception("database error ref=%s path=%s", ref, request.url.path)
        return JSONResponse(status_code=500, content=_body(f"Internal server error (ref {ref})."))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        ref = uuid.uuid4().hex[:12]
        logger.exception("unhandled error ref=%s path=%s", ref, request.url.path)
        return JSONResponse(status_code=500, content=_body(f"Internal server error (ref {ref})."))
