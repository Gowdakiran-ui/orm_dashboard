-- Migration: add risk_events.computed_at for concurrency-safe upsert
-- tiebreaking.
--
-- Confirmed live: an on-demand pipeline run and celery-beat's hourly
-- calculate_client_risks full-corpus scan can both score the same
-- (client_id, document_id, entity_id) concurrently. The prior
-- _upsert_risk_event was a plain SELECT-then-branch UPDATE/INSERT with
-- no row lock, so whichever transaction committed LAST won -- even a
-- worse (fallback_unchanged) LLM-role result overwriting a better (llm)
-- one computed moments earlier, silently. _upsert_risk_event now does a
-- single atomic INSERT ... ON CONFLICT ... DO UPDATE ... WHERE against
-- the existing uq_risk_events_daily unique index, comparing incoming vs.
-- existing explainability->>'role_classification_source' quality tier
-- and, within the same tier, this new computed_at column as the
-- freshness tiebreak. Nullable and purely additive -- existing rows read
-- as NULL, which the upsert's WHERE clause treats as the oldest
-- possible value (COALESCE(..., '-infinity'::timestamptz)), so any real
-- fresh write beats them automatically. No other column, constraint, or
-- index is touched.
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0006_add_risk_events_computed_at.sql
-- Safe to re-run (IF NOT EXISTS guard).

ALTER TABLE public.risk_events
    ADD COLUMN IF NOT EXISTS computed_at timestamp with time zone;
