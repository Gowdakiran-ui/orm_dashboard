"""
Backfill knobs, read from environment variables so no core config file is touched.
Defaults are the ones chosen for the new-client onboarding backfill.
"""
import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off", "")


# Drop collected items whose title/summary mention neither the brand nor a tracked entity.
RELEVANCE_FILTER_DEFAULT = _bool("BACKFILL_RELEVANCE_FILTER", True)

# Max backfilled documents handed to NLP per client; the rest stay PENDING until `--continue-processing`.
MAX_PROCESS_DOCS_PER_CLIENT = _int("BACKFILL_MAX_PROCESS_DOCS_PER_CLIENT", 500)

# YouTube history starts here (Google News still defaults to 2015).
YOUTUBE_START_YEAR = _int("BACKFILL_YOUTUBE_START_YEAR", 2022)

# YouTube: the day's TOTAL search units (live pipeline + backfill) may not pass this, so the
# live pipeline always keeps DAILY_QUOTA_LIMIT (10,000) minus this many units.
YOUTUBE_DAILY_CEILING = _int("BACKFILL_YT_DAILY_CEILING", 4000)
YOUTUBE_RUN_BUDGET = _int("BACKFILL_YT_RUN_BUDGET", 3000)
