-- Migration: add llm_call_log table for persisted LLM call/token/cost
-- observability.
--
-- Both _llm_classify_role (risk_engine.py) and _attempt_split_call
-- (narrative_engine.py) call OpenRouter but previously only logged
-- structured events to stdout via structlog -- no DB record of call
-- counts, token usage, or cost existed anywhere. Container recreates
-- during deploys wipe all prior docker logs, so this history was not
-- even reliably recoverable short-term, and there was no way to answer
-- "how much of our LLM spend is risk classification vs. narrative
-- splitting" after the fact.
--
-- This table is additive-only and purely for observability: one row is
-- inserted per OpenRouter call (both call sites, best-effort, wrapped in
-- try/except so a logging failure can never block or fail the LLM call
-- it's recording). No existing table or column is touched.
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0007_add_llm_call_log.sql
-- Safe to re-run (IF NOT EXISTS guards throughout).

CREATE TABLE IF NOT EXISTS public.llm_call_log (
    id uuid NOT NULL,
    call_type character varying(50) NOT NULL,
    client_id uuid NOT NULL,
    run_id character varying(64),
    tokens_prompt integer,
    tokens_completion integer,
    latency_ms double precision,
    success boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);

ALTER TABLE public.llm_call_log
    DROP CONSTRAINT IF EXISTS llm_call_log_pkey;
ALTER TABLE public.llm_call_log
    ADD CONSTRAINT llm_call_log_pkey PRIMARY KEY (id);

ALTER TABLE public.llm_call_log
    DROP CONSTRAINT IF EXISTS llm_call_log_client_id_fkey;
ALTER TABLE public.llm_call_log
    ADD CONSTRAINT llm_call_log_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_llm_call_log_client_id ON public.llm_call_log USING btree (client_id);
CREATE INDEX IF NOT EXISTS ix_llm_call_log_call_type ON public.llm_call_log USING btree (call_type);
