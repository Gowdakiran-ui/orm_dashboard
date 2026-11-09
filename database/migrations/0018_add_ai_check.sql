-- Migration: "What AI says about you" check (super-admin "Run AI check", flag AI_CHECK_ENABLED).
--
-- Two additive tables. ai_check_runs is one run for one client (status, estimated and measured cost, call counts).
-- ai_check_answers is one stored answer of that run: the prompt, the answer text, and the web pages and domains the answer
-- cited, tied to the run id. Nothing reads these tables except the AI-check endpoints and the Brand Equity card; no score,
-- risk event, alert or report reads them. No existing table or column is touched. Rows go with their run or client
-- (ON DELETE CASCADE).
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0018_add_ai_check.sql
-- Safe to re-run (IF NOT EXISTS / DROP-then-ADD guards; the primary keys are part of CREATE TABLE IF NOT EXISTS because the
-- answers table's foreign key depends on the runs table's primary key, which therefore must not be dropped).

CREATE TABLE IF NOT EXISTS public.ai_check_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    status character varying(20) DEFAULT 'running'::character varying NOT NULL,
    model character varying(100) NOT NULL,
    web_results integer NOT NULL,
    repeats integer NOT NULL,
    prompt_count integer NOT NULL,
    estimated_cost_usd double precision,
    cost_usd double precision DEFAULT 0 NOT NULL,
    calls_ok integer DEFAULT 0 NOT NULL,
    calls_failed integer DEFAULT 0 NOT NULL,
    error text,
    started_at timestamp with time zone DEFAULT now(),
    finished_at timestamp with time zone,
    CONSTRAINT ai_check_runs_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.ai_check_answers (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    client_id uuid NOT NULL,
    prompt_key character varying(40) NOT NULL,
    prompt_text text NOT NULL,
    repeat_index integer NOT NULL,
    answer_text text,
    cited_urls jsonb,
    cited_domains jsonb,
    cost_usd double precision,
    tokens_prompt integer,
    tokens_completion integer,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ai_check_answers_pkey PRIMARY KEY (id)
);

ALTER TABLE public.ai_check_runs DROP CONSTRAINT IF EXISTS ai_check_runs_status_check;
ALTER TABLE public.ai_check_runs ADD CONSTRAINT ai_check_runs_status_check CHECK (((status)::text = ANY (ARRAY[('running'::character varying)::text, ('completed'::character varying)::text, ('stopped_at_cap'::character varying)::text, ('failed'::character varying)::text])));

ALTER TABLE public.ai_check_answers DROP CONSTRAINT IF EXISTS uq_ai_check_answers_run_prompt_repeat;
ALTER TABLE public.ai_check_answers ADD CONSTRAINT uq_ai_check_answers_run_prompt_repeat UNIQUE (run_id, prompt_key, repeat_index);

ALTER TABLE public.ai_check_runs DROP CONSTRAINT IF EXISTS ai_check_runs_client_id_fkey;
ALTER TABLE public.ai_check_runs ADD CONSTRAINT ai_check_runs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

ALTER TABLE public.ai_check_answers DROP CONSTRAINT IF EXISTS ai_check_answers_run_id_fkey;
ALTER TABLE public.ai_check_answers ADD CONSTRAINT ai_check_answers_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.ai_check_runs(id) ON DELETE CASCADE;

ALTER TABLE public.ai_check_answers DROP CONSTRAINT IF EXISTS ai_check_answers_client_id_fkey;
ALTER TABLE public.ai_check_answers ADD CONSTRAINT ai_check_answers_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_ai_check_runs_client_started ON public.ai_check_runs USING btree (client_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_check_answers_run_id ON public.ai_check_answers USING btree (run_id);
CREATE INDEX IF NOT EXISTS ix_ai_check_answers_client_id ON public.ai_check_answers USING btree (client_id);
