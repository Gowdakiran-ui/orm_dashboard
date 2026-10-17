"""
CLI entry point for the one-time historical backfill.

  python -m app.services.backfill.cli --client "Godrej Properties" --dry-run [--probe 12]
  python -m app.services.backfill.cli --client "Godrej Properties" --run-inline --max-slices 20
  python -m app.services.backfill.cli --client "Godrej Properties" --enqueue

--dry-run is read-only (no DB writes, no paid calls); --probe N adds up to N free
Google News GETs to measure items per slice. --enqueue sends the Celery task.
"""
import argparse
import datetime as dt
import json
import sys

from app.core.db import SessionLocal
from app.models.client import Client
from app.services.backfill.engine import BackfillConfig, dry_run, run_client


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True, help="client name or id")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--sources", default="google_news,youtube,gdelt,hn")
    ap.add_argument("--include-competitors", action="store_true")
    ap.add_argument("--include-products", action="store_true")
    ap.add_argument("--exclude-entity", action="append", default=[])
    ap.add_argument("--youtube-budget", type=int, default=3000)
    ap.add_argument("--max-slices", type=int, default=200)
    ap.add_argument("--probe", type=int, default=0)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--run-inline", action="store_true")
    g.add_argument("--enqueue", action="store_true")
    a = ap.parse_args(argv)

    cfg = BackfillConfig(
        start=dt.date.fromisoformat(a.start), sources=tuple(s for s in a.sources.split(",") if s),
        include_competitors=a.include_competitors, include_products=a.include_products,
        exclude_entities=tuple(a.exclude_entity), youtube_units_budget=a.youtube_budget,
        max_slices_per_run=a.max_slices,
    )
    db = SessionLocal()
    try:
        q = db.query(Client)
        client = q.filter(Client.id == a.client).first() if len(a.client) == 36 else q.filter(Client.name == a.client).first()
        if not client:
            print(f"client not found: {a.client}", file=sys.stderr)
            return 2
        if a.dry_run:
            print(json.dumps(dry_run(db, client.id, cfg, probe=a.probe), indent=1, default=str))
        elif a.run_inline:
            print(json.dumps(run_client(db, client.id, cfg), indent=1, default=str))
        else:
            from app.workers.backfill_tasks import run_client_backfill
            r = run_client_backfill.apply_async(args=[str(client.id), cfg.to_dict(), 0])
            print(json.dumps({"enqueued": r.id, "client": client.name}))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
