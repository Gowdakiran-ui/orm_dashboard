from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Phase 5 item 23: hosted providers (RDS idle timeout, Supabase/Neon pooler,
# NAT gateways at ~350s) drop idle connections. Without pool_pre_ping,
# SQLAlchemy hands out a dead connection and the next query fails with
# "server closed the connection unexpectedly". pool_recycle forces
# reconnection before providers close them from their side.
# 7 independent processes share this Postgres instance (backend + 5 split
# Celery workers + celery-beat); pool_size=3, max_overflow=2 caps each at 5
# connections (35 total across all 7) to leave headroom under small hosted-
# Postgres connection limits. Tune here if the actual provisioned limit
# (check the live instance's plan) demands otherwise.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_size=3,
    max_overflow=2,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
