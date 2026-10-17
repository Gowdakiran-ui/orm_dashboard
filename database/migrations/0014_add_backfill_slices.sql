-- Migration: slice-progress table for the one-time historical backfill.
--
-- One row per (client, source, query, slice) so a crashed or re-run backfill
-- resumes where it stopped and never refetches a finished slice. Additive
-- only: no existing table or column is touched, and nothing reads this table
-- except app/services/backfill. Run Pipeline never touches it.
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0014_add_backfill_slices.sql
-- Safe to re-run (IF NOT EXISTS / DROP-then-ADD guards throughout).

CREATE TABLE IF NOT EXISTS public.backfill_slices (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    entity_id uuid,
    entity_name character varying(255) NOT NULL,
    source character varying(30) NOT NULL,
    query text NOT NULL,
    slice_start timestamp with time zone NOT NULL,
    slice_end timestamp with time zone NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    item_count integer,
    new_count integer,
    error text,
    attempts integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

ALTER TABLE public.backfill_slices
    DROP CONSTRAINT IF EXISTS backfill_slices_pkey;
ALTER TABLE public.backfill_slices
    ADD CONSTRAINT backfill_slices_pkey PRIMARY KEY (id);

ALTER TABLE public.backfill_slices
    DROP CONSTRAINT IF EXISTS backfill_slices_status_check;
ALTER TABLE public.backfill_slices
    ADD CONSTRAINT backfill_slices_status_check CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('DONE'::character varying)::text, ('SPLIT'::character varying)::text, ('ERROR'::character varying)::text])));

ALTER TABLE public.backfill_slices
    DROP CONSTRAINT IF EXISTS uq_backfill_slices_slice;
ALTER TABLE public.backfill_slices
    ADD CONSTRAINT uq_backfill_slices_slice UNIQUE (client_id, source, query, slice_start, slice_end);

ALTER TABLE public.backfill_slices
    DROP CONSTRAINT IF EXISTS backfill_slices_client_id_fkey;
ALTER TABLE public.backfill_slices
    ADD CONSTRAINT backfill_slices_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

ALTER TABLE public.backfill_slices
    DROP CONSTRAINT IF EXISTS backfill_slices_entity_id_fkey;
ALTER TABLE public.backfill_slices
    ADD CONSTRAINT backfill_slices_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_backfill_slices_client_status ON public.backfill_slices USING btree (client_id, status);
