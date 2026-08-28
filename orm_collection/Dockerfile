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
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client libgomp1 curl \
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

RUN chmod +x entrypoint.sh && chown -R appuser:appuser /app

USER appuser

ENTRYPOINT ["./entrypoint.sh"]
CMD ["sh", "-c", "python scripts/bootstrap_schema.py && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
