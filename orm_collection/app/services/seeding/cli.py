"""
CLI for seeded top-5 executives / competitors.

  python -m app.services.seeding.cli --client "Godrej Properties" --dry-run     # default: propose + validate, print, write nothing
  python -m app.services.seeding.cli --client "Godrej Properties" --apply       # write the chosen list, entities, feeds, website, rematch
  python -m app.services.seeding.cli --client "Godrej Properties" --apply --refresh   # replace an already stored list (explicit)
  python -m app.services.seeding.cli --client "Godrej Properties" --rematch     # re-run the seed-scoped rematch of existing documents
  python -m app.services.seeding.cli --client "Godrej Properties" --retire "Name"
  python -m app.services.seeding.cli --client X --proposal-file plan.json --preview-rematch   # read-only: documents each chosen entity would gain
  python -m app.services.seeding.cli --client X --link-search-hits [--months 24] [--write]   # link already-held search results to the seeded executives
  python -m app.services.seeding.cli --client X --add-alias "Yatra.com" --aliases "Yatra Online,Yatra" [--write]   # alias safety rule; report only without --write

--dry-run and --apply make ONE web-grounded Claude Haiku 4.5 call through OpenRouter (about $0.015) unless --proposal-file is
given. If that call fails the command aborts and writes nothing; it never falls back to the plain model. The chosen list is
persisted: --apply refuses to replace a stored list unless --refresh is given. Alias measurement, validation and the page checks
use free requests only.
"""
import argparse
import json
import sys

from app.core.db import SessionLocal
from app.models.client import Client
from app.services.seeding import service
from app.services.seeding.proposer import SeedingAborted


def _find_client(db, ident: str):
    q = db.query(Client)
    return q.filter(Client.id == ident).first() if len(ident) == 36 else q.filter(Client.name == ident).first()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client", required=True, help="client name or id")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="propose and validate only (default)")
    mode.add_argument("--apply", action="store_true", help="write the chosen list, entities, feeds, website and rematch")
    mode.add_argument("--retire", metavar="NAME", help="retire one seeded entity (leaves the entity in place)")
    mode.add_argument("--rematch", action="store_true", help="re-run the seed-scoped rematch for the stored active list")
    mode.add_argument("--link-search-hits", action="store_true", help="free Google News search per seeded executive; link the documents already held, then attribute (report only unless --write)")
    mode.add_argument("--add-alias", metavar="NAME", help="add the aliases in --aliases to one active seeded entity (report only unless --write)")
    mode.add_argument("--preview-rematch", action="store_true", help="read-only: existing documents each chosen entity would gain (needs --proposal-file)")
    ap.add_argument("--aliases", metavar="A,B", help="with --add-alias: comma-separated aliases")
    ap.add_argument("--write", action="store_true", help="with --add-alias or --link-search-hits: write (otherwise only report)")
    ap.add_argument("--months", type=int, default=24, help="with --link-search-hits: look-back in months (monthly slices)")
    ap.add_argument("--refresh", action="store_true", help="with --apply: replace an already stored list")
    ap.add_argument("--no-measure-aliases", action="store_true", help="skip the 50-document alias measurement (bare aliases stay off)")
    ap.add_argument("--json", action="store_true", help="print the plan as JSON")
    ap.add_argument("--proposal-file", metavar="PATH", help="validate saved proposal JSON file(s) (comma-separated = their union) instead of making the LLM call")
    a = ap.parse_args(argv)

    db = SessionLocal()
    try:
        client = _find_client(db, a.client)
        if client is None:
            print(f"No client {a.client!r}", file=sys.stderr)
            return 2
        if a.retire:
            print(json.dumps(service.retire(db, client.id, a.retire), indent=2))
            return 0
        if a.link_search_hits:
            from app.services.seeding import attribution
            if not a.write:
                from app.services.seeding.gates import seeded_rows
                print(json.dumps({"would_search": [r.name for r in seeded_rows(db, client.id, "executive")], "months": a.months,
                                  "note": "free Google News requests; saves nothing new; add --write to record the links and attribute them"}, indent=2))
                return 0
            linked = attribution.link_existing(db, client.id, months=a.months)
            print(json.dumps({"linked": linked, "attributed": attribution.attribute_hits(db, client.id)}, indent=2))
            return 0
        if a.add_alias:
            aliases = [x.strip() for x in (a.aliases or "").split(",") if x.strip()]
            if not aliases:
                print("--add-alias needs --aliases", file=sys.stderr)
                return 2
            print(json.dumps(service.add_aliases(db, client.id, a.add_alias, aliases, write=a.write), indent=2, default=str))
            return 0
        if a.rematch:
            from app.services.seeding import rematch
            from app.services.seeding.gates import seeded_rows
            print(json.dumps(rematch.rematch_seeded(db, client.id, [r.entity_id for r in seeded_rows(db, client.id)]), indent=2))
            return 0
        propose_fn = None
        if a.proposal_file:
            from app.services.seeding.proposer import merge_proposals
            saved = merge_proposals([json.load(open(f.strip(), encoding="utf8")) for f in a.proposal_file.split(",")])    # several files = union
            propose_fn = lambda *args, **kwargs: saved      # noqa: E731
        try:
            result = service.seed_client(db, client.id, apply=a.apply, propose_fn=propose_fn, refresh=a.refresh,
                                         measure_aliases=not a.no_measure_aliases)
        except SeedingAborted as e:
            print(f"ABORTED, nothing written: {e}", file=sys.stderr)
            return 3
        except service.AlreadySeeded as e:
            print(f"NOT APPLIED: {e}. Use --refresh to replace it.", file=sys.stderr)
            return 4
        if a.preview_rematch:
            from app.services.seeding import rematch
            print(json.dumps(rematch.preview_plan(db, client.id, result["plan"]), indent=2))
            return 0
        print(json.dumps(result["plan"], indent=2, default=str) if a.json else service.format_plan(result["plan"]))
        if a.apply:
            print("\nAPPLIED:", json.dumps(result["applied"]))
        else:
            print("\nDRY RUN: nothing was written.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
