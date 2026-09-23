-- Migration: add counterfeit_scans table for the Counterfeit Detection
-- page (on-demand deepfake image scan via Reality Defender, and
-- counterfeit/typosquat domain scan via WhoisFreaks + Bolster.ai).
--
-- This is additive-only: no existing table or column is touched, and it
-- does NOT alter risk_events or its uq_risk_events_daily unique index. A
-- scan that produces a real finding (live/malicious domain, or a
-- genuinely deepfake-flagged image) still creates a real RiskEvent, via a
-- synthetic Document row (see counterfeit_detection.py) so it gets a real,
-- unique document_id instead of colliding on that index.
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0010_add_counterfeit_scans.sql
-- Safe to re-run (IF NOT EXISTS / DROP-then-ADD guards throughout).

CREATE TABLE IF NOT EXISTS public.counterfeit_scans (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    scan_type character varying(20) NOT NULL,
    status character varying(20) DEFAULT 'QUEUED'::character varying NOT NULL,
    input_summary character varying(255),
    result json,
    error_message text,
    document_id uuid,
    risk_event_id uuid,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

ALTER TABLE public.counterfeit_scans
    DROP CONSTRAINT IF EXISTS counterfeit_scans_pkey;
ALTER TABLE public.counterfeit_scans
    ADD CONSTRAINT counterfeit_scans_pkey PRIMARY KEY (id);

ALTER TABLE public.counterfeit_scans
    DROP CONSTRAINT IF EXISTS counterfeit_scans_scan_type_check;
ALTER TABLE public.counterfeit_scans
    ADD CONSTRAINT counterfeit_scans_scan_type_check CHECK (((scan_type)::text = ANY (ARRAY[('deepfake'::character varying)::text, ('domain'::character varying)::text])));

ALTER TABLE public.counterfeit_scans
    DROP CONSTRAINT IF EXISTS counterfeit_scans_status_check;
ALTER TABLE public.counterfeit_scans
    ADD CONSTRAINT counterfeit_scans_status_check CHECK (((status)::text = ANY (ARRAY[('QUEUED'::character varying)::text, ('PROCESSING'::character varying)::text, ('COMPLETE'::character varying)::text, ('FAILED'::character varying)::text])));

ALTER TABLE public.counterfeit_scans
    DROP CONSTRAINT IF EXISTS counterfeit_scans_client_id_fkey;
ALTER TABLE public.counterfeit_scans
    ADD CONSTRAINT counterfeit_scans_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

ALTER TABLE public.counterfeit_scans
    DROP CONSTRAINT IF EXISTS counterfeit_scans_document_id_fkey;
ALTER TABLE public.counterfeit_scans
    ADD CONSTRAINT counterfeit_scans_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL;

ALTER TABLE public.counterfeit_scans
    DROP CONSTRAINT IF EXISTS counterfeit_scans_risk_event_id_fkey;
ALTER TABLE public.counterfeit_scans
    ADD CONSTRAINT counterfeit_scans_risk_event_id_fkey FOREIGN KEY (risk_event_id) REFERENCES public.risk_events(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_counterfeit_scans_client_id ON public.counterfeit_scans USING btree (client_id);
CREATE INDEX IF NOT EXISTS ix_counterfeit_scans_scan_type ON public.counterfeit_scans USING btree (scan_type);
