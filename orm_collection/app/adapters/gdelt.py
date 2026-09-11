import time
import requests
import json
from typing import List, Dict, Any
from datetime import datetime, timezone
from .base import BaseAdapter
from app.utils.text_processing import clean_document_content

# B5 fix (2026-09-11): GDELT's own 429 response body states the real,
# confirmed constraint -- "Please limit requests to one every 5 seconds"
# -- global to the calling IP, not per-feed or per-query. None of this
# adapter's three callers (aggregation_tasks.py::_stage_collect's per-client
# feed loop, collection_tasks.py's fetch_feed_task and feed revival
# watchdog) previously paced GDELT calls at all -- a client with multiple
# GDELT feeds (the fleet has clients with up to 5) fires them back-to-back
# in one collection pass with zero spacing. Confirmed live: 3 consecutive
# GDELT feeds within a single client's own COLLECTING stage, ~12-13s apart
# (already looser than the documented 5s), still all returned 429 -- real
# margin is needed, not just the bare documented minimum. Tracked in Redis
# (shared across processes) rather than an in-process timestamp, since
# different clients' collection can run concurrently across multiple
# io_queue worker processes that all share this droplet's one outbound IP
# and therefore the same GDELT quota.
_GDELT_MIN_INTERVAL_SECONDS = 6.0
_GDELT_RATE_LIMIT_REDIS_KEY = "gdelt:last_request_at"


def _respect_gdelt_rate_limit() -> None:
    """
    Best-effort pacing, not a hard lock: two concurrent callers can still
    race and both sleep past the same prior timestamp. That's an accepted
    tradeoff -- a real distributed lock would add real complexity for a
    rate-limit backoff, not a correctness-critical section, and this
    already turns "every multi-feed client 429s every run" into "the rare
    remaining race still gets one retry" (see fetch()'s own 429 retry).
    Never allowed to block collection entirely on a Redis hiccup.
    """
    from app.utils.redis_client import redis_client
    try:
        last = redis_client.get(_GDELT_RATE_LIMIT_REDIS_KEY)
        now = time.time()
        if last:
            elapsed = now - float(last)
            if elapsed < _GDELT_MIN_INTERVAL_SECONDS:
                time.sleep(_GDELT_MIN_INTERVAL_SECONDS - elapsed)
        redis_client.set(_GDELT_RATE_LIMIT_REDIS_KEY, str(time.time()), ex=60)
    except Exception:
        pass


class GDELTAdapter(BaseAdapter):
    """
    GDELT DOC 2.0 API adapter. feed_url is expected to be a fully-formed
    query URL, e.g.
    https://api.gdeltproject.org/api/v2/doc/doc?query=Tesla&mode=artlist&format=json&maxrecords=50

    Rate limit (confirmed live, and in GDELT's own 429 response body): one
    request per ~5s per source IP. See _respect_gdelt_rate_limit above for
    how callers are now paced against it.
    """

    def fetch(self, feed_url: str, **kwargs) -> List[Dict[str, Any]]:
        headers = {
            "User-Agent": "windows:orm_collection:v1.0 (by /u/bot_tester_99)"
        }

        _respect_gdelt_rate_limit()
        response = requests.get(feed_url, headers=headers, timeout=15)

        # One retry specifically for 429 (not other errors): the Redis
        # pacing above is best-effort, not a hard lock, so a concurrent
        # caller can still occasionally win the race. A single properly-
        # spaced retry recovers from that without turning a transient
        # rate-limit hit into a lost feed for this whole run.
        if response.status_code == 429:
            time.sleep(_GDELT_MIN_INTERVAL_SECONDS)
            response = requests.get(feed_url, headers=headers, timeout=15)

        if response.status_code >= 400:
            raise Exception(f"HTTP Error {response.status_code} fetching GDELT feed: {feed_url}")

        data = response.json()
        return data.get("articles", [])

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        """
        Normalizes a GDELT DOC 2.0 article into the standard NormalizedDocument mapping.
        GDELT does not return article body text — only metadata — so `content`
        falls back to `title`, same pattern RSSAdapter uses when a feed has no
        full content, only a summary.
        """
        published_at = None
        seendate = raw_data.get("seendate")
        if seendate:
            try:
                published_at = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                published_at = None

        title = raw_data.get("title", "")
        content = clean_document_content(title)

        return {
            "source_id": str(source_id),
            "source_type": "gdelt",
            "title": title,
            "content": content,
            "url": raw_data.get("url", ""),
            "author": None,
            "published_at": published_at,
            "collected_at": datetime.now(timezone.utc),
            "raw_payload": json.dumps(raw_data)
        }
