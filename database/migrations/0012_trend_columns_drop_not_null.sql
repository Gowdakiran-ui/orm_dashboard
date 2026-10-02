-- Trend-detection removal, SCHEMA STEP 1 of 2 (see audit/deploy-runbook.md).
--
-- The scoring engines no longer compute a trend, but these columns are still
-- NOT NULL, so the engines currently insert a constant placeholder
-- ('NOT_COMPUTED' / 0.0) to satisfy them. This step relaxes the constraint so
-- the NEXT code release (models that no longer define these columns) can insert
-- rows without them.
--
-- Safe for BOTH the currently deployed code (still writes the placeholder) and
-- the next release, which is why it must run BEFORE that release is deployed.
-- Nothing is dropped here and no data changes: ALTER ... DROP NOT NULL is
-- metadata-only. Run it before step 2 (database/migrations/0013_*.sql).
BEGIN;

-- Guarded so a fresh database built from the current schema.sql (which no longer has
-- these columns after schema step 2) can still apply every migration in order.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND table_name = 'reputation_scores' AND column_name = 'reputation_trend') THEN
        ALTER TABLE public.reputation_scores ALTER COLUMN reputation_trend DROP NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND table_name = 'executive_reputation_scores' AND column_name = 'reputation_trend') THEN
        ALTER TABLE public.executive_reputation_scores ALTER COLUMN reputation_trend DROP NOT NULL;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public'
               AND table_name = 'executive_reputation_scores' AND column_name = 'trend_component') THEN
        ALTER TABLE public.executive_reputation_scores ALTER COLUMN trend_component DROP NOT NULL;
    END IF;
END $$;

COMMIT;
