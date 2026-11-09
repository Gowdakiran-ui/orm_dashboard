"""Run the "What AI says about you" check for one client from the command line (same code as the Run AI check button).

    python scripts/run_ai_check.py "Godrej Properties"          # prints the estimate and the questions, asks nothing
    python scripts/run_ai_check.py "Godrej Properties" --yes    # runs it: 24 paid web calls, stops before the per-client cap

Needs AI_CHECK_ENABLED=1 and OPENROUTER_API_KEY, and uses whatever DATABASE_URL points at: point it at a throwaway database
for a test, never at production by accident (the estimate is printed first for that reason).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal  # noqa: E402
from app.models.client import Client  # noqa: E402
from app.services.ai_check import service  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    if not service.ai_check_enabled():
        print("AI_CHECK_ENABLED is not set: nothing to do.")
        return 1
    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.name == args[0]).first()
        if not client:
            print(f"No client named {args[0]!r}.")
            return 1
        prompts = service.prompts_for(db, client)
        est = service.estimate(len(prompts))
        print(f"{client.name}: {est['prompts']} questions x {est['repeats']} repeats = {est['calls']} calls, "
              f"estimated ${est['estimated_cost_usd']:.2f}, stops before ${est['cap_usd']:.2f}  ({est['model']}, {est['web_results']} web results)")
        for p in prompts:
            print(f"  - {p['key']}: {p['text']}")
        if "--yes" not in sys.argv:
            print("Not run. Add --yes to run it.")
            return 0
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            print("OPENROUTER_API_KEY is not set.")
            return 1
        run = service.start_run(db, client.id, len(prompts))
        print(f"run {run.id} started")
        service.execute_run(db, run, prompts, key, log=print)
        print(f"run {run.id}: {run.status}, {run.calls_ok} ok / {run.calls_failed} failed, measured cost ${run.cost_usd:.4f}")
        return 0 if run.status in ("completed", "stopped_at_cap") else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
