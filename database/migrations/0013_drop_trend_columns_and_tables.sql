-- Trend-detection removal, SCHEMA STEP 2 of 2.  *** APPLY ONLY IN THE ORDER BELOW ***
--
-- Run it ONLY after all of these are true (it lives here now because the release
-- below ships in the same commit; do not auto-apply it as part of a deploy):
--   1. the previous code was deployed (engines wrote the placeholder),
--   2. 0012_trend_columns_drop_not_null.sql has been applied,
--   3. the release whose models NO LONGER define these columns/tables is deployed
--      and healthy (audit/pending-trend-drop-step4.patch),
--   4. a pg_dump (or a confirmed recent managed-DB backup) exists.
-- Dropping while the old models are still running makes every reputation /
-- executive insert fail (the 15-day executive-score outage in 0011's header was
-- exactly a leftover column mismatch like this).
--
-- No CASCADE on purpose: if anything unexpected depends on these objects the
-- statement fails loudly and the transaction rolls back.
BEGIN;

ALTER TABLE public.reputation_scores
    DROP COLUMN IF EXISTS reputation_trend,
    DROP COLUMN IF EXISTS trend_component;

ALTER TABLE public.executive_reputation_scores
    DROP COLUMN IF EXISTS reputation_trend,
    DROP COLUMN IF EXISTS trend_component;

DROP TABLE IF EXISTS public.trend_events;
DROP TABLE IF EXISTS public.trend_client_states;

COMMIT;
