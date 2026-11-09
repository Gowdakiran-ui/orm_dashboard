-- Migration: serious-accusation triage of the sentences in an AI-check run's answers (cross-check against XOOP incidents).
--
-- One additive table. After a run's answers are stored, each distinct sentence that contains an accusation-type word (fraud, scam,
-- cheating, criminal, charge, penalty, fine, laundering, FIR, arrest ...) is judged once by a small model call: is it a serious
-- accusation, about the client or an executive, and is it stated as fact (no source named, no hedge). The verdict, the short
-- English `event` phrase (used to find the matching XOOP incident) and where the sentence appeared are stored here, tied to the run.
-- Nothing reads this table except the AI-check endpoint (super admin) and the Brand Equity card; no score, risk event, alert or report
-- reads it. No existing table or column is touched. Rows go with their run or client (ON DELETE CASCADE).
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0019_add_ai_check_flags.sql
-- Safe to re-run (IF NOT EXISTS / DROP-then-ADD guards; the primary key is part of CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS public.ai_check_flags (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    client_id uuid NOT NULL,
    sentence text NOT NULL,
    occurrences jsonb,
    accusation boolean NOT NULL,
    about character varying(20),
    framing character varying(12),
    flagged boolean DEFAULT false NOT NULL,
    event character varying(200),
    inline_domains jsonb,
    cited_domains jsonb,
    cost_usd double precision,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT ai_check_flags_pkey PRIMARY KEY (id)
);

ALTER TABLE public.ai_check_flags DROP CONSTRAINT IF EXISTS ai_check_flags_about_check;
ALTER TABLE public.ai_check_flags ADD CONSTRAINT ai_check_flags_about_check CHECK (((about IS NULL) OR ((about)::text = ANY (ARRAY[('client'::character varying)::text, ('executive'::character varying)::text, ('other'::character varying)::text]))));

ALTER TABLE public.ai_check_flags DROP CONSTRAINT IF EXISTS ai_check_flags_framing_check;
ALTER TABLE public.ai_check_flags ADD CONSTRAINT ai_check_flags_framing_check CHECK (((framing IS NULL) OR ((framing)::text = ANY (ARRAY[('FACT'::character varying)::text, ('ATTRIBUTED'::character varying)::text, ('HEDGED'::character varying)::text]))));

ALTER TABLE public.ai_check_flags DROP CONSTRAINT IF EXISTS ai_check_flags_run_id_fkey;
ALTER TABLE public.ai_check_flags ADD CONSTRAINT ai_check_flags_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.ai_check_runs(id) ON DELETE CASCADE;

ALTER TABLE public.ai_check_flags DROP CONSTRAINT IF EXISTS ai_check_flags_client_id_fkey;
ALTER TABLE public.ai_check_flags ADD CONSTRAINT ai_check_flags_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_ai_check_flags_run_id ON public.ai_check_flags USING btree (run_id);
CREATE INDEX IF NOT EXISTS ix_ai_check_flags_client_id ON public.ai_check_flags USING btree (client_id);
