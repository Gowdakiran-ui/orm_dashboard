--
-- PostgreSQL database dump
--
-- This file is the authoritative schema source of truth for this project
-- (see TASK.md — Remove Alembic, Adopt schema.sql as Source of Truth).
-- Regenerated via `pg_dump --schema-only` against the local dev DB.
--
-- Two things were stripped from the raw pg_dump output before committing:
--  1. `\restrict`/`\unrestrict` — pg_dump 18 wraps dumps in these psql-only
--     meta-commands. They are not valid SQL and this project applies schema
--     via psycopg2/SQLAlchemy, not the psql CLI, so left in they would break
--     any programmatic apply.
--  2. The `pgagent` schema/extension (CREATE SCHEMA pgagent, CREATE
--     EXTENSION pgagent, and their COMMENT ON statements) — this is local
--     pgAdmin job-scheduler tooling that leaked into the local dev DB, not
--     part of the application's own schema. It is not referenced by any
--     model or migration and would likely fail to install on a hosted
--     provider (e.g. Render) that doesn't ship the pgagent extension.
--

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alert_client_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alert_client_states (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    processing_status character varying(30) DEFAULT 'ALERT_PENDING'::character varying NOT NULL,
    run_id character varying(64),
    batch_id character varying(64),
    retry_count integer DEFAULT 0 NOT NULL,
    last_retry_at timestamp with time zone,
    last_run_at timestamp with time zone,
    last_success_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: alerts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alerts (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    document_id uuid,
    entity_id uuid,
    alert_type character varying(50) NOT NULL,
    severity character varying(20) NOT NULL,
    title character varying(255) NOT NULL,
    description character varying,
    trigger_value double precision,
    baseline_value double precision,
    is_acknowledged boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    processing_status character varying(30) DEFAULT 'ALERT_PENDING'::character varying NOT NULL,
    run_id character varying(64),
    batch_id character varying(64),
    worker_id character varying(64),
    latency_ms double precision,
    retry_count integer DEFAULT 0,
    failure_reason text,
    state_history json,
    confidence_score double precision,
    evidence_score double precision,
    article_count integer DEFAULT 1,
    supporting_signals json,
    explainability json,
    lifecycle_status character varying(30) DEFAULT 'NEW'::character varying NOT NULL,
    lifecycle_history json,
    escalation_history json,
    human_summary character varying,
    CONSTRAINT ck_alerts_confidence_score CHECK (((confidence_score IS NULL) OR ((confidence_score >= (0)::double precision) AND (confidence_score <= (100)::double precision)))),
    CONSTRAINT ck_alerts_evidence_score CHECK (((evidence_score IS NULL) OR ((evidence_score >= (0)::double precision) AND (evidence_score <= (100)::double precision))))
);


--
-- Name: client_processing_summary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.client_processing_summary (
    client_id uuid NOT NULL,
    client_name character varying(255) NOT NULL,
    documents_collected integer DEFAULT 0,
    documents_processed integer DEFAULT 0,
    entity_matches integer DEFAULT 0,
    topics_generated integer DEFAULT 0,
    sentiments_generated integer DEFAULT 0,
    risks_generated integer DEFAULT 0,
    alerts_generated integer DEFAULT 0,
    narratives_generated integer DEFAULT 0,
    reputation_score double precision DEFAULT 0.0,
    last_processed_at timestamp with time zone DEFAULT now()
);


--
-- Name: clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clients (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    industry character varying(100),
    created_at timestamp with time zone DEFAULT now(),
    narrative_processing_status character varying(50) DEFAULT 'NARRATIVE_PENDING'::character varying,
    narrative_failure_reason character varying(4000),
    narrative_retry_count integer DEFAULT 0,
    narrative_run_id character varying(100),
    narrative_batch_id character varying(100),
    narrative_latency_ms double precision,
    narrative_failed_at timestamp with time zone,
    reputation_processing_status character varying(50) DEFAULT 'REPUTATION_PENDING'::character varying,
    reputation_failure_reason character varying(4000),
    reputation_retry_count integer DEFAULT 0,
    reputation_run_id character varying(100),
    reputation_batch_id character varying(100),
    reputation_latency_ms double precision,
    reputation_failed_at timestamp with time zone,
    exec_reputation_processing_status character varying(50) DEFAULT 'EXEC_REPUTATION_PENDING'::character varying,
    exec_reputation_failure_reason character varying(4000),
    exec_reputation_retry_count integer DEFAULT 0,
    exec_reputation_run_id character varying(100),
    exec_reputation_batch_id character varying(100),
    exec_reputation_latency_ms double precision,
    exec_reputation_failed_at timestamp with time zone,
    benchmark_processing_status character varying(50) DEFAULT 'BENCHMARK_PENDING'::character varying,
    benchmark_failure_reason character varying(4000),
    benchmark_retry_count integer DEFAULT 0,
    benchmark_run_id character varying(100),
    benchmark_batch_id character varying(100),
    benchmark_latency_ms double precision,
    benchmark_failed_at timestamp with time zone
);


--
-- Name: collection_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collection_jobs (
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    status character varying(50),
    started_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone,
    documents_found integer,
    documents_saved integer,
    documents_matched integer,
    documents_deduplicated integer,
    documents_failed integer
);


--
-- Name: competitor_benchmarks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.competitor_benchmarks (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    competitor_entity_id uuid NOT NULL,
    reputation_score double precision NOT NULL,
    executive_reputation_score double precision NOT NULL,
    sentiment_score double precision NOT NULL,
    risk_score double precision NOT NULL,
    visibility_score double precision NOT NULL,
    share_of_voice double precision NOT NULL,
    top_narrative character varying(255),
    rank integer NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    run_id character varying(100),
    batch_id character varying(100),
    worker_id character varying(100),
    latency_ms double precision,
    retry_count integer,
    calculation_lineage jsonb,
    evidence_metadata jsonb,
    health_status character varying(50),
    confidence_score double precision,
    data_coverage double precision DEFAULT 0.40,
    CONSTRAINT ck_competitor_benchmarks_confidence_score CHECK (((confidence_score IS NULL) OR ((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision))))
);


--
-- Name: competitor_candidates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.competitor_candidates (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    organization_name character varying(255) NOT NULL,
    mention_count integer DEFAULT 1 NOT NULL,
    first_seen timestamp with time zone DEFAULT now() NOT NULL,
    last_seen timestamp with time zone DEFAULT now() NOT NULL,
    confidence double precision DEFAULT '0'::double precision NOT NULL,
    source_documents jsonb DEFAULT '[]'::jsonb,
    promoted_to_competitor_id uuid,
    promoted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: document_matches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_matches (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    keyword_id uuid,
    matched_text text,
    created_at timestamp with time zone DEFAULT now(),
    matched_entity_id uuid NOT NULL,
    match_type character varying(50),
    match_confidence double precision,
    match_metadata jsonb
);


--
-- Name: document_sentiments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_sentiments (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    sentiment_label character varying(50) NOT NULL,
    sentiment_score double precision NOT NULL,
    confidence_score double precision NOT NULL,
    source_reliability double precision,
    weighted_sentiment_score double precision NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    explainability_metadata json,
    CONSTRAINT ck_document_sentiments_sentiment_score CHECK (((sentiment_score >= ('-1'::integer)::double precision) AND (sentiment_score <= (1)::double precision))),
    CONSTRAINT ck_document_sentiments_confidence_score CHECK (((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision))),
    CONSTRAINT ck_document_sentiments_weighted_score CHECK (((weighted_sentiment_score >= ('-1'::integer)::double precision) AND (weighted_sentiment_score <= (1)::double precision)))
);


--
-- Name: document_topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_topics (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    topic_id uuid NOT NULL,
    confidence_score double precision NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    explainability_metadata jsonb,
    CONSTRAINT ck_document_topics_confidence_score CHECK (((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision)))
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id uuid NOT NULL,
    url text NOT NULL,
    content_hash character varying(64),
    source_id uuid,
    document_type character varying(50),
    title text,
    normalized_content text NOT NULL,
    author character varying(255),
    published_at timestamp with time zone,
    collected_at timestamp with time zone DEFAULT now(),
    language character varying(10),
    raw_storage_path character varying(1024),
    processing_status character varying(20),
    processing_started_at timestamp with time zone,
    match_retry_count integer DEFAULT 0,
    match_failed_at timestamp with time zone,
    match_failure_reason text,
    match_run_id character varying(64),
    match_batch_id character varying(64),
    match_processing_time_ms double precision,
    topic_processing_status character varying(30) DEFAULT 'PENDING'::character varying,
    topic_retry_count integer DEFAULT 0,
    topic_failed_at timestamp with time zone,
    topic_failure_reason text,
    topic_run_id character varying(64),
    topic_batch_id character varying(64),
    topic_processing_time_ms double precision,
    sentiment_processing_status character varying(30) DEFAULT 'SENTIMENT_PENDING'::character varying,
    sentiment_retry_count integer DEFAULT 0,
    sentiment_failed_at timestamp with time zone,
    sentiment_failure_reason text,
    sentiment_run_id character varying(64),
    sentiment_batch_id character varying(64),
    sentiment_processing_time_ms double precision,
    CONSTRAINT documents_processing_status_check CHECK (((processing_status)::text = ANY ((ARRAY['PENDING'::character varying, 'PROCESSING'::character varying, 'MATCHED'::character varying, 'FAILED'::character varying, 'SKIPPED'::character varying, 'RETRYING'::character varying, 'COMPLETED'::character varying])::text[])))
);


--
-- Name: entities; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entities (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    entity_type character varying(50),
    created_at timestamp with time zone DEFAULT now(),
    website character varying(255),
    domain character varying(255),
    linkedin_url character varying(1024),
    ticker_symbol character varying(20),
    industry character varying(100)
);


--
-- Name: entity_aliases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_aliases (
    id uuid NOT NULL,
    entity_id uuid NOT NULL,
    alias_text character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: entity_keywords; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_keywords (
    id uuid NOT NULL,
    entity_id uuid NOT NULL,
    keyword_text character varying(255) NOT NULL,
    match_type character varying(20),
    is_active boolean,
    category character varying(50) NOT NULL,
    priority integer,
    search_frequency_minutes integer
);


--
-- Name: entity_mentions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_mentions (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    role character varying(50),
    mention_count integer,
    confidence_score double precision,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ck_entity_mentions_confidence_score CHECK (((confidence_score IS NULL) OR ((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision))))
);


--
-- Name: entity_sentiments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.entity_sentiments (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    sentiment_label character varying(50) NOT NULL,
    sentiment_score double precision NOT NULL,
    confidence_score double precision NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    explainability_metadata json,
    CONSTRAINT ck_entity_sentiments_sentiment_score CHECK (((sentiment_score >= ('-1'::integer)::double precision) AND (sentiment_score <= (1)::double precision))),
    CONSTRAINT ck_entity_sentiments_confidence_score CHECK (((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision)))
);


--
-- Name: executive_candidates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.executive_candidates (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    organization character varying(255),
    mention_count integer DEFAULT 1 NOT NULL,
    first_seen timestamp with time zone DEFAULT now() NOT NULL,
    last_seen timestamp with time zone DEFAULT now() NOT NULL,
    confidence double precision DEFAULT '0'::double precision NOT NULL,
    source_documents jsonb DEFAULT '[]'::jsonb,
    promoted_to_executive_id uuid,
    promoted_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: executive_reputation_scores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.executive_reputation_scores (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    executive_name character varying(255) NOT NULL,
    score double precision NOT NULL,
    grade character varying(2) NOT NULL,
    sentiment_component double precision NOT NULL,
    risk_component double precision NOT NULL,
    narrative_component double precision NOT NULL,
    trend_component double precision NOT NULL,
    visibility_component double precision NOT NULL,
    confidence_score double precision NOT NULL,
    reputation_trend character varying(20) NOT NULL,
    top_positive_narrative character varying(255),
    top_negative_narrative character varying(255),
    created_at timestamp with time zone DEFAULT now(),
    run_id character varying(100),
    batch_id character varying(100),
    worker_id character varying(100),
    latency_ms double precision,
    retry_count integer,
    evidence_metadata jsonb,
    calculation_lineage jsonb,
    health_status character varying(50),
    data_coverage double precision DEFAULT 0.40,
    CONSTRAINT ck_exec_reputation_scores_score CHECK (((score >= (0)::double precision) AND (score <= (100)::double precision))),
    CONSTRAINT ck_exec_reputation_scores_confidence_score CHECK (((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision)))
);


--
-- Name: matching_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.matching_metrics (
    id uuid NOT NULL,
    documents_processed integer,
    matches_found integer,
    processing_time double precision,
    keywords_loaded integer,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: model_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.model_runs (
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    model_name character varying(255) NOT NULL,
    model_version character varying(50),
    processed_at timestamp with time zone DEFAULT now()
);


--
-- Name: narratives; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.narratives (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    narrative_name character varying(255) NOT NULL,
    narrative_type character varying(100) NOT NULL,
    mention_count integer NOT NULL,
    sentiment_score double precision NOT NULL,
    risk_score double precision NOT NULL,
    trend_strength double precision NOT NULL,
    status character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    run_id character varying(100),
    batch_id character varying(100),
    worker_id character varying(100),
    latency_ms double precision,
    retry_count integer,
    summary_text character varying(4000),
    confidence_score double precision DEFAULT 1.0 NOT NULL,
    evidence_metadata jsonb,
    CONSTRAINT ck_narratives_sentiment_score CHECK (((sentiment_score >= ('-1'::integer)::double precision) AND (sentiment_score <= (1)::double precision))),
    CONSTRAINT ck_narratives_risk_score CHECK (((risk_score >= (0)::double precision) AND (risk_score <= (100)::double precision))),
    CONSTRAINT ck_narratives_confidence_score CHECK (((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision)))
);


--
-- Name: pipeline_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id character varying(64) NOT NULL,
    run_id character varying(64) NOT NULL,
    status character varying(20) DEFAULT 'QUEUED'::character varying NOT NULL,
    stage character varying(30) DEFAULT 'QUEUED'::character varying NOT NULL,
    progress_pct integer DEFAULT 0 NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    current_worker character varying(100),
    execution_mode character varying(20) DEFAULT 'async'::character varying NOT NULL,
    celery_task_id character varying(100),
    error_detail text,
    log_tail text,
    duration_s double precision,
    processing_started_at timestamp with time zone,
    execution_duration_s double precision
);


--
-- Name: reputation_scores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reputation_scores (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    score double precision,
    grade character varying(2),
    sentiment_component double precision,
    risk_component double precision,
    narrative_component double precision,
    trend_component double precision,
    source_component double precision,
    visibility_component double precision,
    confidence_score double precision NOT NULL,
    reputation_trend character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    run_id character varying(100),
    batch_id character varying(100),
    worker_id character varying(100),
    latency_ms double precision,
    retry_count integer,
    evidence_metadata jsonb,
    calculation_lineage jsonb,
    health_status character varying(50),
    data_coverage double precision DEFAULT 0.40,
    CONSTRAINT ck_reputation_scores_score CHECK (((score IS NULL) OR ((score >= (0)::double precision) AND (score <= (100)::double precision)))),
    CONSTRAINT ck_reputation_scores_confidence_score CHECK (((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision)))
);


--
-- Name: risk_client_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_client_states (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    processing_status character varying(30) DEFAULT 'RISK_PENDING'::character varying NOT NULL,
    run_id character varying(64),
    batch_id character varying(64),
    retry_count integer DEFAULT 0 NOT NULL,
    last_retry_at timestamp with time zone,
    last_run_at timestamp with time zone,
    last_success_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: risk_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_events (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    document_id uuid,
    entity_id uuid,
    risk_score double precision NOT NULL,
    risk_level character varying(20) NOT NULL,
    confidence_score double precision NOT NULL,
    risk_factors text,
    created_at timestamp with time zone DEFAULT now(),
    run_id character varying(64),
    batch_id character varying(64),
    worker_id character varying(64),
    latency_ms double precision,
    retry_count integer DEFAULT 0,
    source_reliability double precision,
    explainability json,
    CONSTRAINT ck_risk_events_risk_score CHECK (((risk_score >= (0)::double precision) AND (risk_score <= (100)::double precision))),
    CONSTRAINT ck_risk_events_confidence_score CHECK (((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision)))
);


--
-- Name: rss_feeds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.rss_feeds (
    id uuid NOT NULL,
    feed_name character varying(255) NOT NULL,
    feed_url character varying(1024) NOT NULL,
    category character varying(50),
    poll_interval_minutes integer,
    is_active boolean,
    last_polled_at timestamp with time zone,
    last_entry_guid text,
    last_entry_published_at timestamp with time zone,
    reliability_score double precision,
    extract_full_article boolean,
    created_at timestamp with time zone DEFAULT now(),
    client_id uuid,
    source_type character varying(20) DEFAULT 'entity_search'::character varying NOT NULL,
    source_format character varying(20) DEFAULT 'rss'::character varying NOT NULL,
    CONSTRAINT ck_rss_feeds_source_format CHECK (((source_format)::text = ANY ((ARRAY['rss'::character varying, 'gdelt_json'::character varying, 'hn_algolia_json'::character varying])::text[]))),
    CONSTRAINT ck_rss_feeds_source_type CHECK (((source_type)::text = ANY ((ARRAY['entity_search'::character varying, 'topical_global'::character varying, 'json_api'::character varying])::text[])))
);


--
-- Name: search_cursors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_cursors (
    id uuid NOT NULL,
    keyword_id uuid NOT NULL,
    source_type character varying(50) NOT NULL,
    cursor_value character varying(512),
    last_searched_at timestamp with time zone
);


--
-- Name: search_jobs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_jobs (
    job_id uuid NOT NULL,
    source_type character varying(50) NOT NULL,
    keyword character varying(255) NOT NULL,
    status character varying(50),
    started_at timestamp with time zone DEFAULT now(),
    completed_at timestamp with time zone,
    results_found integer,
    results_saved integer,
    results_matched integer
);


--
-- Name: search_source_configurations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.search_source_configurations (
    id uuid NOT NULL,
    source_type character varying(50) NOT NULL,
    enabled boolean,
    daily_quota integer,
    rate_limit integer,
    reliability_score double precision,
    source_priority integer
);


--
-- Name: source_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_categories (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    base_reliability_score numeric(3,2)
);


--
-- Name: source_health; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_health (
    id uuid NOT NULL,
    source_id uuid NOT NULL,
    status character varying(50),
    reliability_penalty numeric(3,2),
    consecutive_failures integer,
    last_success_at timestamp with time zone
);


--
-- Name: sources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sources (
    id uuid NOT NULL,
    category_id uuid,
    name character varying(255) NOT NULL,
    source_type character varying(50) NOT NULL,
    url character varying(1024),
    schedule_cron character varying(50) NOT NULL,
    query_template text,
    is_active boolean
);


--
-- Name: topics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.topics (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description character varying(1024),
    parent_topic_id uuid,
    is_active boolean,
    created_at timestamp with time zone DEFAULT now(),
    confidence_threshold double precision DEFAULT 0.5
);


--
-- Name: trend_client_states; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trend_client_states (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    processing_status character varying(30) DEFAULT 'TREND_PENDING'::character varying NOT NULL,
    run_id character varying(64),
    batch_id character varying(64),
    retry_count integer DEFAULT 0 NOT NULL,
    last_retry_at timestamp with time zone,
    last_run_at timestamp with time zone,
    last_success_at timestamp with time zone,
    last_error text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: trend_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trend_events (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    trend_type character varying(50) NOT NULL,
    entity_id uuid,
    topic_id uuid,
    baseline_value double precision NOT NULL,
    current_value double precision NOT NULL,
    percentage_change double precision NOT NULL,
    severity character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    run_id character varying(64),
    batch_id character varying(64),
    trend_date date,
    baseline_established boolean DEFAULT true NOT NULL,
    trend_direction character varying(50),
    decision_reason text,
    triggering_documents json,
    time_window character varying(50) DEFAULT '24h_vs_7d'::character varying
);


--
-- Name: alert_client_states alert_client_states_client_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_client_states
    ADD CONSTRAINT alert_client_states_client_id_key UNIQUE (client_id);


--
-- Name: alert_client_states alert_client_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_client_states
    ADD CONSTRAINT alert_client_states_pkey PRIMARY KEY (id);


--
-- Name: alerts alerts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_pkey PRIMARY KEY (id);


--
-- Name: client_processing_summary client_processing_summary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_processing_summary
    ADD CONSTRAINT client_processing_summary_pkey PRIMARY KEY (client_id);


--
-- Name: clients clients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clients
    ADD CONSTRAINT clients_pkey PRIMARY KEY (id);


--
-- Name: collection_jobs collection_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_jobs
    ADD CONSTRAINT collection_jobs_pkey PRIMARY KEY (job_id);


--
-- Name: competitor_benchmarks competitor_benchmarks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.competitor_benchmarks
    ADD CONSTRAINT competitor_benchmarks_pkey PRIMARY KEY (id);


--
-- Name: competitor_candidates competitor_candidates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.competitor_candidates
    ADD CONSTRAINT competitor_candidates_pkey PRIMARY KEY (id);


--
-- Name: document_matches document_matches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_matches
    ADD CONSTRAINT document_matches_pkey PRIMARY KEY (id);


--
-- Name: document_sentiments document_sentiments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_sentiments
    ADD CONSTRAINT document_sentiments_pkey PRIMARY KEY (id);


--
-- Name: document_topics document_topics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_topics
    ADD CONSTRAINT document_topics_pkey PRIMARY KEY (id);


--
-- Name: documents documents_content_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_content_hash_key UNIQUE (content_hash);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: documents documents_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_url_key UNIQUE (url);


--
-- Name: entities entities_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities
    ADD CONSTRAINT entities_pkey PRIMARY KEY (id);


--
-- Name: entity_aliases entity_aliases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_aliases
    ADD CONSTRAINT entity_aliases_pkey PRIMARY KEY (id);


--
-- Name: entity_keywords entity_keywords_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_keywords
    ADD CONSTRAINT entity_keywords_pkey PRIMARY KEY (id);


--
-- Name: entity_mentions entity_mentions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_mentions
    ADD CONSTRAINT entity_mentions_pkey PRIMARY KEY (id);


--
-- Name: entity_sentiments entity_sentiments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_sentiments
    ADD CONSTRAINT entity_sentiments_pkey PRIMARY KEY (id);


--
-- Name: executive_candidates executive_candidates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.executive_candidates
    ADD CONSTRAINT executive_candidates_pkey PRIMARY KEY (id);


--
-- Name: executive_reputation_scores executive_reputation_scores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.executive_reputation_scores
    ADD CONSTRAINT executive_reputation_scores_pkey PRIMARY KEY (id);


--
-- Name: matching_metrics matching_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.matching_metrics
    ADD CONSTRAINT matching_metrics_pkey PRIMARY KEY (id);


--
-- Name: model_runs model_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_runs
    ADD CONSTRAINT model_runs_pkey PRIMARY KEY (id);


--
-- Name: narratives narratives_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.narratives
    ADD CONSTRAINT narratives_pkey PRIMARY KEY (id);


--
-- Name: pipeline_runs pipeline_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_pkey PRIMARY KEY (id);


--
-- Name: reputation_scores reputation_scores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reputation_scores
    ADD CONSTRAINT reputation_scores_pkey PRIMARY KEY (id);


--
-- Name: risk_client_states risk_client_states_client_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_client_states
    ADD CONSTRAINT risk_client_states_client_id_key UNIQUE (client_id);


--
-- Name: risk_client_states risk_client_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_client_states
    ADD CONSTRAINT risk_client_states_pkey PRIMARY KEY (id);


--
-- Name: risk_events risk_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_events
    ADD CONSTRAINT risk_events_pkey PRIMARY KEY (id);


--
-- Name: rss_feeds rss_feeds_feed_url_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rss_feeds
    ADD CONSTRAINT rss_feeds_feed_url_key UNIQUE (feed_url);


--
-- Name: rss_feeds rss_feeds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rss_feeds
    ADD CONSTRAINT rss_feeds_pkey PRIMARY KEY (id);


--
-- Name: search_cursors search_cursors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_cursors
    ADD CONSTRAINT search_cursors_pkey PRIMARY KEY (id);


--
-- Name: search_jobs search_jobs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_jobs
    ADD CONSTRAINT search_jobs_pkey PRIMARY KEY (job_id);


--
-- Name: search_source_configurations search_source_configurations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_source_configurations
    ADD CONSTRAINT search_source_configurations_pkey PRIMARY KEY (id);


--
-- Name: search_source_configurations search_source_configurations_source_type_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_source_configurations
    ADD CONSTRAINT search_source_configurations_source_type_key UNIQUE (source_type);


--
-- Name: source_categories source_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_categories
    ADD CONSTRAINT source_categories_pkey PRIMARY KEY (id);


--
-- Name: source_health source_health_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_health
    ADD CONSTRAINT source_health_pkey PRIMARY KEY (id);


--
-- Name: sources sources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_pkey PRIMARY KEY (id);


--
-- Name: topics topics_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_name_key UNIQUE (name);


--
-- Name: topics topics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_pkey PRIMARY KEY (id);


--
-- Name: trend_client_states trend_client_states_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trend_client_states
    ADD CONSTRAINT trend_client_states_pkey PRIMARY KEY (id);


--
-- Name: trend_events trend_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trend_events
    ADD CONSTRAINT trend_events_pkey PRIMARY KEY (id);


--
-- Name: document_topics unique_document_topic; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_topics
    ADD CONSTRAINT unique_document_topic UNIQUE (document_id, topic_id);


--
-- Name: narratives uq_client_narrative; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.narratives
    ADD CONSTRAINT uq_client_narrative UNIQUE (client_id, narrative_name);


--
-- Name: reputation_scores uq_client_reputation_run; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reputation_scores
    ADD CONSTRAINT uq_client_reputation_run UNIQUE (client_id, run_id);


--
-- Name: clients uq_clients_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clients
    ADD CONSTRAINT uq_clients_name UNIQUE (name);


--
-- Name: competitor_candidates uq_comp_cand_client_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.competitor_candidates
    ADD CONSTRAINT uq_comp_cand_client_name UNIQUE (client_id, organization_name);


--
-- Name: competitor_benchmarks uq_competitor_benchmark_run; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.competitor_benchmarks
    ADD CONSTRAINT uq_competitor_benchmark_run UNIQUE (competitor_entity_id, run_id);


--
-- Name: document_sentiments uq_document_sentiments_document_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_sentiments
    ADD CONSTRAINT uq_document_sentiments_document_id UNIQUE (document_id);


--
-- Name: entities uq_entities_client_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities
    ADD CONSTRAINT uq_entities_client_name UNIQUE (client_id, name);


--
-- Name: entity_sentiments uq_entity_sentiments_doc_entity; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_sentiments
    ADD CONSTRAINT uq_entity_sentiments_doc_entity UNIQUE (document_id, entity_id);


--
-- Name: executive_candidates uq_exec_cand_client_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.executive_candidates
    ADD CONSTRAINT uq_exec_cand_client_name UNIQUE (client_id, name);


--
-- Name: executive_reputation_scores uq_exec_reputation_run; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.executive_reputation_scores
    ADD CONSTRAINT uq_exec_reputation_run UNIQUE (entity_id, run_id);


--
-- Name: source_health uq_source_health_source_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_health
    ADD CONSTRAINT uq_source_health_source_id UNIQUE (source_id);


--
-- Name: sources uq_sources_url; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT uq_sources_url UNIQUE (url);


--
-- Name: trend_client_states uq_trend_client_states_client_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trend_client_states
    ADD CONSTRAINT uq_trend_client_states_client_id UNIQUE (client_id);


--
-- Name: idx_comp_cand_promoted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_comp_cand_promoted ON public.competitor_candidates USING btree (promoted_to_competitor_id);


--
-- Name: idx_documents_collected_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_collected_at ON public.documents USING btree (collected_at);


--
-- Name: idx_documents_processing_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_processing_status ON public.documents USING btree (processing_status);


--
-- Name: idx_exec_cand_promoted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_exec_cand_promoted ON public.executive_candidates USING btree (promoted_to_executive_id);


--
-- Name: idx_sources_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sources_category ON public.sources USING btree (category_id);


--
-- Name: idx_topics_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_topics_parent ON public.topics USING btree (parent_topic_id);


--
-- Name: ix_alert_client_states_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_alert_client_states_client_id ON public.alert_client_states USING btree (client_id);


--
-- Name: ix_alerts_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alerts_client_id ON public.alerts USING btree (client_id);


--
-- Name: ix_alerts_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alerts_document_id ON public.alerts USING btree (document_id);


--
-- Name: ix_alerts_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_alerts_entity_id ON public.alerts USING btree (entity_id);


--
-- Name: ix_collection_jobs_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collection_jobs_source_id ON public.collection_jobs USING btree (source_id);


--
-- Name: ix_competitor_benchmarks_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_competitor_benchmarks_client_id ON public.competitor_benchmarks USING btree (client_id);


--
-- Name: ix_competitor_benchmarks_competitor_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_competitor_benchmarks_competitor_entity_id ON public.competitor_benchmarks USING btree (competitor_entity_id);


--
-- Name: ix_competitor_candidates_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_competitor_candidates_client_id ON public.competitor_candidates USING btree (client_id);


--
-- Name: ix_competitor_candidates_organization_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_competitor_candidates_organization_name ON public.competitor_candidates USING btree (organization_name);


--
-- Name: ix_document_matches_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_matches_document_id ON public.document_matches USING btree (document_id);


--
-- Name: ix_document_matches_keyword_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_matches_keyword_id ON public.document_matches USING btree (keyword_id);


--
-- Name: ix_document_matches_matched_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_matches_matched_entity_id ON public.document_matches USING btree (matched_entity_id);


--
-- Name: ix_document_sentiments_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_sentiments_document_id ON public.document_sentiments USING btree (document_id);


--
-- Name: ix_document_topics_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_topics_document_id ON public.document_topics USING btree (document_id);


--
-- Name: ix_document_topics_topic_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_topics_topic_id ON public.document_topics USING btree (topic_id);


--
-- Name: ix_documents_source_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_documents_source_id ON public.documents USING btree (source_id);


--
-- Name: ix_entities_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entities_client_id ON public.entities USING btree (client_id);


--
-- Name: ix_entity_aliases_alias_text; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_aliases_alias_text ON public.entity_aliases USING btree (alias_text);


--
-- Name: ix_entity_aliases_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_aliases_entity_id ON public.entity_aliases USING btree (entity_id);


--
-- Name: ix_entity_keywords_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_keywords_entity_id ON public.entity_keywords USING btree (entity_id);


--
-- Name: ix_entity_keywords_keyword_text; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_keywords_keyword_text ON public.entity_keywords USING btree (keyword_text);


--
-- Name: ix_entity_mentions_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_mentions_document_id ON public.entity_mentions USING btree (document_id);


--
-- Name: ix_entity_mentions_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_mentions_entity_id ON public.entity_mentions USING btree (entity_id);


--
-- Name: ix_entity_sentiments_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_sentiments_document_id ON public.entity_sentiments USING btree (document_id);


--
-- Name: ix_entity_sentiments_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_entity_sentiments_entity_id ON public.entity_sentiments USING btree (entity_id);


--
-- Name: ix_executive_candidates_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_executive_candidates_client_id ON public.executive_candidates USING btree (client_id);


--
-- Name: ix_executive_candidates_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_executive_candidates_name ON public.executive_candidates USING btree (name);


--
-- Name: ix_executive_reputation_scores_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_executive_reputation_scores_client_id ON public.executive_reputation_scores USING btree (client_id);


--
-- Name: ix_executive_reputation_scores_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_executive_reputation_scores_entity_id ON public.executive_reputation_scores USING btree (entity_id);


--
-- Name: ix_model_runs_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_model_runs_document_id ON public.model_runs USING btree (document_id);


--
-- Name: ix_narratives_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_narratives_client_id ON public.narratives USING btree (client_id);


--
-- Name: ix_pipeline_runs_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pipeline_runs_client_id ON public.pipeline_runs USING btree (client_id);


--
-- Name: ix_pipeline_runs_client_id_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pipeline_runs_client_id_started_at ON public.pipeline_runs USING btree (client_id, started_at);


--
-- Name: ix_pipeline_runs_run_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_pipeline_runs_run_id ON public.pipeline_runs USING btree (run_id);


--
-- Name: ix_reputation_scores_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_reputation_scores_client_id ON public.reputation_scores USING btree (client_id);


--
-- Name: ix_risk_client_states_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_risk_client_states_client_id ON public.risk_client_states USING btree (client_id);


--
-- Name: ix_risk_events_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risk_events_client_id ON public.risk_events USING btree (client_id);


--
-- Name: ix_risk_events_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risk_events_document_id ON public.risk_events USING btree (document_id);


--
-- Name: ix_risk_events_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_risk_events_entity_id ON public.risk_events USING btree (entity_id);


--
-- Name: ix_rss_feeds_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_rss_feeds_client_id ON public.rss_feeds USING btree (client_id);


--
-- Name: ix_search_cursors_keyword_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_search_cursors_keyword_id ON public.search_cursors USING btree (keyword_id);


--
-- Name: ix_trend_client_states_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_trend_client_states_client_id ON public.trend_client_states USING btree (client_id);


--
-- Name: ix_trend_client_states_processing_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trend_client_states_processing_status ON public.trend_client_states USING btree (processing_status);


--
-- Name: ix_trend_events_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trend_events_client_id ON public.trend_events USING btree (client_id);


--
-- Name: ix_trend_events_entity_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trend_events_entity_id ON public.trend_events USING btree (entity_id);


--
-- Name: ix_trend_events_topic_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trend_events_topic_id ON public.trend_events USING btree (topic_id);


--
-- Name: ix_trend_events_trend_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_trend_events_trend_date ON public.trend_events USING btree (trend_date);


--
-- Name: uq_alerts_business; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_alerts_business ON public.alerts USING btree (client_id, alert_type, COALESCE((entity_id)::text, ''::text), COALESCE((document_id)::text, ''::text));


--
-- Name: uq_risk_events_daily; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_risk_events_daily ON public.risk_events USING btree (client_id, COALESCE((document_id)::text, ''::text), COALESCE((entity_id)::text, ''::text));


--
-- Name: uq_trend_events_daily; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_trend_events_daily ON public.trend_events USING btree (client_id, trend_type, COALESCE((entity_id)::text, ''::text), COALESCE((topic_id)::text, ''::text), trend_date) WHERE (trend_date IS NOT NULL);


--
-- Name: alert_client_states alert_client_states_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alert_client_states
    ADD CONSTRAINT alert_client_states_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: alerts alerts_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: alerts alerts_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: alerts alerts_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alerts
    ADD CONSTRAINT alerts_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: client_processing_summary client_processing_summary_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.client_processing_summary
    ADD CONSTRAINT client_processing_summary_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: collection_jobs collection_jobs_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_jobs
    ADD CONSTRAINT collection_jobs_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.rss_feeds(id) ON DELETE CASCADE;


--
-- Name: competitor_benchmarks competitor_benchmarks_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.competitor_benchmarks
    ADD CONSTRAINT competitor_benchmarks_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: competitor_benchmarks competitor_benchmarks_competitor_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.competitor_benchmarks
    ADD CONSTRAINT competitor_benchmarks_competitor_entity_id_fkey FOREIGN KEY (competitor_entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: competitor_candidates competitor_candidates_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.competitor_candidates
    ADD CONSTRAINT competitor_candidates_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: competitor_candidates competitor_candidates_promoted_to_competitor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.competitor_candidates
    ADD CONSTRAINT competitor_candidates_promoted_to_competitor_id_fkey FOREIGN KEY (promoted_to_competitor_id) REFERENCES public.entities(id) ON DELETE SET NULL;


--
-- Name: document_matches document_matches_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_matches
    ADD CONSTRAINT document_matches_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: document_matches document_matches_keyword_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_matches
    ADD CONSTRAINT document_matches_keyword_id_fkey FOREIGN KEY (keyword_id) REFERENCES public.entity_keywords(id);


--
-- Name: document_matches document_matches_matched_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_matches
    ADD CONSTRAINT document_matches_matched_entity_id_fkey FOREIGN KEY (matched_entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: document_sentiments document_sentiments_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_sentiments
    ADD CONSTRAINT document_sentiments_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: document_topics document_topics_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_topics
    ADD CONSTRAINT document_topics_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: document_topics document_topics_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_topics
    ADD CONSTRAINT document_topics_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES public.topics(id) ON DELETE CASCADE;


--
-- Name: documents documents_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id);


--
-- Name: entities entities_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entities
    ADD CONSTRAINT entities_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: entity_aliases entity_aliases_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_aliases
    ADD CONSTRAINT entity_aliases_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: entity_keywords entity_keywords_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_keywords
    ADD CONSTRAINT entity_keywords_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: entity_mentions entity_mentions_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_mentions
    ADD CONSTRAINT entity_mentions_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: entity_mentions entity_mentions_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_mentions
    ADD CONSTRAINT entity_mentions_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: entity_sentiments entity_sentiments_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_sentiments
    ADD CONSTRAINT entity_sentiments_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: entity_sentiments entity_sentiments_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.entity_sentiments
    ADD CONSTRAINT entity_sentiments_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: executive_candidates executive_candidates_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.executive_candidates
    ADD CONSTRAINT executive_candidates_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: executive_candidates executive_candidates_promoted_to_executive_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.executive_candidates
    ADD CONSTRAINT executive_candidates_promoted_to_executive_id_fkey FOREIGN KEY (promoted_to_executive_id) REFERENCES public.entities(id) ON DELETE SET NULL;


--
-- Name: executive_reputation_scores executive_reputation_scores_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.executive_reputation_scores
    ADD CONSTRAINT executive_reputation_scores_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: executive_reputation_scores executive_reputation_scores_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.executive_reputation_scores
    ADD CONSTRAINT executive_reputation_scores_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: rss_feeds fk_rss_feeds_client_id; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.rss_feeds
    ADD CONSTRAINT fk_rss_feeds_client_id FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE SET NULL;


--
-- Name: model_runs model_runs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.model_runs
    ADD CONSTRAINT model_runs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: narratives narratives_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.narratives
    ADD CONSTRAINT narratives_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: reputation_scores reputation_scores_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reputation_scores
    ADD CONSTRAINT reputation_scores_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: risk_client_states risk_client_states_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_client_states
    ADD CONSTRAINT risk_client_states_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: risk_events risk_events_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_events
    ADD CONSTRAINT risk_events_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: risk_events risk_events_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_events
    ADD CONSTRAINT risk_events_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: risk_events risk_events_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_events
    ADD CONSTRAINT risk_events_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: search_cursors search_cursors_keyword_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.search_cursors
    ADD CONSTRAINT search_cursors_keyword_id_fkey FOREIGN KEY (keyword_id) REFERENCES public.entity_keywords(id) ON DELETE CASCADE;


--
-- Name: source_health source_health_source_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_health
    ADD CONSTRAINT source_health_source_id_fkey FOREIGN KEY (source_id) REFERENCES public.sources(id) ON DELETE CASCADE;


--
-- Name: sources sources_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sources
    ADD CONSTRAINT sources_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.source_categories(id);


--
-- Name: topics topics_parent_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.topics
    ADD CONSTRAINT topics_parent_topic_id_fkey FOREIGN KEY (parent_topic_id) REFERENCES public.topics(id);


--
-- Name: trend_client_states trend_client_states_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trend_client_states
    ADD CONSTRAINT trend_client_states_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: trend_events trend_events_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trend_events
    ADD CONSTRAINT trend_events_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;


--
-- Name: trend_events trend_events_entity_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trend_events
    ADD CONSTRAINT trend_events_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;


--
-- Name: trend_events trend_events_topic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trend_events
    ADD CONSTRAINT trend_events_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES public.topics(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

