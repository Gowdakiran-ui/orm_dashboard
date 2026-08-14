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
from app.core.config import settings
from app.core.db import SessionLocal, get_db
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS_LIST,
    allow_credentials=False,
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

from app.api.endpoints import clients, entities, sources, matching, feeds, documents, collection, search, client_intelligence, alerts, intelligence
from app.core.auth import verify_api_key

_auth = [Depends(verify_api_key)]

app.include_router(clients.router, prefix="/clients", tags=["clients"], dependencies=_auth)
app.include_router(entities.router, prefix="/entities", tags=["entities"], dependencies=_auth)
app.include_router(sources.router, prefix="/sources", tags=["sources"], dependencies=_auth)
app.include_router(matching.router, prefix="/matching", tags=["matching"], dependencies=_auth)
app.include_router(feeds.router, prefix="/feeds", tags=["feeds"], dependencies=_auth)
app.include_router(documents.router, prefix="/documents", tags=["documents"], dependencies=_auth)
app.include_router(collection.router, prefix="/collection", tags=["collection"], dependencies=_auth)
app.include_router(search.router, prefix="/search", tags=["search"], dependencies=_auth)
app.include_router(client_intelligence.router, prefix="/client-intelligence", tags=["client_intelligence"], dependencies=_auth)
app.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"], dependencies=_auth)
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"], dependencies=_auth)

@app.get("/health")
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
    return health_status

