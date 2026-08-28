import os
import re
import sys
import subprocess

def _expected_schema(schema_sql_path):
    """Parse database/schema.sql for {table: [columns]}, the same source of
    truth bootstrap_schema.py applies to a fresh DB. Skips inline CONSTRAINT
    lines (some CREATE TABLE blocks have them, e.g. documents, rss_feeds) --
    only column names are wanted here."""
    schema = open(schema_sql_path, encoding="utf-8").read()
    pattern = re.compile(r"CREATE TABLE public\.(\w+) \(\n(.*?)\n\);", re.DOTALL)
    expected = {}
    for m in pattern.finditer(schema):
        table, body = m.group(1), m.group(2)
        cols = []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith("CONSTRAINT"):
                continue
            cols.append(line.split()[0].strip('"'))
        expected[table] = cols
    return expected

def _diff_schema(settings, schema_sql_path):
    """Returns a list of 'table' / 'table.column' strings present in
    schema.sql but missing from the live DB. Only checks that direction
    (schema.sql -> DB) -- extra tables/columns in the DB beyond schema.sql
    aren't this check's concern."""
    import psycopg2
    expected = _expected_schema(schema_sql_path)
    # Same fix as the PostgreSQL reachability check above -- must use
    # settings.DATABASE_URL (honors DATABASE_URL_OVERRIDE) so this diffs
    # the actual database the app connects to at runtime, not whatever
    # happens to be reachable on the discrete DB_HOST/DB_PORT fields.
    conn = psycopg2.connect(settings.DATABASE_URL, connect_timeout=5)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public'"
        )
        actual = {}
        for table, column in cur.fetchall():
            actual.setdefault(table, set()).add(column)
    finally:
        conn.close()

    missing = []
    for table, columns in expected.items():
        if table not in actual:
            missing.append(table)
            continue
        for col in columns:
            if col not in actual[table]:
                missing.append(f"{table}.{col}")
    return missing

def print_status(msg, status="OK"):
    if status == "OK":
        print(f"[\033[92mOK\033[0m] {msg}")
    elif status == "FAIL":
        print(f"[\033[91mFAIL\033[0m] {msg}")
    elif status == "WARN":
        print(f"[\033[93mWARN\033[0m] {msg}")

def main():
    print("Running Pre-flight Checks...")
    
    # 1. Change working directory to orm_collection so .env is found
    orm_collection_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'orm_collection'))
    os.chdir(orm_collection_dir)
    sys.path.insert(0, orm_collection_dir)
    
    # 2. Check Environment Variables
    try:
        from app.core.config import settings
        print_status("Environment variables loaded")
    except Exception as e:
        print_status(f"Failed to load environment variables: {e}", "FAIL")
        sys.exit(1)
        
    # 3. Check PostgreSQL
    try:
        import psycopg2
        from urllib.parse import urlparse

        # Bug fix: this used to connect via the discrete DB_HOST/DB_PORT/
        # DB_USER/DB_PASSWORD/DB_NAME fields directly, which silently
        # ignores DATABASE_URL_OVERRIDE (config.py) whenever it's set --
        # exactly the case for this project's real deployment (DATABASE_URL
        # in .env points at the hosted Render Postgres; app/core/db.py's
        # actual engine already connects via settings.DATABASE_URL, which
        # resolves the override). With the old code, if a stale/unrelated
        # local Postgres also happens to be reachable on DB_HOST/DB_PORT
        # with matching credentials, this check (and the schema diff below)
        # silently validates that WRONG database instead of the one the app
        # will actually use at runtime -- confirmed live: a leftover local
        # Postgres from before this project removed Alembic (still has an
        # alembic_version table) was being checked here, while the app
        # itself talks to Render. Connecting via settings.DATABASE_URL
        # (the same property db.py's engine uses) fixes that divergence.
        is_local_host = urlparse(settings.DATABASE_URL).hostname in ("localhost", "127.0.0.1", "::1")
        pg_connect_timeout = 3 if is_local_host else 10
        conn = psycopg2.connect(settings.DATABASE_URL, connect_timeout=pg_connect_timeout)
        conn.close()
        print_status("PostgreSQL is reachable")
    except Exception as e:
        print_status(f"PostgreSQL connection failed: {e}", "FAIL")
        sys.exit(1)
        
    # 4. Check Redis
    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_timeout=3)
        r.ping()
        print_status("Redis is reachable")
    except Exception as e:
        print_status(f"Redis connection failed: {e}", "FAIL")
        sys.exit(1)

    # 5. Check Celery Broker Configuration
    try:
        from app.core.celery_app import celery_app
        broker_url = celery_app.conf.broker_url
        # Phase 5 item 22: managed Redis (ElastiCache in-transit encryption,
        # Upstash, Redis Cloud) requires the TLS scheme rediss://. redis.from_url()
        # and Celery both already handle it; this check didn't.
        if not (broker_url.startswith("redis://") or broker_url.startswith("rediss://")):
            print_status(f"Celery broker is NOT Redis! Current broker: {broker_url}", "FAIL")
            sys.exit(1)
        print_status("Celery configured to use Redis broker")
    except Exception as e:
        print_status(f"Celery configuration check failed: {e}", "FAIL")
        sys.exit(1)

    # 6. Database Schema
    #
    # Replaces the old alembic-based check (TASK.md -- Remove Alembic,
    # Adopt schema.sql as Source of Truth: local DB had drifted 92 columns
    # + 1 table away from what the migration chain actually described,
    # so alembic's own bookkeeping was no longer trustworthy). schema.sql
    # is now the single source of truth for DB structure.
    #
    # Same two-mode split as before, same reason (Phase 5 item 26): this
    # script runs from both install.bat (once, deploy time) and
    # start_platform.ps1 (every startup) -- re-applying schema.sql on
    # every startup is unnecessary since bootstrap_schema.py is itself
    # idempotent (only applies to a genuinely empty DB), but running it on
    # every startup is still one more DB round-trip than needed, so the
    # apply/check split is kept. install.bat passes --apply-schema;
    # everything else does a real column-for-column diff against
    # schema.sql and fails loudly with instructions if anything's missing
    # -- it does not silently proceed on a stale/partial schema.
    apply_schema = "--apply-schema" in sys.argv
    orm_collection_cwd = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'orm_collection'))
    schema_sql_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql'))
    try:
        if apply_schema:
            print("Applying database schema (schema.sql, only if DB is empty)...")
            result = subprocess.run(
                [sys.executable, "scripts/bootstrap_schema.py"],
                cwd=orm_collection_cwd,
                env={**os.environ, "SCHEMA_SQL_PATH": schema_sql_path},
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print_status(f"Schema bootstrap failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}", "FAIL")
                sys.exit(1)
            print_status("Database schema is up to date")
        else:
            print("Checking database schema against schema.sql (use --apply-schema to initialize a fresh DB)...")
            missing = _diff_schema(settings, schema_sql_path)
            if missing:
                print_status(
                    "Database schema does NOT match schema.sql. Missing:\n" +
                    "\n".join(f"  - {item}" for item in missing) +
                    "\nRun install.bat, or 'python scripts/bootstrap_schema.py' in orm_collection\\, to initialize the schema.",
                    "FAIL",
                )
                sys.exit(1)
            print_status("Database schema is up to date")
    except SystemExit:
        raise
    except Exception as e:
        print_status(f"Schema check failed: {e}", "FAIL")
        sys.exit(1)

    print("\nAll pre-flight checks passed!")
    sys.exit(0)

if __name__ == "__main__":
    main()
