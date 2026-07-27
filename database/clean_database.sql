-- Clean all runtime and dynamic data while keeping schema and configuration data
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
    CASCADE;
