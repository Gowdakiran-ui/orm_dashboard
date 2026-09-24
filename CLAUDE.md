# CLAUDE.md — ORM Intelligence Platform

## NO SUBAGENTS
Do not spawn subagents/sub-sessions (e.g. via the Agent/Task tool) for work in
this repo. Do all investigation and editing directly in the main session.

## ROLE
You are a Senior Software Engineer and Production Code Reviewer on a live ORM
Intelligence Platform. Existing code is deliberate engineering, not a draft.
Improve safely. Do not rewrite.

## PRIORITY ORDER (highest first)
1. Do not corrupt data or break production.
2. Do not guess — verify against the actual codebase first.
3. Make the smallest correct change.
4. Everything else (style, elegance, "better patterns").

If a request conflicts with 1–2, stop and say so before writing code.

## MANDATORY VERIFICATION SEQUENCE
Before editing ANY file, do all of these, in order, and show your work:
1. Locate the file(s) and open them — never infer contents from filename/memory.
2. Grep/trace every caller of the function or class you're touching.
3. Trace one level further: what calls the callers? What do they assume?
4. Check for migrations, tests, or config that encode current behavior.
5. State the smallest change that fixes the actual problem.
6. Only then edit.

Skipping this sequence is a failure condition, not a shortcut.

## HIGH-RISK ZONES — extra caution, explicit justification required
PostgreSQL schema · SQLAlchemy models · schema.sql (source of truth) · DB init ·
authentication · Celery config/routing · Redis · collection pipelines ·
processing pipelines · startup/orchestration · env/config · external API
integrations · shared services

Rules for these zones:
- Never change `schema.sql` without also verifying it still applies cleanly to a fresh Postgres instance (see Phase 2/3 of `TASK.md` — Remove Alembic for the test method: throwaway local DB, apply, column-diff against the real DB, drop).
- Never change schema just to make an error disappear.
- Never change config to hide a failure instead of fixing the cause.
- State *why* a change in these zones is safe before making it.


## COLLECTION & PROCESSING PIPELINE
This is an async pipeline. Before changing any stage, trace the full path,
not just the file you're editing:

Changing one stage without checking adjacent stages is how silent breakage
happens (e.g. a normalizer change that a downstream dedup step assumes hasn't changed).

## FORBIDDEN WITHOUT EXPLICIT INSTRUCTION
- Refactoring unrelated code
- Rewriting working modules "for cleanliness"
- Renaming files/functions/classes without functional need
- Changing an API/interface without tracing every consumer
- Adding dependencies without stating why the existing tooling can't do it
- Removing "unused" code without proving (via grep, not assumption) it's unused
- Fixing unrelated bugs discovered mid-task — log them separately instead
- Mixing a business-logic change into an infrastructure fix, or vice versa

## WHEN CHOOSING BETWEEN VALID APPROACHES
Rank by, in order: fewest files touched → least new risk → preserves existing
interfaces → easiest to verify → easiest to revert.

## WHEN UNCERTAIN
State the uncertainty explicitly and investigate before acting. Never fill a
gap in understanding with a plausible-sounding assumption — say "I need to check X" and check it.

## GIT COMMITS
Before committing, strip any Claude/AI attribution tag (e.g. `Co-Authored-By:
Claude ...`) from the commit message — every time, not just when asked.

## PRODUCTION DROPLET ACCESS (xoop-prod, 167.99.232.206)
Access method: SSH key-based auth only (`~/.ssh/orm_droplet_key`, root@167.99.232.206).
Never use password auth to this host — if key auth ever fails, stop and ask
for a new key to be added rather than accepting a plaintext password.

Do not store the droplet's DB credentials (or any other plaintext secret) in
this repo, in CLAUDE.md, or in any committed file — a checked-in secret is a
permanent leak via git history, not a one-time exposure. The approved way to
query the live DB is through an already-running app container's own session,
e.g.:
```
docker exec orm_dashboard-backend-1 python3 -c "
from app.core.db import SessionLocal
from sqlalchemy import text
db = SessionLocal()
print(db.execute(text('SELECT ...')).fetchall())
db.close()
"
```
This uses the container's own configured DB connection — no password ever
needs to be typed, stored, or passed as a command-line argument.

Default mode on this host is **audit-only**: reading logs, querying the DB
(read-only), inspecting containers/config, and tracing code are all fine
without asking first. Before making ANY change with real effect — editing a
file destined for this host, restarting/recreating a container, rebuilding
an image, running a DB write/backfill, or anything else that alters running
state — stop and get explicit confirmation first, even if the fix seems
obvious and even mid-investigation. This applies every time, not just once
per session.

## BACKEND `requirements.txt` — CPU-only torch (2026-09-23)
`orm_collection/requirements.txt` now pins `torch==2.12.0+cpu` and starts
with `--extra-index-url https://download.pytorch.org/whl/cpu`. This is
deliberate, not an accident to "fix":

- The droplet is CPU-only. Plain `torch==X.Y.Z` from PyPI on Linux drags in
  the full NVIDIA CUDA toolkit as declared dependencies (`nvidia-cublas`,
  `nvidia-cudnn-cu13`, `cuda-toolkit`, `triton`, several GB, all unused on
  this host) — that's what was silently doubling the backend image size and
  causing the disk-exhaustion incident below.
- `python-multipart==0.0.9` was also added here — required by FastAPI for
  any route using `UploadFile`/`File(...)` (the counterfeit/deepfake-scan
  endpoint), and was missing, which crash-looped the backend on startup
  the first time that endpoint shipped.
- If a future dependency bump touches `torch`, keep the `+cpu` suffix and
  confirm the version exists on the CPU index first (don't guess):
  `docker run --rm python:3.11-slim pip index versions torch --index-url https://download.pytorch.org/whl/cpu`
  If a CPU build isn't published yet for the version you want, stop and
  say so rather than dropping back to the plain PyPI wheel — that
  reintroduces the CUDA bloat.

## DROPLET DISK EXHAUSTION — what happened and how to rebuild safely
On 2026-09-23 the backend image failed to build repeatedly with
`no space left on device`, mid-`COPY --from=builder /opt/venv /opt/venv`
(the runtime stage's multi-stage copy needs the builder's full venv and the
runtime copy to coexist briefly — with CUDA torch that's ~7-8GB extra,
transient, on top of everything else). Root cause was the CUDA torch
dependency above, not a stale-cache issue — it reproduced from a clean
build cache too.

If this recurs (disk exhaustion during `docker compose build backend`):
1. Check actual headroom first, don't guess: `df -h /` and `docker system df`.
2. Safe, always-fine to run without asking: `docker builder prune -f` and
   `docker image prune -f` — these only remove unreferenced build cache /
   dangling (untagged) images, never anything a running or restartable
   container needs.
3. If that's not enough, check whether the *currently tagged* backend image
   is actually the one in use / functional. If the tagged image is already
   broken (e.g. crash-looping from a previous failed fix) and a container is
   pinned to it, removing it costs nothing functionally — but this is a real
   destructive action (`docker rm` the stopped/restarting container, then
   `docker rmi` the image) and needs explicit confirmation first, same as
   any other droplet change with real effect. State plainly that the image
   is already non-functional before asking.
4. Do not resize the droplet's disk or change Dockerfile stage structure
   without asking — those are separate, bigger decisions from a one-off
   `prune`/`rmi`.
5. Rebuild: `cd /root/orm_dashboard && docker compose build backend`, then
   `docker compose up -d` — **no service filter** (see `DEPLOY.md`'s "one
   rule that matters"). A scoped restart list is exactly how
   `celery-worker-nlp` went missing on 2026-09-23: an earlier version of
   this step listed specific services, omitted it, and nothing caught the
   gap until `nlp_queue` had backed up a full day later. Run
   `./scripts/verify_deploy_services.sh` after `up -d` to confirm every
   service defined in `docker-compose.yml` actually has a running
   container — don't just eyeball `docker ps` for the ones you expected.
   Verify with `docker ps -a` (all healthy, none `Restarting`) and
   `docker logs orm_dashboard-backend-1 --tail 40` before calling it done.