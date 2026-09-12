"""
Reach/credibility-weighted risk scoring config.

CEO's ask: a 10-view post about a client is noise; the same complaint from a
100K-follower account with 20K likes is a real signal even as a single
mention. Same principle for RSS/press -- a mention in a reputed, trustworthy
outlet should carry more weight than one from an unverified source. Applied
as an additional multiplier in risk_engine.py's existing score formula
(alongside source_reliability), not a second/parallel noise filter.

Two independent inputs, both producing a 0.0-1.2-ish modifier in the same
range as DYNAMIC_SOURCE_RELIABILITY_MAP (risk_config.py) so neither can
dominate the formula unexpectedly:

  - REACH_ANCHORS: YouTube/social documents with real view_count data.
  - RSS_TRUST_TIERS / TRUSTED_OUTLETS: RSS/press documents, keyed by the
    outlet name parsed from the article title.
"""
import math
import re

# ---------------------------------------------------------------------------
# Reach modifier (YouTube / social engagement)
# ---------------------------------------------------------------------------
# Anchors are (log10(effective_reach + 1), modifier), piecewise-linear
# interpolated and clamped to the endpoints outside the range. Boundaries are
# grounded in the real view_count distribution measured across 225 real
# collected YouTube documents (2026-09-10, client corpus incl. Godrej
# Properties): p10=28, p25=76, p50=441, p75=1700, p90=7300, p95=19100,
# p99=45400, max=1,200,000 -- NOT round/invented numbers. Log scale because
# the data is extremely long-tailed (median 441 vs. max 1.2M -- a linear
# bucket scheme would put nearly the entire corpus in one bucket).
#
# effective_reach blends comment_count in at a 10x weight relative to
# view_count: comments are a much stronger engagement signal than views
# (62% of real documents have zero comments at all -- comment_count alone is
# too sparse to anchor tiers on, but a real comment thread should still push
# the modifier up).
REACH_ANCHORS = [
    (0.00, 0.50),   # 0 views -- no reach signal, matches the CEO's "10-view post is noise" example
    (1.89, 0.65),   # ~p25 (76 views) -- still low
    (2.65, 0.85),   # ~p50 (441 views) -- typical for this corpus, below full weight
    (3.86, 1.00),   # ~p90 (7,300 views) -- neutral/full weight
    (4.66, 1.10),   # ~p99 (45,400 views) -- elevated, a real signal
    (6.08, 1.20),   # ~observed max (1.2M views) -- strongest elevation, same ceiling as
                     # DYNAMIC_SOURCE_RELIABILITY_MAP's existing government/regulatory/court tier
]

COMMENT_TO_VIEW_WEIGHT = 10

# ---------------------------------------------------------------------------
# Hard reach/trust eligibility gate (replaces the soft modifier for this
# purpose): real verification showed the 0.65-1.15 modifier range can never
# pull a genuinely risk-relevant document's score below the LOW threshold
# (23/23 real risk-relevant RSS documents stayed MEDIUM+ even at the lowest
# 0.65 trust tier), so low reach / low trust must instead exclude a document
# from risk-relevance entirely via is_risk_relevant in risk_engine.py, not
# just down-weight it.
#
# YOUTUBE_MIN_VIEW_COUNT was originally 1000, grounded in a generic "any real
# audience at all" nano-influencer floor. Raised to 10,000 (2026-09-12):
# published 2026 benchmarks put the floor for "reached a genuinely
# non-negligible audience" at 10k-100k views even for a smaller channel, and
# 1,000 was judged too permissive as a real risk-relevance signal. Re-checked
# against the real current corpus (159 YouTube documents with view_count
# populated, prod DB, 2026-09-12): raising the view floor alone takes overall
# eligibility (view OR comment) from 73.0% (116/159) to 27.7% (44/159).
#
# YOUTUBE_MIN_COMMENT_COUNT was investigated separately per the same
# discipline, not scaled up to match the 10x view-count increase: among the
# 118 documents that now fall under the new 10,000-view floor, real
# comment_count distribution is p50=1, p75=4, p90=19.2, p95=34.3, p99=55.9,
# max=92 -- the existing 50 threshold already sits almost exactly at that
# sub-population's p99, i.e. it already selects only genuinely exceptional
# comment engagement (only 3 of 159 documents clear it on comments alone:
# 55, 56, and 92 comments). Scaling it up 10x to 500 would exceed every real
# comment_count ever observed (max 92) and make the comment clause dead
# weight; raising it to any value above 92 has the same effect. 50 is left
# unchanged as already well-calibrated, not left provisional.
# ---------------------------------------------------------------------------
YOUTUBE_MIN_VIEW_COUNT = 10000
YOUTUBE_MIN_COMMENT_COUNT = 50
RSS_ELIGIBLE_TIERS = {"medium", "high"}

# *** PROVISIONAL -- NEEDS RECALIBRATION ONCE REAL GODREJ INSTAGRAM DATA EXISTS ***
# No real Instagram corpus exists yet (unlike YOUTUBE_MIN_VIEW_COUNT/
# YOUTUBE_MIN_COMMENT_COUNT above, which were checked against 159/225 real
# collected documents) -- these two floors are grounded only in published
# external benchmarks, same treatment already given to RSS_TRUST_TIERS
# ("STARTER LIST -- NEEDS KIRAN/TEAM REVIEW") above.
#
# view floor: the real Apify test (instagram.py module docstring) confirmed
# apify/instagram-scraper's `posts` resultsType returns no view/play count at
# all for image posts -- only likesCount/commentsCount. Reels are a different
# post type (productType "clips") and DO carry a real play/view count
# (`playCount`/`videoViewCount`, confirmed via the same actor's Reel-mode
# output fields). A widely-cited "average Reels views" figure like ~283K is
# an all-account-sizes average dominated by large established accounts and
# is not a usable "reached a real audience" floor for the small/local
# accounts this platform actually tracks -- same reasoning YOUTUBE_MIN_VIEW_COUNT
# used to reject a generic floor in favor of a real distribution. The closest
# available substitute is a small-account-tier average: accounts with
# 2,001-10,000 followers average ~2,900 Reels views (cited below). Set as the
# floor itself, not a stricter multiple of it -- unlike YouTube there is no
# real corpus yet to check what "well above average" excludes, so starting at
# the small-account average itself (not an arbitrary multiple of it) is the
# more defensible provisional choice until real Godrej data exists.
INSTAGRAM_MIN_VIEW_COUNT = 2900  # Reels (playCount) only -- see is_instagram_reach_eligible
# comment floor: no schema column exists for likesCount (documents.view_count/
# comment_count are the only two reach columns -- see models/document.py), so
# image posts (no view/play count at all) are gated on commentsCount alone,
# the same "OR comment_count" fallback shape YouTube already uses for
# low-view videos. Published 2026 benchmarks put total engagement (likes +
# comments + shares + saves) for an ~8K-follower nano account around
# 400-640 interactions per post, with comments consistently a minority slice
# of that total (likes dominate) -- 20 is a conservative floor within that
# range, deliberately not the "200 comments" figure benchmarks call out as
# exceptional for a nano account, since that would exclude nearly everything.
INSTAGRAM_MIN_COMMENT_COUNT = 20

# *** PROVISIONAL -- NEEDS RECALIBRATION ONCE REAL GODREJ REDDIT DATA EXISTS ***
# The live Reddit path is reddit_apify.py (trudax/reddit-scraper-lite),
# not the dormant PRAW-based reddit.py -- Reddit's own Data API self-service
# registration is confirmed closed (r/redditdev admin post, 2026-08-05), so
# reddit.py's credentials can never be obtained and it stays unused. The
# Apify actor's real confirmed field names are `upVotes`/`numberOfComments`,
# NOT reddit.py's `score`/`num_comments` -- reddit_apify.py's normalize()
# maps upVotes into the view_count column (same reuse-not-add pattern as
# every other source here), which is what the `score` parameter below
# actually receives at runtime; semantically the same net-upvote count PRAW
# would have returned, just a different field name from a different source.
# Threshold values below are unaffected by the field-name change. Grounded
# in a 2026 Reddit engagement study (cited below): posts need roughly 50-80
# early upvotes to gain real traction in mid-size (20K-500K member)
# subreddits, and roughly 8-11 comments to rank in quieter niche
# subreddits -- the low end of the "real traction" range in each case, same
# floor-not-ceiling choice as the Instagram view floor above.
REDDIT_MIN_SCORE = 50
REDDIT_MIN_COMMENT_COUNT = 10


def is_youtube_reach_eligible(view_count, comment_count=None) -> bool:
    """
    Hard gate for YouTube: eligible only at or above the real "genuinely
    non-negligible audience" reach floor (published 2026 benchmarks) on views
    or comments. Callers must only invoke this when view_count is not None --
    a document with no reach data at all has no reach signal to gate on (see
    get_reach_modifier).
    """
    return (view_count or 0) >= YOUTUBE_MIN_VIEW_COUNT or (comment_count or 0) >= YOUTUBE_MIN_COMMENT_COUNT


def is_instagram_reach_eligible(view_count, comment_count=None) -> bool:
    """
    Hard gate for Instagram. Unlike YouTube, view_count is legitimately
    None for an entire post type (images -- no play/view count exists at
    all, confirmed live), not just for documents with unusually low reach --
    so, unlike is_youtube_reach_eligible, this must be safe to call with
    view_count=None and fall back to the comment-count floor alone rather
    than requiring the caller to special-case that first.
    """
    if (comment_count or 0) >= INSTAGRAM_MIN_COMMENT_COUNT:
        return True
    return view_count is not None and view_count >= INSTAGRAM_MIN_VIEW_COUNT


def is_reddit_reach_eligible(score, comment_count=None) -> bool:
    """
    Hard gate for Reddit. `score` (PRAW's net-upvote count) is the Reddit
    analogue of YouTube's view_count -- always populated for a real
    submission, so no None-handling special case is needed here the way
    Instagram's missing-for-images view_count requires above.
    """
    return (score or 0) >= REDDIT_MIN_SCORE or (comment_count or 0) >= REDDIT_MIN_COMMENT_COUNT


def is_document_reach_trust_eligible(document_type, title, view_count=None, comment_count=None) -> bool:
    """
    Document-level reach/trust eligibility, factored out of risk_engine.py's
    inline dispatch (document_type == "youtube"/"rss" -> is_youtube_reach_eligible
    / is_rss_trust_eligible, else eligible by default) so other callers --
    narrative_engine.py's narrative eligibility gate -- can reuse the exact
    same rule instead of re-deriving it. risk_engine.py's own inline
    reach_trust_eligible computation mirrors this same dispatch (including
    the instagram/reddit branches added here) rather than calling this
    function directly, matching how it already duplicated the youtube/rss
    branches instead of importing them from here.

    view_count doubles as Reddit's `score` for reddit documents -- reddit.py's
    normalize() maps `score` into the view_count column (see its own comment)
    since the schema has no dedicated upvote column, the same reuse-not-add
    approach view_count/comment_count already take for every other source.
    """
    if document_type == "youtube" and view_count is not None:
        return is_youtube_reach_eligible(view_count, comment_count)
    elif document_type == "instagram":
        return is_instagram_reach_eligible(view_count, comment_count)
    elif document_type == "reddit":
        return is_reddit_reach_eligible(view_count, comment_count)
    elif document_type == "rss":
        return is_rss_trust_eligible(title)
    return True


def is_rss_trust_eligible(title: str) -> bool:
    """
    Hard gate for RSS: eligible only if the outlet's existing trust tier
    classification (get_trust_tier) is medium or high. "low" and "unknown"
    are both excluded -- not just the unrecognized floor.
    """
    return get_trust_tier(title) in RSS_ELIGIBLE_TIERS


def get_reach_modifier(view_count, comment_count=None) -> float:
    """
    Returns a 0.50-1.20 multiplier from real view_count/comment_count.
    Callers must only invoke this when view_count is not None -- documents
    with no reach data should not get a reach modifier at all (neutral 1.0),
    not be penalized as if they had zero views.
    """
    if view_count is None:
        return 1.0
    effective_reach = max(0, view_count) + max(0, comment_count or 0) * COMMENT_TO_VIEW_WEIGHT
    x = math.log10(effective_reach + 1)

    if x <= REACH_ANCHORS[0][0]:
        return REACH_ANCHORS[0][1]
    if x >= REACH_ANCHORS[-1][0]:
        return REACH_ANCHORS[-1][1]

    for (x0, y0), (x1, y1) in zip(REACH_ANCHORS, REACH_ANCHORS[1:]):
        if x0 <= x <= x1:
            if x1 == x0:
                return y0
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return 1.0  # unreachable given the bounds checks above


# ---------------------------------------------------------------------------
# Source-trust modifier (RSS / press)
# ---------------------------------------------------------------------------
# No dedicated outlet field exists anywhere in the schema: `sources.name` is
# one row per client keyword query (e.g. "Godrej Properties RSS Source"),
# aggregating hundreds of outlets, and `documents.author` is always NULL for
# RSS (confirmed live: 2,216/2,216). Google News RSS titles reliably carry
# the real outlet as the trailing " - {Outlet}" suffix (confirmed against
# real Godrej Properties documents), so that's the parse point.
#
# *** STARTER LIST -- NEEDS KIRAN/TEAM REVIEW BEFORE BEING TREATED AS FINAL ***
# Seeded only from outlets actually observed in real client RSS data
# (2026-09-10, Godrej Properties / Tesla / Anthropic / Google corpora). Not
# an exhaustive or authoritative trust ranking -- a starting point.
RSS_TRUST_TIERS = {
    "high": 1.15,
    # 0.95, not 1.00 -- 1.00 is also the neutral default final_score keeps for
    # document types with no reach/trust signal at all (gdelt, hn_algolia,
    # YouTube not yet re-collected -- see risk_engine.py's reach_trust_modifier
    # default). A "medium"-tier value identical to that neutral default made a
    # real recognized outlet (Hindustan Times, NDTV, Times of India) look
    # indistinguishable from "no trust data at all" to anyone auditing by
    # reach_trust_modifier value alone instead of also checking
    # reach_trust_basis. Investigated live 2026-09-10: confirmed no RSS
    # document actually falls through to a neutral default (unparseable/
    # unmatched titles already correctly resolve to "unknown" below) -- this
    # is purely to keep every RSS trust tier numerically distinct from
    # out-of-scope "no data".
    "medium": 0.95,
    "low": 0.85,
    "unknown": 0.65,  # default for anything unrecognized -- NOT a neutral/benefit-of-the-doubt tier
}

TRUSTED_OUTLETS = {
    # -- high: established national business/financial press --
    "the economic times": "high",
    "economictimes.com": "high",
    "moneycontrol.com": "high",
    "moneycontrol": "high",
    "business standard": "high",
    "livemint": "high",
    "mint": "high",
    "reuters": "high",
    "reuters.com": "high",
    "bloomberg": "high",
    "bloomberg.com": "high",

    # -- medium: recognized general-interest national press --
    "the hindu": "medium",
    "hindustan times": "medium",
    "the times of india": "medium",
    "times of india": "medium",
    "ndtv": "medium",
    "ndtv profit": "medium",
    "the indian express": "medium",
    "indian express": "medium",

    # -- low: real outlets, but trade/aggregator/lower-scrutiny tier --
    "bw businessworld": "low",
    "construction week india": "low",
    "devdiscourse": "low",
    "realty plus magazine": "low",
}


def _extract_outlet(title: str):
    """
    Google News RSS convention: "{article title} - {Publisher}". Takes the
    text after the LAST " - " since publisher names occasionally contain
    their own hyphens/dashes, and article titles rarely do right at the end.
    """
    if not title or " - " not in title:
        return None
    outlet = title.rsplit(" - ", 1)[-1].strip()
    return outlet or None


def get_trust_tier(title: str) -> str:
    """
    Returns the trust tier ("high", "medium", "low", or "unknown") for the
    outlet parsed out of an RSS document's title. Unrecognized/unparseable
    outlets resolve to "unknown" by design (CEO's ask: unverified sources
    default to lowest trust, not neutral). Shared by get_trust_modifier and
    by the risk_engine.py reach/trust eligibility gate so both use the same
    classification instead of parsing the title twice.
    """
    outlet = _extract_outlet(title)
    if outlet is None:
        return "unknown"
    return TRUSTED_OUTLETS.get(outlet.lower(), "unknown")


def get_trust_modifier(title: str) -> float:
    """
    Returns a 0.65-1.15 multiplier from the outlet parsed out of an RSS
    document's title. Unrecognized/unparseable outlets get the lowest tier
    by design (CEO's ask: unverified sources default to lowest trust, not
    neutral).
    """
    return RSS_TRUST_TIERS[get_trust_tier(title)]
