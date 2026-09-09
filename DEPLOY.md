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
```

If a change is backend-only (no frontend changes), `docker compose build`
still only rebuilds what actually changed — Docker's layer cache makes the
frontend build a no-op. The `up -d` step is what must never be scoped, not
the `build` step.

## Verifying after deploy

- `docker ps` — every container should show `healthy` (or no healthcheck
  defined, for services like `frontend` that don't have one) with a recent
  `Up` time matching the deploy, not a stale multi-hour uptime sitting next
  to freshly-recreated siblings.
- `git log --oneline -1` on the droplet should match local `HEAD`.
- Trigger one real pipeline run and watch it reach `SUCCESS`, not `FAILED`
  with an FSM transition error — that specific error shape is the signature
  of this exact partial-recreation mistake recurring.
