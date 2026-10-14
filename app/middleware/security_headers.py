from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Injects defensive security headers into all outgoing responses
    to prevent MIME-confusion attacks, clickjacking on outer views,
    and enforce strict referrer privacy.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        # Basic browser defense headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Allow /browser to embed iframes, but protect the outer application frame
        if not request.url.path.startswith("/proxy"):
            response.headers["X-Frame-Options"] = "SAMEORIGIN"

        return response