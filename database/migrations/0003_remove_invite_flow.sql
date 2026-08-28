-- Migration: remove the invite/SMTP onboarding flow (TASK_ONBOARDING.md).
--
-- Replaces 0002_add_roles_and_invites.sql's invite mechanism with
-- admin-generated passwords: a super_admin creates a user with a password
-- generated (and returned once) server-side, active immediately -- no
-- pending/inactive row, no email, no accept-invite token.
--
-- Any row left over from the old flow with password_hash IS NULL is a
-- pending invite that was never accepted -- that flow no longer exists (no
-- accept-invite endpoint to ever complete it), so those rows are dead and
-- are removed here rather than left to violate the new NOT NULL constraint.
-- A super_admin can just create the same email fresh via POST /admin/users
-- after this runs.
--
-- Same idempotent pattern as the prior two migrations -- no migration
-- runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0003_remove_invite_flow.sql
-- Re-running is safe (DROP COLUMN IF EXISTS, etc.), EXCEPT that a second run
-- has nothing left to delete -- harmless.

DELETE FROM public.users WHERE password_hash IS NULL;

ALTER TABLE public.users ALTER COLUMN password_hash SET NOT NULL;

DROP INDEX IF EXISTS public.uq_users_invite_token;

ALTER TABLE public.users DROP COLUMN IF EXISTS invite_token;
ALTER TABLE public.users DROP COLUMN IF EXISTS invite_token_expires_at;
