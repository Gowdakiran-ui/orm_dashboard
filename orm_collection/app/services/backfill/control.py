"""
Operator stop switch for the backfill.

Revoking Celery tasks is not a reliable stop (revokes live in worker memory and can miss
scheduled follow-ups; on 2026-10-18/19 the NLP feeder kept running for hours after a revoke).
This Redis flag is checked by the slice loop and every NLP-feeder tick, so setting it stops
all backfill work within one slice / one tick, no matter what is queued.
"""
STOP_KEY = "backfill:stop"


def _redis():
    from app.utils.redis_client import redis_client
    return redis_client.client


def is_stopped() -> bool:
    try:
        return bool(_redis().exists(STOP_KEY))
    except Exception:
        return False        # Redis down: the backfill itself cannot do much either


def set_stopped() -> None:
    _redis().set(STOP_KEY, "1")     # no TTL: stays until cleared on purpose


def clear_stopped() -> None:
    _redis().delete(STOP_KEY)


# Collect-only mode: while this flag is set, backfilled documents are saved as PENDING and never handed to
# NLP (the feeder does not start and a running chain ends). Meant for measuring collection without
# spending compute. Does not touch the live pipeline or the explicit CLI --continue-processing.
COLLECT_ONLY_KEY = "backfill:collect_only"


def is_collect_only() -> bool:
    try:
        return bool(_redis().exists(COLLECT_ONLY_KEY))
    except Exception:
        return False


def set_collect_only() -> None:
    _redis().set(COLLECT_ONLY_KEY, "1")


def clear_collect_only() -> None:
    _redis().delete(COLLECT_ONLY_KEY)
