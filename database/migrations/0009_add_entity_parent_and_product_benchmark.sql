-- Migration: add entities.parent_entity_id (self-referencing FK) and the
-- product_benchmarks table, for Product-Level Compare (product entities
-- nested under a brand/competitor entity, scored the same honest way
-- CompetitorBenchmark already scores competitor entities).
--
-- entities.parent_entity_id is nullable and purely additive: every existing
-- entity row reads as NULL (no parent), unchanged in behavior. A product
-- entity's "own vs. competitor" side is derived by joining
-- parent_entity_id -> entities.entity_type ('brand' or 'competitor'), not
-- duplicated as a second column on the product row. ON DELETE CASCADE
-- mirrors entity_keywords/entity_aliases' existing FK-to-entities
-- convention: a product entity has no meaning once its parent brand/
-- competitor entity is gone.
--
-- product_benchmarks mirrors competitor_benchmarks' column-for-column shape
-- (see benchmark_engine.py's BenchmarkEngine, which computes both via the
-- same per-entity _components_for/_score_from_components logic, just fed a
-- different set of entity ids and writing to a different table), keyed on
-- (client_id, product_entity_id) with the same uq_..._run(entity_id, run_id)
-- upsert-tiebreak constraint competitor_benchmarks already uses, and the
-- same ck_..._confidence_score bounds check.
--
-- Verified against a throwaway local Postgres 16 instance before being
-- applied anywhere real: fresh DB, apply schema.sql, apply this file,
-- confirm both new objects (entities.parent_entity_id, product_benchmarks
-- with all constraints/indexes) create cleanly, then the throwaway instance
-- was dropped. See CLAUDE.md's schema-change ground rule.
--
-- No migration runner in this project (see schema.sql's header). Apply with:
--   psql "$DATABASE_URL" -f database/migrations/0009_add_entity_parent_and_product_benchmark.sql
-- Safe to re-run (IF NOT EXISTS / DROP CONSTRAINT IF EXISTS guards throughout).

ALTER TABLE public.entities
    ADD COLUMN IF NOT EXISTS parent_entity_id uuid;

ALTER TABLE public.entities
    DROP CONSTRAINT IF EXISTS entities_parent_entity_id_fkey;
ALTER TABLE public.entities
    ADD CONSTRAINT entities_parent_entity_id_fkey FOREIGN KEY (parent_entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS ix_entities_parent_entity_id ON public.entities USING btree (parent_entity_id);

CREATE TABLE IF NOT EXISTS public.product_benchmarks (
    id uuid NOT NULL,
    client_id uuid NOT NULL,
    product_entity_id uuid NOT NULL,
    reputation_score double precision NOT NULL,
    executive_reputation_score double precision NOT NULL,
    sentiment_score double precision NOT NULL,
    risk_score double precision NOT NULL,
    visibility_score double precision NOT NULL,
    share_of_voice double precision NOT NULL,
    top_narrative character varying(255),
    rank integer NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    run_id character varying(100),
    batch_id character varying(100),
    worker_id character varying(100),
    latency_ms double precision,
    retry_count integer,
    calculation_lineage jsonb,
    evidence_metadata jsonb,
    health_status character varying(50),
    confidence_score double precision,
    data_coverage double precision DEFAULT 0.40
);

ALTER TABLE public.product_benchmarks
    DROP CONSTRAINT IF EXISTS product_benchmarks_pkey;
ALTER TABLE public.product_benchmarks
    ADD CONSTRAINT product_benchmarks_pkey PRIMARY KEY (id);

ALTER TABLE public.product_benchmarks
    DROP CONSTRAINT IF EXISTS product_benchmarks_client_id_fkey;
ALTER TABLE public.product_benchmarks
    ADD CONSTRAINT product_benchmarks_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE CASCADE;

ALTER TABLE public.product_benchmarks
    DROP CONSTRAINT IF EXISTS product_benchmarks_product_entity_id_fkey;
ALTER TABLE public.product_benchmarks
    ADD CONSTRAINT product_benchmarks_product_entity_id_fkey FOREIGN KEY (product_entity_id) REFERENCES public.entities(id) ON DELETE CASCADE;

ALTER TABLE public.product_benchmarks
    DROP CONSTRAINT IF EXISTS uq_product_benchmark_run;
ALTER TABLE public.product_benchmarks
    ADD CONSTRAINT uq_product_benchmark_run UNIQUE (product_entity_id, run_id);

ALTER TABLE public.product_benchmarks
    DROP CONSTRAINT IF EXISTS ck_product_benchmarks_confidence_score;
ALTER TABLE public.product_benchmarks
    ADD CONSTRAINT ck_product_benchmarks_confidence_score CHECK (((confidence_score IS NULL) OR ((confidence_score >= (0)::double precision) AND (confidence_score <= (1)::double precision))));

CREATE INDEX IF NOT EXISTS ix_product_benchmarks_client_id ON public.product_benchmarks USING btree (client_id);
CREATE INDEX IF NOT EXISTS ix_product_benchmarks_product_entity_id ON public.product_benchmarks USING btree (product_entity_id);
