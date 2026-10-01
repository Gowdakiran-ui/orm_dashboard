-- Complete the 2026-09-19 Narrative Cluster purge (commit 1a6467a), which removed
-- the code, ORM models and schema.sql entries but never dropped these columns
-- from the live DB. executive_reputation_scores.narrative_component being left
-- behind is what caused the 15-day silent executive-reputation failure.
--
-- Columns only. The `narratives` table (502 rows at 2026-10-01) is deliberately
-- NOT dropped here: archive it first and decide separately.
--
-- No CASCADE on purpose: if anything unexpected depends on these columns the
-- statement fails loudly and the transaction rolls back.
BEGIN;

ALTER TABLE public.clients
    DROP COLUMN IF EXISTS narrative_batch_id,
    DROP COLUMN IF EXISTS narrative_failed_at,
    DROP COLUMN IF EXISTS narrative_failure_reason,
    DROP COLUMN IF EXISTS narrative_latency_ms,
    DROP COLUMN IF EXISTS narrative_processing_status,
    DROP COLUMN IF EXISTS narrative_retry_count,
    DROP COLUMN IF EXISTS narrative_run_id;

ALTER TABLE public.client_processing_summary
    DROP COLUMN IF EXISTS narratives_generated;

ALTER TABLE public.executive_reputation_scores
    DROP COLUMN IF EXISTS narrative_component,
    DROP COLUMN IF EXISTS top_negative_narrative,
    DROP COLUMN IF EXISTS top_positive_narrative;

ALTER TABLE public.reputation_scores
    DROP COLUMN IF EXISTS narrative_component;

ALTER TABLE public.competitor_benchmarks
    DROP COLUMN IF EXISTS top_narrative;

ALTER TABLE public.product_benchmarks
    DROP COLUMN IF EXISTS top_narrative;

COMMIT;
