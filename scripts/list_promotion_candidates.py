"""List the people the system would have promoted to a client's tracked executives, for a human to review. READ ONLY.

Automatic promotion is switched off (EntityDiscoveryConfig.EXECUTIVE_AUTO_PROMOTION_ENABLED = False). A person is added by hand through the
"track executive" action. This tool shows, for one client, every not-yet-promoted candidate that meets the old numeric thresholds, with the
evidence a reviewer needs: how often and how confidently the name was found, the articles it came from (outlet or source, whether the
article mentions the client itself) and the words next to the name (a title such as "chairman" or "President").

It runs inside the backend container, which has the database session and the app code (nothing is written; the whole run is one read-only
transaction):

    docker exec -i orm_dashboard-backend-1 python3 - "Adani Group" < scripts/list_promotion_candidates.py
    docker exec -i orm_dashboard-backend-1 python3 - "Adani Group" --wikidata < scripts/list_promotion_candidates.py

--wikidata also asks Wikidata whether the name is a person (a web lookup; the answer is not stored anywhere).
The client can be given by name or by id. Without --all, only candidates meeting the old thresholds are listed.
"""
import re
import sys
import uuid

from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.reach_trust_config import _extract_outlet
from app.services.intelligence.entity_discovery import EntityDiscoveryConfig, EntityDiscoveryEngine

args = [a for a in sys.argv[1:] if not a.startswith("--")]
flags = {a for a in sys.argv[1:] if a.startswith("--")}
if not args:
    sys.exit('usage: python3 - "<client name or id>" [--wikidata] [--all] < scripts/list_promotion_candidates.py')

db = SessionLocal()
db.execute(text("SET TRANSACTION READ ONLY"))
R = lambda s, **p: db.execute(text(s), p).fetchall()

ref = args[0]
client = R("select id, name from clients where id::text = :r or name ilike :r", r=ref)
if len(client) != 1:
    sys.exit(f"client {ref!r} matched {len(client)} clients: {[c.name for c in client]}")
cid, cname = str(client[0].id), client[0].name
brand_ids = [r[0] for r in R("select id from entities where client_id=:c and entity_type in ('brand','product')", c=cid)]
tracked = {r[0].lower() for r in R("select name from entities where client_id=:c and entity_type='person'", c=cid)}
eng = EntityDiscoveryEngine()

print(f"Promotion candidates for {cname}")
print(f"Automatic promotion is {'ON' if EntityDiscoveryConfig.EXECUTIVE_AUTO_PROMOTION_ENABLED else 'OFF'}; people below are NOT tracked until you add them by hand.")
print(f"Tracked people now ({len(tracked)}): {', '.join(sorted(tracked)) or 'none'}")

cands = R("""select id, name, mention_count, confidence, source_documents from executive_candidates
             where client_id=:c and promoted_to_executive_id is null order by confidence desc, mention_count desc, name""", c=cid)
shown = 0
for c in cands:
    meets = (c.mention_count or 0) >= EntityDiscoveryConfig.EXECUTIVE_MENTION_THRESHOLD and (c.confidence or 0) >= EntityDiscoveryConfig.EXECUTIVE_CONFIDENCE_THRESHOLD
    if not meets and "--all" not in flags:
        continue
    shown += 1
    docs = []
    for x in c.source_documents or []:
        try:
            docs.append(uuid.UUID(str(x)))
        except ValueError:
            pass
    print("\n" + "=" * 78)
    print(f"{c.name}   |   found {c.mention_count} times, confidence {float(c.confidence):.2f}, {len(docs)} source article(s)"
          f"{'' if meets else '   (below the old thresholds)'}")
    related = 0
    last = c.name.split()[-1]
    for d in docs:
        row = R("select title, document_type, left(normalized_content, 100000) body from documents where id=:d", d=d)
        if not row:
            print("   - (article no longer in the database)")
            continue
        row = row[0]
        mentions_client = bool(brand_ids) and R("select 1 from entity_mentions where document_id=:d and entity_id = any(:b) limit 1", d=d, b=brand_ids)
        related += 1 if mentions_client else 0
        outlet = _extract_outlet(row.title) or f"[{row.document_type}]"
        m = re.search(re.escape(last), (row.title or "") + " " + (row.body or ""), re.I)
        around = ""
        if m:
            blob = (row.title or "") + " " + (row.body or "")
            around = blob[max(0, m.start() - 70): m.end() + 70].replace("\n", " ")
        print(f"   - {outlet[:28]:28} | {'mentions ' + cname if mentions_client else 'does NOT mention ' + cname}")
        print(f"       headline: {str(row.title)[:110]}")
        if around:
            print(f"       next to the name: ...{around}...")
    has_title = eng._has_executive_context(db, c.name, docs, title_pattern=eng._PROMOTION_ROLE_PATTERN) if docs else False
    print(f"   Summary: {related} of {len(docs)} article(s) mention {cname}; a job title was found next to the name: {'yes' if has_title else 'no'}")
    if "--wikidata" in flags:
        try:
            allow, outcome, reason = eng._check_person_via_kb(c.name)
            print(f"   Wikidata: {outcome} ({reason})")
        except Exception as exc:  # a failed web lookup must not hide the evidence above
            print(f"   Wikidata: lookup failed ({type(exc).__name__})")
    print("   Reminder: a title next to a name can belong to someone else in the sentence (for example a visiting head of state).")

if not shown:
    print("\nNo unpromoted candidates meet the old thresholds.")
print(f"\n{shown} candidate(s) listed of {len(cands)} unpromoted.")
db.rollback()
db.close()
