"""Idempotent schema bootstrap for container/deploy-time startup.

Replaces `alembic upgrade head` (see TASK.md — Remove Alembic, Adopt
schema.sql as Source of Truth). Applying `database/schema.sql` blindly on
every boot would fail with "relation already exists" against any DB that's
already been initialized, so this checks for a known table first and only
applies the dump to a genuinely empty database.

Not a migration tool: this only builds a fresh DB from scratch. A DB that
already has a schema (even an outdated one) is left untouched here -- see
CLAUDE.md's DB State section for why hand-written ALTERs are required for
schema changes against a DB that already holds real data.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import engine  # noqa: E402

# A table that has existed since the very first schema and is always
# present once the schema has been applied -- used as the "is this DB
# already initialized" sentinel.
SENTINEL_TABLE = "clients"

SCHEMA_SQL_PATH = Path(os.environ.get("SCHEMA_SQL_PATH", "/app/database/schema.sql"))


def main() -> int:
    with engine.connect() as conn:
        exists = conn.exec_driver_sql(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name=%s)",
            (SENTINEL_TABLE,),
        ).scalar()

        if exists:
            print(f"[bootstrap_schema] '{SENTINEL_TABLE}' table already present -- schema already applied, skipping.")
            return 0

        if not SCHEMA_SQL_PATH.exists():
            print(f"[bootstrap_schema] FAIL: database is empty but {SCHEMA_SQL_PATH} was not found.")
            return 1

        print(f"[bootstrap_schema] '{SENTINEL_TABLE}' table not found -- applying {SCHEMA_SQL_PATH} to initialize schema.")
        sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
        try:
            conn.exec_driver_sql(sql)
            conn.commit()
        except Exception as e:
            print(f"[bootstrap_schema] FAIL: schema apply failed: {e}")
            return 1

        print("[bootstrap_schema] Schema applied successfully.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
