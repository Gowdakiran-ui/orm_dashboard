"""
Per-source slice fetchers for the historical backfill. Free sources only:
Google News RSS, YouTube Data API (own quota budget), GDELT DOC, HN Algolia.
No Apify and no paid API is reachable from here.

Each fetcher: fetch(query, start, end, ctx) -> list of raw items, and each
source has `normalize(raw, source_id)` plus a `cap` (a slice that returns
>= cap items is split). Network access lives only in the fetch_* functions so
the planner and dry run never touch the network.
"""
import datetime as dt
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import structlog

logger = structlog.get_logger()

GN_CAP = 90            # Google News RSS returns at most 100 items per query
GDELT_CAP = 240        # maxrecords is 250
HN_CAP = 500           # 5 pages x 100; deeper pages are not reachable anyway
YT_SPLIT_AT = 20       # wide YouTube slices come back incomplete (VERIFIED 2026-10-17), so split heavy ones
YT_PAGE_SIZE = 50
YT_MAX_PAGES = 3

# YouTube: backfill may only use units while the day's TOTAL (live pipeline +
# backfill) is below this ceiling, so the live pipeline always keeps
# DAILY_QUOTA_LIMIT - ceiling units of its own.
from app.services.backfill import settings as _bf_settings
YT_BACKFILL_DAILY_CEILING = _bf_settings.YOUTUBE_DAILY_CEILING   # BACKFILL_YT_DAILY_CEILING, default 4000

GN_PACE_SECONDS = 1.0
GDELT_WINDOW_DAYS = 90


class QuotaPaused(Exception):
    """Source budget is used up for now; the run should stop and resume later."""


class SourceUnavailable(Exception):
    """Adapter not configured (e.g. no API key); slices stay PENDING."""


def _ts(d: dt.date) -> int:
    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc).timestamp())


# ---------------------------------------------------------------- Google News
def google_news_url(query: str, start: dt.date, end: dt.date) -> str:
    q = f"{query} after:{start.isoformat()} before:{end.isoformat()}"
    return "https://news.google.com/rss/search?q=" + urllib.parse.quote_plus(q) + "&hl=en-IN&gl=IN&ceid=IN:en"


# One limiter and one circuit breaker for every Google News caller that goes through this function (backfill slices, seeding
# validator counts, alias measurements, attribution), shared across all worker processes through Redis. Measured 2026-11-17: one
# backfill ran about 44 requests a minute from the droplet address for five minutes, then the pipeline's feeds and the validator got
# 503. Now: at most one request every GN_MIN_INTERVAL_SECONDS in total, and after GN_BREAKER_THRESHOLD failures in a row no request
# is sent for GN_BREAKER_OPEN_SECONDS (callers see QuotaPaused, which the backfill treats as "pause this source", not as a slice error).
import os as _os
GN_MIN_INTERVAL_SECONDS = float(_os.environ.get("GN_MIN_INTERVAL_SECONDS", "2.0"))
GN_BREAKER_THRESHOLD = int(_os.environ.get("GN_BREAKER_THRESHOLD", "3"))
GN_BREAKER_OPEN_SECONDS = int(_os.environ.get("GN_BREAKER_OPEN_SECONDS", "180"))
_GN_CIRCUIT_KEY = "gn:circuit_open"
_GN_FAILS_KEY = "gn:consecutive_failures"
_GN_SLOT_KEY = "gn:request_slot"


def _gn_redis():
    try:
        from app.utils.redis_client import redis_client
        return redis_client.client
    except Exception:
        return None


def _gn_before_request() -> None:
    """Raise QuotaPaused while the breaker is open; otherwise wait for this process's turn in the global request spacing."""
    r = _gn_redis()
    if r is None:
        time.sleep(GN_MIN_INTERVAL_SECONDS)
        return
    try:
        if r.exists(_GN_CIRCUIT_KEY):
            raise QuotaPaused("Google News paused: circuit breaker open after repeated errors")
        deadline = time.monotonic() + 60
        while not r.set(_GN_SLOT_KEY, "1", nx=True, px=max(1, int(GN_MIN_INTERVAL_SECONDS * 1000))):
            if time.monotonic() > deadline:
                break
            time.sleep(0.25)
    except QuotaPaused:
        raise
    except Exception:
        time.sleep(GN_MIN_INTERVAL_SECONDS)       # Redis trouble must not remove the spacing


def _gn_record(ok: bool) -> None:
    r = _gn_redis()
    if r is None:
        return
    try:
        if ok:
            r.delete(_GN_FAILS_KEY)
            return
        n = r.incr(_GN_FAILS_KEY)
        r.expire(_GN_FAILS_KEY, GN_BREAKER_OPEN_SECONDS * 2)
        if n >= GN_BREAKER_THRESHOLD:
            r.set(_GN_CIRCUIT_KEY, "1", ex=GN_BREAKER_OPEN_SECONDS)
            r.delete(_GN_FAILS_KEY)
            logger.warning("google_news_circuit_opened", failures=n, open_seconds=GN_BREAKER_OPEN_SECONDS)
    except Exception:
        pass


def fetch_google_news(query: str, start: dt.date, end: dt.date, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.adapters.rss import RSSAdapter
    _gn_before_request()
    try:
        items = list(RSSAdapter().fetch(google_news_url(query, start, end)))
    except Exception:
        _gn_record(False)
        raise
    _gn_record(True)
    return items


# -------------------------------------------------------------------- YouTube
def fetch_youtube(query: str, start: dt.date, end: dt.date, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.adapters import youtube as yt
    adapter = ctx.get("youtube_adapter") or yt.YouTubeAdapter()
    ctx["youtube_adapter"] = adapter
    if not adapter.available:
        raise SourceUnavailable("YOUTUBE_API_KEY missing")
    after = f"{start.isoformat()}T00:00:00Z"
    before = f"{end.isoformat()}T00:00:00Z"
    items: List[Dict[str, Any]] = []
    token: Optional[str] = None
    for _ in range(YT_MAX_PAGES):
        used_today = int(yt.redis_client.get(yt._quota_key()) or 0)
        if used_today + yt.SEARCH_LIST_COST > YT_BACKFILL_DAILY_CEILING:
            raise QuotaPaused(f"YouTube backfill ceiling reached ({used_today}/{YT_BACKFILL_DAILY_CEILING} units today)")
        if ctx.get("youtube_units_budget") is not None and ctx.get("youtube_units_used", 0) + yt.SEARCH_LIST_COST > ctx["youtube_units_budget"]:
            raise QuotaPaused("YouTube per-run budget reached")
        try:
            page, token = adapter.search(query, cursor=token, limit=YT_PAGE_SIZE, order="date",
                                         published_after=after, published_before=before)
        except (yt.YouTubeQuotaExhaustedError, yt.YouTubeCircuitBreakerOpenError) as e:
            raise QuotaPaused(str(e))
        ctx["youtube_units_used"] = ctx.get("youtube_units_used", 0) + yt.SEARCH_LIST_COST + yt.VIDEOS_LIST_COST
        items.extend(page)
        if not token or not page:
            break
    return items


# ---------------------------------------------------------------------- GDELT
def gdelt_url(query: str, start: dt.date, end: dt.date) -> str:
    fmt = lambda d: d.strftime("%Y%m%d") + "000000"
    return ("https://api.gdeltproject.org/api/v2/doc/doc?query=" + urllib.parse.quote(query)
            + "&mode=artlist&format=json&maxrecords=250&startdatetime=" + fmt(start) + "&enddatetime=" + fmt(end))


def fetch_gdelt(query: str, start: dt.date, end: dt.date, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.adapters.gdelt import GDELTAdapter   # paces itself to >= 6 s between calls via Redis
    return list(GDELTAdapter().fetch(gdelt_url(query, start, end)))


# ------------------------------------------------------------------ HN Algolia
def hn_url(query: str, start: dt.date, end: dt.date, page: int = 0) -> str:
    nf = f"created_at_i>{_ts(start)},created_at_i<{_ts(end)}"
    return ("https://hn.algolia.com/api/v1/search_by_date?query=" + urllib.parse.quote_plus(query)
            + "&tags=story&hitsPerPage=100&page=" + str(page) + "&numericFilters=" + urllib.parse.quote(nf))


def fetch_hn(query: str, start: dt.date, end: dt.date, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.adapters.hn_algolia import HNAlgoliaAdapter
    out: List[Dict[str, Any]] = []
    for page in range(5):
        hits = HNAlgoliaAdapter().fetch(hn_url(query, start, end, page))
        out.extend(hits)
        if len(hits) < 100:
            break
        time.sleep(0.5)
    return out


# ------------------------------------------------------------------- registry
@dataclass
class SourceDef:
    name: str                       # value stored in backfill_slices.source
    document_type: str              # value normalize() writes to documents.document_type
    cap: int                        # split a slice at/over this many items
    fetch: Callable[..., List[Dict[str, Any]]]
    query_attr: str                 # QuerySpec attribute holding this source's query
    category: str                   # SourceCategory name (same categories the live feeds use)
    adapter_path: str               # module:Class for normalize()
    split_at: Optional[int] = None  # override cap for the split decision


SOURCES: Dict[str, SourceDef] = {
    "google_news": SourceDef("google_news", "rss", GN_CAP, fetch_google_news, "google_news", "RSS News", "app.adapters.rss:RSSAdapter"),
    "youtube": SourceDef("youtube", "youtube", YT_SPLIT_AT, fetch_youtube, "youtube", "Video Search", "app.adapters.youtube:YouTubeAdapter"),
    "gdelt": SourceDef("gdelt", "gdelt", GDELT_CAP, fetch_gdelt, "gdelt", "RSS News", "app.adapters.gdelt:GDELTAdapter"),
    "hn": SourceDef("hn", "hn_algolia", HN_CAP, fetch_hn, "hn", "RSS News", "app.adapters.hn_algolia:HNAlgoliaAdapter"),
}


def load_adapter(src: SourceDef):
    import importlib
    mod, cls = src.adapter_path.split(":")
    return getattr(importlib.import_module(mod), cls)()
