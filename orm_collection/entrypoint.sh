#!/bin/sh
# Dev-review image only (see TASK.md — Dockerize for Frictionless Reviewer
# Handoff): the image bakes in a dev .env for a self-contained docker-run
# experience. This sources it into the real process environment before
# exec'ing the actual command, so raw os.environ.get() lookups (e.g. the
# Groq key in app/services/ai/advisor/llm_providers.py) work the same way
# docker-compose's own `env_file:` directive already does today, not just
# pydantic-settings' own .env parsing (which only populates declared
# Settings fields, not os.environ).
# Baked .env values are FALLBACK DEFAULTS only -- any variable
# docker-compose already injected (e.g. REDIS_URL=redis://redis:6379/0,
# DB_HOST=db -- the real in-network hostnames) must win over the baked
# .env's own localhost-oriented values. Blindly `. .env`-sourcing here
# would silently clobber those with the wrong host, breaking Celery/DB
# connectivity while looking like a healthy container.
if [ -f /app/.env ]; then
    while IFS='=' read -r key value; do
        case "$key" in
            ''|'#'*) continue ;;
        esac
        eval "already_set=\${${key}+set}"
        if [ -z "$already_set" ]; then
            export "$key=$value"
        fi
    done < /app/.env
fi
exec "$@"
