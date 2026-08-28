"""Security response headers (API_FORENSICS.md Section 9) — separate from
CORSMiddleware (already correct, untouched) and the rate limiter. Applied
via a plain ASGI-style Starlette middleware function, no new dependency:
FastAPI/Starlette already let you mutate response.headers directly.

This is a pure JSON API, so the CSP can be strict (default-src 'none') --
except /docs and /redoc, which render FastAPI's Swagger/ReDoc HTML pages
and pull JS/CSS from a CDN. Those two get no CSP header at all rather than
a loosened one, so a future docs-UI change can't silently start violating a
policy nobody's watching. /openapi.json stays under the strict policy --
it's inert JSON, not something a browser renders.
"""
from starlette.requests import Request
from starlette.responses import Response

_DOCS_PATHS = {"/docs", "/redoc"}

_CSP = "default-src 'none'"


async def add_security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    # Meaningful only over HTTPS; a browser ignores it over plain HTTP, so
    # it's safe to set unconditionally rather than branching on scheme.
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    if request.url.path not in _DOCS_PATHS:
        response.headers["Content-Security-Policy"] = _CSP

    return response
