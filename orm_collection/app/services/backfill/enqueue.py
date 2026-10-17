"""One-time enqueue of the historical backfill for a newly onboarded client."""
import os

import structlog

logger = structlog.get_logger()

_ENQUEUED_KEY = "backfill:enqueued:{client_id}"
_ENQUEUED_TTL = 365 * 24 * 3600


def enqueue_client_backfill(client_id) -> bool:
    """
    Enqueue run_client_backfill exactly once per client. Never raises: a broker
    or Redis hiccup must not fail onboarding (the CLI can always enqueue it
    later, and finished slices are never refetched). Set BACKFILL_ON_ONBOARD=false
    to disable. This is a one-time job, not a schedule.
    """
    if os.environ.get("BACKFILL_ON_ONBOARD", "true").strip().lower() in ("0", "false", "no", "off"):
        logger.info("backfill_on_onboard_disabled", client_id=str(client_id))
        return False
    try:
        from app.utils.redis_client import redis_client
        if not redis_client.client.set(_ENQUEUED_KEY.format(client_id=client_id), "1", nx=True, ex=_ENQUEUED_TTL):
            logger.info("backfill_already_enqueued", client_id=str(client_id))
            return False
    except Exception as e:      # guard is best effort; the slice table + task lock keep a double enqueue harmless
        logger.warning("backfill_enqueue_guard_unavailable", client_id=str(client_id), error=str(e)[:200])
    try:
        from app.workers.backfill_tasks import run_client_backfill
        run_client_backfill.apply_async(args=[str(client_id), None, 0])
        logger.info("backfill_enqueued", client_id=str(client_id))
        return True
    except Exception as e:
        logger.warning("backfill_enqueue_failed", client_id=str(client_id), error=str(e)[:200])
        return False
