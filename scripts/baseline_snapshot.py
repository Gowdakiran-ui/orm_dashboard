"""Read-only baseline of every client (score, risk, entities, docs by source, slices, runs). Save before a deploy, run again after and diff. Run: docker exec -i orm_dashboard-backend-1 python3 - < scripts/baseline_snapshot.py > baseline.json"""
import json, datetime
from app.core.db import SessionLocal
from sqlalchemy import text
db=SessionLocal()
q=lambda s,**k:[dict(r._mapping) for r in db.execute(text(s),k).fetchall()]
out={"taken_utc":datetime.datetime.utcnow().isoformat(),"clients":{}}
for c in q("select id,name,industry,created_at from clients order by id"):
    cid=c['id']; d={"client":c}
    d['score']=q("select score,grade,confidence_score,created_at,data_coverage from reputation_scores where client_id=:c order by created_at desc limit 1",c=cid)
    d['risk_by_level']=q("select risk_level,count(*) n,count(distinct document_id) docs from risk_events where client_id=:c group by 1 order by 1",c=cid)
    d['entities_by_type']=q("select entity_type,count(*) n from entities where client_id=:c group by 1",c=cid)
    d['seeded']=q("select kind,name,rank,role,status,validated from seeded_entities where client_id=:c order by kind,rank",c=cid)
    d['docs_by_source']=q("select s.name src,count(distinct d.id) n from document_matches m join entities e on e.id=m.matched_entity_id join documents d on d.id=m.document_id left join sources s on s.id=d.source_id where e.client_id=:c group by 1 order by 2 desc",c=cid)
    d['matched_docs']=q("select count(distinct m.document_id) n from document_matches m join entities e on e.id=m.matched_entity_id where e.client_id=:c",c=cid)
    d['slices']=q("select source,status,count(*) n,sum(item_count) items,sum(new_count) new from backfill_slices where client_id=:c group by 1,2 order by 1,2",c=cid)
    d['runs']=q("select run_id,status,stage,started_at,finished_at,duration_s from pipeline_runs where client_id=cast(:c as varchar) order by started_at desc limit 3",c=cid)
    d['exec_scores']=q("select executive_name,score,grade,created_at from (select distinct on (entity_id) * from executive_reputation_scores where client_id=:c order by entity_id,created_at desc) x order by executive_name",c=cid)
    d['benchmarks']=q("select competitor_entity_id,reputation_score,rank,created_at from (select distinct on (competitor_entity_id) * from competitor_benchmarks where client_id=:c order by competitor_entity_id,created_at desc) x order by rank",c=cid)
    out['clients'][str(cid)]=d
out['users']=q("select count(*) n from users")
print(json.dumps(out,default=str,indent=1))
