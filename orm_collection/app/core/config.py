import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DB_HOST: str = "localhost"  # override with DB_HOST env var in production
    DB_PORT: int = 5432
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_NAME: str = "postgres"

    # Phase 5 item 21: hosted providers (RDS, Supabase, Neon, Railway, Heroku)
    # issue connection details as a single DATABASE_URL. Previously this was
    # silently discarded by extra="ignore" since Settings had no field to
    # catch it. Mapped via validation_alias (not field name "DATABASE_URL")
    # so it doesn't collide with the derived DATABASE_URL property below.
    DATABASE_URL_OVERRIDE: Optional[str] = Field(default=None, validation_alias="DATABASE_URL")

    REDIS_URL: str = "redis://localhost:6379/0"  # override with REDIS_URL env var in production

    # Per-service SQLAlchemy pool sizing (db.py). Defaults match the old
    # one-size-fits-all values (3/2) so any service without an explicit
    # override in docker-compose.yml keeps today's behavior. Every service
    # sharing this Postgres instance forks its own OS processes (Celery
    # --concurrency=N children, each with its own independent pool), so the
    # real ceiling is pool_size+max_overflow times process count, not times
    # "number of services" -- see docker-compose.yml for the per-service
    # values and the 2026-09-02/03 investigation that sized them.
    DB_POOL_SIZE: int = 3
    DB_MAX_OVERFLOW: int = 2

    # How many client pipeline runs may be active at once (any client). 1 = a new run for another client is refused with HTTP 409
    # while one is active (services/pipeline_service.py). One run peaks at about 15 of the 22 usable DB connections.
    MAX_CONCURRENT_PIPELINE_RUNS: int = 1

    # Run Pipeline limits for CLIENT users (a super admin is exempt), per client: at most one run every PIPELINE_COOLDOWN_HOURS hours and at
    # most PIPELINE_MAX_RUNS_PER_DAY runs in any rolling 24 hours (services/pipeline_service.py). A run costs Apify and LLM money, so a
    # client user cannot start one back-to-back. 0 (or less) switches that limit off. Environment: PIPELINE_COOLDOWN_HOURS, PIPELINE_MAX_RUNS_PER_DAY.
    PIPELINE_COOLDOWN_HOURS: float = 6.0
    PIPELINE_MAX_RUNS_PER_DAY: int = 3

    # Opt-in per-service override for celery-beat (see db.py): beat only ever
    # enqueues task messages via Redis on its cron schedule -- every scheduled
    # task is routed to a worker queue and executed by a worker process, never
    # by beat itself -- so a standing QueuePool allocation sits idle 100% of
    # the time. NullPool opens/closes a fresh connection per checkout instead
    # of holding any idle ones. False for every other service: they have real,
    # frequent DB usage where reusing a warm connection matters.
    DB_USE_NULLPOOL: bool = False

    # Scoring windows (days). Config, not formulas: the same engines run, only the look-back changes.
    # EXEC_WINDOW_DAYS is the executive-score window; BENCHMARK_WINDOW_DAYS is the competitor-benchmark window and is
    # used for the client and every competitor alike. Exposed to the UI as `window_days` so the page text matches.
    EXEC_WINDOW_DAYS: int = 365
    BENCHMARK_WINDOW_DAYS: int = 90

    # Seeded executives: count documents their own "Name" "Company" search returned even when the person's name is only in the article
    # body (services/seeding/attribution.py). OFF by default: the links are always recorded, but nothing is attributed or counted until
    # this is true. Measured on 24 articles read in full: all 24 name the person, 17 name the person twice or in the headline, 3 in the
    # headline; a person named once in a company-results article takes that article's sentiment, so turning this on moves scores.
    SEEDED_COUNT_SEARCH_HITS: bool = False

    # DigitalOcean-managed PgBouncer connection pool (structural fix for the
    # 2026-09-05 connection-exhaustion incident -- see db.py/docker-compose.yml
    # comments). A distinct setting, not a DATABASE_URL override: backup_tasks.py
    # shells out to `pg_dump settings.DATABASE_URL` directly (pg_dump does not
    # work against a transaction-mode PgBouncer pool per DO's own docs), so
    # DATABASE_URL itself must keep meaning "the direct connection" for every
    # caller that already reads it. Only db.py's engine consults these two.
    DATABASE_URL_POOLED: Optional[str] = None
    DB_USE_POOLED_URL: bool = False

    @property
    def CELERY_BROKER_URL(self) -> str:
        return self.REDIS_URL
        
    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return self.REDIS_URL

    S3_ENDPOINT_URL: str = "http://localhost:9000"  # override with S3_ENDPOINT_URL env var in production
    S3_ACCESS_KEY: str = "minioadmin"
    S3_SECRET_KEY: str = "minioadmin"
    S3_BUCKET_NAME: str = "orm-raw-data"
    ENABLE_S3_STORAGE: bool = True

    # Interactive API docs (/docs, /redoc) and the schema (/openapi.json) are off unless this is true. Production leaves it unset:
    # the pages are public and list every route. Set ENABLE_API_DOCS=true in a local .env when you want them.
    ENABLE_API_DOCS: bool = False
    
    # AI Reputation Advisor Configuration (Phase 12.3)
    AI_PROVIDER: str = "groq"
    AI_MODEL: str = "llama-3.3-70b-versatile"
    AI_TIMEOUT_SECONDS: float = 30.0
    AI_MAX_RETRIES: int = 3
    AI_MAX_TOKENS: int = 4096
    
    ADVISOR_CACHE_MAX_SIZE: int = 500
    ADVISOR_CACHE_TTL_SECONDS: int = 600

    # Counterfeit Detection page (on-demand deepfake + typosquat/counterfeit
    # domain scan, not a pipeline stage). Keys live only in the repo-root
    # .env (same place APIFY_API_TOKEN lives), delivered to backend/celery
    # containers via docker-compose's env_file, not orm_collection/.env.
    # Free tiers for the pilot: Reality Defender 50 scans/month, WhoisFreaks
    # 500 credits total -- unset disables the corresponding tool (same
    # "missing key -> reports itself unavailable" convention as
    # YOUTUBE_API_KEY/APIFY_API_TOKEN).
    REALITY_DEFENDER_API_KEY: Optional[str] = None
    WHOISFREAKS_API_KEY: Optional[str] = None
    BOLSTER_API_KEY: Optional[str] = None

    # Session auth (replaces the platform-wide shared-secret gate — see
    # auth.py / TASK_AUTH.md, API_FORENSICS.md Section 1). Sessions are
    # opaque tokens stored in Redis (core/security.py), handed to the
    # browser as an httpOnly cookie -- never readable by client-side JS.
    SESSION_TTL_SECONDS: int = 4 * 60 * 60  # 4 hours; re-login required after

    # Must be True in any deployment served over HTTPS -- browsers refuse to
    # send a Secure cookie over plain HTTP, so this needs to be False only
    # for local http://localhost dev (docker-compose's .env can override).
    SESSION_COOKIE_SECURE: bool = True

    # CORS — comma-separated list of allowed origins. Override with
    # CORS_ALLOWED_ORIGINS env var in production (e.g. the real dashboard
    # domain). Default covers Next.js's local dev server.
    CORS_ALLOWED_ORIGINS: str = "http://localhost:3000"

    @property
    def CORS_ALLOWED_ORIGINS_LIST(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def DATABASE_URL(self) -> str:
        # Phase 5 item 21: DATABASE_URL env var wins if set (hosted-provider
        # path); otherwise fall back to the discrete DB_HOST/etc. fields
        # (existing local-dev path, unchanged).
        if self.DATABASE_URL_OVERRIDE:
            return self.DATABASE_URL_OVERRIDE
        import urllib.parse
        encoded_password = urllib.parse.quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
