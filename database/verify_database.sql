-- Database Integrity & Forensic Verification Suite

-- 1. Check for Orphan Rows (Should return 0)
SELECT 'entity_mentions missing entity' AS check_name, COUNT(*) AS orphan_count 
FROM entity_mentions em WHERE NOT EXISTS (SELECT 1 FROM entities e WHERE e.id = em.entity_id)
UNION ALL
SELECT 'entity_mentions missing document', COUNT(*) 
FROM entity_mentions em WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = em.document_id)
UNION ALL
SELECT 'document_topics missing document', COUNT(*) 
FROM document_topics dt WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = dt.document_id)
UNION ALL
SELECT 'document_sentiments missing document', COUNT(*) 
FROM document_sentiments ds WHERE NOT EXISTS (SELECT 1 FROM documents d WHERE d.id = ds.document_id)
UNION ALL
SELECT 'risk_events missing client', COUNT(*) 
FROM risk_events re WHERE NOT EXISTS (SELECT 1 FROM clients c WHERE c.id = re.client_id);

-- 2. Check for Duplicate Entities under the same Client (Should return 0)
SELECT client_id, name, COUNT(*) AS duplicate_count
FROM entities 
GROUP BY client_id, name 
HAVING COUNT(*) > 1;

-- 3. Check for Stale/Duplicate Benchmark Runs per Competitor
-- (This lists how many historical runs exist per competitor - used to verify API deduplication is active)
SELECT client_id, competitor_entity_id, COUNT(*) AS historical_runs_count
FROM competitor_benchmarks
GROUP BY client_id, competitor_entity_id;

-- 4. Verify Foreign Key Validity (Should return 0)
SELECT 'entities -> clients FK' AS fk_name, COUNT(*) AS broken_count FROM entities WHERE client_id NOT IN (SELECT id FROM clients)
UNION ALL
SELECT 'entity_keywords -> entities FK', COUNT(*) FROM entity_keywords WHERE entity_id NOT IN (SELECT id FROM entities)
UNION ALL
SELECT 'entity_aliases -> entities FK', COUNT(*) FROM entity_aliases WHERE entity_id NOT IN (SELECT id FROM entities)
UNION ALL
SELECT 'competitor_benchmarks -> entities FK', COUNT(*) FROM competitor_benchmarks WHERE competitor_entity_id NOT IN (SELECT id FROM entities);

-- 5. List all custom indexes present in the public schema
SELECT indexname, tablename, indexdef 
FROM pg_indexes 
WHERE schemaname = 'public' AND tablename NOT LIKE 'alembic_%';

-- 6. List all constraints (Unique, Foreign Key, Primary Key) in the public schema
SELECT conname, contype::text, conind::regclass::text AS index_ref
FROM pg_constraint 
WHERE connamespace = 'public'::regnamespace;
