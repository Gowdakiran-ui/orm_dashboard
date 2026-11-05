-- Migration: seeded top-5 executives / competitors per client.
--
-- One additive table. Records which tracked entities came from the seeding step (services/seeding), their order,
-- role, aliases, source URLs and validation result. No existing table or column is touched. Rows are never deleted by
-- the application (retire sets status = 'retired'). needs_review rows have no entity yet (entity_id NULL).
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0016_add_seeded_entities.sql
-- Safe to re-run (IF NOT EXISTS / DROP-then-ADD guards throughout).

CREATE TABLE IF NOT EXISTS public.seeded_entities (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id uuid NOT NULL,
    entity_id uuid,
    kind character varying(20) NOT NULL,
    name character varying(255) NOT NULL,
    rank integer NOT NULL,
    role text,
    context_term character varying(120),
    aliases jsonb,
    sources jsonb,
    pair_count_24m integer,
    validated boolean DEFAULT false NOT NULL,
    status character varying(20) DEFAULT 'needs_review'::character varying NOT NULL,
    seeded_at timestamp with time zone DEFAULT now()
);

ALTER TABLE public.seeded_entities DROP CONSTRAINT IF EXISTS seeded_entities_pkey;
ALTER TABLE public.seeded_entities ADD CONSTRAINT seeded_entities_pkey PRIMARY KEY (id);

ALTER TABLE public.seeded_entities DROP CONSTRAINT IF EXISTS seeded_entities_kind_check;
ALTER TABLE public.seeded_entities ADD CONSTRAINT seeded_entities_kind_check CHECK (((kind)::text = ANY (ARRAY[('executive'::character varying)::text, ('competitor'::character varying)::text])));

ALTER TABLE public.seeded_entities DROP CONSTRAINT IF EXISTS seeded_entities_status_check;
ALTER TABLE public.seeded_entities ADD CONSTRAINT seeded_entities_status_check CHECK (((status)::text = ANY (ARRAY[('active'::character varying)::text, ('needs_review'::character varying)::text, ('retired'::character varying)::text])));

ALTER TABLE public.seeded_entities DROP CONSTRAINT IF EXISTS uq_seeded_entities_client_kind_name;
ALTER TABLE public.seeded_entities ADD CONSTRAINT uq_seeded_entities_client_kind_name UNIQUE (client_id, kind, name);

ALTER TABLE public.seeded_entities DROP CONSTRAINT IF EXISTS seeded_entities_client_id_fkey;
ALTER TABLE public.seeded_entities ADD CONSTRAINT seeded_entities_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

ALTER TABLE public.seeded_entities DROP CONSTRAINT IF EXISTS seeded_entities_entity_id_fkey;
ALTER TABLE public.seeded_entities ADD CONSTRAINT seeded_entities_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_seeded_entities_client_kind ON public.seeded_entities USING btree (client_id, kind, status);
CREATE INDEX IF NOT EXISTS ix_seeded_entities_entity_id ON public.seeded_entities USING btree (entity_id);
