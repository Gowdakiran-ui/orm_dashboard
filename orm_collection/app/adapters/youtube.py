import json
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import structlog
from .search_base import BaseSearchAdapter
from app.utils.redis_client import redis_client

logger = structlog.get_logger()

# YouTube Data API v3 costs (confirmed from Google's published quota table):
# search.list = 100 units, videos.list = 1 unit regardless of how many IDs
# are requested in one call (up to 50).
SEARCH_LIST_COST = 100
VIDEOS_LIST_COST = 1
DAILY_QUOTA_LIMIT = 10000

# 3 consecutive 403/429 responses trips a 30-minute platform-wide cooldown.
# Deliberately separate from quota tracking below -- a 403 can mean a bad/
# revoked key, not quota exhaustion, and that distinction matters for
# debugging (see _record_api_failure/_check_circuit_breaker).
CIRCUIT_BREAKER_THRESHOLD = 3
CIRCUIT_BREAKER_COOLDOWN_MINUTES = 30

_QUOTA_KEY_TTL_SECONDS = 2 * 24 * 60 * 60  # best-effort cleanup, 2 days
_CIRCUIT_BREAKER_KEY = "quota:youtube:consecutive_4xx"
_COOLDOWN_KEY = "quota:youtube:cooldown_until"


class YouTubeQuotaExhaustedError(Exception):
    """Raised when today's platform-wide YouTube quota is used up."""
    pass


class YouTubeCircuitBreakerOpenError(Exception):
    """Raised when repeated 403/429 responses have tripped the cooldown."""
    pass


def _pt_date_str() -> str:
    """
    YouTube's quota resets at midnight Pacific Time, not UTC (confirmed
    against Google's published Data API quota documentation). Using
    ZoneInfo instead of a fixed UTC offset so PST/PDT transitions are
    handled automatically.
    """
    return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")


def _quota_key() -> str:
    return f"quota:youtube:search_list:{_pt_date_str()}"


def _reserve_search_quota() -> int:
    """
    Reserve-then-check: INCRBY is atomic in Redis, so concurrent pipeline
    workers can't both read "9950 remaining" and both proceed. Reserve the
    full cost first; if that pushes the day's total over the limit, give
    the units back and report exhaustion instead of proceeding.
    """
    key = _quota_key()
    total = redis_client.incrby(key, SEARCH_LIST_COST)
    if total > DAILY_QUOTA_LIMIT:
        redis_client.incrby(key, -SEARCH_LIST_COST)
        raise YouTubeQuotaExhaustedError(
            f"Daily YouTube search.list quota exhausted ({total - SEARCH_LIST_COST}/{DAILY_QUOTA_LIMIT} units already used today)"
        )
    try:
        redis_client.client.expire(key, _QUOTA_KEY_TTL_SECONDS)
    except Exception:
        # Best-effort housekeeping only -- never let this affect quota
        # correctness, which relies solely on the date-scoped key name.
        pass
    return total


def _check_circuit_breaker() -> None:
    cooldown_until = redis_client.get(_COOLDOWN_KEY)
    if cooldown_until:
        now_ts = datetime.now(timezone.utc).timestamp()
        if now_ts < float(cooldown_until):
            raise YouTubeCircuitBreakerOpenError(
                f"YouTube circuit breaker open until {datetime.fromtimestamp(float(cooldown_until), tz=timezone.utc).isoformat()} "
                f"({CIRCUIT_BREAKER_THRESHOLD} consecutive 403/429 responses)"
            )


def _record_api_success() -> None:
    redis_client.delete(_CIRCUIT_BREAKER_KEY)


def _record_api_failure_4xx(status: int) -> None:
    consecutive = redis_client.incrby(_CIRCUIT_BREAKER_KEY)
    if consecutive >= CIRCUIT_BREAKER_THRESHOLD:
        cooldown_until = datetime.now(timezone.utc).timestamp() + CIRCUIT_BREAKER_COOLDOWN_MINUTES * 60
        redis_client.set(_COOLDOWN_KEY, cooldown_until)
        redis_client.delete(_CIRCUIT_BREAKER_KEY)
        logger.warning(
            "youtube_circuit_breaker_tripped",
            consecutive_failures=consecutive,
            last_status=status,
            cooldown_minutes=CIRCUIT_BREAKER_COOLDOWN_MINUTES,
        )


def _format_count(value) -> str:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return "unknown"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


class YouTubeAdapter(BaseSearchAdapter):
    def __init__(self):
        self.api_key = os.environ.get("YOUTUBE_API_KEY")
        self.available = bool(self.api_key)
        self.youtube = None
        if not self.available:
            logger.warning("youtube_adapter_unavailable", reason="missing_api_key")
            return
        self.youtube = build("youtube", "v3", developerKey=self.api_key)

    def search(self, keyword: str, cursor: Optional[str] = None, limit: int = 25, **kwargs) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not self.available:
            return [], cursor

        _check_circuit_breaker()
        _reserve_search_quota()

        try:
            request = self.youtube.search().list(
                part="snippet",
                q=keyword,
                maxResults=limit,
                pageToken=cursor,
                type="video",
                order="date"
            )
            response = request.execute()
        except HttpError as e:
            status = e.resp.status if getattr(e, "resp", None) is not None else None
            if status in (403, 429):
                _record_api_failure_4xx(status)
            raise Exception(f"YouTube Search Failed: {e}") from e
        except Exception as e:
            raise Exception(f"YouTube Search Failed: {e}") from e

        _record_api_success()

        items = response.get("items", [])
        new_cursor = response.get("nextPageToken")

        video_ids = [
            item["id"]["videoId"] for item in items
            if item.get("id", {}).get("videoId")
        ]
        details_by_id = self._fetch_video_details(video_ids) if video_ids else {}

        results = []
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            details = details_by_id.get(video_id)
            if details:
                item = {**item, "statistics": details.get("statistics", {})}
            results.append(item)

        return results, new_cursor

    def _fetch_video_details(self, video_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        One batched videos.list call (1 unit total, regardless of how many
        of the up-to-50 IDs are requested) instead of re-searching or
        calling per video -- search.list's snippet part never returns
        viewCount/commentCount.
        """
        try:
            request = self.youtube.videos().list(
                part="snippet,statistics",
                id=",".join(video_ids[:50]),
            )
            response = request.execute()
        except HttpError as e:
            status = e.resp.status if getattr(e, "resp", None) is not None else None
            if status in (403, 429):
                _record_api_failure_4xx(status)
            logger.warning("youtube_videos_list_failed", error=str(e))
            return {}
        except Exception as e:
            logger.warning("youtube_videos_list_failed", error=str(e))
            return {}

        _record_api_success()
        return {item["id"]: item for item in response.get("items", [])}

    def normalize(self, raw_data: Dict[str, Any], source_id: str, **kwargs) -> Dict[str, Any]:
        snippet = raw_data.get("snippet", {})
        statistics = raw_data.get("statistics", {})
        video_id = raw_data.get("id", {}).get("videoId", "")

        published_str = snippet.get("publishedAt")
        published_at = datetime.now(timezone.utc)
        if published_str:
            try:
                # YouTube's publishedAt is always Z-suffixed (UTC).
                published_at = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        description = snippet.get("description", "")
        content = description
        if statistics:
            view_str = _format_count(statistics.get("viewCount"))
            comment_str = _format_count(statistics.get("commentCount"))
            content = f"{view_str} views, {comment_str} comments\n\n{description}"

        return {
            "source_id": source_id,
            "source_type": "youtube",
            "title": snippet.get("title", ""),
            "content": content,
            # youtu.be/{id} keeps the video identifier in the URL PATH, not a
            # query string. canonicalize_url() (text_processing.py) strips
            # query strings/fragments entirely -- the old /watch?v={id} form
            # made every video collapse onto the same canonical URL
            # ("https://www.youtube.com/watch") and get silently
            # deduplicated by document_service.py's ON CONFLICT after the
            # first one ever saved.
            "url": f"https://youtu.be/{video_id}" if video_id else "",
            "author": snippet.get("channelTitle", ""),
            "published_at": published_at,
            "collected_at": datetime.now(timezone.utc),
            "raw_payload": json.dumps(raw_data)
        }
