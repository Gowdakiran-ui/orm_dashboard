import os
import sys
import uuid
import json
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import urllib.parse
_db_host     = os.environ.get("DB_HOST", "localhost")
_db_port     = os.environ.get("DB_PORT", "5432")
_db_user     = os.environ.get("DB_USER", "postgres")
_db_password = urllib.parse.quote_plus(os.environ.get("DB_PASSWORD", ""))
_db_name     = os.environ.get("DB_NAME", "postgres")
DB_URL = f"postgresql://{_db_user}:{_db_password}@{_db_host}:{_db_port}/{_db_name}"

try:
    engine = create_engine(DB_URL)
    Session = sessionmaker(bind=engine)
    db = Session()
except Exception as e:
    print(f"Error connecting to db: {e}")
    sys.exit(1)

def run_query(query, params=None):
    try:
        result = db.execute(text(query), params or {})
        return result.mappings().all()
    except Exception as e:
        db.rollback()
        raise e

print("--- ORM FORENSIC AUDIT ---")
try:
    clients = run_query("SELECT id, name FROM clients LIMIT 1")
    if not clients:
        print("No clients found.")
        sys.exit(0)
    
    client = clients[0]
    client_id = client['id']
    print(f"Testing Client: {client['name']} ({client_id})")
except Exception as e:
    print(f"Error getting client: {e}")
    sys.exit(1)

tables = [
    "documents",
    "entities",
    "entity_mentions",
    "trend_events",
    "risk_events",
    "alerts",
    "narratives",
    "reputation_scores",
    "executive_reputation_scores",
    "competitor_benchmarks"
]

print("\n--- DATABASE CONSISTENCY ---")
for table in tables:
    try:
        if table == "documents":
            count = run_query("SELECT COUNT(*) as c FROM documents")[0]['c']
            print(f"{table}: {count} rows")
        elif table == "entities":
            count = run_query("SELECT COUNT(*) as c FROM entities")[0]['c']
            print(f"{table} (all clients): {count} rows")
            count_client = run_query("SELECT COUNT(*) as c FROM entities WHERE client_id = :cid", {"cid": client_id})[0]['c']
            print(f"{table} (this client): {count_client} rows")
        elif table == "entity_mentions":
            count = run_query("SELECT COUNT(*) as c FROM entity_mentions dm JOIN entities e ON dm.entity_id = e.id WHERE e.client_id = :cid", {"cid": client_id})[0]['c']
            print(f"{table}: {count} rows for client")
        else:
            count = run_query(f"SELECT COUNT(*) as c FROM {table} WHERE client_id = :cid", {"cid": client_id})[0]['c']
            print(f"{table}: {count} rows for client")
    except Exception as e:
        print(f"Error querying {table}: {e}")

print("\n--- PIPELINE RUNS ---")
try:
    runs = run_query("SELECT run_id, status, stage, progress_pct, started_at, finished_at, duration_s FROM pipeline_runs WHERE client_id = :cid::varchar ORDER BY started_at DESC LIMIT 5", {"cid": str(client_id)})
    for run in runs:
        print(f"Run {run['run_id']}: Status={run['status']}, Stage={run['stage']}, Progress={run['progress_pct']}%, Duration={run['duration_s']}")
except Exception as e:
    print(f"Error querying pipeline_runs: {e}")

print("\n--- DATA QUALITY ---")
try:
    reps = run_query("SELECT score, grade, confidence_score, health_status FROM reputation_scores WHERE client_id = :cid ORDER BY created_at DESC LIMIT 1", {"cid": client_id})
    if reps:
        print(f"Latest Reputation: Score={reps[0]['score']}, Grade={reps[0]['grade']}, Confidence={reps[0]['confidence_score']}, Health={reps[0]['health_status']}")
except Exception as e:
    print(f"Error: {e}")

