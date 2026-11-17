"""Read-only acceptance check for a freshly onboarded client. Run it before any client is shown a new client's pages.

It writes nothing: every query is a SELECT and the session is rolled back at the end. Run it inside the backend container (it needs
the app code and the database session), the same way as scripts/run_pipeline.py:

    docker exec -i orm_dashboard-backend-1 python3 - "<client name or id>"               < scripts/new_client_acceptance.py
    docker exec -i orm_dashboard-backend-1 python3 - "<client name or id>" --check-token < scripts/new_client_acceptance.py

--check-token makes ONE free read-only call to the Apify account endpoint (never prints the token). Without it the token line is SKIPPED.

Result tiers:
  FAIL  only when setup did not run (no seeding record and no backfill slice), a queue holds a stale message (the default "celery" queue
        has no consumer except the io worker's safety net), or a required count is 0 (executives, competitors, documents, risk events,
        feeds, a reputation score).
  WARN  something is below what the design wants but not absent: fewer than 5 executives or competitors (the reason is shown), the latest
        pipeline run is not SUCCESS, the reputation score is older than the latest run, nobody can see the client.
  INFO  shown for a human to read; never changes the result.
Exit code: 0 no FAIL (WARNs allowed), 1 at least one FAIL, 2 usage, 4 client not found.

evaluate() is a pure function over a plain dict of facts, so tests/test_new_client_acceptance.py can check the PASS / WARN / FAIL paths
without a database.
"""
import json
import os
import sys


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def evaluate(f):
    """f: dict of facts (see collect()). Returns [(status, name, detail)]. Pure: no I/O."""
    out = []

    def add(status, name, detail):
        out.append((status, name, detail))

    # ---- FAIL conditions -------------------------------------------------------------------------------------------------------
    setup_ran = f["seeded_rows"] > 0 or f["backfill_slices"] > 0
    add("PASS" if setup_ran else "FAIL", "setup ran (a seeding record or a backfill slice exists)",
        f"{f['seeded_rows']} seeded row(s), {f['backfill_slices']} backfill slice(s)" + ("" if setup_ran else ": onboarding setup never ran for this client"))
    q = f["default_queue_len"]
    if q is None:
        add("WARN", "default 'celery' queue is empty", "could not read Redis")
    else:
        add("PASS" if q == 0 else "FAIL", "default 'celery' queue is empty (no stale message)", f"LLEN celery = {q}")

    def required(name, n, what):
        add("PASS" if n > 0 else "FAIL", name, f"{n} {what}" if n > 0 else f"0 {what}: required, nothing there")

    required("documents matched to the client", f["documents"], "document(s)" + (f" ({f['documents_by_source']})" if f["documents_by_source"] else ""))
    required("risk events exist", f["risk_events"], "event(s)" + (f" ({f['risk_by_level']})" if f["risk_by_level"] else ""))
    required("search feeds provisioned and active", f["active_feeds"], "active feed(s)")
    required("a reputation score exists", f["reputation_rows"], "score row(s)")
    required("executives seeded (active)", f["active_executives"], "active executive(s)")
    required("competitors seeded (active)", f["active_competitors"], "active competitor(s)")

    # ---- WARN conditions -------------------------------------------------------------------------------------------------------
    for kind, key, rows_key in (("executives", "active_executives", "rows_executives"), ("competitors", "active_competitors", "rows_competitors")):
        n = f[key]
        if 0 < n < 5:
            total, review = f[rows_key], f["review_" + kind]
            add("WARN", f"{kind}: 5 wanted, {n} active",
                f"{total} seeded row(s) stored, {review} held for review (failed validation); the proposal supplied no further valid candidate, "
                f"or the validator rejected them. Reason per candidate: python -m app.services.seeding.cli --client <name> --dry-run (one paid model call).")
        elif n >= 5:
            add("PASS", f"{kind}: 5 wanted, {n} active", "")
    if f["active_rows_incomplete"]:
        add("WARN", "every active seeded row has a source URL and a linked entity", f"{f['active_rows_incomplete']} active row(s) lack a source or an entity")
    lr = f["latest_run_status"]
    add("PASS" if lr == "SUCCESS" else "WARN", "latest pipeline run is SUCCESS", lr or "no run yet")
    if f["reputation_rows"] and f["latest_run_finished"] and f["reputation_created"]:
        stale_s = (f["latest_run_finished"] - f["reputation_created"]).total_seconds()
        if stale_s > 300:
            add("WARN", "reputation score was recomputed by the latest run",
                f"newest score is {round(stale_s / 60)} min older than the latest run (a stage skips when the last score is under 2 h old); "
                f"it was computed from {f['reputation_docs']} document(s) while {f['documents']} are now matched")
        else:
            add("PASS", "reputation score was recomputed by the latest run", f"score {f['reputation_text']}")
    if f["active_executives"] > 0:
        add("PASS" if f["executive_scored"] > 0 else "WARN", "executive reputation scored", f"{f['executive_scored']} executive(s) scored")
    can_see = f["grants"] > 0 or f["super_admins"] > 0
    add("PASS" if can_see else "WARN", "at least one user can see the client (a grant, or an active super admin)",
        f"grants={f['grants']}, active super admins={f['super_admins']}")
    if f["pending_slices"]:
        add("INFO", "backfill slices still PENDING (the backfill is bounded and may finish later)", str(f["pending_slices"]))
    add("INFO", "client_user grants", f"{f['grants']} (0 means only super admins can see it)")
    tok = f.get("token")
    add("INFO" if tok is None else ("PASS" if tok[0] else "WARN"), "Apify token valid", "SKIPPED (pass --check-token for one free read-only call)" if tok is None else tok[1])
    return out


def result_of(results):
    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    return ("FAIL" if fails else "PASS"), len(fails), len(warns)


def collect(db, cid, check_token=False):
    from sqlalchemy import text
    q = lambda sql, p=None: db.execute(text(sql), p or {"c": cid}).fetchall()
    f = {}
    try:
        from app.utils.redis_client import redis_client
        f["default_queue_len"] = redis_client.client.llen("celery")
    except Exception:
        f["default_queue_len"] = None
    seeded = q("select kind, status, validated, sources, entity_id is not null as linked from seeded_entities where client_id=:c")
    f["seeded_rows"] = len(seeded)
    act = [r for r in seeded if r.status == "active"]
    for kind, plural in (("executive", "executives"), ("competitor", "competitors")):
        f["active_" + plural] = sum(1 for r in act if r.kind == kind)
        f["rows_" + plural] = sum(1 for r in seeded if r.kind == kind)
        f["review_" + plural] = sum(1 for r in seeded if r.kind == kind and r.status == "needs_review")
    f["active_rows_incomplete"] = sum(1 for r in act if not (r.validated and r.linked and (r.sources or [])))
    sl = q("select status, count(*) n from backfill_slices where client_id=:c group by 1")
    f["backfill_slices"] = sum(r.n for r in sl)
    f["pending_slices"] = sum(r.n for r in sl if r.status == "PENDING")
    docs = q("""select coalesce(s.source_type,'?') st, count(distinct d.id) n
                from document_matches m join entities e on e.id = m.matched_entity_id
                join documents d on d.id = m.document_id left join sources s on s.id = d.source_id
                where e.client_id = :c group by 1 order by 2 desc""")
    f["documents"] = sum(r.n for r in docs)
    f["documents_by_source"] = ", ".join(f"{r.st}={r.n}" for r in docs)
    rk = q("select risk_level, count(*) n from risk_events where client_id=:c group by 1 order by 2 desc")
    f["risk_events"] = sum(r.n for r in rk)
    f["risk_by_level"] = ", ".join(f"{r.risk_level}={r.n}" for r in rk)
    f["active_feeds"] = sum(r.n for r in q("select count(*) n from rss_feeds where client_id=:c and is_active"))
    pr = q("select status, finished_at from pipeline_runs where client_id::text = :c order by started_at desc limit 1", {"c": str(cid)})
    f["latest_run_status"] = pr[0].status if pr else None
    ok = q("select max(finished_at) m from pipeline_runs where client_id::text = :c and status='SUCCESS'", {"c": str(cid)})
    f["latest_run_finished"] = ok[0].m if ok else None
    rs = q("select score, grade, created_at, calculation_lineage from reputation_scores where client_id=:c order by created_at desc")
    f["reputation_rows"] = len(rs)
    f["reputation_created"] = rs[0].created_at if rs else None
    f["reputation_text"] = f"{round(rs[0].score, 1)} grade {rs[0].grade}" if rs else ""
    f["reputation_docs"] = ((rs[0].calculation_lineage or {}).get("raw_values") or {}).get("document_count", "?") if rs else 0
    f["executive_scored"] = q("select count(distinct entity_id) n from executive_reputation_scores where client_id=:c")[0].n
    f["grants"] = q("select count(*) n from user_client_access where client_id=:c")[0].n
    f["super_admins"] = q("select count(*) n from users where role='super_admin' and is_active")[0].n
    f["token"] = _check_apify_token() if check_token else None
    return f


def _check_apify_token():
    import urllib.request
    tok = os.environ.get("APIFY_API_TOKEN", "")
    if not tok:
        return (False, "APIFY_API_TOKEN is not set in this container")
    try:
        req = urllib.request.Request("https://api.apify.com/v2/users/me", headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            json.loads(resp.read().decode("utf-8"))
        return (resp.status == 200, f"HTTP {resp.status}, account endpoint answered")
    except Exception as e:
        code = getattr(e, "code", None)
        return (False, f"HTTP {code}" if code else f"call failed: {type(e).__name__}")


def main():
    from sqlalchemy import text
    from app.core.db import SessionLocal
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit('usage: python3 - "<client name or id>" [--check-token] < scripts/new_client_acceptance.py')
    db = SessionLocal()
    rows = db.execute(text("select id, name from clients where id::text = :r or name ilike :r"), {"r": args[0]}).fetchall()
    if len(rows) != 1:
        print(f"client {args[0]!r} matched {len(rows)} client(s): {[r.name for r in rows]}")
        sys.exit(4)
    cid, cname = rows[0].id, rows[0].name
    results = evaluate(collect(db, cid, "--check-token" in sys.argv[1:]))
    db.rollback()
    db.close()
    print(f"Acceptance for {cname} ({cid})")
    for status, name, detail in results:
        print(f"  [{status:4}] {name}" + (f": {detail}" if detail else ""))
    verdict, nfail, nwarn = result_of(results)
    print(f"RESULT: {verdict} ({nfail} failing, {nwarn} warning(s))")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
