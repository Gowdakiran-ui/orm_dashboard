import structlog
import logging
from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
import uuid
import time
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from prometheus_client import REGISTRY
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.db import SessionLocal, get_db
from app.core.metrics import CeleryTaskCounterCollector
from app.core.rate_limit import limiter
from app.core.security_headers import add_security_headers
from app.services.matching_engine import engine_instance
from app.core.pubsub import start_pubsub_listener

# Configure structlog
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load the global matching engine.
    # Phase 5 item 25: a DB hiccup here previously propagated out of
    # lifespan and killed the whole uvicorn process before it could ever
    # serve /health. Degrade gracefully instead, matching the pattern
    # already used for the Redis listener below (pubsub.py) — the engine
    # stays unloaded (engine_instance.is_loaded stays False, surfaced via
    # /health) and refresh_processor's other callers (endpoints, tasks)
    # can still populate it once the DB recovers.
    db = SessionLocal()
    try:
        engine_instance.refresh_processor(db)
    except Exception as e:
        logger.error("Failed to load matching engine at startup; continuing degraded", error=str(e))
    finally:
        db.close()

    # Start Redis Pub/Sub listener for keyword updates
    start_pubsub_listener()
    
    logger.info("Application started up successfully.")
    yield
    # Shutdown logic if any

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ORM Collection Layer API", lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS_LIST,
    # Real auth now runs on an httpOnly session cookie (core/auth.py)
    # instead of a header-carried shared secret, so the browser needs to be
    # allowed to send it cross-origin (dashboard on :3000, API on :8000).
    # Safe with a non-wildcard origin list (CORS_ALLOWED_ORIGINS_LIST above).
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "status": 500}
    )

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status": exc.status_code}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": str(exc.errors()), "status": 422}
    )

@app.middleware("http")
async def structlog_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    client_id = None
    parts = request.url.path.split("/")
    for i, part in enumerate(parts):
        if part in ["client", "client-intelligence"] and i + 1 < len(parts):
            potential_id = parts[i+1]
            if len(potential_id) > 10:  
                client_id = potential_id
            break

    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
    except Exception as e:
        status_code = 500
        raise e
    finally:
        latency_ms = (time.time() - start_time) * 1000
        
        log_data = {
            "request_id": request_id,
            "endpoint": request.url.path,
            "method": request.method,
            "latency_ms": round(latency_ms, 2),
            "status_code": status_code,
        }
        if client_id:
            log_data["client_id"] = client_id
            
        if status_code >= 400:
            log_data["error_type"] = "client_error" if status_code < 500 else "server_error"
            
        if latency_ms > 500:
            logger.warning("Slow request", **log_data)
        else:
            logger.info("Request processed", **log_data)
            
    return response

from app.api.endpoints import clients, entities, sources, matching, feeds, documents, collection, search, client_intelligence, alerts, intelligence, auth as auth_endpoints, admin_users
from app.core.auth import get_current_user, require_client_access, require_super_admin

_auth = [Depends(get_current_user)]
_super_admin_only = [Depends(require_super_admin)]

# Routers where every route exposes client_id as a path or query param get
# an extra router-level tenant-authorization check for free (require_client_access
# resolves client_id from wherever that router's routes already declare it).
# clients.py and entities.py are NOT here -- their client_id shows up as a
# request-body field (onboarding, entity create) or only indirectly via a
# looked-up entity, so they check access explicitly inside the endpoint
# instead (see those files).
_auth_and_client = _auth + [Depends(require_client_access)]

app.include_router(auth_endpoints.router, prefix="/auth", tags=["auth"])
app.include_router(admin_users.router, prefix="/admin/users", tags=["admin_users"], dependencies=_super_admin_only)
app.include_router(clients.router, prefix="/clients", tags=["clients"], dependencies=_auth)
app.include_router(entities.router, prefix="/entities", tags=["entities"], dependencies=_auth)
app.include_router(sources.router, prefix="/sources", tags=["sources"], dependencies=_auth)
app.include_router(matching.router, prefix="/matching", tags=["matching"], dependencies=_auth)
app.include_router(feeds.router, prefix="/feeds", tags=["feeds"], dependencies=_auth)
app.include_router(documents.router, prefix="/documents", tags=["documents"], dependencies=_auth_and_client)
app.include_router(collection.router, prefix="/collection", tags=["collection"], dependencies=_auth)
app.include_router(search.router, prefix="/search", tags=["search"], dependencies=_auth)
app.include_router(client_intelligence.router, prefix="/client-intelligence", tags=["client_intelligence"], dependencies=_auth_and_client)
app.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"], dependencies=_auth_and_client)
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"], dependencies=_auth_and_client)

# Request count/latency/in-progress gauges (API_FORENSICS.md Section 3).
# excluded_handlers keeps /metrics itself out of its own request counters.
REGISTRY.register(CeleryTaskCounterCollector())
Instrumentator(
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],
).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# Same rate-limit exemption treatment as /health below -- a scrape target
# shouldn't be able to 429 itself out, and Prometheus polls far more often
# than the global per-IP limit allows. expose() registers the route via its
# own internal @app.get(...), so there's no local function to decorate;
# grab the live route's endpoint and exempt that instead.
for _route in app.routes:
    if getattr(_route, "path", None) == "/metrics":
        limiter.exempt(_route.endpoint)
        break


@app.get("/health")
@limiter.exempt
def health_check(db: Session = Depends(get_db)):
    health_status = {"status": "ok", "db": "ok", "redis": "ok"}
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
    except Exception as e:
        health_status["db"] = "failed"
        health_status["status"] = "degraded"
        logger.error("DB health check failed", error=str(e))

    try:
        from app.utils.redis_client import redis_client
        redis_client.ping()
    except Exception as e:
        health_status["redis"] = "failed"
        health_status["status"] = "degraded"
        logger.error("Redis health check failed", error=str(e))

    health_status["db_host"] = settings.DB_HOST
    health_status["engine_loaded"] = engine_instance.is_loaded

    # Every caller that matters here (docker-compose's `curl -f`, an ALB/
    # Render HTTP health check) gates on HTTP status, not response body --
    # this endpoint always returned 200 even when "status": "degraded" was
    # in the body, so a DB or Redis outage was invisible to any real health
    # check and would never trigger a restart. 503 makes degraded actually
    # observable at the status-code level other checks rely on.
    status_code = 200 if health_status["status"] == "ok" else 503
    return JSONResponse(status_code=status_code, content=health_status)


# Wraps the whole app (rather than app.add_middleware/app.middleware("http"))
# so it also covers the generic-Exception handler above: FastAPI installs
# that handler into Starlette's ServerErrorMiddleware, which
# build_middleware_stack() always places OUTSIDE every add_middleware-
# registered middleware -- so a raw unhandled exception's 500 response would
# otherwise skip this middleware and go out with no security headers at all.
from starlette.middleware.base import BaseHTTPMiddleware

app = BaseHTTPMiddleware(app, dispatch=add_security_headers)

