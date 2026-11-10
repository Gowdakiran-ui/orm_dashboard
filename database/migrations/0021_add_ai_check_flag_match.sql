-- Migration: store which XOOP incident a flagged AI sentence was matched to (one cheap model call per flagged sentence).
--
-- Three additive columns on ai_check_flags (migration 0019). The match used to be computed on every admin read by word overlap; it is
-- now decided once by a small model call and kept here, so reading the card costs nothing:
--   matched_document_id  the lead document of the matched XOOP incident at the time of the call (NULL = no incident matches).
--                        No foreign key on purpose: a deleted document must not delete or block the flag; the reader simply
--                        finds no current incident containing it and shows "Not matched automatically".
--   match_checked        true once the model call has been made and read (false = never checked or the call failed; a later
--                        backfill picks those rows up).
--   match_cost_usd       the cost of that call (added to the run's cost as well).
-- Nothing else reads these columns; no score, risk event, alert or report does. No existing column or row is changed.
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0021_add_ai_check_flag_match.sql
-- Safe to re-run (ADD COLUMN IF NOT EXISTS).

ALTER TABLE public.ai_check_flags ADD COLUMN IF NOT EXISTS matched_document_id uuid;
ALTER TABLE public.ai_check_flags ADD COLUMN IF NOT EXISTS match_checked boolean DEFAULT false NOT NULL;
ALTER TABLE public.ai_check_flags ADD COLUMN IF NOT EXISTS match_cost_usd double precision;
