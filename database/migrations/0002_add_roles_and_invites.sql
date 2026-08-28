-- Migration: add roles and invite-based onboarding (TASK_ROLES.md).
--
-- Adds to `users`:
--   role                     -- 'super_admin' | 'client_user', default 'client_user'
--   invite_token             -- nullable, unique; set while an invite is pending
--   invite_token_expires_at  -- nullable; 48h from invite creation
--
-- password_hash also becomes nullable: an invited-but-not-yet-activated user
-- has no password until they accept the invite (auth.py's get_current_user
-- already only loads is_active=true users, so a NULL-password row can never
-- log in before activation regardless).
--
-- Same idempotent-ALTER pattern as 0001_add_auth_tables.sql -- no migration
-- runner in this project (Alembic was removed, see schema.sql's header).
-- Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0002_add_roles_and_invites.sql
-- Safe to re-run.

ALTER TABLE public.users ALTER COLUMN password_hash DROP NOT NULL;

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS role character varying(20) NOT NULL DEFAULT 'client_user';
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS invite_token character varying(64);
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS invite_token_expires_at timestamp with time zone;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_users_role'
    ) THEN
        ALTER TABLE public.users
            ADD CONSTRAINT ck_users_role CHECK (role IN ('super_admin', 'client_user'));
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_invite_token
    ON public.users USING btree (invite_token)
    WHERE invite_token IS NOT NULL;
