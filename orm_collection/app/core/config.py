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
    
    # AI Reputation Advisor Configuration (Phase 12.3)
    AI_PROVIDER: str = "groq"
    AI_MODEL: str = "llama-3.3-70b-versatile"
    AI_TIMEOUT_SECONDS: float = 30.0
    AI_MAX_RETRIES: int = 3
    AI_MAX_TOKENS: int = 4096
    
    ADVISOR_CACHE_MAX_SIZE: int = 500
    ADVISOR_CACHE_TTL_SECONDS: int = 600

    # Shared-secret API gate (Phase 1 of API_FORENSICS.md fixes) — every
    # non-health route requires this value in the X-API-Key header.
    API_SHARED_SECRET: str = ""

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
