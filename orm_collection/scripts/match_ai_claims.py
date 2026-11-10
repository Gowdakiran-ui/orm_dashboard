"""Match the flagged sentences of a company's latest AI-check run to its XOOP incidents (one small model call per sentence).

    python scripts/match_ai_claims.py "Godrej Properties"          # shows how many sentences would be matched, makes no call
    python scripts/match_ai_claims.py "Godrej Properties" --yes    # makes the calls (about $0.001 each) and stores the matches

New runs do this by themselves; use this for a run stored before the matching existed (the card reads "Not matched automatically"
until then) or to retry sentences whose call failed. Needs OPENROUTER_API_KEY and migration 0021. Uses whatever DATABASE_URL points at.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.models.ai_check import AiCheckFlag, AiCheckRun  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.services.ai_check import claims  # noqa: E402

CAP_USD = 0.10


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.name == args[0]).first()
        if not client:
            print(f"No company named {args[0]!r}.")
            return 1
        run = db.query(AiCheckRun).filter(AiCheckRun.client_id == client.id).order_by(AiCheckRun.started_at.desc()).first()
        if not run:
            print("This company has no AI check run.")
            return 1
        todo = db.query(AiCheckFlag).filter(AiCheckFlag.run_id == run.id, AiCheckFlag.flagged.is_(True), AiCheckFlag.match_checked.is_(False)).count()
        print(f"Run {str(run.id)[:8]} ({run.status}): {todo} flagged sentences still to match, about ${todo * claims.EST_COST_PER_MATCH_CALL:.3f}.")
        if "--yes" not in sys.argv or todo == 0:
            return 0
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            print("OPENROUTER_API_KEY is not set.")
            return 1
        before = run.cost_usd or 0.0
        matched = claims.match_run_flags(db, run, client, key, cap_usd=before + CAP_USD, log=print)
        print(f"{matched} sentences matched to an incident; spent ${(run.cost_usd or 0.0) - before:.4f}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
