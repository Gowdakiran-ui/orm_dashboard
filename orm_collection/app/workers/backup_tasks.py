"""backup_tasks.py — API_FORENSICS.md Section 10.

Daily pg_dump of the live Postgres DB (settings.DATABASE_URL, hosted on
Render — see db.py) to a local Docker-managed volume mounted at /backups.
Routed to io_queue (celery_app.py task_routes) since it's a lightweight,
periodic I/O-bound job, same category as the existing watchdog tasks —
not worth a dedicated queue/worker.

AWS deployment task: each dump is now also uploaded to S3 (offsite copy)
after the local write completes, using the same lazy/gated
get_s3_client() pattern as app/utils/s3_client.py's upload_payload — gated
on settings.ENABLE_S3_STORAGE, and failures are logged, not raised. This is
additive: the local volume + BACKUP_RETENTION_DAYS rotation below is
unchanged and remains the source of truth for restores — see docs/BACKUP.md.
"""
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import structlog
from celery import shared_task

from app.core.config import settings
from app.utils.s3_client import get_s3_client

logger = structlog.get_logger()

BACKUP_DIR = Path("/backups")

# How many days of dumps to retain before rotation deletes the rest.
# Tune here if retention needs change.
BACKUP_RETENTION_DAYS = 7


def _rotate_old_backups(log) -> int:
    """Delete dump files older than BACKUP_RETENTION_DAYS. Returns count deleted."""
    if not BACKUP_DIR.exists():
        return 0

    cutoff = datetime.now(timezone.utc).timestamp() - (BACKUP_RETENTION_DAYS * 86400)
    deleted = 0
    for f in BACKUP_DIR.glob("backup_*.dump"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                deleted += 1
        except OSError as e:
            log.warning("backup_rotation_delete_failed", file=str(f), error=str(e))
    return deleted


@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def run_backup(self):
    """
    pg_dump settings.DATABASE_URL to a timestamped custom-format dump under
    /backups, then delete dumps older than BACKUP_RETENTION_DAYS.

    Custom format (-Fc) rather than plain .sql: smaller, and restorable with
    pg_restore (see docs/BACKUP.md), including selective/parallel restore.
    """
    log = logger.bind(task="run_backup")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dump_path = BACKUP_DIR / f"backup_{timestamp}.dump"

    log.info("backup_started", dump_path=str(dump_path))
    try:
        subprocess.run(
            [
                "pg_dump",
                settings.DATABASE_URL,
                "-Fc",
                "-f", str(dump_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except subprocess.CalledProcessError as e:
        log.error("backup_failed", error=e.stderr, returncode=e.returncode)
        dump_path.unlink(missing_ok=True)
        raise self.retry(exc=e)
    except subprocess.TimeoutExpired as e:
        log.error("backup_timed_out", error=str(e))
        dump_path.unlink(missing_ok=True)
        raise self.retry(exc=e)

    size_bytes = dump_path.stat().st_size
    log.info("backup_complete", dump_path=str(dump_path), size_bytes=size_bytes)

    s3_uri = _upload_to_s3(dump_path, log)

    deleted = _rotate_old_backups(log)
    if deleted:
        log.info("backup_rotation_complete", deleted_count=deleted, retention_days=BACKUP_RETENTION_DAYS)

    return {"dump_path": str(dump_path), "size_bytes": size_bytes, "rotated_deleted": deleted, "s3_uri": s3_uri}


def _upload_to_s3(dump_path: Path, log) -> str | None:
    """Best-effort offsite copy of a completed local dump to S3.

    Never raises: the local dump (already written and rotated by the
    caller) is the backup of record. An S3 outage or misconfiguration must
    not fail this task or trigger a retry that re-runs pg_dump.
    """
    if not settings.ENABLE_S3_STORAGE:
        return None

    client = get_s3_client()
    if not client:
        return None

    key = f"backups/{dump_path.name}"
    try:
        client.upload_file(str(dump_path), settings.S3_BUCKET_NAME, key)
    except Exception as e:
        log.warning("backup_s3_upload_failed", error=str(e), dump_path=str(dump_path))
        return None

    uri = f"s3://{settings.S3_BUCKET_NAME}/{key}"
    log.info("backup_s3_upload_complete", s3_uri=uri)
    return uri
