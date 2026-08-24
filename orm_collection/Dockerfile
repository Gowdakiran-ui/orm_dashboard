# Pinned to bookworm (Debian 12), not floating `python:3.11` (currently
# resolves to Debian 13 "trixie"): playwright==1.41.2's `--with-deps`
# package list predates trixie and references font packages
# (ttf-unifont/ttf-ubuntu-font-family) that trixie renamed/dropped, which
# broke `playwright install --with-deps chromium` with no relation to any
# change in this task. bookworm still has the packages under the names
# this playwright version expects.
FROM python:3.11-bookworm

# DEV-ONLY IMAGE (see TASK.md — Dockerize for Frictionless Reviewer
# Handoff). This bakes in the dev .env, including live Render DB
# credentials, for frictionless reviewer handoff. Never reuse this pattern
# for a production image, and never push this image to a public registry.
LABEL org.opencontainers.image.description="ORM Intelligence Platform backend — DEV-ONLY, contains baked-in dev credentials. Not for production use." \
      dev.orm-platform.dev-only="true"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

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

RUN playwright install --with-deps chromium

COPY . .

# .dockerignore normally excludes .env — explicitly un-excluded there for
# this dev-review image only. entrypoint.sh sources it into the real
# process environment before exec'ing whatever command runs (uvicorn by
# default, or a celery worker/beat command override from docker-compose).
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

CMD ["sh", "-c", "python scripts/bootstrap_schema.py && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
