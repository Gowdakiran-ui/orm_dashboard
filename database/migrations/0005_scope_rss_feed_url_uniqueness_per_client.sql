-- Migration: scope rss_feeds.feed_url uniqueness to (client_id, feed_url).
--
-- The global UNIQUE(feed_url) constraint meant two different clients whose
-- primary_entity_name sanitizes to the same query string (e.g. two clients
-- both named "Tesla") silently collided in onboard_client()
-- (app/services/client_service.py): the second onboarding's existing_feed
-- lookup matched the first client's row and skipped provisioning entirely --
-- no exception, no log, the endpoint still returned 200 -- leaving the
-- second client with zero feed rows and no collection ever possible. Same
-- root cause and same fix pattern as 0004_remove_client_name_uniqueness.sql.
--
-- Note: client_id is nullable (topical_global feeds have no single owning
-- client -- see rss_feed.py). Postgres does not treat NULL = NULL for
-- uniqueness purposes, so multiple client_id=NULL rows with the same
-- feed_url would no longer be deduped against each other by this
-- constraint. No code path currently creates client_id=NULL feeds (grepped
-- source_type="topical_global" -- no matches), so this is not a live
-- regression; flagged here in case that changes.
--
-- Dropping a UNIQUE constraint also drops its backing index automatically
-- in Postgres -- no separate DROP INDEX needed.
--
-- Same idempotent pattern as the prior migrations -- no migration runner in
-- this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0005_scope_rss_feed_url_uniqueness_per_client.sql
-- Safe to re-run.

ALTER TABLE public.rss_feeds DROP CONSTRAINT IF EXISTS rss_feeds_feed_url_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_rss_feeds_client_id_feed_url'
    ) THEN
        ALTER TABLE public.rss_feeds
            ADD CONSTRAINT uq_rss_feeds_client_id_feed_url UNIQUE (client_id, feed_url);
    END IF;
END $$;
