# Pinned to bookworm (Debian 12) in both stages for consistency with the
# original single-stage image; nothing here still depends on the
# playwright/trixie package-naming issue that originally justified the pin
# (playwright's chromium install is removed below -- see note), but there's
# no reason to churn the base OS version in the same pass.
FROM python:3.11-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .

# Large deps (torch, via transformers) can hit mid-download read timeouts
# on a flaky connection; pip's own --retries doesn't cover a timeout
# mid-stream, so retry the whole install a few times before giving up. The
# explicit success flag matters here -- without it a loop whose last command
# is `sleep` exits 0 even when every install attempt failed, silently
# shipping an image with no dependencies installed.
RUN success=0; \
    for i in 1 2 3 4 5; do \
      if pip install --no-cache-dir --default-timeout=180 -r requirements.txt; then success=1; break; fi; \
      echo "pip install attempt $i failed, retrying..."; sleep 5; \
    done; \
    if [ "$success" -ne 1 ]; then echo "pip install failed after 5 attempts"; exit 1; fi

# install.bat's local install flow downloads this separately after pip
# install (see scripts/verify_environment.py's spacy check) -- the
# Dockerfile never had an equivalent step, so entity discovery
# (executive/competitor candidates) silently ran with an empty model.
RUN python -m spacy download en_core_web_sm

# AWS deployment task: grepped every .py file under orm_collection for
# playwright/chromium/Browser usage -- zero references in application code.
# `playwright install --with-deps chromium` was pulling in Chromium plus its
# full apt dependency tree (fonts, GTK, NSS, etc.) into every one of the 8
# services built from this image for a feature nothing calls. Dropped
# entirely rather than moved to "the one worker that needs it," since no
# worker needs it. If a future feature (e.g. JS-rendered page scraping)
# starts using playwright, re-add `RUN playwright install --with-deps
# chromium` here (or better, only in a dedicated service's image) at that
# point.

# ---------------------------------------------------------------------------

FROM python:3.11-slim-bookworm AS runtime

# All secrets (DATABASE_URL, session cookie config, etc.) are injected at
# container runtime via env_file/--env-file, ECS task-definition secrets, or
# the hosting platform's own secrets mechanism -- never baked into the image.
LABEL org.opencontainers.image.description="ORM Intelligence Platform backend"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# postgresql-client provides pg_dump/pg_restore, used by
# app/workers/backup_tasks.py -- needed at runtime (not just build time) so
# it stays in the final image, unlike the builder-only compile toolchain
# that stops here with the slim base. libgomp1 is torch's OpenMP runtime
# dependency (`import torch` fails with "libgomp.so.1: cannot open shared
# object file" without it) -- present transitively on the non-slim bookworm
# base the single-stage image used to run on, but debian-slim strips it, so
# it needs to be explicit now that the runtime stage is slim. curl is used
# by docker-compose.yml's backend healthcheck (`curl -f localhost:8000/health`)
# -- debian-slim ships neither curl nor wget, so that healthcheck was
# unconditionally failing with "executable file not found in $PATH" on
# every single check, forever reporting the container unhealthy regardless
# of whether the app was actually up (confirmed live: /health returned a
# real 200 from inside the container the whole time). Every other service
# in docker-compose.yml has `depends_on: backend: condition:
# service_healthy`, so this alone blocked the entire local stack from ever
# starting.
#
# Debian bookworm's own `postgresql-client` meta-package resolves to pg_dump
# 15.x, but the real DB (both the live Render instance and this project's
# local docker-compose.override.local.yml) is Postgres 18 -- see
# database/schema.sql's own header ("Dumped by pg_dump version 18.6"). A
# pg_dump older than its target server errors out and fails run_backup
# (celery_app.py's daily beat schedule) every single run. pg_dump generally
# needs to be >= the server's major version, so pull the matching
# postgresql-client-18 from the official PGDG apt repo instead of bookworm's
# default.
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-18 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user. /backups is created (not just chowned) here so
# that when docker-compose's backup_data named volume (or an EFS/ephemeral
# mount in ECS) is first mounted over this path, it inherits this
# directory's ownership instead of defaulting to root -- otherwise
# BACKUP_DIR.mkdir()/pg_dump -f in backup_tasks.py would fail with
# Permission denied as a non-root user.
RUN groupadd --system appuser && useradd --system --gid appuser --home-dir /app --shell /usr/sbin/nologin appuser \
    && mkdir -p /backups \
    && chown -R appuser:appuser /app /backups

COPY --from=builder /opt/venv /opt/venv
COPY . .

# FinBERT and distilbart-mnli-12-3 (app/services/intelligence/
# sentiment_analyzer.py, topic_classifier.py) were never pre-downloaded here,
# unlike en_core_web_sm above -- transformers.pipeline(..., model=...) lazily
# pulled both from the HuggingFace Hub on first use inside whichever
# container happened to run first, measured live at ~300s for that first
# document (forensic audit, Stage 5) versus ~11-13s once cached. HF_HOME is
# set under /app so the final chown below (which already covers the rest of
# /app) hands this cache to appuser too, and so it's a real directory this
# non-root user can read at runtime instead of defaulting to root's own home.
# Same retry-on-flaky-connection reasoning as the pip install step above.
# HF_HUB_OFFLINE is intentionally NOT set yet here -- this download step
# needs real Hub access. It's set right after, once the cache below is
# populated, so it never applies to this RUN itself.
ENV HF_HOME=/app/.cache/huggingface
RUN success=0; \
    for i in 1 2 3 4 5; do \
      if python -c "from transformers import pipeline; pipeline('sentiment-analysis', model='ProsusAI/finbert'); pipeline('zero-shot-classification', model='valhalla/distilbart-mnli-12-3')"; then success=1; break; fi; \
      echo "HF model pre-download attempt $i failed, retrying..."; sleep 5; \
    done; \
    if [ "$success" -ne 1 ]; then echo "HF model pre-download failed after 5 attempts"; exit 1; fi

# Forces transformers.pipeline()/from_pretrained() to read only from the
# cache just populated above and never attempt the Hub freshness HEAD-check
# `from_pretrained` otherwise makes on every call (confirmed live -- without
# this, first-load still made a real network request even with the cache
# warm, defeating "no runtime network dependency", the reason baking was
# chosen over a persistent HF-cache volume in the first place). Deliberately
# set AFTER the download RUN above, not combined with HF_HOME's ENV, so it
# never applies to that RUN itself.
ENV HF_HUB_OFFLINE=1

RUN chmod +x entrypoint.sh && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["./entrypoint.sh"]
CMD ["sh", "-c", "python scripts/bootstrap_schema.py && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
