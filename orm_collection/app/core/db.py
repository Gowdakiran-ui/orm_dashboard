from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

# Phase 5 item 23: hosted providers (RDS idle timeout, Supabase/Neon pooler,
# NAT gateways at ~350s) drop idle connections. Without pool_pre_ping,
# SQLAlchemy hands out a dead connection and the next query fails with
# "server closed the connection unexpectedly". pool_recycle forces
# reconnection before providers close them from their side.
engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
