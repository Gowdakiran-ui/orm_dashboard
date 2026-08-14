"""
Phase A3 — one-time re-validation of already-promoted competitor entities.

WHY THIS EXISTS
    The competitor-promotion guard (`_is_valid_org_name`) only ever ran at
    promotion time, so the entities promoted under the old blocklist stay in
    `entities` with `entity_type='competitor'` forever. Fixing the guard (A1)
    stops new noise; it does not retract what is already there. Confirmed live:
    all six of Apple Inc's "competitors" were publishers, exchanges, tickers or
    the client's own product, and Tesla's included two test fixtures.

WHY RECLASSIFY INSTEAD OF DELETE  (traced before choosing — CLAUDE.md)
    Every FK pointing at `entities.id` is ON DELETE CASCADE:
        entity_keywords, entity_aliases, entity_mentions, entity_sentiments,
        document_matches, trend_events, risk_events, alerts,
        executive_reputation_scores, competitor_benchmarks
    (`competitor_candidates.promoted_to_competitor_id` and
     `executive_candidates.promoted_to_executive_id` are ON DELETE SET NULL.)

    Deleting a junk competitor therefore also deletes its `risk_events`. Those
    rows are client-scoped inputs to ReputationEngine's risk component, which
    filters on `client_id` only — not on entity. Measured live, risk events
    attached to competitor entities are 58/182 of Tata Motors' total, 22/276 of
    Apple's. Deleting them would silently move every client's headline
    reputation score, which is a data-corrupting side effect nobody asked for.

    Reclassifying to `entity_type='rejected_competitor'` instead:
      * removes the entity from every competitor query in the codebase, all of
        which are equality tests on `== "competitor"` (benchmark_engine,
        client_intelligence `/benchmark` + `/share-of-voice`, client_service,
        narrative_engine, intelligence_tasks verification);
      * keeps `entity_type != "person"` true, which executive discovery's
        Layer 1 relies on;
      * preserves every child row, so no aggregate moves;
      * is a single reversible UPDATE — `--revert` undoes it exactly;
      * needs no migration. `entities.entity_type` is a free-form String(50)
        with no CHECK constraint and no enum (verified against the live DB).

USAGE
    Dry run (default — reports, changes nothing):
        python -m app.scripts.revalidate_promoted_competitors
    Apply:
        python -m app.scripts.revalidate_promoted_competitors --apply
    Undo a previous apply:
        python -m app.scripts.revalidate_promoted_competitors --revert --apply

    Idempotent: re-running after an apply reports zero changes.
"""
import argparse
import sys

from app.core.db import SessionLocal
from app.models.client import Client
from app.models.entity import Entity
from app.services.intelligence.entity_discovery import EntityDiscoveryEngine

REJECTED_TYPE = "rejected_competitor"


def _engine() -> EntityDiscoveryEngine:
    """Instantiate without __init__ so the spaCy model is not loaded — this
    script only uses the pure name-classification helpers."""
    return EntityDiscoveryEngine.__new__(EntityDiscoveryEngine)


def revalidate(db, apply_changes: bool = False):
    eng = _engine()
    source_terms = eng._registered_source_terms(db)

    rows = []
    for client in db.query(Client).order_by(Client.name).all():
        competitors = db.query(Entity).filter(
            Entity.client_id == client.id,
            Entity.entity_type == "competitor",
        ).order_by(Entity.name).all()
        if not competitors:
            continue

        self_terms = eng._client_self_reference_terms(db, str(client.id))
        for entity in competitors:
            is_valid, layer, reason = eng._is_valid_org_name_layered(
                entity.name,
                client_name=client.name,
                self_reference_terms=self_terms,
                source_terms=source_terms,
            )
            rows.append({
                "client": client.name,
                "entity": entity,
                "keep": is_valid,
                "layer": layer,
                "reason": reason,
            })

    failed = [r for r in rows if not r["keep"]]

    print(f"{'client':<14} {'competitor':<22} {'verdict':<8} reason")
    print("-" * 110)
    for r in sorted(rows, key=lambda x: (x["client"], x["keep"], x["entity"].name)):
        verdict = "keep" if r["keep"] else "REJECT"
        detail = f"{r['layer']} | {r['reason']}" if r["reason"] else ""
        print(f"{r['client']:<14} {r['entity'].name[:22]:<22} {verdict:<8} {detail}")

    print("-" * 110)
    print(f"{len(rows)} promoted competitors checked — {len(rows) - len(failed)} kept, {len(failed)} fail the current guard.")

    if not failed:
        return 0

    if not apply_changes:
        print("\nDRY RUN — nothing written. Re-run with --apply to reclassify the "
              f"{len(failed)} entities above to entity_type='{REJECTED_TYPE}'.")
        return 0

    for r in failed:
        r["entity"].entity_type = REJECTED_TYPE
    db.commit()
    print(f"\nAPPLIED — {len(failed)} entities reclassified to '{REJECTED_TYPE}'. "
          "Child rows (mentions, risk events, benchmarks) are untouched. "
          "Run with --revert --apply to undo.")
    return len(failed)


def revert(db, apply_changes: bool = False):
    entities = db.query(Entity).filter(Entity.entity_type == REJECTED_TYPE).all()
    for e in entities:
        print(f"  restore {e.name} -> competitor")
    if not entities:
        print("Nothing to revert.")
        return 0
    if not apply_changes:
        print(f"\nDRY RUN — would restore {len(entities)} entities to entity_type='competitor'.")
        return 0
    for e in entities:
        e.entity_type = "competitor"
    db.commit()
    print(f"\nREVERTED — {len(entities)} entities restored to 'competitor'.")
    return len(entities)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write changes (default is dry run)")
    parser.add_argument("--revert", action="store_true", help="restore reclassified entities")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if args.revert:
            revert(db, apply_changes=args.apply)
        else:
            revalidate(db, apply_changes=args.apply)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
