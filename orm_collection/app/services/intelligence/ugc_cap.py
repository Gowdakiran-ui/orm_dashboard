"""
User-generated / video allegations are held at Medium unless they are from a news outlet or reach many people.

Applies only to items the case-status label (case_status.py) calls `allegation`, and only when CASE_STATUS_ENABLED is on. An allegation is a
claim with no authority action behind it; when it sits in a user-generated or video source (YouTube, Instagram, Reddit, forum posts) that
has under 100,000 views and is not a news outlet, it should not reach High on its own. The score is capped at the MEDIUM / HIGH boundary
(50.0), like the other case-status caps. Probe, charged, penalty_or_order and every other status are never touched, and neither is any
press (rss / gdelt) item.

  * user-generated / video types:  youtube, instagram, reddit, hn_algolia (forum), and the generic post / video / review / forum types.
  * "news outlet": the channel or author name is on NEWS_OUTLET_NAMES below (a starting list of Indian and international news brands,
    matched as whole words, case-insensitive). A channel that is not on the list is NOT treated as a news outlet; add it to the list
    when it is one.
  * views: `view_count` under 100,000. A source that reports no view count (forum posts) counts as under 100,000: its reach is not shown.
"""
import re
from typing import Optional, Tuple

VIEWS_THRESHOLD = 100_000
UGC_TYPES = frozenset({"youtube", "instagram", "reddit", "hn_algolia", "post", "video", "forum", "review", "tiktok", "facebook", "twitter", "x"})

NEWS_OUTLET_NAMES = (
    # India: television and digital news
    "ndtv", "aaj tak", "abp news", "abp ananda", "zee news", "zee business", "zee 24 taas", "india today", "cnbc tv18", "cnbc-tv18",
    "cnbc awaaz", "times now", "news18", "republic world", "republic bharat", "the hindu", "hindustan times", "indian express",
    "economic times", "et now", "et realty", "business standard", "livemint", "moneycontrol", "financial express", "the print", "theprint",
    "wion", "dd news", "doordarshan", "tv9", "news9", "india tv", "firstpost", "business today", "bloomberg quint", "bq prime",
    "ndtv profit", "news nation", "etv bharat", "times of india", "dainik bhaskar", "dainik jagran", "amar ujala", "navbharat times",
    "lokmat", "asianet news", "mathrubhumi news", "manorama news", "suvarna news", "public tv", "tv9 kannada", "news first kannada",
    "sakshi tv", "ntv telugu", "tv5 news", "sun news", "puthiya thalaimurai", "pti news", "ani news", "ians",
    # international
    "bloomberg", "reuters", "bbc news", "cnn", "al jazeera", "cnbc", "financial times", "wall street journal", "associated press",
    "the guardian", "sky news", "dw news", "france 24",
)
_NEWS_RE = re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(n) for n in sorted(NEWS_OUTLET_NAMES, key=len, reverse=True)) + r")(?![a-z0-9])", re.IGNORECASE)


def is_news_outlet(name: Optional[str]) -> bool:
    return bool(name and _NEWS_RE.search(name))


def ugc_cap_decision(document_type: Optional[str], view_count: Optional[int], author: Optional[str], case_status: Optional[str]) -> Tuple[bool, str]:
    """(cap, reason). Cap only an `allegation` from a user-generated / video source, under 100,000 views, not from a news outlet."""
    if case_status != "allegation":
        return False, "not an allegation"
    if (document_type or "").lower() not in UGC_TYPES:
        return False, "not a user-generated or video source"
    if is_news_outlet(author):
        return False, "the channel is a news outlet"
    if isinstance(view_count, (int, float)) and view_count >= VIEWS_THRESHOLD:
        return False, "100,000 views or more"
    views = "no view count shown" if not isinstance(view_count, (int, float)) else f"{int(view_count):,} views"
    return True, f"an allegation from a user-generated or video source ({views}, under 100,000) that is not a news outlet"
