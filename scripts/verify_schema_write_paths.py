"""Prove the scoring engines' write paths against a REAL Postgres built from
database/schema.sql + database/migrations/*.sql (not from the ORM models).

Why: the unit tests use SQLite built from the ORM models, so they cannot catch a
NOT NULL / CHECK / length mismatch between what the engines write and the real
schema (migration 0011's header documents a 15-day executive-score outage from
exactly that kind of leftover NOT NULL column).

It runs ReputationEngine, ExecutiveReputationEngine and BenchmarkEngine twice
with the same run_id (INSERT, then the ON CONFLICT upsert path) on seeded data
and checks what was stored.

Usage (throwaway database only -- the script refuses non-local hosts):
    python scripts/verify_schema_write_paths.py --embedded         # needs `pip install pgserver` in a venv
    python scripts/verify_schema_write_paths.py --embedded --with-pending   # also apply database/migrations_pending/*.sql
                                                                          # (use with the step-4 code change set)
    python scripts/verify_schema_write_paths.py --url postgresql://user:pw@127.0.0.1:5432/scratch

--embedded starts a private Postgres in a temp dir and removes it afterwards.
"""
import argparse
import datetime
import glob
import os
import re
import sys
import tempfile
import uuid
from urllib.parse import urlparse

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
COLLECTION = os.path.join(ROOT, "orm_collection")


def _guard_local(url: str) -> None:
    host = urlparse(url).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit(f"refusing to run against non-local host {host!r}: throwaway databases only")


def _apply_sql(conn, path: str, server_major: int) -> None:
    sql = open(path, encoding="utf-8").read()
    if server_major < 17:
        # schema.sql is a PG18 dump; drop settings older servers don't know.
        sql = re.sub(r"^SET transaction_timeout = 0;\s*$", "", sql, flags=re.M)
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def build_schema(url: str, with_pending: bool = False) -> None:
    import psycopg2
    conn = psycopg2.connect(url)
    try:
        with conn.cursor() as cur:
            cur.execute("show server_version_num")
            major = int(cur.fetchone()[0]) // 10000
        _apply_sql(conn, os.path.join(ROOT, "database", "schema.sql"), major)
        print(f"schema.sql applied (server major {major})")
        migs = sorted(glob.glob(os.path.join(ROOT, "database", "migrations", "*.sql")))
        if with_pending:
            migs += sorted(glob.glob(os.path.join(ROOT, "database", "migrations_pending", "*.sql")))
        for mig in migs:
            try:
                _apply_sql(conn, mig, major)
                print(f"  migration applied: {os.path.basename(mig)}")
            except Exception as exc:  # migrations are incremental on top of an older DB; schema.sql already has them
                conn.rollback()
                print(f"  migration skipped (already in schema.sql?): {os.path.basename(mig)}: {str(exc).splitlines()[0]}")
    finally:
        conn.close()


def seed_and_run(url: str) -> list:
    os.environ["DATABASE_URL"] = url
    os.environ["DATABASE_URL_POOLED"] = url
    sys.path.insert(0, COLLECTION)
    from app.core.db import SessionLocal
    from app.models.client import Client
    from app.models.entity import Entity, EntityMention
    from app.models.document import Document
    from app.models.sentiment import DocumentSentiment
    from app.models.risk import RiskEvent
    from app.models.source import Source, SourceCategory
    from app.services.intelligence.reputation_engine import ReputationEngine
    from app.services.intelligence.executive_reputation_engine import ExecutiveReputationEngine
    from app.services.intelligence.benchmark_engine import BenchmarkEngine
    from sqlalchemy import text

    db = SessionLocal()
    now = datetime.datetime.now(datetime.timezone.utc)
    cid = uuid.uuid4()
    db.add(Client(id=cid, name="Schema Check Co"))
    cat = SourceCategory(id=uuid.uuid4(), name="RSS News", base_reliability_score=1.00)
    db.add(cat)
    db.flush()
    src = Source(id=uuid.uuid4(), category_id=cat.id, name="s", source_type="rss", schedule_cron="* * * * *")
    db.add(src)
    brand = Entity(id=uuid.uuid4(), client_id=cid, name="Schema Check Co", entity_type="brand")
    rival = Entity(id=uuid.uuid4(), client_id=cid, name="Rival Co", entity_type="competitor")
    silent = Entity(id=uuid.uuid4(), client_id=cid, name="Silent Co", entity_type="competitor")  # no evidence at all
    person = Entity(id=uuid.uuid4(), client_id=cid, name="Jane Doe", entity_type="person")
    db.add_all([brand, rival, silent, person])
    db.flush()
    for i in range(8):
        d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", title=f"d{i}", normalized_content="x",
                     source_id=src.id, published_at=now)
        db.add(d)
        db.flush()
        for e in (brand, person) + ((rival,) if i < 4 else ()):
            db.add(EntityMention(document_id=d.id, entity_id=e.id, mention_count=2, created_at=now))
        db.add(DocumentSentiment(document_id=d.id, sentiment_label="Neutral", sentiment_score=0.1 * (i % 3),
                                 confidence_score=0.9, weighted_sentiment_score=0.1))
        for e in (brand, person):
            db.add(RiskEvent(client_id=cid, document_id=d.id, entity_id=e.id, risk_score=10.0 + i,
                             risk_level="LOW", created_at=now))
    # A document with no sentiment/risk where the brand and "Silent Co" co-occur: Silent Co passes the brand gate
    # but has too little evidence to score -> INSUFFICIENT_EVIDENCE row with the stored 0.0 placeholder.
    d = Document(id=uuid.uuid4(), url=f"http://t.test/{uuid.uuid4()}", title="bare", normalized_content="x",
                 source_id=src.id, published_at=now)
    db.add(d)
    db.flush()
    for e in (brand, silent):
        db.add(EntityMention(document_id=d.id, entity_id=e.id, mention_count=1, created_at=now))
    db.commit()

    problems = []
    run_id = uuid.uuid4().hex
    for label, call in (
        ("reputation", lambda: ReputationEngine().calculate_reputation_score(db, str(cid), run_id=run_id)),
        ("executive", lambda: ExecutiveReputationEngine().calculate_executive_reputation(db, str(cid), run_id=run_id)),
        ("benchmark", lambda: BenchmarkEngine().calculate_competitor_benchmarks(db, str(cid), run_id=run_id)),
    ):
        for attempt in ("insert", "upsert (same run_id, ON CONFLICT)"):
            try:
                call()
                db.commit()
                print(f"  OK   {label:11s} {attempt}")
            except Exception as exc:
                db.rollback()
                problems.append(f"{label} {attempt}: {exc}")
                print(f"  FAIL {label:11s} {attempt}: {str(exc).splitlines()[0]}")

    def rows(sql):
        return db.execute(text(sql), {"c": str(cid)}).fetchall()

    def has_col(table, col):
        return bool(db.execute(text("select 1 from information_schema.columns where table_name=:t and column_name=:c"),
                               {"t": table, "c": col}).fetchall())

    trend_cols_present = has_col("reputation_scores", "reputation_trend")
    if trend_cols_present:
        rep = rows("select reputation_trend, trend_component, score, data_coverage from reputation_scores where client_id = :c")
        ex = rows("select reputation_trend, trend_component, score from executive_reputation_scores where client_id = :c")
    else:  # after schema step 2: the columns are gone, nothing to check beyond the row existing
        rep = rows("select 'dropped', null, score, data_coverage from reputation_scores where client_id = :c")
        ex = rows("select 'dropped', null, score from executive_reputation_scores where client_id = :c")
    bm = rows("select health_status, rank, reputation_score, calculation_lineage->>'client_comparable_score_exact' from competitor_benchmarks where client_id = :c")
    print("  reputation_scores:", rep)
    print("  executive_reputation_scores:", ex)
    print("  competitor_benchmarks:", bm)
    if len(rep) != 1:
        problems.append(f"expected 1 reputation row after insert+upsert, found {len(rep)}")
    if trend_cols_present and any(r[0] != "NOT_COMPUTED" for r in rep + ex):
        problems.append("reputation_trend is not the NOT_COMPUTED placeholder")
    if not ex:
        problems.append("no executive_reputation_scores row written")
    if not bm:
        problems.append("no competitor_benchmarks rows written")
    if not any(r[0] == "INSUFFICIENT_EVIDENCE" for r in bm):
        problems.append("no-evidence competitor did not produce an INSUFFICIENT_EVIDENCE row")

    # Every NOT NULL column without a DB default must be covered by what the engines write (the inserts above prove it
    # for this data); list them so a reviewer can see exactly what the engines must supply.
    print("  NOT NULL columns without a default:")
    for t in ("reputation_scores", "executive_reputation_scores", "competitor_benchmarks"):
        cols = db.execute(text(
            "select column_name from information_schema.columns where table_name=:t and is_nullable='NO' and column_default is null order by ordinal_position"),
            {"t": t}).fetchall()
        print(f"    {t}: {[c[0] for c in cols]}")
    db.close()
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--embedded", action="store_true", help="start a private throwaway Postgres via pgserver")
    g.add_argument("--url", help="URL of a LOCAL throwaway Postgres")
    ap.add_argument("--with-pending", action="store_true", help="also apply database/migrations_pending/*.sql (schema step 2)")
    args = ap.parse_args()

    server = None
    if args.embedded:
        import pgserver
        tmp = tempfile.mkdtemp(prefix="schema_check_pg_")
        server = pgserver.get_server(tmp)
        url = server.get_uri()
    else:
        url = args.url
    _guard_local(url)
    try:
        build_schema(url, args.with_pending)
        problems = seed_and_run(url)
    finally:
        if server is not None:
            server.cleanup()
    if problems:
        print("\nPROBLEMS:")
        for p in problems:
            print(" -", p)
        return 1
    print("\nALL WRITE PATHS OK against a Postgres built from schema.sql + migrations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
