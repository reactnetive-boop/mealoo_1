"""HTTP hardening: security headers and request size limits."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import MAX_REQUEST_BYTES, IS_PRODUCTION


class SecurityHeadersMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")

        path = request.url.path
        if path.startswith("/uploads/"):
            # User-supplied files: never let a browser execute them
            headers.setdefault("Content-Security-Policy", "default-src 'none'; img-src 'self'; sandbox")
        elif not path.startswith(("/docs", "/redoc")):
            headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            # API responses carry personal / financial data
            headers.setdefault("Cache-Control", "no-store")

        if IS_PRODUCTION:
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length is not None:
            try:
                too_big = int(length) > MAX_REQUEST_BYTES
            except ValueError:
                return JSONResponse(status_code=400, content={"success": False, "detail": "Invalid Content-Length"})
            if too_big:
                return JSONResponse(
                    status_code=413,
                    content={"success": False, "detail": "Request body too large"},
                )
        return await call_next(request)


def install_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
