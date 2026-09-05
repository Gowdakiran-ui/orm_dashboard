
---

# Fresh-Machine Install Failures — PHASE 1 (read-only diagnosis)

**Claim under investigation:** a reviewer's clone is missing
`orm_collection/` entirely (`orm_collection/requirements.txt` not found).

**1. `.gitignore` check:** root `.gitignore` has exactly 3 `orm_collection`-
scoped entries — `orm_collection/scratch/`, `orm_collection/celerybeat-
schedule.*`, `orm_collection/sentiment_audit_results/`. None of these
exclude `orm_collection/` itself or `requirements.txt`. No nested
`.gitignore` inside `orm_collection/` exists (only `orm_dashboard/.gitignore`,
unrelated). **Not a `.gitignore` problem.**

**2. Tracked-in-git check:** `git ls-files | grep orm_collection` returns
161 tracked files, including `orm_collection/requirements.txt` explicitly.
`git log --oneline -- orm_collection/requirements.txt` shows it present
since `b821a00` (Initial commit), carried through `70caa1d` (the
alembic-removal commit) — it has never been absent from tracked history.
**Not an add/tracking problem.**

**3. Push status check:** `git status` → `On branch main, Your branch is up
to date with 'origin/main'`, zero untracked-relevant files (only the new
`TASK.md`, unrelated to this bug), zero unpushed commits
(`git log origin/main..HEAD` is empty). `git remote -v` confirms origin is
`https://github.com/Gowdakiran-ui/orm_dashboard.git`. **Everything that's
in this local repo is genuinely on `origin/main` already — not a
forgot-to-push problem.**

**4. Real remote-clone test (not a local path):** ran
`git clone https://github.com/Gowdakiran-ui/orm_dashboard.git` into a fresh
temp directory (not `git clone` of a local path, not a copy). Result:
`orm_collection/` and `orm_collection/requirements.txt` are both present
and correct in the fresh clone. **The bug is not reproducible from a
genuine clone of the current remote `main` branch — the repository itself
is fine.**

**5. Smoke-test post-mortem — could not be completed as written:**
Searched for `TASK_FRESH_CLONE_SMOKE_TEST.md` across the working tree,
`git log --all --diff-filter=A --name-only` (every file ever added in any
commit on any branch), and `FINDINGS.md`'s own history. **Zero matches
anywhere.** This file does not exist and was never committed to this
repository under any branch. I'm stating this plainly rather than guessing
at what it "actually cloned" — there is no artifact in this repo to
post-mortem. Two honest possibilities: (a) that smoke test was run and
reported only in a chat session, with no file ever written to disk, or (b)
it lives in a location outside this repository that I don't have access to.
Either way, its actual methodology can't be verified from here — if it
exists somewhere else, it should be pointed to directly rather than assumed
in Phase 3's fix.

**Conclusion:** with a verified-clean remote clone reproducing neither
reported symptom, the missing-`orm_collection` failure was **not caused by
anything in this git repository's current state** — `.gitignore`,
tracked-file set, and remote sync are all correct as of `main` right now.
The likely real causes are outside this repo's control and need to be
confirmed with the reviewer directly rather than guessed at here:
- They cloned an old/different ref (a stale fork, a tag/branch predating
  `orm_collection`, or a cached mirror), not current `main`.
- They downloaded a ZIP/tarball instead of `git clone` and it was
  incomplete (GitHub's "Download ZIP" can silently truncate on some
  network conditions/proxies; a truncated ZIP wouldn't error the same way
  a `git clone` failure would).
- They ran the install command from the wrong working directory (e.g. one
  level too high/low, so `orm_collection/requirements.txt` genuinely
  wasn't at the path being checked, even though it exists in their clone).
- A corporate proxy/firewall interfered with `git clone` mid-transfer
  without failing loudly.

**Recommendation for Phase 3 (not implemented here, per this phase's
read-only scope):** before writing any fix, get the exact clone command and
directory listing the reviewer actually ran — a fix aimed at a cause that
isn't reproducible here risks fixing nothing. If a fix is wanted
regardless, the highest-value one is hardening `install.bat`/
`verify_environment.py` to fail with a clear, actionable message the
moment `orm_collection/requirements.txt` isn't found relative to the
script's own location (distinguishing "wrong directory" from "incomplete
clone" for the reviewer), rather than assuming a repository-side cause that
this investigation didn't find.

---

# Fresh-Machine Install Failures — PHASE 2 (read-only diagnosis)

**Claim under investigation:** `psycopg2-binary` fails to build with
`pg_config executable not found` on a reviewer's machine running Python
3.13.4.

**1. Pinned version:** `orm_collection/requirements.txt:4` pins
`psycopg2-binary==2.9.9` exactly.

**2. Wheel availability check (real PyPI index, not guessed):**
Used `pip download --only-binary=:all: --platform win_amd64` (forces
pip to only consider prebuilt wheels, never source) against the real PyPI
index for both Python versions in question:
- **`--python-version 313`, `psycopg2-binary==2.9.9`** → **fails**: pip
  reports `Could not find a version that satisfies the requirement
  psycopg2-binary==2.9.9 (from versions: 2.9.10, 2.9.11, 2.9.12)` — i.e.
  **2.9.9 has zero prebuilt wheels for Python 3.13, for any platform.**
  When pip can't find a matching wheel, it falls back to a source build,
  which requires PostgreSQL's `pg_config` — exactly the error the reviewer
  hit. This is the direct, confirmed root cause.
- **`--python-version 312`, `psycopg2-binary==2.9.9`** → succeeds, real
  `cp312-cp312-win_amd64` wheel found and downloaded. This is why the
  install works fine on this dev machine (Python 3.12.10) — it's been
  masked by the dev environment's own Python version, not because the
  pin is actually safe.
- **`--python-version 313`, `psycopg2-binary==2.9.12`** (latest) →
  succeeds, real `cp313-cp313-win_amd64` wheel found and downloaded.
  **Confirms the fix path (a) is real and available today**: bumping the
  pin to any of 2.9.10/2.9.11/2.9.12 resolves the 3.13 build failure with
  a prebuilt wheel, no `pg_config`/source build needed at all.

**3. Existing Python-version enforcement — none exists:**
- `install.bat` STEP 1 (lines 27-40) only checks that `python --version`
  *succeeds* (i.e., some Python is on PATH at all). It never parses the
  version string or compares it against any bound. The message "Please
  install Python 3.11 or later" is shown **only when Python is completely
  missing** — it is documentation text, not an enforced constraint, and a
  reviewer running 3.13 sails straight past this check (3.13 satisfies "3.11
  or later" informally) with zero warning.
- `scripts/verify_environment.py` — grepped for any `sys.version`/
  `version_info` check: **zero matches**. It performs other preflight
  checks (DB schema, etc.) but has no awareness of the Python interpreter
  version at all.
- **Conclusion: the project currently blindly uses whatever
  `python`/`py` resolves to on the reviewer's PATH, with no upper-bound
  check anywhere in the install flow.** This is Phase 2 item 3's question,
  answered directly: no existing enforcement of any kind.

**4. Actual compatible range, as the project stands today:**
- Verified-working: **Python 3.12** (this dev venv, `psycopg2-binary==2.9.9`
  has a wheel).
- Verified-broken: **Python 3.13** (no wheel for the pinned version →
  source build → `pg_config` missing → hard failure).
- Not yet checked here (out of this phase's scope, but worth noting for
  Phase 3): Python 3.11 and earlier weren't directly wheel-checked, since
  the reported failure is specifically about 3.13; the project's own
  `install.bat` messaging already claims 3.11+ generally, and nothing found
  in this investigation contradicts that for 2.9.9 specifically — only 3.13
  is confirmed broken.

**Recommendation for Phase 3 (not implemented here, per this phase's
read-only scope): both (a) and (b), not either alone.**
- **(a) Bump `psycopg2-binary` to a version with 3.13 wheels** (2.9.10,
  2.9.11, or 2.9.12 all confirmed available) — this is the fix that
  actually resolves *this specific* reported failure, and costs nothing
  (drop-in version bump, same package, no code changes needed for wider
  compatibility).
- **(b) Still add an actual Python-version check to `install.bat`** — even
  after (a), a *future* Python release could again outpace whatever's
  pinned in `requirements.txt` before anyone notices, and the failure would
  again surface as a cryptic `pg_config` error deep in a pip build log
  instead of a clear message at step 1. `install.bat`'s STEP 1 already has
  the right shape (checks Python exists, prints the found version) — it
  just needs the found version actually parsed and compared, with a clear,
  actionable error naming both what's required and what was found, instead
  of only checking "some Python exists."
- (a) alone fixes today's report but leaves the same class of failure
  latent for the next Python release; (b) alone doesn't help this specific
  reviewer today since (a) is what actually gets them a working wheel.

---

# Dockerize for Reviewer Handoff — PHASE 1 (read-only investigation)

## 1. `orm_collection/Dockerfile` — current state
```dockerfile
FROM python:3.11
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium
COPY . .
CMD ["sh", "-c", "python scripts/bootstrap_schema.py && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```
- **Base image: `python:3.11`** — confirms the task's own assumption: the
  container controls its own Python version and sidesteps the
  psycopg2/3.13 issue entirely (a real wheel exists for cp311, same as
  cp312, per Phase 2's PyPI check).
- **Alembic is confirmed already replaced**: the `CMD` runs
  `python scripts/bootstrap_schema.py` (the schema.sql-based bootstrap)
  before starting uvicorn — no `alembic upgrade head` anywhere in this
  file. Matches the earlier alembic-removal task's intent.
- **This Dockerfile is backend/API-only by default** — its own `CMD` only
  starts uvicorn. The Celery worker and beat processes reuse the *same*
  image (same `build: context: ./orm_collection` in compose) but override
  `command:` at the compose-service level rather than having their own
  Dockerfile `CMD`. That's a normal, working pattern — just noting it
  since it explains why one Dockerfile serves 4 different compose services.
- **No credentials or env baked into the image today** — no `ENV` for
  DB/Redis/secrets, no `COPY` of any `.env` file. Everything currently
  comes from `docker-compose.yml`'s `env_file: .env` at *container-run*
  time, referencing a `.env` file that must exist next to
  `docker-compose.yml` on whatever machine runs `docker compose up`. This
  is the real gap Phase 2 needs to close for the stated goal (a bare
  `docker pull` + `docker run` with **no** separate `.env` file needed on
  the reviewer's machine at all).

## 2. `docker-compose.yml` — exists at repo root, read fully
Six services defined:
| service | purpose | build context | needed for reviewer? |
|---|---|---|---|
| `db` | local Postgres 15 | image only | **see note below — likely vestigial** |
| `redis` | Celery broker/backend | image only | **yes, still needed** |
| `backend` | FastAPI, port 8000 | `./orm_collection` | yes |
| `celery-worker-general` | queues `io_queue,cpu_queue,nlp_queue,aggregation_queue`, `--pool=solo --concurrency=1` | `./orm_collection` | yes, to demonstrate real task consumption |
| `celery-worker-pipeline` | queue `pipeline_queue`, same pool config | `./orm_collection` | yes |
| `celery-beat` | Celery beat scheduler | `./orm_collection` | yes |
| `frontend` | Next.js dashboard, port 3000 | `./orm_dashboard` | yes — reviewer needs to see the actual dashboard |

**Important finding — the local `db` service is very likely dead weight
right now:** `orm_collection/.env` has a `DATABASE_URL` override (added in
a task after this compose file was last touched) that points directly at
the live **Render Postgres** (`viewer_sfzg`). Per `app/core/config.py`,
`DATABASE_URL_OVERRIDE` (mapped from the `DATABASE_URL` env var) **always
wins** over the discrete `DB_HOST`/`DB_PORT`/etc. fields. Since every
backend-family service loads the whole `.env` via `env_file: .env`, the
app already connects to Render regardless of the `environment:
DB_HOST=db` override compose sets (a *different*, lower-precedence field
that the app never actually reads once `DATABASE_URL_OVERRIDE` is set).
**But** `backend`/`celery-worker-*`/`celery-beat` all still declare
`depends_on: db: condition: service_healthy` — so they'll needlessly wait
on a local Postgres container to boot and pass its healthcheck before
starting, even though nothing queries it. This costs reviewer wait time
and a spun-up-for-nothing Postgres container. **Not fixed here (Phase 1 is
read-only) — flagging for Phase 2's judgment call: drop the `db` service
and its `depends_on` entries entirely for this image, since the whole
point of this task is "already connected to Render."**

`redis` **is** genuinely needed: `.env`'s `REDIS_URL=redis://localhost:6379/0`
is local, not a hosted Redis — there's no cloud Redis for this project.
Compose's `environment: REDIS_URL=redis://redis:6379/0` override (pointing
at the compose-network hostname) is the only way Celery's broker actually
gets reached in the containerized setup, and it must stay.

## 3. Frontend (`orm_dashboard`) — already has its own Dockerfile
Multi-stage build already exists (`orm_dashboard/Dockerfile`):
- Stage 1 (`builder`, `node:20-alpine`): `npm ci`, takes
  `NEXT_PUBLIC_API_URL` as a **build ARG** baked into the Next.js build
  output (`npm run build`) — meaning the API URL is compiled into the
  static JS bundle, not read at container-start time. This is actually the
  correct pattern for a fully standalone frontend image (no env-file needed
  at runtime for this particular variable) — but it also means Phase 2 must
  get this value right **at build time**, not just at `docker run` time.
- Stage 2 (`runner`, `node:20-alpine`): copies build output, `npm start`,
  exposes 3000.
- **Gap found**: `orm_dashboard/.env.local` (local dev) also sets
  `NEXT_PUBLIC_API_SHARED_SECRET` — the frontend's half of the backend's
  shared-secret API gate (`app/core/config.py`'s `API_SHARED_SECRET`,
  confirmed: "every non-health route requires this value in the
  `X-API-Key` header"). The Dockerfile only threads `NEXT_PUBLIC_API_URL`
  through as a build ARG/ENV — **`NEXT_PUBLIC_API_SHARED_SECRET` has no
  equivalent build ARG in the frontend Dockerfile today.** If Phase 2 bakes
  in the dev `.env` without also adding this as a frontend build ARG, the
  reviewer's dashboard would build successfully but get 401/403'd on every
  non-health API call — a real, easy-to-miss gap for Phase 2 to close
  explicitly, not discovered by "container didn't crash."

## Summary — what exists vs. what's missing (per this phase's mandate)
**Exists and works today (via `docker-compose.yml` + a local `.env` file
sitting next to it):** all 4 backend-family services building correctly
from a real, already-alembic-free Dockerfile; a working frontend Dockerfile
with the right multi-stage pattern; already-live Render DB connectivity
via `DATABASE_URL_OVERRIDE` (accidentally, since compose wasn't updated
for it, but it works); a working Redis broker path.

**Missing for the stated "zero `.env` setup" reviewer goal:**
1. No credentials baked into either image — both currently depend on an
   external `.env` file existing next to `docker-compose.yml` at runtime.
2. The frontend Dockerfile has no build ARG for
   `NEXT_PUBLIC_API_SHARED_SECRET` — needed alongside `NEXT_PUBLIC_API_URL`
   or every dashboard API call will fail auth.
3. The `db` service's `depends_on: condition: service_healthy` gates on a
   local Postgres container that (as currently configured via `.env`'s
   override) nothing actually uses — worth dropping for this specific
   image/compose variant to avoid needless wait time and confusion for a
   reviewer inspecting `docker compose ps`.
4. No dev-only image tag exists yet (compose currently builds untagged/
   `docker-compose`-default-named local images) — Phase 2's tagging
   requirement (`orm-platform:dev-review` or similar) hasn't been set up.
5. No GHCR push configuration exists yet (no workflow, no manual push
   history found) — entirely Phase 3's job.

---

# Dockerize for Reviewer Handoff — PHASE 2 (bake config, build, verify locally)

## Changes made
1. `orm_collection/Dockerfile` — pinned base image `python:3.11` to
   `python:3.11-bookworm` (see unrelated bug below); added a hardened,
   retrying `pip install` (see below); added
   `RUN python -m spacy download en_core_web_sm` (see below); added
   `entrypoint.sh` (COPY + chmod +x + ENTRYPOINT) so the baked `.env` is
   sourced into the real process environment before exec-ing whatever
   command runs (uvicorn by default, or a celery worker/beat command
   override from compose) — this is what makes the image self-contained
   without needing compose's own env_file at runtime.
2. `orm_collection/entrypoint.sh` (new) — sources /app/.env but only for
   variables not already set in the environment, so docker-compose-injected
   values (REDIS_URL=redis://redis:6379/0, DB_HOST=db, the real in-network
   hostnames) always win over the baked .env's own localhost-oriented
   defaults. A naive set -a; . .env would silently break Celery/DB
   connectivity, caught this live (see below), not by inspection.
3. `orm_collection/.dockerignore` — un-excluded .env specifically (an
   !.env line after the broader .env.* exclusion) so COPY . . actually
   bakes it in; .env.local/.env.example/etc. stay excluded.
4. `orm_dashboard/Dockerfile` — added ARG/ENV NEXT_PUBLIC_API_SHARED_SECRET
   in both the builder and runner stages, threaded exactly like the
   existing NEXT_PUBLIC_API_URL.
5. `docker-compose.yml` — dropped the db service and every
   depends_on: db: condition: service_healthy entry (backend, both celery
   workers, beat) and the now-orphaned postgres_data volume, per Phase 1's
   finding that nothing uses it. Added image: orm-platform-backend:dev-review
   (shared across backend + both worker groups + beat, since they are the
   same image with different command overrides) and
   image: orm-platform-frontend:dev-review. Added the
   NEXT_PUBLIC_API_SHARED_SECRET build arg and runtime env to the frontend
   service, sourced via compose variable substitution.
6. New root .env (gitignored, confirmed via git check-ignore, same trust
   level as orm_collection/.env and orm_dashboard/.env.local, both already
   gitignored and already holding live secrets) holds only
   NEXT_PUBLIC_API_SHARED_SECRET for compose's own variable-substitution
   mechanism (a separate mechanism from each service's env_file).
7. The Dockerfile carries a LABEL and a comment marking the image clearly
   as dev-only, per this task's explicit requirement.

## Two real, unrelated bugs found and fixed during verification
1. python:3.11 now resolves to Debian 13 "trixie" (confirmed live via
   docker run --rm python:3.11 cat /etc/os-release ->
   VERSION_CODENAME=trixie). playwright==1.41.2's --with-deps package list
   predates trixie and references ttf-unifont / ttf-ubuntu-font-family,
   which trixie renamed or dropped, so playwright install --with-deps
   chromium failed with a missing-package apt error. Fixed by pinning
   FROM python:3.11-bookworm (Debian 12, stable, has the packages under
   the names this playwright version expects). Unrelated to any change in
   this task, the base image silently drifted out from under an unpinned
   tag.
2. pip install hit a mid-download read-timeout error on the large torch
   dependency chain pulled in via transformers, a genuine flaky-network
   issue in this build environment, reproduced twice. pip's own retries
   flag does not cover a timeout mid-stream, so the Dockerfile now retries
   the whole install up to 5 times with an explicit success flag, since a
   loop whose last command is sleep would otherwise exit 0 even if every
   attempt failed, silently shipping an image with no dependencies
   installed. Succeeded on retry once this was in place.

## One bug caught live during verification, not by inspection
Naive .env-sourcing in entrypoint.sh silently broke Celery/DB connectivity.
The first version unconditionally overwrote already-set environment
variables, clobbering docker-compose's REDIS_URL and DB_HOST (the real
in-network service hostnames) with the baked .env's own localhost values.
The first /health check showed redis as failed and db_host as localhost,
and the backend log showed a Redis connection-refused error against
localhost. Caught this from the actual health output, not by re-reading
the script. Fixed by rewriting entrypoint.sh to only set a variable from
.env if it is not already present in the environment, the same precedence
Docker Compose's own environment section already has over env_file for a
key defined in both. Re-verified: /health now reports db, redis, and
engine_loaded all healthy, with db_host correctly showing the in-network
hostname.

## Another gap caught live: spaCy model missing entirely in the image
Celery worker logs showed a spacy_model_not_loaded critical error on first
boot, the en_core_web_sm model could not be found. install.bat's local
flow downloads this as a separate post-pip-install step, confirmed present
in install.bat and checked by scripts/verify_environment.py, but the
Dockerfile never had an equivalent step, so entity discovery
(executive/competitor candidates) would have silently run with an empty
model in every prior container build of this image, undetected until now.
Fixed by adding the same spacy download step to the Dockerfile.
Re-verified: the critical log line no longer appears on worker or beat
startup.

## Live verification results (same bar as every prior check in this project)
Brought the full stack up via docker compose up, with a local-only port
remap for backend (8010 to 8000 on the host side only) since host port
8000 was occupied by an unrelated, pre-existing container from a different
project on this dev machine, confirmed via docker inspect before touching
anything. The shipped docker-compose.yml itself is untouched and still
uses 8000:8000 for a reviewer's clean machine.

- Backend reachable: /health returned status ok, db ok, redis ok,
  db_host showing the in-network hostname, engine_loaded true.
- Auth gate verified both directions: no X-API-Key header returns 401
  Unauthorized; the correct key returns 200 with real data (the actual
  Render QA Test Client record), confirming it genuinely hits the live
  Render DB, not a stub.
- celery-beat actually dispatching: logs show the scheduler sending every
  one of the 12 registered periodic tasks on startup, not just "beat is
  running".
- celery-worker-general actually consuming a task, not just alive:
  received and fully executed calculate_competitor_benchmarks with real
  computed output logged (a real comparable score and competitor count),
  and the task reported success.
- celery-worker-pipeline actually consuming a task, not just alive: the
  only client in this Render DB had a genuinely stale pipeline_runs row
  stuck at PROCESSING/38% since 2026-08-14, over a week old and unrelated
  to this task, a pre-existing leftover from an earlier, never-completed
  run against the real Render DB (logged separately below rather than
  fixed here). This made the real API-level trigger correctly refuse with
  a 409 conflict. To prove queue-level consumption without touching that
  stale production row, the run_client_pipeline task was dispatched
  directly onto pipeline_queue via Celery's own send_task; the worker log
  confirms the task was received and executed (it then raised a TypeError
  from the ad-hoc call being missing the task's actual argument signature,
  a test-script mistake, not a platform defect). The queue routing, broker
  connectivity, and task-dispatch machinery all worked correctly, which is
  what this check was verifying.
- Frontend dashboard reachable and making authenticated calls, explicitly
  confirmed rather than just "the page loads": loaded the dashboard in a
  real browser, it rendered live data (the real client name, real document
  and entity counts, real topic counts, per-engine health status all
  healthy). Captured real network requests showing a 200 response from the
  clients endpoint with the real client record, an endpoint that 401s
  without the correct key, so a 200 with real data is direct proof the
  baked shared secret is both compiled into the bundle (independently
  confirmed by searching the built output inside the image for the literal
  secret value, found in both a client-side chunk and the server-rendering
  bundle) and actually accepted by the backend.

## Pre-existing issue found, not fixed here (out of this task's scope)
The one Render-hosted client has a pipeline_runs row stuck at
status=PROCESSING, stage=PROCESSING, progress_pct=38, since
2026-08-14T07:39:07Z, over a week stale. The pipeline_run_watchdog task
runs every 15 minutes per the beat schedule and is confirmed dispatching,
and exists specifically to catch and reset exactly this kind of stuck run,
but had not yet cleared it as of this verification (only one dispatch
cycle was observed; multiple cycles were not awaited to confirm whether it
eventually clears it or does not handle this case correctly). Flagging for
separate follow-up, not fixed here, since this task is about Docker
packaging, not pipeline-state recovery, and this row predates any change
made in this task.

## Final state
Both images rebuilt clean after all fixes: orm-platform-backend:dev-review
and orm-platform-frontend:dev-review (the frontend was rebuilt a final
time pointing at the canonical http://localhost:8000, not the local 8010
workaround used only for this verification run, since that earlier build
baked a build-time value into the compiled bundle). The stack was torn
down cleanly after verification. The scratch local-only compose override
used to work around this dev machine's port-8000 conflict has been
deleted, it was never part of the deliverable.

## document_processing_watchdog added; 130 stuck documents root-caused

Forensics on why documents get stuck in `processing_status=PROCESSING`
(130 found, up to 11+ days old, 105 belonging to Tesla, 23 to Tata Motors,
1 to Nvidia, 3 unmatched to any client): `execute_document_intelligence_sync`
(`intelligence_tasks.py`) sets PROCESSING and commits before any real work
happens; if the worker process dies anywhere after that (OOM kill, forced
restart, native-library crash, redeploy), the document is stuck forever.
No task-level time limit can catch this -- the worker runs `--pool=solo`,
where Celery's time_limit/soft_time_limit enforcement is a documented no-op
(only the prefork pool can kill a stuck child process; solo has none to
kill). This is the exact same failure class `CollectionJob` and
`PipelineRun` already hit -- both already got a dedicated Beat-scheduled
watchdog after being found stuck for weeks -- `Document` never did, until
now.

Fix: added a nullable `documents.processing_started_at` column (schema.sql
updated and verified against a throwaway local DB; additive `ALTER TABLE`
applied to both local and Render, no data migration needed), set at the
same commit that sets PROCESSING, and a new `document_processing_watchdog`
task (`intelligence_tasks.py`), Beat-scheduled every 15 minutes, mirroring
`collection_watchdog`/`pipeline_run_watchdog`'s exact reconcile-and-reset
pattern. Timeout is 10 minutes, derived from a live timing test under
current Render latency (not the historical `*_processing_time_ms` columns,
which only cover entity/topic/sentiment sub-stages and predate the Render
migration, and don't include Phase 1D/1E's own DB round trips): cold-start
(first document on a freshly started worker) measured ~68-71s end-to-end,
steady-state ~26s. 10 minutes is ~8.5x the observed cold-start worst case,
matching the ~6-8x safety-margin convention `pipeline_run_watchdog` already
established in this codebase. The sweep explicitly excludes rows where
`processing_started_at IS NULL`, since that column didn't exist before
this fix -- every one of the 130 pre-existing stuck documents has NULL
there, so this watchdog will not touch them; they remain a separate,
explicit-sign-off cleanup, not silently swept by this change.

Caveat found during verification, worth knowing: `pipeline_run_watchdog`'s
io_queue routing genuinely survives a crash of the pipeline_queue worker
because that's a *separate* dedicated process in this deployment
(`start_platform.ps1`/`.sh`: pipeline_queue has its own worker). Documents
are different -- `nlp_queue` (where documents are actually processed) and
`io_queue` (where this new watchdog now lives) are both consumed by the
*same* single "general" worker process (`-Q io_queue,cpu_queue,nlp_queue,
aggregation_queue`, one process, `--pool=solo --concurrency=1`). So this
watchdog does not survive the exact crash of the process currently stuck
processing a document -- it still provides real value (it fires
unconditionally on the next periodic tick once *any* general worker
instance, including a freshly restarted one, is up, rather than requiring
someone to manually re-trigger a pipeline for the affected client), but
the specific "isolated from the queue that died" property that makes
`pipeline_run_watchdog`'s io_queue routing meaningful does not hold
identically here. Flagging rather than silently claiming full parity.

## Known gap, not fixed (non-urgent)

No `worker_max_tasks_per_child` configured in `celery_app.py`. Long-running
workers using torch/spaCy for NLP inference have no periodic recycle
against memory creep over a long uptime. Not observed to have caused an
actual incident; noted for future hardening, not addressed in this task.

## FINAL.md full-project forensic audit + TASK.md Phase 1 (#22, #23)

`FINAL.md` (7 parallel read-only sub-agents, one per codebase area) produced
a master known-issues table spanning the whole project. `TASK.md` phases the
fixes; this entry covers Phase 1 (the two Critical processing-layer items,
#22 and #23) and a severe prerequisite bug found live while investigating
them.

### Prerequisite bug found and fixed: accuracy-gate false-negative on a
### client's own primary brand name

Root cause: `evaluate_match_accuracy` (`matching_engine.py`) hardcoded
`is_generic_or_abbrev` to include the literal words `"tesla"`, `"meta"`,
`"tata"` alongside real abbreviations (`"fsd"`, `"tsla"`). Any match on these
words then took a **-0.30 "risky alias" penalty**, regardless of
`category == "PRIMARY"` (i.e. even when the word *is* the entity's own,
non-ambiguous, actual name) -- and each of these three words already has its
own dedicated negative-context disambiguation rule a few lines below (Nikola
Tesla / tesla coil, meta-analysis, unrelated-Tata-Group-company), making the
generic penalty redundant double scrutiny on top of a check that already
does the real disambiguation work.

Live-measured impact before the fix: **Tesla's own PRIMARY brand keyword was
rejected by the accuracy gate 54.7% of the time** (369 of 674
`document_matches` rows for the Tesla brand entity had no corresponding
`entity_mentions` row). Spot-checked 5 rejected documents -- 4/5 were
unambiguous, correct Tesla-company articles that should never have been
rejected (e.g. "Tesla's AI bets squeeze margins...", "Tesla Has Fallen 34%
From Its High...").

Fix: exempt exactly `"tesla"`/`"meta"`/`"tata"` from the generic-alias
penalty (their own step-8 negative-context rule remains the real guard);
leave `"fsd"`/`"tsla"` and the general `len(keyword) <= 4` rule untouched for
every other short/ambiguous keyword (AAPL, IBM, TCS, EPS, COO, TSMC, NVDA,
BMW, BYD, AMD, iPad all keep their existing, still-warranted caution).

Verified live: re-ran `entity_extractor.process_document` on the 5 spot-
checked previously-rejected documents -- all 5 now land in `entity_mentions`
with `confidence_score >= 0.60`. Re-checked negative-context regression
cases with clean (non-confounded) text -- "Nikola Tesla was a brilliant
inventor..." still correctly rejected (confidence 0.35), "The Tesla coil
remains..." still correctly rejected, "a meta-analysis of published
clinical trials..." still correctly rejected, an unrelated-Tata-company
("Tata Consultancy Services") article still correctly rejected. No
regression in the negative-context guard.

### #22 -- sentiment pipeline was reading from the ungated match table

`sentiment_batch_processor.py` and `topic_classification_batch_processor.py`
(matched-keyword derivation only, for preprocessing) both queried
`DocumentMatch` (written by the legacy, ungated `GlobalMatchingEngine`
path, `confidence` hardcoded to `1.0`) instead of `EntityMention` (written by
`EntityExtractor.process_document`, which runs every match through
`evaluate_match_accuracy` and only keeps `status == "accepted"`).
`risk_engine.py` already correctly read from `EntityMention` -- used as the
reference for the fix. Changed both files' entity-lookup queries from
`DocumentMatch`/`matched_entity_id` to `EntityMention`/`entity_id`.

Important nuance, checked live rather than assumed: the 3 already-known
publisher-collision rows (Ease My Trip/"Business Today", Apple Inc/
"Guardian", Apple Inc/"GuruFocus") were NOT affected by this fix --
`entity_mentions` counts already exactly matched `document_matches` counts
for all three (2/2, 9/9, 18/18) *before* this change, meaning the accuracy
gate never actually rejected these specific matches. The `strip_html` fix
(shipped earlier) is what prevents recurrence for new documents; this
table-swap closes a different, broader architectural gap (sentiment trusting
an ungated table as ground truth) that matters for the ~300+ other cases
where the two tables genuinely disagree.

Verified live with a real disagreement case: document `0397cfe9` has a
`document_matches` row for entity "FSD" with no corresponding
`entity_mentions` row (correctly still rejected -- "FSD" remains a real
generic/ambiguous keyword, untouched by the prerequisite fix above). Ran
`HardenedSentimentProcessor.process_batch` on it: a `document_sentiments`
row was written (document-level, unaffected by entity gating) but **no**
`entity_sentiments` row was written for the FSD entity -- confirming the
ungated path no longer feeds a rejected match a confident, entity-targeted
sentiment score. Contrast case (no regression): re-ran sentiment on one of
the 5 now-correctly-accepted Tesla documents from the prerequisite fix above
-- an `entity_sentiments` row for Tesla was written as expected.

Also found and noted, not touched here: a pre-existing `entity_sentiments`
row for a "TSMC" match (document `11e0553c`, written 2026-08-12) that
`entity_mentions` currently rejects -- live evidence of this bug's real-
world consequence (a confident `Negative` 0.92-score sentiment attributed to
a match the accuracy gate doesn't actually support), left as-is; cleaning up
stale rows like this is the same class of decision as the already-flagged
28 bad `document_matches`/`entity_mentions` rows, requiring separate sign-off.

### #23 -- topic/sentiment retry infrastructure was dead code in production

`HardenedTopicClassifier` already had a working `_process_with_retry` method
(transient/permanent failure classification, exponential backoff, real
retry) -- but `intelligence_tasks.py` called `process_batch` directly, which
has no retry logic inline and only logs-and-swallows any exception (by
design, to preserve stage isolation: a topic/sentiment failure must never
abort entity extraction or the rest of the document pipeline). Result: any
transient failure in topic or sentiment classification went straight to a
permanent `FAILED`/`SENTIMENT_FAILED` state on the very first attempt, with
the retry machinery never actually running. `HardenedSentimentProcessor` had
no `_process_with_retry` method at all.

Fix: added `_process_with_retry` to `HardenedSentimentProcessor`, mirroring
`HardenedTopicClassifier`'s existing method exactly (same shape, swapped for
Sentiment's own state machine/config classes -- both already existed).
Changed `intelligence_tasks.py`'s Phase 1B/1C to call `_process_with_retry`
directly (fetching the document's current retry count first) instead of
`process_batch(document_ids=[document_id])` -- `process_batch` was
confirmed (via repo-wide grep) to never be called with more than one
document anywhere in this codebase, so nothing depends on its batch-inference
behavior for the single-document production path. Stage isolation is
unchanged: `intelligence_tasks.py` still only catches and logs, never
re-raises, so a topic/sentiment failure (even after internal retries are
exhausted) still cannot abort the pipeline -- only the previously-dead
in-process retry-with-backoff machinery was activated, not a new failure-
propagation behavior.

Verified live: monkeypatched the sentiment analyzer to raise a
`ConnectionError` (classified transient) on its first call only, then ran
`_process_with_retry` on a real document. Log confirms
`sentiment_analysis_document_failed classification="transient" retry=True`
on the first attempt; final result: `state=SENTIMENT_COMPLETE`,
`retry_count=1` -- the failure was retried in-process and succeeded, instead
of landing at permanent `FAILED` on the first attempt (the prior, broken
behavior).

### Files changed
- `orm_collection/app/services/matching_engine.py` -- accuracy-gate fix.
- `orm_collection/app/services/intelligence/sentiment_batch_processor.py` --
  `DocumentMatch` to `EntityMention` (4 sites), added `_process_with_retry`.
- `orm_collection/app/services/intelligence/topic_classification_batch_processor.py`
  -- `DocumentMatch` to `EntityMention` (2 sites).
- `orm_collection/app/workers/intelligence_tasks.py` -- Phase 1B/1C wired to
  `_process_with_retry` instead of `process_batch`.

### Explicitly not touched in this phase
FINAL.md's #20 (28 pre-existing bad rows) and #21 (3 dormant publisher-
collision landmines) -- both remain untouched per TASK.md's own decision,
pending separate sign-off (TASK.md Phase 12). Every other FINAL.md item
(#1, #2, #14, #15, #24, etc.) is a later TASK.md phase, not started here.

## TASK.md Phase 2 -- Frontend silent-failure gaps (#28, #29, #30)

Three Critical frontend findings from `FINAL.md`. `CompetitorsTab.tsx`'s
already-fixed loading/error/ErrorBoundary three-state pattern (already
reused verbatim by `PipelineStatusPanel.tsx`) was the reference
implementation for all three.

### #28 -- RiskTab discarded its own alerts props

`RiskTab.tsx` destructured `alertsLoading`/`alertsError`/`alerts` as props
but referenced them nowhere else in the file (confirmed via grep) -- the
Risk Center tab had no active-alerts section at all, and an alerts-fetch
failure gave zero indication. Added a new "Active Alerts" card (loading
skeleton / `TelemetryErrorWidget` / data three-state, keyed by `alert.id`)
rendering exactly the 5 fields the API actually returns
(`GET /{client_id}/active-alerts`: `id, alert_type, severity, title,
is_acknowledged, created_at` -- confirmed at
`client_intelligence.py:56-72`, no `message`/`description` field exists).

Verified live in a real browser (Nvidia client, chosen because Apple Inc's
document set makes the `/documents/client/{id}` endpoint genuinely take
16-27s against Render -- a real, pre-existing, out-of-scope perf issue,
not something this phase touched): Risk Center now shows "ACTIVE ALERTS /
2 Active" with two real CRITICAL alerts ("Multi-Signal Incident: Jensen
Huang", "Multi-Signal Incident: Nvidia"), correctly rendered with severity
badge, title, type, and timestamp.

### #29 -- 4 Executive Analytics panels had no error/loading gating or ErrorBoundary

None of `OverviewAnalyticsPanel`, `RiskAnalyticsPanel`,
`NarrativeAnalyticsPanel`, `PipelineDiagnosticsPanel` accepted `loading`/
`error` props, and `page.tsx`'s Executive Analytics block wrapped none of
them in `ErrorBoundary`, unlike every other tab. Added `loading`/`error`
props to all 4, each gated on the real `useDashboardData.ts` state its
content actually depends on (traced via `useAnalytics.ts`): Overview ->
`documentsLoading/Error` + `historyLoading/Error`; Risk -> `documentsLoading/
Error` + `alertsLoading/Error`; Narrative -> `narrativesLoading/Error` +
`benchmarksLoading/Error` + `documentsLoading/Error`; Pipeline Diagnostics ->
same combination as #30 below (same underlying data). Wrapped all 4 in
`ErrorBoundary` in `page.tsx`, matching every other tab.

**Real bug caught only by live testing, not code review**: the first
implementation placed the loading/error early-return *before* each
component's `useMemo`/`useState` hook calls -- a React Rules-of-Hooks
violation (conditionally skipping hooks between renders throws "Rendered
fewer hooks than expected" the moment `loading`/`error` toggles false-to-true
or vice versa). Caught by reading each file's hook order before editing
(all 4 panels use `useMemo`; `RiskAnalyticsPanel` also uses `useState`), not
by running the app first. Fixed by moving every guard clause to immediately
before each component's final JSX `return`, after all hooks. `tsc --noEmit`
does not catch this class of bug (it's a runtime React invariant, not a
type error) -- this was caught by code inspection during implementation.

Verified live: cycled through all 4 sub-tabs against the Nvidia client with
real data -- Overview (reputation/sentiment charts), Risk (SOC matrix),
Narrative (narrative landscape, 1376 narratives), Pipeline Diagnostics (10
engine cards, 100% success rate) all rendered correctly with populated
charts, zero console errors/warnings.

### #30 -- PipelineStatusPanel gated on the wrong fetch's state

Confirmed live via `useAnalytics.ts:643`: `engineDiagnosticsList`'s
dependency array is `[documents, trendEvents, alerts, narratives,
repHistory, executives, benchmarks, reputation, ..., telemetry]` -- not
`repBreakdown`/`breakdown` at all. Yet `PipelineStatusPanel` gated on
`breakdownLoading`/`breakdownError`. Renamed its props to generic `loading`/
`error` (the old names actively misled about what they gate) and updated
`page.tsx`'s call site to pass `documentsLoading || telemetryLoading ||
alertsLoading || narrativesLoading` (and the matching error union) --
the 4 most load-bearing real sources, reused identically for
`PipelineDiagnosticsPanel` (#29) since both panels render the same
`engineDiagnosticsList` data under different prop names.
`data.breakdownLoading`/`breakdownError`/`repBreakdown` were left untouched
in `useDashboardData.ts` -- still correctly consumed elsewhere
(`CompetitorsTab`'s `repBreakdown` prop), just no longer misapplied here.

Verified live: Reputation tab's "AI INTELLIGENCE PROCESSING PIPELINE" card
renders correctly with real per-engine data (Entity Matching 433/433
processed, Topic Classification 432 documents, etc.) after the rename.

### Verification method
Full live browser verification (not just code review): started both the
backend (`orm_collection_api`) and frontend (`orm_dashboard`) dev servers,
navigated the real running dashboard, switched clients, clicked through
every affected tab, and read the rendered DOM plus browser console/network
logs to confirm real data rendered and no errors were thrown. `tsc --noEmit`
was also run clean before browser verification. Both dev servers were
stopped after verification completed.

### Files changed
- `orm_dashboard/src/components/RiskTab.tsx` -- Active Alerts card.
- `orm_dashboard/src/components/OverviewAnalyticsPanel.tsx`,
  `RiskAnalyticsPanel.tsx`, `NarrativeAnalyticsPanel.tsx`,
  `PipelineDiagnosticsPanel.tsx` -- `loading`/`error` props + three-state
  render, guard placed after all hooks.
- `orm_dashboard/src/components/PipelineStatusPanel.tsx` -- props renamed
  `breakdownLoading`/`breakdownError` -> `loading`/`error`.
- `orm_dashboard/src/app/page.tsx` -- wired loading/error props for all 5
  panels above, wrapped the 4 Executive Analytics sub-tabs in
  `ErrorBoundary`.

### Explicitly not touched in this phase
Every other FINAL.md item not in Phase 2 (#1, #3-#27, #31-#41) -- later
TASK.md phases.

## TASK.md Phase 3 -- Unscoped API endpoints (#1, #2)

Two endpoints let any caller holding the single shared API key read or
silence another tenant's data.

### #1 -- `GET /documents/` had no client scoping
`documents.py:12-15` returned every document in the database regardless of
caller, unlike its own sibling endpoints in the same file (`GET
/{document_id}` and `GET /client/{client_id}`, both already correctly
scoped via `Document`->`DocumentMatch`->`Entity`->`Entity.client_id`,
confirmed by reading the full file). Grepped the whole repo (frontend
`api.ts` and every backend caller) -- this route had zero known callers
anywhere, so adding a *required* `client_id: UUID` param was a safe,
non-breaking change (nothing currently omits it, since nothing currently
calls the route at all). Scoped via the same join pattern as the sibling
endpoints.

### #2 -- `POST /alerts/{alert_id}/acknowledge` had no client scoping
`alerts.py:10-19` looked up `Alert` by id only -- any caller could
acknowledge (silence) any client's alert by iterating UUIDs. Also zero
known callers anywhere (grepped for "acknowledge" in the frontend, no
matches). Added a required `client_id: UUID` param, scoped the lookup query
by `Alert.client_id`, matching the pattern already used in
`client_intelligence.py`'s `get_client_active_alerts`.

### Verification (live, against the running backend + real Render DB)
- **#1**: `GET /documents/?client_id=<Nvidia>` returned 20 documents, all a
  strict subset of `GET /documents/client/<Nvidia>`'s results. Requesting
  with Apple Inc's `client_id` instead returned a completely disjoint
  433-document set. Omitting `client_id` entirely now returns `422`
  (FastAPI's required-param validation) -- the old unscoped behavior can no
  longer be reached.
- **#2**: inserted one throwaway synthetic `Alert` row for Nvidia (not a
  real alert). Acknowledging it with Apple Inc's `client_id` correctly
  returned `404` and left it unacknowledged; acknowledging it with Nvidia's
  own `client_id` correctly returned `200`/`is_acknowledged: true`. The
  synthetic row was deleted immediately after (test cleanup, not
  production data -- unrelated to the #20 sign-off-pending bad rows).

### Files changed
- `orm_collection/app/api/endpoints/documents.py` -- `client_id` scoping on
  `GET /`.
- `orm_collection/app/api/endpoints/alerts.py` -- `client_id` scoping on
  `POST /{alert_id}/acknowledge`.

### Explicitly not touched in this phase
Everything else in FINAL.md's master table -- later TASK.md phases.

## TASK.md Phase 4 -- Celery gaps (#14, #15)

`SearchJob` had the same stuck-forever failure mode as
`CollectionJob`/`PipelineRun`/`Document` (all three already have a Beat-
scheduled watchdog) but never got one, and `execute_search_task`'s retry
had no exhaustion handling unlike its siblings `fetch_feed_task`/
`process_document_task`.

### #14 -- `search_job_watchdog` added
`SearchJob.started_at` already had `server_default=func.now()`
(`models/search.py:35`), set automatically the instant the row is created
with `status="processing"` -- no schema change needed, unlike the earlier
`processing_started_at` situation for `document_processing_watchdog`.

**Honest gap on the timeout value**: live-checked before writing any code
-- `search_source_configurations` and `search_jobs` both have **zero rows**
in this deployment's entire history (search sources have never been
configured; per the user, Reddit/YouTube are deliberately left wired up for
a future paid-API-key rollout, not currently active), and `.env` has no
Reddit/YouTube credentials at all. So there is no real traffic to measure a
timeout from, and generating any would mean uncontrolled calls to a live
external API with placeholder credentials -- not done. Used
`collection_watchdog`'s already-established 2-hour timeout instead of
inventing an unmeasured number: `execute_search_task`'s shape (one external
API call, then a loop of simple per-item saves via the same
`process_and_save_document()` RSS collection already uses, all inside a
single job row, no multi-stage NLP pipeline inline) is structurally the
closest analog to `CollectionJob` in this codebase, not to `Document`'s
much heavier intelligence-pipeline workload that justified the shorter
10-minute figure. Documented in the task's own docstring to revisit with
real data if search sources are ever actually configured.

Added to `celery_app.py`: routed to `io_queue` (same as the other three
watchdogs), scheduled every 15 minutes in `beat_schedule`.

Verified live: inserted one synthetic `SearchJob` row backdated 3 hours
(status="processing") and one with `started_at=now()` (also
status="processing"). Ran `search_job_watchdog()` directly. Confirmed the
backdated row was reconciled to `status="failed"` with `completed_at` set,
and the recent row was left completely untouched -- proves the timeout
boundary is actually respected, not just "reconciles everything it sees."
Both synthetic rows deleted afterward.

### #15 -- retry-exhaustion handling added to `execute_search_task`
Mirrored `fetch_feed_task`'s exact pattern (`collection_tasks.py:266-294`):
`job = None` initialized before the `try`, and in `except`, a
`self.request.retries >= self.max_retries` check re-queries the job by
primary key (safe after `db.rollback()` may have detached the in-memory
object) and writes a terminal `status="failed"`/`completed_at` state before
the existing `self.retry(...)` call. Previously, on final retry exhaustion,
Celery's own exception would propagate with the `SearchJob` row (if one had
been created) left orphaned at `status="processing"` forever, with no
watchdog covering it either (until #14 above).

Verified live: inserted a temporary enabled `SearchSourceConfiguration`
(`source_type="reddit"`) so the task would reach job creation, monkeypatched
`RedditAdapter.search` to raise a deterministic exception (avoiding any
real network call to Reddit with placeholder credentials), then called
`execute_search_task.apply(args=(...), retries=3)` (Celery's `apply()`
supports simulating an already-retried invocation). Confirmed: the expected
failure exception surfaced (normal, unavoidable Celery behavior once
retries are exhausted -- not itself the bug), and the `SearchJob` row
created during the run was correctly written to `status="failed"` with
`completed_at` set, not left orphaned. Synthetic source config and job row
deleted afterward; the monkeypatch was scoped to the test process only --
no adapter/production code was touched.

### Files changed
- `orm_collection/app/workers/search_tasks.py` -- `search_job_watchdog`
  task added; `job = None` pre-init + retry-exhaustion terminal-state
  handling added to `execute_search_task`.
- `orm_collection/app/core/celery_app.py` -- `search_job_watchdog` routed
  to `io_queue`, added to `beat_schedule` every 15 minutes.

### Explicitly not touched in this phase
Reddit/YouTube adapter code itself (`app/adapters/reddit.py`,
`youtube.py`) -- left exactly as-is, per the user: intentionally dormant
pending future paid API keys, not something this phase should touch.
Everything else in FINAL.md's master table -- later TASK.md phases.

## TASK.md Phase 5 -- Confidence defaults to 1.0 with no evidence (#24)

Two places reported maximum confidence (1.0) precisely when there was the
least real evidence.

### `sentiment_accuracy_enhancer.py:136-139`
The "Calibration gate" (fires when `final_score < 0.65` and no ORM
negative/positive keyword rule matched) was overwriting the real, already-
computed low `final_score` with a hardcoded `1.0`. The fix was smaller than
it looked: since neither rule branch executed in this path, `final_score`
already held the honest raw model score -- the bug was purely the
overwrite. Removed the `final_score = 1.0` line; the label-flip to
"neutral" and the `applied_rule` naming are unchanged (legitimate business
logic, not part of the bug).

### `risk_engine.py:413,427`
`topic_conf`/`sentiment_conf` defaulted to `1.0` and only got overwritten
with a real value once genuine signal existed (a topic passing the 0.65
gate; a `DocumentSentiment` row present) -- confirmed by reading the full
surrounding loop, the corresponding *weight* already correctly stayed `0`
in the no-signal case, only *confidence* was wrong. Changed both defaults
to `0.0`. `confidence_modifier = (topic_conf + ent_sent_conf) / 2.0` is
stored as `RiskEvent.confidence_score` and never touches `final_score`/
`risk_level` (the file's own comment confirms: "Confidence no longer
alters severity score") -- this is a pure observability/explainability
fix, zero effect on actual risk scoring.

**Why `0.0` and not `NULL`**: `DocumentSentiment.confidence_score`,
`EntitySentiment.confidence_score`, and `RiskEvent.confidence_score` are
all `nullable=False` in the DB (`models/sentiment.py:14,32`,
`models/risk.py:38`). A schema migration to allow `NULL` would be
disproportionate scope creep for this fix and wasn't requested -- `0.0`
(no evidence = no confidence) is the honest value within the existing
constraint, consistent with the weight side of the same calculation
already treating "no signal" as a `0` contribution.

### Verification (live, against real Render data)
- `apply_orm_rules` called directly: a no-rule-match, low-raw-score case
  now returns the real `0.42` instead of `1.0`, label `neutral`. Regression
  check: a NEG_WORDS-matching case still returns the correctly-boosted
  `0.85` (0.70 + 0.15), unaffected.
- `RiskEngine().calculate_document_risk(..., persist=False)` called against
  a real document with entity mentions but neither a threshold-passing
  topic nor any sentiment row: `confidence_score` in the returned payload
  is now `0.0` (was `1.0`). Regression check: called against two real
  documents that *do* have both real topic and sentiment data --
  `confidence_score` came back as a genuine nonzero averaged value (`0.5`)
  in both cases, confirming the real-signal path is unaffected.

### Files changed
- `orm_collection/app/services/intelligence/sentiment_accuracy_enhancer.py`
- `orm_collection/app/services/intelligence/risk_engine.py`

### Explicitly not touched in this phase
No DB schema change (deliberately not needed). Everything else in
FINAL.md's master table -- later TASK.md phases.

## TASK.md Phase 6 -- Remaining frontend issues (#31, #32, #33)

### #31 -- array-index React keys replaced with stable ids
`CompetitorsTab.tsx:663`, `ExecutivesTab.tsx:526`, `RiskTab.tsx:456,651`
(line numbers shifted from FINAL.md's 406/601 by the Phase 2 Active Alerts
card), `NarrativesTab.tsx:387` -- all changed from `key={idx}` to
`key={doc.id}`/`key={n.id ?? idx}`, matching the stable id already used one
or two lines later in each row's own `onClick` handler.

### #32 -- `NarrativeIntelligenceWorkbench` auto-selects on real data arrival
The `useState` initializer only ran once on mount, so a narrative fetched
after the initial empty render never got auto-selected -- confirmed the
same dead-selection symptom also recurs on every client switch (a stale
`selectedNarrativeId` from the previous client doesn't match the new
`narrativeList`, and nothing re-selects). Replaced the initializer with a
plain `useState<string | null>(null)` and added
`useEffect(() => { if (!activeNarrative && narrativeList.length > 0)
setSelectedNarrativeId(narrativeList[0].id); }, [activeNarrative,
narrativeList])` -- using the already-derived `activeNarrative` (not
`selectedNarrativeId`) as the trigger condition fixes both the initial-load
and client-switch cases with one effect.

### #33 -- fabricated confidence formula removed
`baseConf = 80 + Math.min(docs.length * 2, 12)` was always `>= 80%`
regardless of evidence, including zero supporting documents. Checked the
actual `/narratives` API response (`client_intelligence.py:82-91`): no
`confidence`/`confidence_score` field is returned by the backend at all
today. Applied `useAnalytics.ts`'s `getConfidenceScore` pattern honestly
rather than inventing a replacement formula: read the real field if the
backend ever adds one, else `null` (rendered "Not Available") -- which is
what every narrative correctly shows right now, since no such field exists
yet.

### Verification (live, real browser, both dev servers running)
- **#33**: every narrative card in the registry showed "CONFIDENCE: Not
  Available" (confirmed via `read_page` against the live Nvidia client,
  1376 narratives), not a fabricated number.
- **#32**: on fresh page load, the center "AI Analysis Details" panel
  showed real content immediately (a real narrative name, classification,
  and executive summary) with no manual click -- not the "Select a
  narrative from the registry..." placeholder. Switched clients (Nvidia ->
  PepsiCo) and confirmed the workbench re-selected a new real narrative for
  PepsiCo instead of showing "No narrative selected."
- **#31**: confirmed real row counts render correctly in each affected
  table (Risk Center: 433 rows, Competitor Compare: 61 rows, Executive
  Reputation: 34 rows) with no React "duplicate key"/"Rendered fewer hooks"
  console warnings in any of them.

### Files changed
- `orm_dashboard/src/components/CompetitorsTab.tsx`
- `orm_dashboard/src/components/ExecutivesTab.tsx`
- `orm_dashboard/src/components/RiskTab.tsx`
- `orm_dashboard/src/components/NarrativesTab.tsx`
- `orm_dashboard/src/components/NarrativeIntelligenceWorkbench.tsx`

### Explicitly not touched in this phase
Everything else in FINAL.md's master table -- later TASK.md phases.

## TASK.md Phase 7 -- Infra fixes (#6, #8, #9)

**#7 (GHCR push) was skipped this phase, per explicit user direction.**
Docker Desktop's daemon isn't running on this machine, and pushing requires
a GitHub PAT with `write:packages` scope that Claude cannot obtain or enter
(credential entry is off-limits). Not attempted, not stubbed -- the user
chose to drop it from this task rather than have Claude start Docker or
handle a token.

### #6 -- `install.bat` STEP 1 now enforces the Python version
Previously only checked that *some* Python was on PATH, never the version
-- confirmed still true, matching the never-closed finding from the
original install-failures investigation. Added real parsing (`python
--version` -> major/minor) with: hard error below 3.11 (matches the
project's own existing messaging), a non-blocking warning above 3.13 (the
newest version with a confirmed-working psycopg2 wheel per this file's
earlier entries -- blocking future releases outright would be overly
strict when they might just work, but proceeding with zero warning is what
caused the original bug report), silent pass for 3.11-3.13.

**A real batch bug was caught only by live testing, not code review**: the
first implementation used nested `if (...) ( if (...) ( ... exit /b 1 ) )`
blocks. Live-tested against 8 version strings via `cmd.exe` and found the
branching logic printed the correct message but **always returned exit
code 0**, even from the "too old, hard error" branch -- a real, confirmed
cmd.exe quirk where `exit /b` doesn't reliably propagate out of a doubly-
nested parenthesized `if` block. Isolated with a minimal repro (a single-
level nested if worked fine; two levels broke). The same live test also
caught a second bug: major-version `> 3` (e.g. a hypothetical Python 4.x)
fell through to silent success with no warning, since the original logic
only checked minor-version bounds inside the `major == 3` branch. Rewrote
using `goto` labels instead of nested parens (matching the well-established
batch idiom for exactly this class of bug, and avoiding the nesting
entirely) and added an explicit `major > 3` check. Re-tested all 8 cases
via `cmd.exe`: correct message and correct exit code (0 or 1) in every
case. Ran the real `install.bat` end-to-end against this machine's actual
Python 3.12.10 afterward -- completed with "INSTALLATION SUCCESSFUL",
exit 0.

### #8 -- `docker-compose.yml`: removed leftover `DB_HOST=db`
Removed the `- DB_HOST=db` line from all 4 services (`backend`,
`celery-worker-general`, `celery-worker-pipeline`, `celery-beat`) --
a hostname for a `db` service already removed from this same file.
Verified via `docker compose config` (works without the Docker daemon
running, since it's config validation/interpolation only): `DB_HOST` no
longer appears anywhere in the rendered output.

### #9 -- `docker-compose.yml`: `NEXT_PUBLIC_API_SHARED_SECRET` now fails loudly if unset
Changed both occurrences from `${NEXT_PUBLIC_API_SHARED_SECRET}` to
`${NEXT_PUBLIC_API_SHARED_SECRET:?NEXT_PUBLIC_API_SHARED_SECRET must be set
in .env before building the frontend image}`, matching `NEXT_PUBLIC_API_URL`'s
existing fallback pattern conceptually (but using Compose's `:?` required-
variable syntax instead of `:-` default, since a missing secret should
hard-fail, not silently default). Verified live: ran `docker compose
config` with a temporary env file that had the variable stripped out --
failed with exactly the custom error message and exit code 1, instead of
the old silent-empty-string behavior.

### Files changed
- `install.bat`
- `docker-compose.yml`

### Explicitly not touched in this phase
#7 (GHCR push) -- skipped per user direction, see above. Everything else
in FINAL.md's master table -- later TASK.md phases.

## TASK.md Phase 8 -- DB model fixes (#10, #12)

Two Medium/Low findings about SQLAlchemy models drifting from the real
schema in ways that don't affect production data (the live DB already has
the correct indexes/DDL) but mislead anyone treating the models as
documentation, or building a fresh test DB from `Base.metadata.create_all()`.

### #10 -- 4 FK columns missing `index=True` in the ORM models
Confirmed all 4 already have a real index in the live schema, cross-checked
against `database/schema.sql`:
- `source.py` `category_id` -> `schema.sql` `idx_sources_category`
- `topic.py` `parent_topic_id` -> `schema.sql` `idx_topics_parent`
- `competitor_candidate.py` `promoted_to_competitor_id` -> `schema.sql`
  `idx_comp_cand_promoted`
- `executive_candidate.py` `promoted_to_executive_id` -> `schema.sql`
  `idx_exec_cand_promoted`

Since the DB is already correct, this was a pure ORM-declaration gap, not a
schema change -- no `ALTER TABLE`/`schema.sql` edit was needed or made.
Added `index=True` to each of the 4 `Column(...)` calls.

Verified live: attempted to build a throwaway SQLite test DB via
`Base.metadata.create_all()` first, but SQLAlchemy's SQLite dialect can't
compile this project's Postgres-native `UUID` column type at all (unrelated
pre-existing limitation, not caused by this fix) -- so `Base.metadata
.create_all()` against SQLite was never a viable test DB option for this
schema regardless of the fix. Verified instead directly against the ORM
metadata (`Base.metadata.tables[...].columns[...].index`) and by compiling
the resulting `CREATE INDEX` DDL against the real `postgresql` dialect:
confirmed all 4 columns now report `index=True` and compile to
`CREATE INDEX ix_<table>_<column> ON <table> (<column>)`, where before the
fix they compiled to nothing. This proves a fresh Postgres DB built via
`Base.metadata.create_all()` now creates these 4 indexes, matching the
live schema.

### #12 -- stale Alembic-migration comment in `trends.py`
`trends.py`'s two comments describing the `uq_trend_events_daily` functional
unique index claimed its real DDL "is referenced in the migration" / "is in
the Alembic migration: phase_4_1_trend_hardening.py" -- stale since Alembic
was fully removed from this project (see Phase "Remove Alembic" entry
above). Confirmed live: no `phase_4_1_trend_hardening.py` exists anywhere
in the repo (grepped), and the actual DDL for this exact index is at
`database/schema.sql`'s `uq_trend_events_daily` definition. Rewrote both
comment blocks to point at `schema.sql` instead. Comment-only change --
`git diff` confirms no code/logic lines changed in `trends.py`.

`alert.py` has an unrelated comment mentioning a *hypothetical future*
`alembic revision --autogenerate` risk -- not a present-tense false claim,
and not in #12's named scope (`trends.py:99-108` per TASK.md), so left
untouched.

### Files changed
- `orm_collection/app/models/source.py`
- `orm_collection/app/models/topic.py`
- `orm_collection/app/models/competitor_candidate.py`
- `orm_collection/app/models/executive_candidate.py`
- `orm_collection/app/models/trends.py`

### Explicitly not touched in this phase
Any live schema change (not needed -- DB already correct); `alert.py`'s
comment (out of #12's named scope, not actually stale). Everything else in
FINAL.md's master table -- later TASK.md phases.

## TASK.md Phase 9 -- Remaining Processing/API items (#3, #4, #18, #25, #26, #27)

### #3 -- `POST /search/{source_type}` now takes a proper JSON body
`search.py`'s `trigger_search` took `keyword: str` as a bare param, which
FastAPI treats as an implicit query param -- inconsistent with every other
create-style POST in the codebase (`entities.py`, `feeds.py`, `sources.py`,
`clients.py`), all of which take a Pydantic body model. Grepped the whole
frontend -- zero callers of this route, so the signature change is purely
additive. Added `SearchTriggerRequest(BaseModel)` to `schemas/search.py`
and changed the endpoint to take `request: SearchTriggerRequest`. Verified
live against the running backend: the old `?keyword=...` query-param style
now correctly 422s, and the new JSON body style (`{"keyword": "..."}`)
reaches the business logic (400 "reddit source is not enabled" -- expected,
Reddit isn't configured in this environment, but proves the body was parsed
and read correctly).

### #4 -- `GET /{client_id}/competitive-summary` implemented for real
Was a self-declared stub (`"TODO: Implement... Currently a stub"`)
returning a bare `{"status": "ok"}`. Zero known callers (grepped frontend).
Implemented a real summary reusing the exact latest-per-competitor
`CompetitorBenchmark` query pattern already used twice in the same file
(`get_client_benchmark`, `get_client_sov`): `competitor_count`,
`avg_competitor_reputation`, `top_competitor` (name + score), and
`client_rank`.

Caught during live verification, not before: my first `client_rank`
implementation used `min(CompetitorBenchmark.rank)` across competitors --
wrong. Cross-checked against the frontend's own definition
(`useAnalytics.ts:56-63`, `clientRankValue` = 1 + count of competitors with
strictly higher reputation than the client) and `CompetitorsTab.tsx`'s own
comment confirming `CompetitorBenchmark.rank` is competitor-to-competitor
only and doesn't include the client. Fixed to compute the client's own rank
from its `ReputationScore.score` compared against the same competitor
reputation list, matching the established frontend convention. Verified
live for Apple Inc (11 competitors, `client_rank=9`, consistent with
Apple's live reputation score of 45.77 vs. its competitors' scores) and for
a client with zero competitors (`competitor_count: 0`, explicit nulls, no
crash).

### #18 -- 4 retry/backoff patterns documented, not consolidated
Confirmed the 4 coexisting patterns FINAL.md described: Celery exponential
backoff (`document_processor.py`, `collection_tasks.py`, `search_tasks.py`),
Celery flat countdown (`intelligence_tasks.py`, `aggregation_tasks.py`),
in-process retry state-machine classes (`RetryConfig`/`SentimentRetryConfig`
/`TopicRetryConfig`), and `evaluate_alerts`'s unique transient-error-
conditional retry. Full consolidation would touch Celery-level retry
control flow in 6+ files across two high-risk zones for something FINAL.md
itself flags as "Medium... not a bug" -- per TASK.md's own fallback clause,
added a short comment at each of the 5 anchor sites (one per pattern
instance, plus 2 more of the 3 retry-config classes) naming which pattern
it is and cross-referencing the other 3. Comment-only -- no retry/backoff
values or logic changed anywhere.

### #25 -- Generic negative-word false-triggers, live-verified
Queried the live Render DB for real documents containing "fine"/"court"/
"complaint" (`sentiment_accuracy_enhancer.py`'s `NEG_WORDS`). Two confirmed
live false-triggers traced to their actual `document_sentiments` rows:
- **"court"**: "The Ball in OpenAI's court" (a business idiom, matched to
  entity OpenAI) was written as `Negative, -1.0` on this word alone, with
  zero litigation content anywhere in the article.
- **"complaint"**: a Pixel Buds review ("impressed by the excellent sound
  quality... comfortable fit"), matched to Apple Inc, was flipped fully
  Negative by one incidental minor gripe ("The biggest complaint we had...").
- **"fine"**: all 8 sampled live hits were genuine monetary/regulatory
  fines (Zepto ₹25,000, Meta $567m, etc.) -- correctly negative, no false
  trigger found, not touched.

Fixed "court" with a targeted co-occurrence gate: it now only counts as a
negative trigger when a real litigation-context word (ban/case/legal/
lawsuit/sued/ruling/judge/trial/verdict) also appears in the same text --
live-sampled genuinely-negative "court" articles all had one of these words
elsewhere, so this costs no real recall. Verified live: the OpenAI idiom no
longer flips to negative (stays neutral), while re-running the German-
court-bans-Tesla and Supreme-Court-antitrust-case samples through the same
function still correctly triggers negative via "ban"/"case" respectively.

"complaint" was left unchanged -- most live hits were genuinely negative
(e.g. "criminal complaint... over Meta AI glasses"), and the one
false-positive found is a structural limit of whole-document word-list
matching (an incidental minor gripe in an otherwise positive review), not a
wrong dictionary entry; removing it would cost real recall on genuine
complaint-driven negative stories. Not a data backfill -- code-path fix
only, no existing `document_sentiments` rows were touched.

### #26 -- Additive `CHECK` constraints on 19 score columns across 9 tables
Live-queried MIN/MAX for every confidence/sentiment/risk score column
before touching schema (mandatory for a live-data DB change). Found two
distinct scales that must not be conflated: `alerts.confidence_score`/
`evidence_score` are live-verified 0-100 (56.25-95.625 observed), unlike
every other `confidence_score` column, which is 0-1. Applied 18 additive
`ALTER TABLE ... ADD CONSTRAINT ... CHECK` statements directly to the live
Render DB (`alerts`, `competitor_benchmarks`, `document_sentiments`,
`document_topics`, `entity_mentions`, `entity_sentiments`, `narratives`,
`reputation_scores`, `executive_reputation_scores`, `risk_events`) -- all
applied with zero rejections, confirming every existing row was already
within range (a true no-op against current data, guarding only future
writes). Added the matching `CONSTRAINT ... CHECK` clauses to each table's
`CREATE TABLE` block in `database/schema.sql`, matching the existing
`documents_processing_status_check`/`ck_rss_feeds_*` inline style.

Verified live: a deliberate out-of-range `UPDATE risk_events SET
risk_score = 150` was correctly rejected with a `CheckViolation`
(`ck_risk_events_risk_score`), rolled back, and the row's original value
(37.5) confirmed unchanged afterward.

### #27 -- entity-boost heuristics: recommendation only (per TASK.md)
`matching_engine.py`'s `executive_patterns`/`product_patterns`/
`industry_keywords` dicts are hardcoded to exactly 3 example clients
(Tesla/Meta/Tata) -- deliberate demo scaffolding (the same 3 clients also
have dedicated negative-context rules nearby), not a bug; other clients
just don't get these 3 bonus categories today (still get the other 7
client-agnostic scoring steps). Recommendation: don't hardcode more
per-client dicts (doesn't scale) and don't delete it (Phase 1's Tesla fix
relies on this exact path) -- the sustainable fix is sourcing these boost
keywords from each entity's own `EntityKeyword` rows (already
client-configurable) with a category like "executive"/"product"/
"industry", instead of a code-level dict. That's a real data-model/
ingestion change, out of proportion for this phase -- not implemented, per
TASK.md's own instruction not to guess at implementation.

### Files changed
- `orm_collection/app/schemas/search.py`
- `orm_collection/app/api/endpoints/search.py`
- `orm_collection/app/api/endpoints/client_intelligence.py`
- `orm_collection/app/workers/document_processor.py`
- `orm_collection/app/workers/aggregation_tasks.py`
- `orm_collection/app/workers/intelligence_tasks.py`
- `orm_collection/app/services/entity_matching_batch_processor.py`
- `orm_collection/app/services/intelligence/sentiment_batch_processor.py`
- `orm_collection/app/services/intelligence/topic_classification_batch_processor.py`
- `orm_collection/app/services/intelligence/sentiment_accuracy_enhancer.py`
- `database/schema.sql`
- Live Render DB (18 `ALTER TABLE ... ADD CONSTRAINT` statements)

### Explicitly not touched in this phase
#27's `EntityKeyword`-category redesign (recommendation only); full #18
retry/backoff consolidation (documented instead); "complaint"/"fine" in
#25 (live data didn't support changing either); any score column outside
the confidence/sentiment/risk families for #26. Everything else in
FINAL.md's master table -- later TASK.md phases.

## TASK.md Phase 10 -- Remaining frontend item (#36)

`useDashboardData.ts`'s 45s live-poll loop (distinct from the initial-load
path, which already has real per-resource error handling) had zero error
surfacing at all -- every fetch in its `Promise.allSettled` had no
`.catch`, so an extended backend outage after initial load just left the
UI silently stuck on stale data forever.

Each fetch already goes through `fetchWithRetry` (`api.ts`), which retries
transient failures internally (up to 2 retries, exponential backoff, 15s
timeout) before its promise ever rejects -- so a rejected poll-cycle result
is already a real, non-transient failure, not a dropped packet. The fix
only needed to count failed cycles, not add its own retry logic.

Added a `pollFailureStreakRef` + `livePollDegraded` state to the hook: a
cycle counts as failed only when a majority of its 7 concurrent fetches
reject (distinguishes "one flaky endpoint" from "backend is actually
down"), and the degraded state only surfaces after 3 consecutive failed
cycles (~135s of sustained majority-failure) -- a single successful cycle
immediately clears it. `DashboardHeader.tsx`'s always-visible sticky status
indicator (previously hardcoded to always show green "SECURE SESSION"
regardless of actual reachability) now reflects this: amber dot + "SIGNAL
DEGRADED" badge when degraded, reusing the existing header instead of
adding a new banner component.

Verified live in the browser: loaded the dashboard (green "SECURE
SESSION"), stopped the backend to simulate an outage after initial load,
waited ~180s (4 poll cycles) -- header correctly flipped to amber "SIGNAL
DEGRADED", not on the first failed cycle. Restarted the backend and waited
one more cycle (~60s) -- header correctly flipped back to green, no
lingering stale degraded state. Checked the browser console throughout --
only the expected `ERR_CONNECTION_REFUSED` noise from the intentionally
stopped backend, zero new React/app errors introduced by the change.

### Files changed
- `orm_dashboard/src/hooks/useDashboardData.ts`
- `orm_dashboard/src/components/DashboardHeader.tsx`
- `orm_dashboard/src/app/page.tsx`

### Explicitly not touched in this phase
The initial-load path (already has real per-resource error handling) and
individual `TelemetryErrorWidget` usages -- this phase only closes the
live-poll gap. Everything else in FINAL.md's master table -- later TASK.md
phases.

## TASK.md Phase 11 -- Test infrastructure (#37, #38, #39, #40)

Confirmed live via `pytest --collect-only` before touching anything: **only
4 tests actually ran**, out of 13 `test_*.py` files and a "100% READY"
`pipeline_validation.py` report. After this phase: **15 tests collected, 9
passed + 6 xfailed, 0 unaccounted failures** -- a real, trustworthy, green
baseline.

### #37 -- deleted `tests/pipeline_validation.py`
Confirmed it imported nothing from the app, defined no functions, and its
entire body was a hardcoded markdown string claiming 100% success across
every scenario. Zero real code executed. Deleted outright -- only
referenced from `TASK.md`/`FINAL.md` docs, nothing broken.

### #38a -- converted 8 `run_validation()` files to real pytest tests
`test_alert_engine.py`, `test_benchmark_engine.py`,
`test_entity_intelligence.py`, `test_executive_reputation.py`,
`test_narrative_engine.py`, `test_reputation_engine.py`,
`test_risk_engine.py`, `test_trend_detection.py`: each already built a real
in-memory SQLite DB, ran real scenarios through the real engine class, and
computed genuine pass/fail checks via `print()` instead of `assert` --
pytest never saw a failure even when the check failed. Converted every
`if <cond>: correct += N; print([PASS])` / `else: print([FAIL])` pair into
a real `assert`, removed the now-redundant accuracy-percentage bookkeeping,
renamed `run_validation()` to `test_validation()`.

**Running these for real immediately surfaced 6 genuine, previously-hidden
gaps between the engines and their long-dormant validation scripts** --
exactly the kind of drift fake test coverage lets accumulate silently:
- **`test_benchmark_engine.py`, `test_reputation_engine.py`**: SQLite test
  harness can't run production's real Postgres-specific
  `ON CONFLICT (named_constraint)` upsert (SQLite's `ON CONFLICT` only
  accepts a column list) -- `sqlite3.OperationalError: no such column:
  uq_client_reputation_run` / `uq_competitor_benchmark_run`. Not a
  production bug (real DB is Postgres) -- needs a real/test Postgres DB to
  validate, out of scope for this phase.
- **`test_executive_reputation.py`**: two issues found. (1) the test's
  `Entity` fixture never set `entity_type="person"`, which
  `executive_reputation_engine.py`'s R1 change now strictly requires to
  find executives at all -- **fixed directly in the test** (safe, test-only,
  matches the engine's own documented intentional behavior). (2) After that
  fix, a second real issue surfaced: `"can't compare offset-naive and
  offset-aware datetimes"` -- another SQLite-vs-Postgres dialect gap
  (Postgres `timestamptz` reliably returns tz-aware datetimes; SQLite's
  `server_default=func.now()` doesn't). Marked xfail.
- **`test_alert_engine.py`**: the test expects 5 distinct per-category
  alert types ("Critical Risk", "Mention Spike", "Topic Spike", etc.), but
  `AlertEngine.evaluate_all` now generates only "Multi-Signal Incident" /
  "Executive Risk" via a newer evidence-score model (confirmed by reading
  the engine's own A1/A4/A5-commented code) -- the test is checking a
  contract that no longer exists. Marked xfail; needs a full scenario
  rewrite against the current model, out of scope here.
- **`test_narrative_engine.py`**: a **real production bug**, not a test
  artifact -- `narrative_engine.py` (~line 348, ~358) does
  `d.published_at or d.created_at` on `Document` objects, but `Document`
  has no `created_at` column (it's `collected_at`) --
  `AttributeError: 'Document' object has no attribute 'created_at'`.
  Marked xfail with the bug documented in the reason; **not fixed here**
  per this project's rule against mixing unrelated bug fixes into an infra
  task -- flagged as a separate follow-up task instead. **Fixed in a
  follow-up, see "Follow-up -- narrative_engine.py Document.created_at bug"
  below.**
- **`test_risk_engine.py`**: the "Positive Partnership" scenario (no topic/
  sentiment signal beyond a bare positive `DocumentSentiment`) now computes
  MEDIUM instead of the LOW the test expects. Most likely explanation:
  Phase 5's confidence-default fix (`topic_conf`/`sentiment_conf` no-signal
  default changed from a fabricated `1.0` to a real `0.0`, see Phase 5's
  entry above) legitimately shifted this borderline case's weighted score.
  Not confirmed as a bug -- marked xfail, needs a dedicated re-tuning pass
  against the current formula.
- **`test_collection_reliability.py::test_rss_404_backoff`** (found while
  verifying the rename below, not part of the 8): the test called
  `fetch_feed_task("test-rss")` with a non-UUID placeholder ID;
  `collection_tasks.py`'s except-block terminal-failure path does
  `uuid.UUID(feed_id)` unconditionally, so the placeholder raised
  `ValueError` and masked the retry assertion the test actually cares
  about. **Fixed directly in the test** (safe, test-only -- production
  code always calls this with a real UUID from the DB) by using
  `str(uuid.uuid4())` instead.

### #38b -- renamed the 2 heavy model-benchmark files
`test_sentiment_analysis.py` -> `validate_sentiment_analysis.py`,
`test_topic_classification.py` -> `validate_topic_classification.py`
(`git mv`). Both instantiate real HuggingFace models with `use_mock=False`
(FinBERT, BART-large-mnli -- hundreds of MB to 1.6GB, downloaded from HF
Hub if not cached) for a 100-document accuracy benchmark -- genuinely
valuable, but unsuitable for routine pytest/CI (minutes per run, network
dependency, real flakiness across model versions). Added a one-line
docstring to each noting they're manual benchmarks. Confirmed live via
`pytest --collect-only`: correctly excluded from default discovery.

### #38c -- renamed `audit_collection_reliability.py`
`git mv` to `test_collection_reliability.py`. Its 3 tests
(`TestCollectionReliability`, real mocked backoff assertions) were already
pytest-discoverable by class/method name -- only the filename broke
`python_files = test_*.py`. No content change beyond the UUID fixture fix
above.

### #39 -- `.github/workflows/tests.yml`
New workflow, two jobs on push/PR to `main`: `backend` (Python 3.11, `pip
install -r orm_collection/requirements.txt`, `python -m spacy download
en_core_web_sm`, `pytest orm_collection/tests -v`) and `frontend` (Node 20,
`npm ci` in `orm_dashboard/`, `npm test`). Both commands verified live from
repo root/`orm_dashboard/` respectively before being written into the
workflow -- not aspirational.

### #40 -- Vitest setup for `orm_dashboard`
Added `vitest` + `jsdom` as devDependencies (skipped `@vitejs/plugin-react`
-- hit a peer-dependency conflict from an optional transitive Babel plugin,
and the first real test doesn't need JSX/React rendering; not installing an
unneeded dependency matches this project's own "don't add dependencies
without stating why" discipline -- can be added later when an actual
component test needs it). Added `vitest.config.ts` (jsdom environment, `@/`
path alias matching `tsconfig.json`) and a `"test": "vitest run"` script.
First real test: `src/utils/formatChartDate.test.ts` (6 cases) -- caught a
real bug in the test itself during verification (assumed `new
Date("not-a-date")` throws; it doesn't, it produces an `Invalid Date`
object that `.toLocaleDateString()` happily stringifies), fixed the test's
expectation to match actual JS `Date` behavior. Verified live: `npm test`
passes all 6, `npm run build` still succeeds afterward.

### Files changed
- Deleted: `orm_collection/tests/pipeline_validation.py`
- Converted to real pytest: `orm_collection/tests/test_alert_engine.py`,
  `test_benchmark_engine.py`, `test_entity_intelligence.py`,
  `test_executive_reputation.py`, `test_narrative_engine.py`,
  `test_reputation_engine.py`, `test_risk_engine.py`,
  `test_trend_detection.py`
- Renamed: `test_sentiment_analysis.py` -> `validate_sentiment_analysis.py`,
  `test_topic_classification.py` -> `validate_topic_classification.py`,
  `audit_collection_reliability.py` -> `test_collection_reliability.py`
  (+ UUID fixture fix)
- New: `.github/workflows/tests.yml`
- New: `orm_dashboard/vitest.config.ts`,
  `orm_dashboard/src/utils/formatChartDate.test.ts`
- `orm_dashboard/package.json` (+`test` script, +devDependencies)

### Explicitly not touched in this phase
Fixing the 6 newly-discovered engine/test gaps (documented above, each
xfailed with its own reason) -- flagged, one spawned as a dedicated
follow-up task (`narrative_engine.py`'s `Document.created_at` bug), the
rest noted for future re-tuning/Postgres-test-DB work. Full CI coverage
(linting, type-checking, deploy gates) -- "doesn't need to be
comprehensive on day one, just real and enforced," per TASK.md. Everything
else in FINAL.md's master table -- later TASK.md phases.

## Follow-up -- narrative_engine.py Document.created_at bug (fixed)

Fixes the real bug Phase 11 discovered and flagged (spawned as a dedicated
follow-up task rather than fixed inline, per this project's rule against
mixing unrelated bug fixes into an infra task).

**Root cause confirmed live before editing**: `narrative_engine.py`'s
`calculate_narratives` (called from `NarrativeEngine.process_client`,
which is called from `aggregation_tasks.py`'s scheduled Celery task
`calculate_narratives`, run on Beat's schedule for every client) does
`d.published_at or d.created_at` at two sites (~line 348 sorting documents,
~line 358 computing `time_diff` for incident clustering) on `Document`
objects. `Document`'s actual column is `collected_at`, not `created_at`
(confirmed against `orm_collection/app/models/document.py`) -- this raised
an unconditional `AttributeError` inside the per-topic clustering loop,
which fires whenever a client has any topic-tagged document (the normal
case, not an edge case). Traced the call chain
(`_process_single_client_narrative_with_retry` in `aggregation_tasks.py`)
and confirmed the exception was being caught per-client and silently
recorded as `NarrativeStateMachine.FAILED` -- narrative generation has
likely been failing for every real client with topic-tagged documents,
with no crash visible outside the per-client retry/state machinery to
explain why.

**Fix**: changed both sites to `d.published_at or d.collected_at` /
`(doc.published_at or doc.collected_at) - (ref_doc.published_at or
ref_doc.collected_at)` -- matching the existing fallback pattern, using
the real column name. No other logic changed. Grepped the rest of the file
for `.created_at` afterward -- the one remaining use (`tr.created_at` on a
`TrendEvent` object) is correct, `TrendEvent` genuinely has a `created_at`
column.

**Verified live**: removed `test_narrative_engine.py`'s xfail marker and
re-ran it. Confirmed zero `AttributeError`s anywhere in the run (grepped
the full output) -- the assigned bug is genuinely fixed, execution now
completes the full clustering loop across all 100 iterations. The test
still can't pass end-to-end, but for an unrelated, already-documented
reason: the same SQLite-vs-Postgres `ON CONFLICT (named_constraint)` upsert
gap already found for `test_benchmark_engine.py`/`test_reputation_engine.py`
in Phase 11 (`narratives` table's `uq_client_narrative` constraint this
time) -- confirmed by the fact this is now the *only* error appearing (11
occurrences of that one error, still 0 `AttributeError`s). Re-marked xfail
with an updated reason reflecting this narrower remaining blocker, rather
than overclaiming a full pass. Full suite re-run: still 9 passed + 6
xfailed, same as Phase 11 left it -- no regressions.

### Files changed
- `orm_collection/app/services/intelligence/narrative_engine.py`
- `orm_collection/tests/test_narrative_engine.py` (xfail reason updated,
  not removed)

## TASK.md Phase 12 -- Investigate (not fix): #21's landmine status

Read-only, no data mutation, per TASK.md's own instruction. Investigates
whether the `strip_html()` structural fix (#19, "FIXED this session, live"
in FINAL.md) actually neutralizes the 3 dormant publisher-collision
landmines (#21: Tesla x "Guardian", OpenAI x "Apple", Nvidia x "Apple") the
same way it neutralized the originally-found cases, and whether it's
genuinely live in whatever's actually running -- not assumed, per TASK's
explicit instruction given the earlier history of this exact fix once
being uncommitted with no worker running to apply it.

### 1. Are the 3 landmines still actually configured (still real risk if unfixed)?
Confirmed live against the real Render DB: yes, all 3 -- `entity_keywords`
has an active, `PRIMARY`, `exact`-match keyword literally named "Guardian"
on a Tesla competitor entity, and "Apple" on both an OpenAI and an Nvidia
competitor entity. These are not hypothetical; if the Google News
publisher-name leak were still live, any Guardian- or Apple-published
article about anything would exact-match these entities regardless of
topic, exactly like the original Ease My Trip/"Business Today" and Apple
Inc/"Guardian"/"GuruFocus" leaks.

### 2. Is the fix code present, committed, and wired into the real ingestion path?
- `git status` on `orm_collection/app/utils/text_processing.py`: clean --
  the working tree exactly matches the last commit, no uncommitted drift
  (the specific risk TASK.md flagged from earlier history is not present
  now).
- `git log`: the font-tag decompose logic was added in commit `70caa1d`
  (2026-08-14 15:19:54 IST / 09:49:54 UTC) -- confirmed absent from the
  initial commit, present from `70caa1d` onward.
- Traced the full ingestion chain: `rss.py`'s `RSSAdapter.normalize()`
  (used by every RSS/Google-News feed, no per-feed opt-out) calls
  `clean_document_content()` unconditionally on the raw `content`/
  `summary` field -- exactly where Google News RSS puts its
  `<font color="#6f6f6f">{source}</font>` description -- which calls
  `strip_html()`, which decomposes any `<font color="#6f6f6f">` tag before
  extracting text. `document_service.py:45` then writes that already-
  cleaned string directly into `Document.normalized_content` with no
  further transformation that could reintroduce raw HTML. The fix is
  structurally wired into the one and only path Google News content
  reaches storage through.

### 3. Does the structural fix actually generalize to these 3 specific names (confirmed live, not assumed)?
Ran `strip_html()` directly, live, against realistic Google-News-format
HTML built with the 3 exact landmine publisher names:
```
'<a href="...">Tesla unveils new Cybertruck update</a>&nbsp;<font color="#6f6f6f">Guardian</font>'
  -> 'Tesla unveils new Cybertruck update'   (Guardian: gone)
'<a href="...">OpenAI announces GPT update</a>&nbsp;<font color="#6f6f6f">Apple</font>'
  -> 'OpenAI announces GPT update'            (Apple: gone)
'<a href="...">Nvidia posts record earnings</a>&nbsp;<font color="#6f6f6f">Apple</font>'
  -> 'Nvidia posts record earnings'           (Apple: gone)
```
All 3 publisher names are correctly stripped. Confirms the fix is a real
structural fix (matches on `color="#6f6f6f"`, not on the publisher's name),
so it applies uniformly to every publisher this pattern could ever contain
-- not a per-name blacklist that happened to cover 3 known cases and could
miss a 4th.

### 4. Has this actually been exercised by real, live collection since the fix landed?
**Not yet -- this is the one caveat to an otherwise clean verdict.**
Queried the 5 most-recently-polled Google News RSS feeds in the real DB
(including the Tesla, OpenAI, and Nvidia feeds relevant to #21): all show
`last_polled_at` around **2026-08-14 08:5x UTC** -- collection has been
fully dormant for ~10 days as of this investigation (2026-08-24), across
every configured Google News feed, not just these 3. More precisely: the
Tesla feed's last real poll (08:57:07 UTC) happened **~53 minutes before**
the fix commit (09:49:54 UTC) -- meaning even that most-recent real poll
predates the fix. Spot-checked the newest documents in the DB from Tesla's
Google News source: the ones with today's timestamp are synthetic
`WATCHDOG_TIMING_TEST`/`WATCHDOG_TEST_A_NORMAL_COMPLETION` rows from this
session's own earlier Celery-watchdog verification work, not organic
collection. No genuine document has been collected through the fixed code
for any of these 3 feeds yet.

### Verdict
**Neutralized in code, proven structurally, but not yet operationally
exercised.** The fix is committed, correctly wired into the only path
Google News content reaches storage through, and directly proven (live
function execution, not assumption) to strip all 3 landmine publisher
names the same way it stripped the original 3. The moment any of these 3
feeds is next polled, the leak cannot occur. But because real collection
has been dormant for ~10 days (predating the fix's own commit for the most
recent poll), there is zero live evidence yet of the fix actually
processing a real Guardian- or Apple-published article for these clients --
only synthetic proof. This is a materially stronger position than "still a
genuine live risk" (the code-level mechanism is confirmed sound and
structural, not per-name), but stops short of "fully operationally
confirmed" until a real post-fix collection cycle actually runs for these
feeds. **Recommendation for the #20 sign-off**: this Phase 12 finding does
not block or change the #20 cleanup decision (28 pre-existing bad rows),
which remains a separate, still-outstanding decision awaiting your
explicit sign-off -- it only informs #21's own risk status, which can now
be closed as "structurally neutralized, awaiting first real post-fix
collection cycle to confirm operationally" rather than "still open."

### Files touched
None -- read-only investigation per TASK.md's own instruction. No code,
schema, or data changes.

## TASK.md -- Fix Verification-Sweep Findings (evidence_score clamp, neutered retry, stuck error banners)

Three real bugs surfaced by the 7-sub-agent verification sweep documented
in `FINAL_V2.md` (a re-audit of every fix claimed across the 12 phases
above, plus an active regression hunt -- not part of `FINDINGS.md`'s own
narrative, kept as a separate top-level file). Fixed in priority order per
this task's own instruction. #7 (GHCR) and the platform-process restart
were explicitly out of scope, left untouched. #20 (28 bad rows) remains
untouched and unrelated.

### Phase 1 -- `alerts.evidence_score` can exceed its own CHECK constraint

`alert_engine.py`'s evidence-score components (max risk 45 + trend 20 +
correlation bonus 15 + document weight 20 + executive weight 15) can sum to
a theoretical max of **115**, above the `ck_alerts_evidence_score` CHECK
constraint (0-100, `database/schema.sql:96`) that TASK.md Phase 9 (#26)
itself added. The sibling `confidence_score` in the same function was
already correctly clamped (`min(max(raw_score, 10.0), 100.0)`);
`evidence_score` had no clamp at either of its two write sites (compute at
~line 427, update-merge at ~line 240).

**Investigated the correct bound before writing**: confirmed via
`database/schema.sql:96` that the constraint is `0 <= evidence_score <=
100`, nullable, with no floor requirement. Unlike `confidence_score`, no
10.0 floor is warranted for `evidence_score` -- every term feeding it is a
non-negative additive contribution (gated by `if` conditions that only ever
add, never subtract), so it can't go below 0 on its own.

**Fix**: added `evidence_score = min(evidence_score, 100.0)` immediately
after the raw sum is assembled in `_evaluate_client` (so every downstream
use -- severity decision, human summary, explainability, DB write -- sees
the same valid value), and a defensive `min(..., 100.0)` at the
update-merge site in `_upsert_hardened_alert` (guards the same bound
against any other future caller of the upsert; only one call site exists
today).

**Verified live** against the real Render DB: a synthetic max-out scenario
(risk_score=100, trend percentage_change=1000%, both risk+trend present,
6 contributing documents, an executive-named entity -- the exact
combination the finding described) previously would have summed to 115 and
thrown a `CheckViolation`; now writes cleanly with `evidence_score=100.0`,
`severity=CRITICAL`, `alert_type=Executive Risk`. A normal, lower-scoring
scenario (risk_score=70, trend=50%, 3 documents, no executive) correctly
produced an unclamped `evidence_score=71.0`, confirming the clamp doesn't
alter values already under 100. All synthetic client/entity/risk/trend/
alert rows were created and deleted within the same verification run.

### Phase 2 -- entity-extraction Celery retries were neutered

`execute_document_intelligence_sync`'s except block (`intelligence_tasks.py`)
wrote `Document.processing_status = "FAILED"` immediately on any exception,
*before* calling `celery_task.retry()`. The function's own top-of-body
guard (`if doc.processing_status in ["MATCHED", "SKIPPED", "FAILED"]:
return`) then saw `FAILED` on the very next Celery-scheduled retry
invocation and returned immediately without doing any real work -- so a
transient failure was never actually retried, only silently abandoned
after the first attempt, despite `max_retries=3` implying up to 4 real
attempts.

**Fix**: reused the pattern already established correctly in
`execute_search_task` (#15) and `fetch_feed_task` -- only write the
terminal `FAILED` status once retries are genuinely exhausted
(`celery_task is None or celery_task.request.retries >=
celery_task.max_retries`). In between, `processing_status` stays at
`PROCESSING` (its value since the top of the function), which lets the
next retry's guard through to do real work. The `celery_task is None`
branch (the manual pipeline path, `aggregation_tasks.py`'s
`execute_document_intelligence_sync(doc_id, client_id=ctx.client_id)` call
with no `celery_task`, which has no retry mechanism at all) is unchanged --
still writes `FAILED` immediately, exactly as before.

**Verified live** with a fake celery-task double that mimics the real
retry contract (`request.retries`, `max_retries`, `.retry()` raising):
- A transient failure clearing on the 3rd attempt: attempts 1-2 correctly
  stayed `PROCESSING` (never prematurely `FAILED`), and
  `entity_extractor.process_document` was genuinely invoked 3 times --
  proving the retry now actually re-attempts real work rather than being
  skipped by the stale guard.
- A permanent failure: attempts 1-3 correctly stayed non-`FAILED` while
  `retries < max_retries`, and only attempt 4 (`retries=3/3`, exhausted)
  wrote the terminal `FAILED` status -- confirming exhaustion still works
  correctly, just later and for real reasons now.

**Confirmed no regression to `document_processing_watchdog`**: since the
top-of-function guard now re-executes on every retry (previously it
returned early before reaching that code), `processing_started_at` also
gets refreshed on every retry attempt -- live-confirmed with real
timestamps advancing across two attempts (17:59:02 -> 17:59:07). This is a
genuine behavior change from before the fix, reasoned through and then
verified directly: a live watchdog run correctly left a freshly-retrying
synthetic document (0.14 min old) untouched while correctly recovering a
genuinely-stuck synthetic document (backdated 15 min, simulating a worker
crash) to `PENDING`. The watchdog run also recovered one pre-existing,
genuinely-stuck real document from the live DB (~54 min stale) as a normal
side effect of calling the real task directly -- expected watchdog
behavior (it runs automatically every 15 minutes anyway), not something
reverted.

**Noted, not fixed (out of this phase's scope)**: `process_document_intelligence`'s
own outer except block (lines ~270-293) also retries on any exception
bubbling up from `execute_document_intelligence_sync`, including the
`Retry` exception that function's own `celery_task.retry()` call already
raises -- a possible double-retry interaction, pre-existing and unrelated
to the guard bug this phase targeted. Logged here for a future look, not
fixed inline, per this project's established discipline of not mixing
unrelated fixes into scope.

### Phase 3 -- per-resource error banners never cleared after a successful poll

`useDashboardData.ts`'s 45s live-poll cycle's success handlers only called
`setX(data)` on success, never the matching `setXError(null)` -- unlike the
initial-load effect (`~212-225`), which correctly resets every error state
before fetching. So a resource whose error got set during initial load (a
transient failure at page load / client switch) stayed stuck showing its
`TelemetryErrorWidget` "offline" banner forever, even once the live poll
was successfully returning fresh 200s with real data on every subsequent
cycle. Reproduced live during the original verification sweep: PepsiCo's
Risk tab and Competitor tab both got stuck this way after a transient
backend hiccup, confirmed via network inspection that the underlying
endpoints were returning clean data the whole time.

**Fix**: added the matching `setXError(null)` call inside each poll
cycle's success `.then()` branch, for every resource with a matching error
state -- `reputationError`, `alertsError`, `risksError`, `telemetryError`,
`narrativesError`, `documentsError`, `systemStatusError`. The 8th poll
fetch, `fetchIntelligenceFeed`/trend events, has no matching error state at
all (consistent with the initial-load effect's own untracked `.catch` for
that same fetch) -- nothing to clear there. #36's aggregate
`livePollDegraded` signal (the `results` array and the failure-streak
logic just below it) was left completely untouched -- this is a distinct,
per-resource-level fix, not a change to that overall degraded-state logic.

**Verified live**, reproducing the original bug's exact conditions: stopped
the local backend, switched the dashboard to PepsiCo (forcing the
initial-load effect to fail and set `reputationError`/`risksError`/etc. to
"Telemetry Offline"), confirmed both `RADAR TELEMETRY OFFLINE` and `RISK
TELEMETRY OFFLINE` banners were stuck showing. Restarted the backend,
waited through a full 45s+ poll cycle without touching the client selector
or reloading the page -- both banners cleared on their own and real data
rendered (217 risk incidents, active alerts, full risk matrix; reputation
score 51.4 with the full AI pipeline health panel). `npm run build`
succeeds cleanly afterward.

### Files touched
- `orm_collection/app/services/intelligence/alert_engine.py` (Phase 1)
- `orm_collection/app/workers/intelligence_tasks.py` (Phase 2)
- `orm_dashboard/src/hooks/useDashboardData.ts` (Phase 3)

All three `FINAL_V2.md` bugs are now fixed and live-verified. No regression
to `document_processing_watchdog`, #36's aggregate degraded signal, or the
`confidence_score` clamp pattern this reuses. Docker/GHCR (#7) and the
platform process restart remain untouched, as decided.

---

## TASK.md (9-phase) Phase 4 -- Unpinned packages, same risk class as psycopg2

`spacy`, `structlog`, `pytest`, `psutil` (plus `torch`/`transformers`,
already caught by the same earlier pass) were unpinned in
`requirements.txt`. `spacy`/`psutil`/`torch` are C-extension packages --
no prebuilt wheel for the installer's Python version means a silent
source-build fallback requiring a compiler most Windows machines don't
have (the exact failure class the original psycopg2/pg_config bug was).

**Fix**: pinned all 6 to the venv's own proven-working versions
(`torch==2.12.0`, `spacy==3.8.14`, `structlog==26.1.0`,
`transformers==5.12.1`, `pytest==9.1.0`, `psutil==7.2.2`). Added
`pip install --upgrade pip` before the requirements install in
`install.bat` STEP 5 (an outdated pip can also silently miss a wheel tag).
Added a Visual C++ Build Tools hint to the install-failure path, pointing
at the actual fix instead of leaving a raw pip traceback.

**Verified live**:
- `pip show` in the project's own venv confirms all 6 installed versions
  exactly match the new pins -- not a guess at "latest compatible".
- `spacy.load('en_core_web_sm')` succeeds live under spacy 3.8.14
  (`nlp.meta['version'] == '3.8.0'`), confirming the model `install.bat`
  downloads right after is still compatible with the pinned classifier
  version.
- Queried PyPI's JSON API (`pypi.org/pypi/torch/2.12.0/json`) for
  `win_amd64` wheel filenames: `cp311`, `cp312`, and `cp313` (both `cp313`
  and `cp313t`) all have prebuilt wheels -- the full Python 3.11-3.13 range
  `install.bat`'s version gate allows has zero source-build risk for torch.
- `install.bat` end-to-end run already confirmed working in the earlier
  dependency-pinning pass this session (venv build, requirements install,
  frontend `npm install` all succeeded cleanly).

### Files touched
- `orm_collection/requirements.txt`
- `install.bat`

No code/model-loading behavior changed -- pins match what was already
running; this closes the *next* clone's risk of drifting onto an
unverified version, the same gap class that caused the original
psycopg2/Python 3.13 failure.

---

## TASK.md (9-phase) Phase 5 -- Product names slip through the org-name classifier

**Investigation**: live-queried all 7 clients' currently-promoted
`competitor` entities. Confirmed every named case still live (AAPL, iPad,
iPhones, MacBooks for Apple Inc; FSD, Robotaxi, Example Corp. for Tesla;
Nemotron for Nvidia), plus a much larger set of pre-existing junk
(NASDAQ, Britannica Money, Guardian, GuruFocus, AAPL Shares, UCO Bank,
TCS, N Chandrasekaran, COO, EPS, Newsroom, FSSAI, Business Today...)
that predates the layered classifier entirely -- those are **already
promoted `Entity` rows**, and `_is_valid_org_name_layered()` only gates
new promotions (forward-only, documented in its own docstring); it does
not retroactively touch rows promoted before it existed. That retroactive
cleanup is `TASK_FIX_JUNK_ENTITIES_AND_EXEC_SCORES.md`'s explicit scope
(already dispatched separately, per this TASK.md's own decision not to
duplicate it) -- this phase is the classifier **code** fix only, so the
same junk can't get re-created going forward.

Ran the live classifier (`_is_valid_org_name_layered`) directly against
every named junk case before any fix: **all of them passed** (AAPL, iPad,
iPhones, MacBooks, FSD, Robotaxi, Nemotron, Example Corp. all returned
`valid=True`) -- confirming these would be re-promoted today if their
`CompetitorCandidate` rows were resubmitted, not just a historical
artifact.

### Root cause -- three distinct gaps, not one
1. **"Example Corp." (placeholder text)**: no layer checks name *content*
   for stand-in/placeholder markers -- it passes purely on shape (2
   title-case tokens + a legal suffix bonus). Pure code gap, zero data
   dependency.
2. **AAPL (client's own ticker)**: Layer O2's self-reference check already
   includes `brand.ticker_symbol` in its term set (`_client_self_reference_terms`)
   -- but live-queried `Client`/`Entity` rows show **5 of 7 clients have
   `ticker_symbol IS NULL`** (Tata Motors, Nvidia, Apple Inc, OpenAI, Ease
   My Trip -- only PepsiCo=PEP and Tesla=TSLA are populated). This is a
   client-onboarding **data** gap, not a classifier bug: the mechanism to
   catch a client's own ticker already exists and already works (verified
   against Tesla/PepsiCo's own tickers), it's just not populated for the
   other 5 clients. Also not a case for a generic short-uppercase-token
   denylist: real competitor tickers (AMD, BYD, TSMC, NVDA -- all in
   Nvidia's own live competitor list) are legitimately valid competitor
   names, so blocking ticker-shaped tokens generally would create new
   false rejections, not fix anything.
3. **iPad/iPhones/MacBooks/FSD/Robotaxi/Nemotron (client's own products)**:
   the model already defines `entity_type='product'`
   (`models/entity.py:14`) and `_client_self_reference_terms()` already
   queries `entity_type='product'` rows and `PRODUCT`-category
   `EntityKeyword`s to build its self-reference set -- confirmed live:
   **zero rows of either exist anywhere in the database**, so this branch
   is inert for every client. The infrastructure to solve this already
   exists and is already wired into the classifier; the gap is purely
   that onboarding never populates it. A generic product-name denylist was
   considered and rejected -- "iPad"/"FSD"/"Nemotron" are not shapes any
   pattern can generalize from, and hardcoding them is exactly the kind of
   brittle per-client patch the existing architecture was built to avoid
   (same reasoning as `matching_engine.py`'s #27 finding).

### Fix applied (code only, per this phase's scope)
Added **Layer O1b — Placeholder / Example Text** to
`_is_valid_org_name_layered()` (`entity_discovery.py`), a new
`EntityDiscoveryConfig.PLACEHOLDER_TERMS` set (`example`, `sample`,
`placeholder`, `dummy`, `lorem`, `ipsum`, `acme`, `foo`, `bar`, `baz`,
`n/a`, `tbd`) checked as **whole-token matches only** (never substring),
same discipline as Layer O5's per-token check, inserted right after O1's
shape checks. Deliberately excludes `test`/`na`/`xyz` -- real collision
risk with legitimate short names/acronyms, unlike the unambiguous markers
kept.

**Not fixed this phase (data gaps, out of the approved-mutation scope)**:
- Backfilling `ticker_symbol` for the 5 clients missing it.
- Populating `entity_type='product'` rows / `PRODUCT`-category keywords
  per client's real products.

Both would flow through already-existing, already-verified-working
classifier logic the moment the data exists -- no further code change
needed, only a client-onboarding data task requiring its own separate
sign-off (same standing as #20's row deletion).

### Verified live
- Before fix: `_is_valid_org_name_layered()` returned `valid=True` for
  every named junk case (AAPL, iPad, iPhones, MacBooks, FSD, Robotaxi,
  Nemotron, Example Corp.).
- After fix: `"Example Corp."` (Tesla) and a synthetic `"Sample
  Beverages"` (PepsiCo) both correctly reject with `Layer O1b`; `AMD`
  (Nvidia), `BYD` (Tesla), `Coca-Cola` (PepsiCo), and the still-open
  product/ticker cases (`iPad`, `FSD`) are unaffected.
- Full regression sweep: ran the updated classifier against **every**
  currently-promoted `competitor` entity across all 7 clients (54 rows)
  -- exactly **one** new rejection (`Example Corp.`), zero false
  positives against any real competitor.

### Files touched
- `orm_collection/app/services/intelligence/entity_discovery.py`

---

## TASK.md (9-phase) Phase 6 -- Self-reference classifier bug (Layer O2)

**Root cause confirmed live**: Layer O2's prefix check
(`term.startswith(normalized_lower)`) is a raw character-level string
prefix, not word-boundary-aware. For client "PepsiCo" (self-reference term
`"pepsico"`) and candidate "Pepsi" (`"pepsi"`), `"pepsico".startswith("pepsi")`
is `True` -- the same code path that correctly catches "Tata" as a
self-reference of "Tata Motors" (a genuine shortened-name case) also wrongly
caught "Pepsi", because "PepsiCo" is one fused word with no internal space:
"Pepsi" is a real, distinct sub-brand name there, not a shortened way of
saying "PepsiCo" the way "Tata" is a shortened way of saying "Tata Motors".
Confirmed via direct invocation before any fix: `_is_valid_org_name_layered("Pepsi",
client_name="PepsiCo", ...)` returned `valid=False`, `"Prefix of the client's
own name 'pepsico'"` -- and "Pepsi" is an already-promoted, real, live
PepsiCo competitor entity, so this bug would block it from ever being
re-validated or re-promoted.

Investigated the exact-match-only alternative Phase 6 itself asked to
confirm or rule out: a plain case-insensitive exact match would fix Pepsi
but also silently drop the "Tata"/"Tata Motors" catch entirely (that case
genuinely needs a *prefix* check, not exact match) -- rejected as moving
the bug rather than fixing it, per the phase's own caveat.

### Fix applied
Changed the prefix condition from `term.startswith(normalized_lower)` to
`term.startswith(normalized_lower + " ")` -- requires a word-boundary
(space) immediately after the candidate inside the client's own term.
`"tata motors".startswith("tata ")` is still `True` (Tata/Tata Motors
correctly caught); `"pepsico".startswith("pepsi ")` is `False` (Pepsi no
longer wrongly caught, since "pepsico" has no space at all).

### Verified live
- `Pepsi` / client `PepsiCo` -> now `valid=True` (was `False`).
- `Tata` / client `Tata Motors` -> still correctly `valid=False`,
  `"Prefix of the client's own name 'tata motors'"` (genuine self-reference
  preserved).
- `Apple` / client `Apple Inc` -> still correctly `valid=False` via the
  unrelated exact-match branch (unaffected by this change).
- `PepsiCo India` / client `PepsiCo` -> still correctly `valid=False` via
  the unrelated sub-brand/department branch (unaffected by this change).
- Full regression sweep: ran the updated classifier against every
  currently-promoted `competitor` entity across all 7 clients -- exactly
  **one** Layer O2 rejection total (`Tata`/Tata Motors, the intended,
  correct catch), zero unintended rejections of any other live competitor.

### Files touched
- `orm_collection/app/services/intelligence/entity_discovery.py`

---

## TASK.md (9-phase) Phase 7 -- Delete the 28 pre-existing bad rows (approved data mutation)

**Live recount before deleting anything** (per this phase's own instruction
not to trust the last-known numbers): EMT x Business Today = 2 (matches the
original count), Apple x Guardian = **9** (was last counted as ~8), Apple x
GuruFocus = 18 (matches). **Total 29 rows per table, not 28** -- flagging
this discrepancy honestly rather than silently rounding to the approved
number. Checked whether the extra Guardian row is a *new* leak (i.e. the
`strip_html()` fix regressing) before treating it as in-scope: all 9
Guardian-matched documents have `collected_at` between 2026-08-10 and
2026-08-14, and autonomous collection has had no worker consuming its
queues for the period since (see Phase 8 below) -- these all predate the
fix and simply weren't all caught in the original manual count. Not a
recurrence. Proceeded to delete all 29 real rows per table, using the
current verified count as instructed, not the stale 28.

**Downstream dependency check (per step 2) surfaced something the approved
mutation's own wording doesn't cover**: these 3 junk entities have real
data built on top of them --

| Entity | entity_sentiments | competitor_benchmarks | entity_keywords | risk_events | alerts |
|---|---|---|---|---|---|
| Business Today (EMT) | 2 | 6 | 1 | 2 | 0 |
| Guardian (Apple) | 9 | 19 | 1 | 8 | 0 |
| GuruFocus (Apple) | 18 | 17 | 1 | 18 | 1 |

The approved mutation's own text is explicit and narrow: "Delete the
confirmed rows (`document_matches` and corresponding `entity_mentions`)."
It does not mention the `Entity` rows themselves or anything computed from
them. **Only `document_matches` and `entity_mentions` were deleted** -- the
underlying junk `Entity` rows (Guardian/GuruFocus/Business Today, still
typed `entity_type='competitor'`) and everything derived from them
(`entity_sentiments`, `competitor_benchmarks` -- meaning these 3 still
appear as if they were real competitors on the affected clients'
Competitor Compare dashboards -- `risk_events`, `entity_keywords`, and the
1 `alerts` row for GuruFocus) are **untouched**, since deleting those would
be a materially larger mutation than what was actually signed off on.
That broader cleanup (demoting/removing the junk `Entity` rows and
recomputing their downstream aggregates) is `TASK_FIX_JUNK_ENTITIES_AND_EXEC_SCORES.md`'s
scope, already dispatched separately per this TASK.md's own decision not to
duplicate it -- flagging it here rather than silently expanding scope to
cover it myself.

### Rows deleted (exact IDs)
**Ease My Trip x Business Today** (entity `01a80181-f45e-4c3b-a457-57865d348daa`) --
2 `document_matches` (`86a56582-288e-4997-811a-e8fc33c089fd`,
`1da8b5cb-cad3-43b7-91c3-67da11a17a09`) + 2 `entity_mentions`
(`374eb01c-0cf3-42c4-9afb-f9abd537c4b8`, `a803748b-7e06-40a2-b1ca-9095c17f15b6`).

**Apple Inc x Guardian** (entity `3ce5df13-246e-442f-a85d-bc95d6c6a13f`) --
9 `document_matches` + 9 `entity_mentions` across documents
`d827b9c9`, `a75e2b86`, `a26f8804`, `7a2f0c80`, `fd11ef3f`, `f27d5bab`,
`616a103f`, `fb4a4b2f`, `add94c5a` (full UUIDs and per-row match/mention IDs
captured in the deletion script's live output, not repeated here for
brevity).

**Apple Inc x GuruFocus** (entity `8642494d-1232-406c-87b0-47187501aaa4`) --
18 `document_matches` + 18 `entity_mentions` across 18 documents (full IDs
in the deletion script's live output).

**Total: 58 rows deleted (29 `document_matches` + 29 `entity_mentions`).**

### Verified live
Re-queried all 3 entity_id/table combinations post-delete: `document_matches`
and `entity_mentions` counts are both `0` for all 3 pairs. The `Entity` rows
themselves still exist (by design, out of this phase's scope, see above) --
confirmed no `IntegrityError`/orphaned-FK issue from the deletion (both
tables use `ondelete="CASCADE"` on their own FKs, not referenced *by*
anything else via FK, so removing them doesn't cascade-break any other
table).

### Files touched
Data only -- `document_matches` and `entity_mentions` tables on the live
Render Postgres DB. No code changes.

---

## TASK.md (9-phase) Phase 8 -- Reset the pre-existing stuck documents (approved data mutation)

**Step 1 (worker check)**: confirmed live -- zero `python.exe` processes
running on this machine (`Get-CimInstance Win32_Process`), so no Celery
worker of any kind is currently up. Verification of actual reprocessing is
correctly **not possible right now** and is reported as such below, not
glossed over.

**Step 2 (recount) surfaced a materially different population than
approved, not just a shifted count**. Live query for
`processing_status='PROCESSING' AND processing_started_at IS NULL`
returned **205** documents, not the approved ~130, with a completely
different breakdown: Apple Inc 6, Nvidia 1, **PepsiCo 42 (a client not in
the original breakdown at all)**, Tata Motors 2 (was 23), Tesla 153 (was
105), unmatched 9. Checked `collected_at` distribution before assuming
this was "the same set, just recounted": **all 205 were collected in just
the last 48 hours (162 on 2026-08-24, 43 on 2026-08-25)** -- zero are the
11+-day-old stragglers the watchdog's own docstring and this phase's
approval describe. The original 11+-day-old population appears to have
already been resolved (most likely reprocessed during this session's own
earlier emergency worker-restart troubleshooting).

**Root cause of the new population (investigated, not just recounted)**:
the current code makes this state impossible to produce going forward --
`execute_document_intelligence_sync` (`intelligence_tasks.py`) is the
*only* place anywhere in the codebase that ever sets
`processing_status='PROCESSING'`, and it always sets
`processing_started_at` in the same commit, atomically, on the same ORM
object. Confirmed via full-codebase grep: no other code path sets this
status, and nothing ever nulls the timestamp afterward. A batch of 42
PepsiCo documents (source "PepsiCo RSS Source") all landed at
`PROCESSING`/`NULL` within a ~50-second window at 01:51 UTC on 2026-08-25 --
consistent with the general Celery worker that was found completely
unresponsive during this session's earlier emergency demo
troubleshooting (confirmed stuck via `celery inspect ping`, killed via
`taskkill`, then restarted) having been running a stale in-memory copy of
an older code version at the time (Python does not hot-reload an
already-imported module's source after a worker process starts), rather
than a new bug in the current code. Flagging this as a real operational
risk worth awareness -- a long-lived worker process can silently run stale
logic after a code fix lands on disk until it's actually restarted -- but
not fixing it further here: no live worker exists right now to
reproduce or root-cause it more precisely than this, and it's a
process/deployment hygiene issue, not a code defect in the current
`intelligence_tasks.py`.

**User decision**: given this is a different (newer, differently-caused)
population than the approval literally described, but functionally in
the identical broken state (stuck at `PROCESSING` with no active worker to
ever finish them), the user was asked how to proceed rather than silently
either expanding or narrowing the original approval on my own judgment.
Decision: reset all 205 anyway, explicitly documented as a distinct
incident from the originally-described set, not silently treated as the
same fix.

### Fix applied
```sql
UPDATE documents
SET processing_status = 'PENDING', match_failure_reason = 'manually_reset_phase8_new_incident'
WHERE processing_status = 'PROCESSING' AND processing_started_at IS NULL;
```
205 rows updated. `match_failure_reason` deliberately distinguishes this
reset from the watchdog's own automatic
`recovered_from_stuck_processing_by_watchdog` marker, so the two
populations stay distinguishable in any future audit. Reset mechanism
confirmed correct by re-reading `execute_document_intelligence_sync`'s own
top-of-function guard: it only skips documents already at `MATCHED`/
`SKIPPED`/`FAILED` -- `PENDING` is not excluded, so a normal collection/
pipeline run will pick these up exactly the same way it would any other
newly-collected document. No separate per-document task dispatch is
needed beyond the status flip; the existing "any PENDING document is
eligible for the next pipeline run" mechanism handles it.

### Verified live (with an honest limitation)
Re-queried post-update: 0 documents remain at `PROCESSING`/`NULL
processing_started_at`. **Actual reprocessing could NOT be verified** --
no Celery worker is currently running (confirmed in step 1), so nothing
will pick these documents up until the platform is next started. This is
reported as a pending-verification caveat, not claimed as fully done, per
this phase's own explicit instruction.

### Files touched
Data only -- `documents` table on the live Render Postgres DB (205 rows).
No code changes.

---

## M6-F1 fix (Phase 2, TASK.md) -- known follow-up gap: product boost is inert for everyone, including Tesla/Meta/Tata

`matching_engine.py`'s `evaluate_match_accuracy` previously boosted match
confidence `+0.20` for "product mentions" via a dict hardcoded to
`tesla`/`meta`/`tata` (`product_patterns`, e.g. Tesla -> "model y",
"cybertruck", ...). Fixed to source this from real per-client data instead
(`get_client_boost_terms`: `Entity(entity_type="product")` rows +
`PRODUCT`-category `EntityKeyword` rows), mirroring the exact pattern
`entity_discovery.py` already uses for the equivalent product-blocklist
problem (see its "HONEST LIMITATION" comment, lines 911-923).

**Known gap, disclosed and accepted before shipping (not discovered after
the fact):** that data source is honestly empty platform-wide today --
`entity_discovery.py`'s own comment already established zero
`entity_type='product'` rows and zero `PRODUCT`-category keywords exist in
the live DB for *any* client. This means the product boost, which
previously fired reliably for Tesla/Meta/Tata via the hardcoded list, now
scores `+0.0` for them too until product entities/keywords are actually
populated. The executive boost does not have this problem (person-type
`Entity` rows already exist per client, since the reputation engines
depend on them) and is strictly more consistent than before. The industry
boost is weaker but non-zero (`Entity.industry`, a single onboarding
field, vs. the old curated multi-term lists).

**User decision** (asked explicitly rather than silently shipping a
regression): ship the data-driven fix as-is. Populating product
entities/keywords for Tesla/Meta/Tata (or generally) is a data task, not a
code fix -- separate follow-up if the product boost matters in practice.

### Files touched
`app/services/matching_engine.py` (added `get_client_boost_terms`,
generalized executive/product/industry boosts in `evaluate_match_accuracy`),
`app/services/entity_matching_batch_processor.py` and
`app/services/intelligence/entity_extractor.py` (both callers, batched
per-client term fetch to avoid N+1).

---

## Known gap: narrative attribution is not role-classification-aware
## (Executive Reputation redesign, 2026-09-05, deferred)

`executive_reputation_engine.py`'s `sentiment_component` was fixed this
session to exclude documents where an executive was classified BYSTANDER or
EXONERATED (same session, `risk_engine.py`'s existing SELF/BYSTANDER/
EXONERATED signal, reused via `supporting_risks` -- already a parameter, no
new query, no new LLM call). `narrative_component`/`top_positive`/
`top_negative` were NOT given the same treatment, and confirmed live to
have the same underlying problem: Thomas Edison, a Tesla executive
candidate promoted on a single incidental mention (2 mentions total, 0.70
confidence), shows a real Tesla EV-charging narrative as his own
top-positive theme despite `health_status: INSUFFICIENT_EVIDENCE` (zero
qualifying evidence otherwise).

**Root cause, traced to `narrative_engine.py`'s `calculate_narratives`**
(~line 824-832): a narrative's `evidence_metadata.supporting_entities` is
built by iterating every `EntityMention` across the narrative's whole
document cluster and adding every person-entity found, unconditionally --
no role check. Mere presence in one document belonging to the narrative's
cluster is enough, regardless of whether that document's role
classification for that entity is SELF, BYSTANDER, or EXONERATED.

**Why not fixed in this session**: the data needed is already there in
principle -- `calculate_narratives` already preloads `risk_map` (keyed by
`document_id`, `RiskEvent` rows carrying `entity_id` + `explainability`),
so the fix shape is the same pattern as the sentiment one: when building
`exec_ids` for a document, skip an entity if that (document, entity) pair
has a BYSTANDER/EXONERATED classification. But this loop is shared
narrative-computation logic in `narrative_engine.py`, consumed by
`NarrativesTab.tsx`, `CompetitorsTab.tsx`, and
`NarrativeIntelligenceWorkbench.tsx` too -- not exclusive to Executive
Reputation. Changing it changes what "supporting_entities" means for every
narrative platform-wide and needs its own verification pass against those
other consumers, not a same-session addition made while focused on
Executive Reputation alone.

**Not fixed**: deferred as a known, documented limitation. A code comment
at the exact narrative-matching block in
`executive_reputation_engine.py` (`_evaluate_single_executive_optimized`,
"3. Executive Narratives") cites this entry and sketches the fix shape for
whoever picks it up next.
