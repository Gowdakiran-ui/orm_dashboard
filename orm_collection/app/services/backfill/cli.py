"""
CLI entry point for the one-time historical backfill.

  python -m app.services.backfill.cli --client "Godrej Properties" --dry-run [--probe 12]
  python -m app.services.backfill.cli --client "Godrej Properties" --run-inline --max-slices 20
  python -m app.services.backfill.cli --client "Godrej Properties" --enqueue
  python -m app.services.backfill.cli --client "Godrej Properties" --status
  python -m app.services.backfill.cli --client "Godrej Properties" --continue-processing [--limit 500]
  python -m app.services.backfill.cli --stop            # Redis stop switch: all backfill work stops within one slice/tick
  python -m app.services.backfill.cli --clear-stop
  python -m app.services.backfill.cli --collect-only-on   # save PENDING, never hand documents to NLP (no restart needed)
  python -m app.services.backfill.cli --collect-only-off

--dry-run is read-only (no DB writes, no paid calls); --probe N adds up to N free Google News GETs to
measure items per slice. --enqueue sends the Celery task. --continue-processing hands the next --limit
(default 500) PENDING backfilled documents of that client to NLP in priority order, past the per-client cap.
"""
import argparse
import datetime as dt
import json
import sys

from app.core.db import SessionLocal
from app.models.client import Client
from app.services.backfill.engine import BackfillConfig, dry_run, run_client


def _find_client(db, ident: str):
    q = db.query(Client)
    return q.filter(Client.id == ident).first() if len(ident) == 36 else q.filter(Client.name == ident).first()


def status(db, client) -> dict:
    from sqlalchemy import text
    from app.services.backfill import control, processing, settings as bf_settings
    rows = db.execute(text("select source,status,count(*) from backfill_slices where client_id=:c group by 1,2 order by 1,2"),
                      {"c": client.id}).fetchall()
    return {
        "client": client.name,
        "slices": [{"source": r[0], "status": r[1], "count": r[2]} for r in rows],
        "docs_handed_to_nlp": processing.processed_count(db, client.id),
        "docs_pending": processing.pending_count(db, client.id),
        "process_cap": bf_settings.MAX_PROCESS_DOCS_PER_CLIENT,
        "stop_switch_on": control.is_stopped(),
        "collect_only_on": control.is_collect_only(),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", help="client name or id")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--sources", default="google_news,youtube,gdelt,hn")
    ap.add_argument("--include-competitors", action="store_true")
    ap.add_argument("--include-products", action="store_true")
    ap.add_argument("--exclude-entity", action="append", default=[])
    ap.add_argument("--no-relevance-filter", action="store_true", help="keep items that name neither the brand nor a tracked entity")
    ap.add_argument("--youtube-start-year", type=int, default=None)
    ap.add_argument("--youtube-budget", type=int, default=None)
    ap.add_argument("--max-slices", type=int, default=200)
    ap.add_argument("--probe", type=int, default=0)
    ap.add_argument("--limit", type=int, default=500, help="with --continue-processing: documents to hand to NLP")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run-inline", action="store_true")
    g.add_argument("--enqueue", action="store_true")
    g.add_argument("--status", action="store_true")
    g.add_argument("--continue-processing", action="store_true")
    g.add_argument("--stop", action="store_true")
    g.add_argument("--clear-stop", action="store_true")
    g.add_argument("--collect-only-on", action="store_true")
    g.add_argument("--collect-only-off", action="store_true")
    a = ap.parse_args(argv)

    if a.stop or a.clear_stop:
        from app.services.backfill import control
        (control.set_stopped if a.stop else control.clear_stopped)()
        print(json.dumps({"stop_switch_on": control.is_stopped()}))
        return 0
    if a.collect_only_on or a.collect_only_off:
        from app.services.backfill import control
        (control.set_collect_only if a.collect_only_on else control.clear_collect_only)()
        print(json.dumps({"collect_only_on": control.is_collect_only()}))
        return 0
    if not a.client:
        print("--client is required for this command", file=sys.stderr)
        return 2

    from app.services.backfill import settings as bf_settings
    cfg = BackfillConfig(
        start=dt.date.fromisoformat(a.start), sources=tuple(s for s in a.sources.split(",") if s),
        include_competitors=a.include_competitors, include_products=a.include_products,
        exclude_entities=tuple(a.exclude_entity),
        youtube_units_budget=a.youtube_budget if a.youtube_budget is not None else bf_settings.YOUTUBE_RUN_BUDGET,
        youtube_start_year=a.youtube_start_year if a.youtube_start_year is not None else bf_settings.YOUTUBE_START_YEAR,
        max_slices_per_run=a.max_slices, relevance_filter=not a.no_relevance_filter,
    )
    db = SessionLocal()
    try:
        client = _find_client(db, a.client)
        if not client:
            print(f"client not found: {a.client}", file=sys.stderr)
            return 2
        if a.dry_run:
            print(json.dumps(dry_run(db, client.id, cfg, probe=a.probe), indent=1, default=str))
        elif a.run_inline:
            print(json.dumps(run_client(db, client.id, cfg), indent=1, default=str))
        elif a.status:
            print(json.dumps(status(db, client), indent=1, default=str))
        elif a.continue_processing:
            from app.services.backfill import processing
            res = processing.dispatch(db, client.id, a.limit, respect_cap=False)
            print(json.dumps({"client": client.name, **res}))
        else:
            from app.core.celery_app import celery_app
            r = celery_app.send_task("app.workers.backfill_tasks.run_client_backfill", args=[str(client.id), cfg.to_dict(), 0])
            print(json.dumps({"enqueued": r.id, "client": client.name}))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
