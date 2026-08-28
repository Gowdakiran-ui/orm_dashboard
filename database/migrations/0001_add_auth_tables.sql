-- Migration: add real per-user auth tables (TASK_AUTH.md, API_FORENSICS.md
-- Section 1 — "No Real Auth; Shared Secret Is Exposed Client-Side").
--
-- This project has no migration runner (Alembic was removed — see
-- database/schema.sql's header and TASK.md "Remove Alembic, Adopt
-- schema.sql as Source of Truth"). bootstrap_schema.py only ever applies
-- schema.sql to a genuinely EMPTY database, so an existing database that
-- already holds real client data needs this hand-written, idempotent ALTER
-- script instead. schema.sql itself has also been updated with these same
-- two tables so a fresh bootstrap includes them without running this file.
--
-- Apply with, e.g.:
--   psql "$DATABASE_URL" -f database/migrations/0001_add_auth_tables.sql
-- Safe to re-run: every statement is guarded with IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS public.users (
    id uuid NOT NULL PRIMARY KEY,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'users_email_key'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_email_key UNIQUE (email);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.user_client_access (
    id uuid NOT NULL PRIMARY KEY,
    user_id uuid NOT NULL,
    client_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_user_client_access'
    ) THEN
        ALTER TABLE public.user_client_access
            ADD CONSTRAINT uq_user_client_access UNIQUE (user_id, client_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'user_client_access_user_id_fkey'
    ) THEN
        ALTER TABLE public.user_client_access
            ADD CONSTRAINT user_client_access_user_id_fkey
            FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'user_client_access_client_id_fkey'
    ) THEN
        ALTER TABLE public.user_client_access
            ADD CONSTRAINT user_client_access_client_id_fkey
            FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_user_client_access_user_id ON public.user_client_access USING btree (user_id);
CREATE INDEX IF NOT EXISTS ix_user_client_access_client_id ON public.user_client_access USING btree (client_id);
