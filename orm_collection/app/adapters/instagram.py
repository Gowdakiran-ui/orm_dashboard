import json
import re
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
import os
import requests
import structlog
from .search_base import BaseSearchAdapter
from app.utils.text_processing import clean_document_content

logger = structlog.get_logger()

# apify/instagram-scraper (actor id shu8hvrXbJbY3Eb9W), confirmed live via
# GET /v2/acts/apify~instagram-scraper on 2026-09-12. PAY_PER_EVENT pricing,
# $0.0027/result at the FREE tier ($2.70/1000) -- confirmed against this
# account's own /v2/users/me/usage/monthly after a real test call.
APIFY_ACTOR_ENDPOINT = "https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items"

# Hard ceiling on results per call, independent of whatever `limit` a caller
# passes in -- mirrors youtube.py's fixed 25-per-call discipline, but here
# the stakes are different: Apify bills per result with no daily quota of
# its own, so an uncapped or caller-supplied-only limit is a direct,
# unbounded cost lever. 25 keeps one call's worst case at ~$0.0675
# (confirmed pricing above), the same shape as YouTube's per-call cost cap.
#
# Briefly raised to 100 (2026-09-12) alongside an entity-loop expansion
# (brand+competitor+executive+product per client) that was real-cost-tested
# at $152-$1,554/month across the 4 real clients -- an order-of-magnitude+
# jump over this single-brand-keyword baseline's verified $2.71-$8.09/month.
# Reverted back to 25 by explicit decision; full tracked-entity coverage
# (and the batching fix it needs to be affordable) is a deferred future
# task, not this one.
MAX_RESULTS_PER_CALL = 25

# Real, cheap test call (2026-09-12, directUrls=[".../explore/tags/godrejproperties/"],
# resultsType=posts, resultsLimit=5) confirmed these are the actual fields
# apify/instagram-scraper returns for a hashtag-post scrape -- do not assume
# the browser dataset-viewer's column list matches the raw API JSON without
# re-checking; it didn't exactly (e.g. `musicInfo` is a large nested object
# not shown as a plain column there).
#
# Also confirmed live: this actor's fuzzy `search` + `searchType=hashtag`
# input resolved "GodrejProperties" to an unrelated "growthscope" tag with
# 0 posts -- NOT reliable for brand monitoring. `directUrls` pointed at the
# hashtag's own explore page (Instagram's own priority order: URLs over
# search queries) returned real, on-topic posts instead. This adapter only
# ever uses directUrls for that reason.


class InstagramAdapter(BaseSearchAdapter):
    def __init__(self):
        self.api_token = os.environ.get("APIFY_API_TOKEN")
        self.available = bool(self.api_token)
        if not self.available:
            logger.warning("instagram_adapter_unavailable", reason="missing_api_token")

    def search(self, keyword: str, cursor: Optional[str] = None, limit: int = 25, **kwargs) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Scrapes posts tagged with `keyword` as an Instagram hashtag. `keyword`
        is reduced to Instagram's hashtag character set (letters/digits only,
        lowercased) -- Instagram hashtags can't contain spaces or punctuation,
        unlike the +-joined query strings the RSS/GDELT/HN adapters build.

        This actor's input schema (confirmed live, see module docstring above)
        exposes no incremental-pagination parameter (no "after"/"maxId" akin
        to YouTube's pageToken or Reddit's `after`) -- `cursor` is accepted
        for interface compatibility with BaseSearchAdapter but is a no-op,
        and this always returns cursor=None.
        """
        if not self.available:
            return [], None

        hashtag = re.sub(r"[^a-z0-9]", "", keyword.lower())
        if not hashtag:
            logger.warning("instagram_search_empty_hashtag", keyword=keyword)
            return [], None

        capped_limit = min(limit, MAX_RESULTS_PER_CALL)
        hashtag_url = f"https://www.instagram.com/explore/tags/{hashtag}/"

        try:
            response = requests.post(
                APIFY_ACTOR_ENDPOINT,
                params={"token": self.api_token},
                json={
                    "directUrls": [hashtag_url],
                    "resultsType": "posts",
                    "resultsLimit": capped_limit,
                },
                # Actor run is synchronous end-to-end (scrape + dataset write);
                # observed ~30-60s for a 5-result call during live testing.
                timeout=170,
            )
        except requests.RequestException as e:
            raise Exception(f"Instagram Search Failed: {e}") from e

        if response.status_code >= 400:
            raise Exception(f"Instagram Search Failed: HTTP {response.status_code}: {response.text[:500]}")

        results = response.json()
        return results, None

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        caption = raw_data.get("caption") or ""
        content = clean_document_content(caption)

        published_at = None
        timestamp = raw_data.get("timestamp")
        if timestamp:
            try:
                published_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                published_at = None

        comment_count = None
        try:
            comment_count = int(raw_data["commentsCount"])
        except (KeyError, TypeError, ValueError):
            pass

        # Reels (productType "clips") are a different post type from the
        # image posts the original live test used, and DO carry a real
        # play/view count -- confirmed against apify/instagram-scraper's own
        # documented Reel-mode output fields (playCount/videoPlayCount).
        # Image posts have neither field at all, so this stays None for them
        # -- reach_trust_config.is_instagram_reach_eligible is built to
        # handle that (falls back to comment_count alone), not to require
        # this adapter to fake a value.
        view_count = None
        for key in ("playCount", "videoPlayCount", "videoViewCount"):
            try:
                if raw_data.get(key) is not None:
                    view_count = int(raw_data[key])
                    break
            except (TypeError, ValueError):
                continue

        return {
            "source_id": str(source_id),
            "source_type": "instagram",
            # No distinct title field for Instagram posts (unlike RSS/YouTube) --
            # same "empty title, full text lives in content" pattern rss.py's
            # normalize() already uses for feed items without one.
            "title": "",
            "content": content,
            "url": raw_data.get("url", ""),
            "author": raw_data.get("ownerUsername") or raw_data.get("ownerFullName") or "",
            "published_at": published_at,
            "collected_at": datetime.now(timezone.utc),
            "raw_payload": json.dumps(raw_data),
            "view_count": view_count,
            "comment_count": comment_count,
        }
