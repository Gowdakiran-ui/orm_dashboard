"""Start a client's pipeline run without a web login session (admin tool). Same code path as the Run Pipeline button.

It calls app.services.pipeline_service.start_pipeline_run, the function behind POST /clients/{id}/pipeline/run, so the run it creates is
identical (a QUEUED PipelineRun, then run_client_pipeline dispatched) and the same refusals apply: unknown client, a run already active for
the client, or another client's run active (MAX_CONCURRENT_PIPELINE_RUNS, default 1).

Nothing starts unless you pass --start; without it the tool only reports whether a run would be accepted right now (read-only).
Run it inside the backend container (it needs the app code and the database session):

    docker exec -i orm_dashboard-backend-1 python3 - "Adani Group"          < scripts/run_pipeline.py          # check only
    docker exec -i orm_dashboard-backend-1 python3 - "Adani Group" --start  < scripts/run_pipeline.py          # start the run

The client can be given by name or by id. Exit codes: 0 ok (accepted / would be accepted), 2 usage, 3 refused (409), 4 client not found,
5 broker unreachable.
"""
import sys

from sqlalchemy import text

from app.core.db import SessionLocal
from app.services.pipeline_service import PipelineStartError, active_runs, check_can_start, start_pipeline_run

args = [a for a in sys.argv[1:] if not a.startswith("--")]
start = "--start" in sys.argv[1:]
if len(args) != 1:
    sys.exit('usage: python3 - "<client name or id>" [--start] < scripts/run_pipeline.py')

db = SessionLocal()
rows = db.execute(text("select id, name from clients where id::text = :r or name ilike :r"), {"r": args[0]}).fetchall()
if len(rows) != 1:
    print(f"client {args[0]!r} matched {len(rows)} client(s): {[r.name for r in rows]}")
    sys.exit(4)
client_id, client_name = rows[0].id, rows[0].name

running = [(str(r.client_id), r.run_id[:8], r.stage) for r in active_runs(db)]
print(f"Client: {client_name} ({client_id}). Active runs right now: {running or 'none'}")

if not start:
    refusal = check_can_start(db, client_id)
    db.rollback()
    if refusal:
        print(f"WOULD BE REFUSED ({refusal.status_code}): {refusal.detail}")
        sys.exit(3 if refusal.status_code == 409 else 4)
    print("WOULD BE ACCEPTED. Nothing was started (add --start to start it).")
    sys.exit(0)

try:
    result = start_pipeline_run(db, client_id)
except PipelineStartError as exc:
    print(f"REFUSED ({exc.status_code}): {exc.detail}")
    sys.exit({404: 4, 409: 3, 503: 5}.get(exc.status_code, 3))
print(f"QUEUED run {result['run_id']} for {result['client_name']}")
db.close()
