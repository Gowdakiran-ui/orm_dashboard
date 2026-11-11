# Deploying to the production droplet

Target: `xoop-prod`, a single DigitalOcean droplet (`167.99.232.206`) running
the whole stack via `docker-compose.yml` in `/root/orm_dashboard` — backend,
frontend, and every Celery worker (`celery-worker-io`, `-cpu`, `-nlp`,
`-pipeline`, `-pipeline-2`, `-aggregation`, `-beat`) all run from the **same**
`orm-platform-backend:dev-review` image, built from `orm_collection`.

## The one rule that matters: recreate everything, every time

**Rebuilding the image is not enough.** `docker compose build` only produces
a new image; every already-running container still runs the *old* image
until it's individually recreated. This repo's containers are one shared
image split across many services (one orchestrator queue, several worker
queues) — if you recreate only *some* of them, the orchestrator and its
stage workers can end up running two different code versions of the same
pipeline at the same time.

This is not theoretical. It happened on 2026-09-09: a backend change added a
new pipeline stage (`AI_SUMMARY`) between `NARRATIVE` and `REPUTATION`, both
in the FSM model and in the `chain(...)` the orchestrator builds. The deploy
rebuilt the image and recreated `backend`, `frontend`, and
`celery-worker-aggregation` — but not `celery-worker-pipeline` /
`celery-worker-pipeline-2`, which is where the orchestrator task
(`run_client_pipeline`, `queue="pipeline_queue"`) actually runs. That worker
kept running the *old* image, so it built the *old* 9-stage chain (no
`AI_SUMMARY`) and told a stage worker running the *new* code to transition
`NARRATIVE → REPUTATION` directly. The new code's FSM correctly rejected
that as an illegal transition, and a real, live pipeline run failed:

```
ValueError: PipelineRun ...: illegal transition 'NARRATIVE' → 'REPUTATION'.
Allowed: {'FAILED', 'AI_SUMMARY'}
```

The fix was simply to recreate every container on the shared image. The
lesson: **never scope `docker compose up -d` to "the services I think I
changed."** Always run it with no service filter, so every container
sharing the rebuilt image restarts together, every time — regardless of
which files the change actually touched.

## Standard deploy sequence

From your local machine:

```bash
git add <changed files>
git commit -m "..."
git push origin main
```

On the droplet (`ssh -i ~/.ssh/orm_droplet_key root@167.99.232.206`, or via
`docker exec` into `orm_dashboard-backend-1` for anything that needs the
app's own DB session — see `CLAUDE.md`'s droplet section for that
convention):

```bash
cd /root/orm_dashboard
git pull
docker compose build backend frontend   # only rebuilds images that changed; harmless to include both every time
docker compose up -d                    # NO service filter -- recreates every container on any rebuilt image
docker ps --format 'table {{.Names}}\t{{.Status}}'   # confirm every container is (healthy), not just the ones you expected to touch
./scripts/verify_deploy_services.sh     # fails loudly if any defined service has no running container
```

After that passes, free the build cache: see "Free the build cache after a successful deploy" below.

If a change is backend-only (no frontend changes), `docker compose build`
still only rebuilds what actually changed — Docker's layer cache makes the
frontend build a no-op. The `up -d` step is what must never be scoped, not
the `build` step.

## Verifying after deploy

- `./scripts/verify_deploy_services.sh` — confirms every service *defined*
  in `docker-compose.yml` has a *running* container, not just that the ones
  you expected are healthy. `docker ps`/`docker compose ps` only show what
  exists, not what's missing entirely — a service that's absent (not even
  stopped) is invisible to eyeballing that output. This is what would have
  caught `celery-worker-nlp` going missing after the 2026-09-23
  disk-exhaustion recovery (see CLAUDE.md's droplet section) instead of it
  silently backing up `nlp_queue` until the next pipeline run happened to
  need it, a day later.
- `docker ps` — every container should show `healthy` (or no healthcheck
  defined, for services like `frontend` that don't have one) with a recent
  `Up` time matching the deploy, not a stale multi-hour uptime sitting next
  to freshly-recreated siblings.
- `git log --oneline -1` on the droplet should match local `HEAD`.
- Trigger one real pipeline run and watch it reach `SUCCESS`, not `FAILED`
  with an FSM transition error — that specific error shape is the signature
  of this exact partial-recreation mistake recurring.

## Free the build cache after a successful deploy

Every `docker compose build` leaves its build cache behind (measured 2026-11-11: 27.7 GB of a 48 GB disk, rebuilt by each
build and never reused, next to 8.4 GB of images). Prune it as the LAST step of a deploy, and only after
`./scripts/verify_deploy_services.sh` has passed and `docker ps` shows every container healthy:

```bash
df -h /                  # before
docker builder prune -af # build cache only: never removes an image or container that exists
df -h /                  # after: note the freed space
```

- Do not run it before verification: if the deploy has to be rolled back, the cache is what makes the rebuild fast.
- `docker builder prune` touches build cache only. It does not remove images, containers, volumes or networks, so it is safe
  while the stack is running. (Do not use `docker system prune -a` or `--volumes` here.)
- The next build is slower because it starts from an empty cache (the CPU-only torch wheel is downloaded again).
- Record the `df` figures in the deploy notes the first few times; the expected saving is about 30 GB (an estimate, not yet measured).

## Redis password and published ports

Production Redis requires a password and the three published ports are bound to the host's loopback (`127.0.0.1`):

- `.env` on the droplet holds `REDIS_PASSWORD=<hex>` (generate with `openssl rand -hex 24`; never commit it). `docker-compose.yml` starts Redis
  with `--requirepass` and gives every service `REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/0`. Keep the `REDIS_URL` line in `.env` in step
  (`redis://:<same password>@redis:6379/0`), because the frontend container, which does not use Redis, inherits it from `.env`.
- Changing the password needs the whole stack recreated (`docker compose down`, then `up -d`), like any other deploy.
- Redis, backend (8000) and frontend (3000) listen on `127.0.0.1` only. Caddy on the host proxies `api.xoop.theaicompany.co` to
  `localhost:8000` and `xoop.theaicompany.co` to `localhost:3000`; the containers reach each other by service name. For `redis-cli` from the
  host use `REDISCLI_AUTH=<password> redis-cli -h 127.0.0.1 ping`.
- Check after a deploy: `docker exec orm_dashboard-redis-1 redis-cli ping` must answer `NOAUTH Authentication required.`

## spaCy model wheel (so a GitHub outage cannot stop a build)

The backend image installs `en_core_web_sm` (spaCy 3.8, model 3.8.0). On 2026-11-09 GitHub's release download returned 504 to the
droplet for several minutes mid-deploy, with production already down. `orm_collection/Dockerfile` therefore installs the model from
`orm_collection/wheels/en_core_web_sm-3.8.0-py3-none-any.whl` when that file exists (the directory is gitignored; it is kept on the
droplet), and otherwise falls back to `spacy download` with 5 retries. To refresh it when spaCy or the model version changes:

```bash
mkdir -p /root/orm_dashboard/orm_collection/wheels
curl -L -o /root/orm_dashboard/orm_collection/wheels/en_core_web_sm-<version>-py3-none-any.whl   https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-<version>/en_core_web_sm-<version>-py3-none-any.whl
```

SHA-256 of the 3.8.0 wheel stored on 2026-11-09: `1932429db727d4bff3deed6b34cfc05df17794f4a52eeb26cf8928f7c1a0fb85`.
The wheel directory is inside the build context, so it is also copied into the image by `COPY . .` (12.8 MB).
