-- Migration: which seeded executive's search returned each document.
--
-- One additive table. For a seeded executive the backfill and the Run Pipeline search for "Name" "Company". A document that search
-- returned names the person somewhere in the article, but the document stores only the headline and summary, so the name is often
-- not in the stored text and no entity_mention exists. This table records the link (including documents that were already held,
-- for example from the brand feed). services/seeding/attribution.py turns a link into a mention only when the stored text also
-- holds the company, the surname or a role word; gates.py counts such a document for the executive. No existing table or column is
-- touched; scoring formulas and weights are not touched. Rows go with their document, client or entity (ON DELETE CASCADE).
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0017_add_document_feed_hits.sql
-- Safe to re-run (IF NOT EXISTS / DROP-then-ADD guards throughout).

CREATE TABLE IF NOT EXISTS public.document_feed_hits (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    document_id uuid NOT NULL,
    client_id uuid NOT NULL,
    entity_id uuid NOT NULL,
    source character varying(30) NOT NULL,
    query text,
    seen_at timestamp with time zone DEFAULT now()
);

ALTER TABLE public.document_feed_hits DROP CONSTRAINT IF EXISTS document_feed_hits_pkey;
ALTER TABLE public.document_feed_hits ADD CONSTRAINT document_feed_hits_pkey PRIMARY KEY (id);

ALTER TABLE public.document_feed_hits DROP CONSTRAINT IF EXISTS uq_document_feed_hits_document_entity;
ALTER TABLE public.document_feed_hits ADD CONSTRAINT uq_document_feed_hits_document_entity UNIQUE (document_id, entity_id);

ALTER TABLE public.document_feed_hits DROP CONSTRAINT IF EXISTS document_feed_hits_document_id_fkey;
ALTER TABLE public.document_feed_hits ADD CONSTRAINT document_feed_hits_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;

ALTER TABLE public.document_feed_hits DROP CONSTRAINT IF EXISTS document_feed_hits_client_id_fkey;
ALTER TABLE public.document_feed_hits ADD CONSTRAINT document_feed_hits_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

ALTER TABLE public.document_feed_hits DROP CONSTRAINT IF EXISTS document_feed_hits_entity_id_fkey;
ALTER TABLE public.document_feed_hits ADD CONSTRAINT document_feed_hits_entity_id_fkey FOREIGN KEY (entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_document_feed_hits_entity_id ON public.document_feed_hits USING btree (entity_id);
CREATE INDEX IF NOT EXISTS ix_document_feed_hits_client_id ON public.document_feed_hits USING btree (client_id);
