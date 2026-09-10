-- Migration: add documents.view_count / documents.comment_count.
--
-- Reach/credibility-weighted risk scoring (CEO priority): risk_engine.py
-- needs real YouTube engagement numbers as an input to the score formula.
-- Confirmed live: the YouTube adapter already fetches real integer
-- viewCount/commentCount from the API (videos.list, statistics part) but
-- previously only formatted them into a human-readable string baked into
-- normalized_content ("1.7K views, 0 comments\n\n{description}") -- no
-- queryable numeric field existed. Nullable and purely additive: existing
-- rows read as NULL (no backfill -- this is a going-forward pipeline
-- change per the task scope), non-YouTube document types simply never
-- populate these columns, and no existing constraint, index, or column is
-- touched.
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0008_add_document_view_comment_counts.sql
-- Safe to re-run (IF NOT EXISTS guard).

ALTER TABLE public.documents
    ADD COLUMN IF NOT EXISTS view_count integer,
    ADD COLUMN IF NOT EXISTS comment_count integer;
