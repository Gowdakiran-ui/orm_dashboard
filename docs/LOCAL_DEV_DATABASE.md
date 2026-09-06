# Local development: use a throwaway local Postgres, never the production DB

## Decision

**Local development must point at a local/throwaway Postgres instance, not
the live production database.** `orm_collection/.env`'s `DATABASE_URL` was
found (2026-09-06) pointing directly at the production DigitalOcean-managed
Postgres instance — the same database backing the live app on xoop-prod
(167.99.232.206). This was not a deliberate, reviewed choice; it had simply
been left that way, and every local `pytest`/manual script run against it
was a live write to production data.

This is not hypothetical risk — it already caused a real incident the same
night this was found: a local test of the new YouTube collection adapter
(before a guard condition was added) wrote a stale `SearchCursor` row
directly into the production `search_cursors` table for a real client
(Godrej Properties), requiring a manual `DELETE` to clean up. A less
carefully-run local test — or one run by someone without a session
watching for exactly this — could just as easily have written bad
`Document`/`Client`/`Entity` rows, corrupted the matching engine's index, or
burned a shared, metered API quota (YouTube, Reddit) against the platform's
real daily budget instead of a disposable one.

`REDIS_URL` in the same `.env` already points at local Redis — this fix
brings Postgres in line with that, not the other way around.

## How to point local dev at a throwaway Postgres instead

1. Start a disposable local Postgres (no docker-compose service exists for
   this yet — spin one up directly):
   ```bash
   docker run --name orm_local_pg -e POSTGRES_PASSWORD=localdev \
     -e POSTGRES_DB=orm_local -p 5433:5432 -d postgres:16
   ```
   (Port 5433, not 5432, so it doesn't collide with a system-wide Postgres
   install if one exists.)

2. Apply the schema (source of truth, kept in sync with production via
   `pg_dump --schema-only` — see `database/schema.sql`'s own header):
   ```bash
   psql postgresql://postgres:localdev@localhost:5433/orm_local -f database/schema.sql
   ```

3. Optionally seed it with representative dev data instead of starting
   empty:
   ```bash
   psql postgresql://postgres:localdev@localhost:5433/orm_local -f database/seed_dev.sql
   ```

4. Point `orm_collection/.env` at it — comment out (or delete) the
   `DATABASE_URL=...` line that overrides to the DigitalOcean instance, and
   set the discrete fields instead:
   ```
   DB_HOST=localhost
   DB_PORT=5433
   DB_USER=postgres
   DB_PASSWORD=localdev
   DB_NAME=orm_local
   ```
   (`app/core/config.py`'s `DATABASE_URL` property already falls back to
   these discrete fields whenever `DATABASE_URL_OVERRIDE`/`DATABASE_URL`
   isn't set — no code change needed, this is purely an `.env` edit.)

5. When you actually need to test against real production data or scale
   (e.g. verifying a change behaves correctly against the full real
   dataset), do that deliberately and explicitly — SSH to the droplet and
   use an already-running container's own DB session (see root `CLAUDE.md`
   — "PRODUCTION DROPLET ACCESS"), not by pointing a local `.env` at it.

## Status

Documented and proposed here; **not yet executed** on this machine (Docker
Desktop wasn't running at the time this was written). `orm_collection/.env`
still points at production as of this writing. Whoever picks this up next
should run the steps above once, then this file's job is done — treat it as
a one-time setup note, not a standing process.
