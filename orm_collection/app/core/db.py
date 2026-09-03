from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
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
engine = create_engine(
    settings.DATABASE_URL,
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
