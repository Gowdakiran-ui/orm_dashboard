"""Seeding caps, read from environment variables (same convention as services/backfill/settings.py)."""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# One-time backfill: new documents saved per seeded entity (newest and risk-worded slices first).
EXEC_BACKFILL_CAP = _int("SEED_EXEC_BACKFILL_CAP", 60)
COMPETITOR_BACKFILL_CAP = _int("SEED_COMPETITOR_BACKFILL_CAP", 30)
# Steady state: new documents saved per seeded entity feed per Run Pipeline run.
RUN_CAP_PER_ENTITY = _int("SEED_RUN_CAP_PER_ENTITY", 25)
