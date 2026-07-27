-- 1. Clean all dynamic/runtime data and restart sequences
TRUNCATE TABLE 
    alerts, alert_client_states,
    reputation_scores, executive_reputation_scores, competitor_benchmarks,
    executive_candidates, competitor_candidates,
    narratives,
    risk_events, risk_client_states,
    trend_events, trend_client_states,
    entity_mentions, entity_sentiments, document_sentiments,
    document_topics,
    matching_metrics, model_runs, document_matches, documents,
    rss_feeds, collection_jobs,
    search_jobs, search_cursors, search_source_configurations,
    entity_keywords, entity_aliases, entities,
    source_health, sources,
    client_processing_summary,
    clients
    RESTART IDENTITY
    CASCADE;

-- 2. Seed development configuration data
INSERT INTO source_categories (id, name, base_reliability_score) VALUES ('925d4ee4-cba1-4896-8493-04776b86be8f', 'RSS News', 1.00) ON CONFLICT (id) DO NOTHING;

INSERT INTO topics (id, name, description) VALUES ('b9fb0a8d-fc14-4a22-9aab-17bbc63ebad6', 'Financial Results', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('0503f68d-62db-4c87-9e48-94105e5bc48f', 'Executive Leadership', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('c11bb3c4-aad7-4e83-9e54-c540eda8354e', 'Product Launch', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('01c78f9a-95c1-4950-a4d4-be72eda9dbda', 'Legal Risk', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('b26fd5c2-af9f-477e-8ef3-eac37ad70deb', 'Regulatory Risk', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('912c2e3f-8118-40a0-a29b-6772e1673489', 'Environmental', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('113a8e5b-fdf1-490b-bc7b-ecb1f7d048ad', 'Cybersecurity', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('36c6e649-1c3c-4752-9e9f-639689eb1f67', 'Labor Relations', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('6f147c3c-0c10-4a71-9c0e-44046cfbd89d', 'Mergers & Acquisitions', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('f985dcb1-6806-4f3b-8e7f-7960f32d27d2', 'Market Share', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('63db838d-0e3c-4b11-940b-ab03bc6e117f', 'Innovation', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('ca23009c-968b-44d1-a419-ff0ab4b11d7c', 'Customer Satisfaction', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('5cc2f789-43e8-4197-b78d-99649357c8a5', 'Safety Recall', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('a74832d4-8628-4a1e-a309-864fe5dc2fb7', 'Competition', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('5fa14fa1-36d6-4cbb-97d6-1dce5eb24733', 'Electric Vehicles', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('0d900b05-aec2-4ea8-8f8f-628f84598e19', 'Autonomous Driving', NULL) ON CONFLICT (id) DO NOTHING;
INSERT INTO topics (id, name, description) VALUES ('2faa9f2a-b639-40f7-b9ee-4524649d8a03', 'Energy Storage', NULL) ON CONFLICT (id) DO NOTHING;
