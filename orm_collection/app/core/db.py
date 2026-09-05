from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool
from app.core.config import settings

# Phase 5 item 23: hosted providers (RDS idle timeout, Supabase/Neon pooler,
# NAT gateways at ~350s) drop idle connections. Without pool_pre_ping,
# SQLAlchemy hands out a dead connection and the next query fails with
# "server closed the connection unexpectedly". pool_recycle forces
# reconnection before providers close them from their side.
#
# pool_size/max_overflow are per-service now (DB_POOL_SIZE/DB_MAX_OVERFLOW
# env vars, set per service in docker-compose.yml), not a single shared
# 3/2 for everyone. The old uniform value undercounted the real ceiling:
# each Celery worker forks --concurrency=N child processes, and each child
# independently gets its own pool -- the true total across all services is
# pool_size(+overflow) times *process* count, not times *service* count.
# 2026-09-02/03 investigation found this already exceeded the DB's real
# max_connections=25 even at steady state (idle, no load). Sized per
# service by real DB usage (celery-worker-io is I/O-bound against external
# feeds, barely touches the DB despite having the most processes;
# celery-beat's schedule is pure in-memory Python, effectively zero DB
# use) -- see docker-compose.yml for the actual per-service values.
# Right-sizing alone does not guarantee staying under 25 in a genuine
# worst-case burst across every service at once; PgBouncer or a DB plan
# upgrade is the structural fix if that's still not enough headroom.
# DB_USE_NULLPOOL (celery-beat only, see config.py): NullPool's constructor
# doesn't accept pool_size/max_overflow (TypeError if passed) -- it opens a
# fresh connection per checkout and holds none idle, so those args are
# meaningless for it anyway. pool_pre_ping/pool_recycle are base-Pool params
# both classes accept -- confirmed against this project's installed
# SQLAlchemy 2.0.25 via a throwaway sqlite:// engine before wiring this in.
#
# DB_USE_POOLED_URL (2026-09-05, the structural fix named above): routes this
# service's engine through DigitalOcean's managed PgBouncer connection pool
# (DATABASE_URL_POOLED) instead of connecting to Postgres directly. Deliberately
# NOT a change to DATABASE_URL itself -- backup_tasks.py's pg_dump call reads
# settings.DATABASE_URL directly and must keep hitting the real Postgres port,
# since pg_dump doesn't work against a transaction-mode PgBouncer pool. Only
# set true on services whose real, frequent per-query DB usage benefits from
# pool multiplexing (backend, celery-worker-cpu/nlp/aggregation) -- see
# docker-compose.yml for which services opt in.
_engine_url = (
    settings.DATABASE_URL_POOLED
    if settings.DB_USE_POOLED_URL and settings.DATABASE_URL_POOLED
    else settings.DATABASE_URL
)

if settings.DB_USE_NULLPOOL:
    engine = create_engine(
        _engine_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
else:
    engine = create_engine(
        _engine_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
