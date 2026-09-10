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
# ---------------------------------------------------------------------------
YOUTUBE_MIN_VIEW_COUNT = 1000
YOUTUBE_MIN_COMMENT_COUNT = 50
RSS_ELIGIBLE_TIERS = {"medium", "high"}


def is_youtube_reach_eligible(view_count, comment_count=None) -> bool:
    """
    Hard gate for YouTube: eligible only at or above the real "nano-influencer"
    reach floor (eMarketer 2026) on views or comments. Callers must only
    invoke this when view_count is not None -- a document with no reach data
    at all has no reach signal to gate on (see get_reach_modifier).
    """
    return (view_count or 0) >= YOUTUBE_MIN_VIEW_COUNT or (comment_count or 0) >= YOUTUBE_MIN_COMMENT_COUNT


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
