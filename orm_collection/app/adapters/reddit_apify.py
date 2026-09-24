import json
import time
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
import os
import requests
import structlog
from .search_base import BaseSearchAdapter
from app.utils.text_processing import clean_document_content

logger = structlog.get_logger()

# Reddit's own Data API self-service registration is confirmed closed
# (Reddit admin post on r/redditdev, 2026-08-05) -- new script-app
# credentials are not obtainable, so the old PRAW-based reddit.py cannot be
# fixed/tested and is left in place, dormant. This is the real, live Reddit
# path instead, via Apify -- same actor-scraping approach as instagram.py.
#
# trudax/reddit-scraper-lite chosen after checking the Apify store directly
# (2026-09-12): far and away the most-used Reddit actor there (42k+ users vs.
# single-digit-thousands for alternatives), and -- confirmed via its real
# input schema, not assumed -- supports a genuine site-wide keyword `searches`
# parameter with `searchPosts=True`, unlike Instagram's actor where the
# equivalent fuzzy `search` input turned out to resolve to unrelated content
# and had to be replaced with directUrls. No such replacement was needed
# here: a real test call for "Godrej Properties" returned 4 posts, 3 of the
# 4 genuinely on-topic (Godrej Plots Coimbatore, a Godrej Finance mortgage
# mention, Godrej Whitefield Bangalore) -- real keyword search, not a
# fallback path.
APIFY_ACTOR_ID = "trudax~reddit-scraper-lite"
APIFY_RUNS_ENDPOINT = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/runs"
APIFY_RUN_STATUS_ENDPOINT = "https://api.apify.com/v2/actor-runs/{run_id}"
APIFY_DATASET_ITEMS_ENDPOINT = "https://api.apify.com/v2/datasets/{dataset_id}/items"

# 2026-09-24: this used to POST straight to the actor's own
# run-sync-get-dataset-items convenience endpoint, which blocks until the
# run finishes and returns the dataset in one call. Confirmed live against
# a real Adani Group pipeline run that this endpoint has its own
# platform-side ~300s ceiling, independent of both this adapter's own
# `requests` timeout (600s, see below) and the actor's configured run
# timeout (3600s) -- it returned "HTTP 408: Actor run exceeded the timeout
# of 300 seconds for this API endpoint" for a keyword with enough Reddit
# volume to take longer than that, silently dropping Reddit collection for
# that entire pipeline run (caught, logged, non-fatal -- but zero results).
# Switched to Apify's own documented async pattern instead: start the run
# (returns immediately), poll actor-runs/{id} for a terminal status, then
# fetch the dataset separately once it's done. This removes the sync
# endpoint's artificial 300s wall entirely -- the real ceiling is now
# _MAX_POLL_SECONDS below, chosen to match the same 600s headroom this
# adapter's prior client-side timeout was already tuned to.
_POLL_INTERVAL_SECONDS = 5
_MAX_POLL_SECONDS = 600
_TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}

# Same discipline as Instagram (MAX_RESULTS_PER_CALL = 25 there) and
# YouTube's 25-per-call pattern -- an explicit, low, hard ceiling
# independent of whatever `limit` a caller passes in.
#
# Briefly raised to 100 (2026-09-12) alongside an entity-loop expansion
# (brand+competitor+executive+product per client) that was real-cost-tested
# at $152-$1,554/month across the 4 real clients -- an order-of-magnitude+
# jump over this single-brand-keyword baseline's verified $2.71-$8.09/month.
# Reverted back to 25 by explicit decision; full tracked-entity coverage
# (and the batching fix it needs to be affordable) is a deferred future
# task, not this one.
MAX_RESULTS_PER_CALL = 25

# Real, cheap test call (2026-09-12, searches=["Godrej Properties"],
# searchPosts=True, maxItems=5) confirmed:
#   - Real fields returned: title, body, url/link, username, upVotes,
#     upVoteRatio, numberOfComments, createdAt, communityName/
#     parsedCommunityName, contentType, dataType. NOT "score"/"selftext"/
#     "subreddit"/"created_utc"/"num_comments" -- the dormant PRAW-based
#     reddit.py's field names do NOT match this actor's real output; do not
#     assume they do.
#   - Pricing: PAY_PER_EVENT, confirmed against the actual run's own
#     usageTotalUsd ($0.056 for 4 results at the actor's default 2048MB) --
#     NOT a pure per-result model like Instagram's $0.0027/result. Two
#     charged events: a flat $0.02-per-1GB-memory fee once per run
#     ("actor-start-gb", one-time) plus $0.004 per result stored. Confirmed
#     math: $0.02 * 2 (2048MB) + 4 * $0.004 = $0.04 + $0.016 = $0.056,
#     exactly matching the real run's billed total.


class RedditApifyAdapter(BaseSearchAdapter):
    def __init__(self):
        self.api_token = os.environ.get("APIFY_API_TOKEN")
        self.available = bool(self.api_token)
        if not self.available:
            logger.warning("reddit_apify_adapter_unavailable", reason="missing_api_token")

    def search(self, keyword: str, cursor: Optional[str] = None, limit: int = 25, **kwargs) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Real, site-wide Reddit keyword search (not subreddit-scoped) via
        trudax/reddit-scraper-lite's `searches` input, confirmed live to
        return genuinely on-topic results for a real brand keyword (see
        module docstring).

        This actor's input schema (confirmed live) has no incremental-
        pagination parameter -- `cursor` is accepted for interface
        compatibility with BaseSearchAdapter but is a no-op, same as
        instagram.py's search(), and this always returns cursor=None.
        """
        if not self.available:
            return [], None

        capped_limit = min(limit, MAX_RESULTS_PER_CALL)

        try:
            start_resp = requests.post(
                APIFY_RUNS_ENDPOINT,
                params={"token": self.api_token},
                json={
                    "searches": [keyword],
                    "searchPosts": True,
                    "searchComments": False,
                    "searchCommunities": False,
                    "searchUsers": False,
                    "searchMedia": False,
                    # Needed to get upVotes/numberOfComments at all -- without
                    # this the actor omits engagement fields entirely
                    # (confirmed against its own input schema description).
                    "includeMediaLinks": True,
                    "skipComments": True,
                    "skipUserPosts": True,
                    "skipCommunity": True,
                    "sort": "new",
                    "maxItems": capped_limit,
                    "maxPostCount": capped_limit,
                },
                timeout=30,
            )
        except requests.RequestException as e:
            raise Exception(f"Reddit (Apify) Search Failed: could not start run: {e}") from e

        if start_resp.status_code >= 400:
            raise Exception(f"Reddit (Apify) Search Failed: HTTP {start_resp.status_code} starting run: {start_resp.text[:500]}")

        run_data = start_resp.json().get("data") or {}
        run_id = run_data.get("id")
        if not run_id:
            raise Exception(f"Reddit (Apify) Search Failed: run start response had no run id: {start_resp.text[:500]}")

        status_url = APIFY_RUN_STATUS_ENDPOINT.format(run_id=run_id)
        deadline = time.monotonic() + _MAX_POLL_SECONDS
        status = run_data.get("status")
        dataset_id = run_data.get("defaultDatasetId")

        while status not in _TERMINAL_STATUSES:
            if time.monotonic() >= deadline:
                raise Exception(f"Reddit (Apify) Search Failed: run {run_id} did not finish within {_MAX_POLL_SECONDS}s (last status: {status})")
            time.sleep(_POLL_INTERVAL_SECONDS)
            try:
                poll_resp = requests.get(status_url, params={"token": self.api_token}, timeout=30)
            except requests.RequestException as e:
                raise Exception(f"Reddit (Apify) Search Failed: polling run {run_id}: {e}") from e
            if poll_resp.status_code >= 400:
                raise Exception(f"Reddit (Apify) Search Failed: HTTP {poll_resp.status_code} polling run {run_id}: {poll_resp.text[:500]}")
            poll_data = poll_resp.json().get("data") or {}
            status = poll_data.get("status")
            dataset_id = poll_data.get("defaultDatasetId") or dataset_id

        if status != "SUCCEEDED":
            raise Exception(f"Reddit (Apify) Search Failed: run {run_id} finished with status {status}")
        if not dataset_id:
            raise Exception(f"Reddit (Apify) Search Failed: run {run_id} succeeded but had no dataset id")

        try:
            items_resp = requests.get(
                APIFY_DATASET_ITEMS_ENDPOINT.format(dataset_id=dataset_id),
                params={"token": self.api_token, "format": "json"},
                timeout=60,
            )
        except requests.RequestException as e:
            raise Exception(f"Reddit (Apify) Search Failed: fetching dataset {dataset_id}: {e}") from e

        if items_resp.status_code >= 400:
            raise Exception(f"Reddit (Apify) Search Failed: HTTP {items_resp.status_code} fetching dataset {dataset_id}: {items_resp.text[:500]}")

        results = items_resp.json()
        return results, None

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        content = clean_document_content(raw_data.get("body") or "")

        published_at = None
        created_at = raw_data.get("createdAt")
        if created_at:
            try:
                published_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                published_at = None

        comment_count = None
        try:
            comment_count = int(raw_data["numberOfComments"])
        except (KeyError, TypeError, ValueError):
            pass

        # No dedicated upvote/score column exists (documents.view_count/
        # comment_count are the only two reach columns -- see
        # models/document.py) -- reused here exactly like YouTube's
        # view_count, same pattern reach_trust_config.is_reddit_reach_eligible
        # was already built to expect (its `score` parameter is this value).
        view_count = None
        try:
            view_count = int(raw_data["upVotes"])
        except (KeyError, TypeError, ValueError):
            pass

        return {
            "source_id": str(source_id),
            "source_type": "reddit",
            "title": raw_data.get("title") or "",
            "content": content,
            "url": raw_data.get("url") or raw_data.get("link") or "",
            "author": raw_data.get("username") or "",
            "published_at": published_at,
            "collected_at": datetime.now(timezone.utc),
            "raw_payload": json.dumps(raw_data),
            "view_count": view_count,
            "comment_count": comment_count,
        }
