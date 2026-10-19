-- Migration: allow a 'SKIPPED' status on backfill_slices.
--
-- SKIPPED means "deliberately not fetched" (an operator decided a client does not
-- need more history). The backfill only ever picks PENDING slices, so a SKIPPED
-- slice is never refetched, and re-seeding cannot bring it back (the slice unique
-- key already exists). Rows are never deleted.
--
-- Only a CHECK constraint is replaced; no data is touched. Safe to re-run.
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0015_backfill_slices_skipped_status.sql

ALTER TABLE public.backfill_slices
    DROP CONSTRAINT IF EXISTS backfill_slices_status_check;
ALTER TABLE public.backfill_slices
    ADD CONSTRAINT backfill_slices_status_check CHECK (((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('DONE'::character varying)::text, ('SPLIT'::character varying)::text, ('ERROR'::character varying)::text, ('SKIPPED'::character varying)::text])));
