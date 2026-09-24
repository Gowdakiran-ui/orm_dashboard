#!/usr/bin/env bash
# verify_deploy_services.sh — post-deploy safeguard for xoop-prod.
#
# Confirms every service defined in docker-compose.yml actually has a
# running container after `docker compose up -d`. `docker compose ps`
# alone doesn't catch this -- it only shows what happens to exist, not
# what SHOULD exist, so a service silently missing from a scoped
# `docker compose up -d <list>` call (or dropped during an incident
# recovery that never restored it) goes unnoticed until someone notices
# a queue backing up. That's exactly what happened to celery-worker-nlp:
# it was defined in docker-compose.yml with restart:unless-stopped but
# absent from CLAUDE.md's own documented disk-exhaustion recovery
# command (2026-09-23), and nothing caught the gap until Adani Group's
# pipeline run the next day found nlp_queue with 229 unconsumed tasks
# and zero containers to read them.
#
# Run this from /root/orm_dashboard on the droplet, after every
# `docker compose up -d` (per DEPLOY.md's standard deploy sequence).
# Exits non-zero and prints the missing services if any are found --
# wire it into the deploy sequence so a missing service is a loud
# failure, not a silent one.
#
# Usage: ./scripts/verify_deploy_services.sh

set -euo pipefail

defined="$(docker compose config --services | sort)"
running="$(docker compose ps --services --status running | sort)"

missing="$(comm -23 <(echo "$defined") <(echo "$running"))"

if [ -n "$missing" ]; then
  echo "FAIL: service(s) defined in docker-compose.yml with no running container:"
  echo "$missing" | sed 's/^/  - /'
  echo
  echo "Every defined service must be running after 'docker compose up -d'."
  echo "If this is unexpected, re-run: docker compose up -d   (no service filter -- see DEPLOY.md)"
  exit 1
fi

echo "OK: all $(echo "$defined" | wc -l) defined services have a running container."
