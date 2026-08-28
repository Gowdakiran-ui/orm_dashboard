-- Migration: remove clients.name uniqueness (TASK_CLIENT_NAME.md).
--
-- Isolation in this system is per client_id via user_client_access, not per
-- name -- two different users each onboarding a company called "Anthropic"
-- are two unrelated tenants that happen to share a display name. The
-- uq_clients_name UNIQUE constraint (and the application-level dedup check
-- in client_service.py's onboard_client, removed in the same change)
-- wrongly rejected the second, unrelated onboarding as "already exists".
--
-- Dropping a UNIQUE constraint also drops its backing index automatically
-- in Postgres -- no separate DROP INDEX needed.
--
-- Same idempotent pattern as the prior migrations -- no migration runner in
-- this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0004_remove_client_name_uniqueness.sql
-- Safe to re-run.

ALTER TABLE public.clients DROP CONSTRAINT IF EXISTS uq_clients_name;
