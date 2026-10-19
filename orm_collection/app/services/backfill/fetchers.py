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


def fetch_google_news(query: str, start: dt.date, end: dt.date, ctx: Dict[str, Any]) -> List[Dict[str, Any]]:
    from app.adapters.rss import RSSAdapter
    time.sleep(GN_PACE_SECONDS)
    return list(RSSAdapter().fetch(google_news_url(query, start, end)))


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
