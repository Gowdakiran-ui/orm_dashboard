-- Migration: Run Pipeline cost meter (per run, per client).
--
-- One additive table, one row per pipeline run (run_id is the same correlation id as pipeline_runs.run_id). It records what the run
-- cost where the cost is knowable: Apify actor usage (Reddit reports its own usageTotalUsd; Instagram is estimated from the number
-- of results at the documented per-result price and flagged as estimated), LLM calls and tokens with an estimated dollar cost (read
-- from llm_call_log for this client during the run), and keyword search calls (search cursors touched during the run).
-- Written best-effort by the collection stage (Apify) and the finalize stage (the rest); a failure to write never fails a pipeline.
-- Read only by the diagnostics endpoint for super admins. No existing table or column is touched; no score reads it.
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0020_add_pipeline_run_costs.sql
-- Safe to re-run (IF NOT EXISTS / DROP-then-ADD guards; the primary key is part of CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS public.pipeline_run_costs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id character varying(64) NOT NULL,
    client_id uuid NOT NULL,
    apify_calls integer DEFAULT 0 NOT NULL,
    apify_cost_usd double precision DEFAULT 0 NOT NULL,
    apify_cost_estimated boolean DEFAULT false NOT NULL,
    apify_by_source jsonb,
    llm_calls integer DEFAULT 0 NOT NULL,
    llm_tokens_prompt bigint DEFAULT 0 NOT NULL,
    llm_tokens_completion bigint DEFAULT 0 NOT NULL,
    llm_est_cost_usd double precision DEFAULT 0 NOT NULL,
    llm_by_type jsonb,
    search_calls integer DEFAULT 0 NOT NULL,
    search_by_source jsonb,
    finalized boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT pipeline_run_costs_pkey PRIMARY KEY (id)
);

ALTER TABLE public.pipeline_run_costs DROP CONSTRAINT IF EXISTS uq_pipeline_run_costs_run_id;
ALTER TABLE public.pipeline_run_costs ADD CONSTRAINT uq_pipeline_run_costs_run_id UNIQUE (run_id);

ALTER TABLE public.pipeline_run_costs DROP CONSTRAINT IF EXISTS pipeline_run_costs_client_id_fkey;
ALTER TABLE public.pipeline_run_costs ADD CONSTRAINT pipeline_run_costs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_pipeline_run_costs_client_created ON public.pipeline_run_costs USING btree (client_id, created_at DESC);
