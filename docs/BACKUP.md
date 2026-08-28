# Database Backups

## What runs

`app.workers.backup_tasks.run_backup` (Celery beat, `io_queue`) runs `pg_dump`
against `DATABASE_URL` daily at **02:00 UTC** and writes a timestamped
custom-format dump to `/backups`, which is the `backup_data` named Docker
volume mounted on the `celery-worker-io` service (`docker-compose.yml`).

Filename: `backup_YYYYmmdd_HHMMSS.dump`

Rotation: dumps older than **7 days** are deleted at the end of every backup
run (`BACKUP_RETENTION_DAYS` in `backup_tasks.py`).

## Restore

1. Copy the dump out of the volume (or exec into the container that has it mounted):
   ```bash
   docker cp $(docker-compose ps -q celery-worker-io):/backups/backup_20260827_020000.dump ./backup.dump
   ```

2. Restore into a target database (drops/recreates conflicting objects via `--clean --if-exists`; add `--create` to also create the database itself):
   ```bash
   pg_restore --clean --if-exists --no-owner --no-privileges \
     -d "$DATABASE_URL" \
     ./backup.dump
   ```
   `DATABASE_URL` is the standard `postgresql://user:password@host:5432/dbname` connection string (same format as `orm_collection/.env`'s `DATABASE_URL`/`DB_*` fields).

   To restore into a *different* (e.g. throwaway/local) database instead of overwriting the live one:
   ```bash
   pg_restore --clean --if-exists --no-owner --no-privileges \
     -d "postgresql://postgres:postgres@localhost:5432/restore_test" \
     ./backup.dump
   ```

## Manually triggering a backup

Same invocation style as any other task in this codebase:
```bash
docker-compose exec celery-worker-io celery -A app.core.celery_app.celery_app call app.workers.backup_tasks.run_backup
```

## Offsite copy (S3)

As of the AWS deployment task, `run_backup` also uploads each completed
local dump to S3 at `s3://$S3_BUCKET_NAME/backups/backup_<timestamp>.dump`,
gated on `ENABLE_S3_STORAGE` (same lazy client pattern as
`app/utils/s3_client.py`). This is additive, not a replacement:

- The local volume write + `BACKUP_RETENTION_DAYS` rotation above are
  unchanged and remain the restore source of truth.
- An S3 upload failure (bad credentials, bucket unreachable, etc.) is
  logged (`backup_s3_upload_failed`) and swallowed — it never fails the
  task or triggers a retry, since the local dump already succeeded.
- The S3 copy has no rotation of its own yet; the bucket's lifecycle rule
  (see `copilot/environments/addons/s3.yml`) expires objects under
  `backups/` after 30 days.

## Known gaps / follow-ups

- **Render's own platform-level backups are not verified by this doc or by
  any code in this repo.** The DB is hosted on Render, which may offer its
  own automated backups — check the Render dashboard for this database
  manually and confirm it's actually enabled. Nothing here does that for you.
- **S3 upload has no independent alerting.** A silently-failing upload
  (bad credentials, bucket policy drift) is only visible in logs
  (`backup_s3_upload_failed`) — no dashboard/alert wired up for it yet.
