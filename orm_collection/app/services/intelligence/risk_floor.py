"""
Serious-coverage floor for risk scoring (classification rule, not a scoring-formula change).

Legal, regulatory, enforcement, fraud and protest coverage about the client's own brand is at least HIGH,
even when the formula scored it 0 only because the outlet is not on the trusted list or because the topic /
sentiment model was lukewarm. Measured on Godrej (2026-10-20): 63 serious items, 2 scored; the rest were
zeroed by the hard outlet-trust gate and the neutral-sentiment gate.

OFF by default: set RISK_FLOOR_ENABLED=1 to turn it on, so deploying the code changes no score.

Deliberately narrow: press-type documents only (rss / gdelt / hn_algolia; social keeps its reach gate),
the title must name the entity, Positive sentiment and approval / launch / settlement / merger wording are
excluded, and coverage in which the client is the complainant or the aggrieved party is excluded. The LLM
SELF/BYSTANDER/EXONERATED role gate still runs afterwards and can zero the score.
"""
import os
import re
from typing import Optional

HIGH_FLOOR_SCORE = 51.0          # first score above the MEDIUM_TO_HIGH boundary (50.0) in RISK_THRESHOLDS
FLOOR_DOCUMENT_TYPES = ("rss", "gdelt", "hn_algolia")

# Outlets whose coverage never gets the floor: Sprouts News (court-restrained for defamatory articles about the client)
# and Inventiva / inventiva.co.in (blog-style allegation pieces, low reliability).
FLOOR_EXCLUDED_OUTLETS = ("sprouts news", "inventiva")

# Plain serious terms (case-insensitive). Terms that are also ordinary words (court, probe, refund, dispute,
# fine) are NOT here: they only count in the context patterns below.
_SERIOUS = re.compile(
    r"\b(?:rera|maharera|ncdrc|consumer (?:commission|court|forum)|tribunal|nclt|nclat|enforcement|"
    r"arrest\w*|raids?|penalt\w+|scam|fraud|forgery|cheating|money laundering|tax (?:demand|evasion)|"
    r"gst demand|protest\w*|lawsuit)\b"
    r"|\bfined\b|\bfines?\s+(?:of\s+)?(?:rs\.?|₹|inr|\d)"
    r"|\b(?:high|supreme|district|civil|sessions|magistrate|consumer)\s+court\b"
    r"|\bcourt\s+(?:orders?|directs?|denies|rejects?|dismisses|slams|summons|restrains|stays|notice|"
    r"pulls up|upholds|issues notice)\b"
    r"|\b(?:moves?|moved|approach\w*|taken to|goes? to|drag\w*(?:\s+\w+)?\s+to)\s+(?:the\s+)?court\b"
    r"|\b(?:ed|cbi|sebi|police|sit|eow|income[- ]tax|it dept|govt|government|cag)\s+probe\b"
    r"|\bprobe\s+(?:into|against|ordered|launched)\b"
    r"|\b(?:orders?|ordered|directs?|directed|asks?|asked|told)\b[^.;]{0,40}\brefund\w*"
    r"|\b(?:legal|land|property|tax|title|payment|contractual|boundary)\s+disputes?\b"
    r"|\bin dispute\b",
    re.IGNORECASE,
)
# Agency / court abbreviations count only when written in capitals ("ED probe", "CBI FIR"), never as the words
# "ed", "hc" or "fir" in lower or title case.
_SERIOUS_ABBR = re.compile(r"\b(?:ED|FIR|HC|CBI|SC)\b")
# Wording that makes the item not a reputational risk, or one where the client is the complainant / aggrieved.
_EXCLUDE = re.compile(
    r"\b(approved|approval|nod|launch|pre-?launch|eoi|offers?|registered|merger|amalgamation|sanction\w*|"
    r"settle\w*|settlement|resolve[sd]?|defamat\w*)\b|rera (?:received|ii)|\balleges\b|filed by|\bheld in\b"
    r"|\bdismiss\w*[^.;]{0,60}\bcomplaints?\s+against\b",   # the complaint against the client failed: not a risk
    re.IGNORECASE,
)
# Charges dropped / case withdrawn or cleared: good news for the client, never a risk ("US drops fraud charges against Adani").
_CHARGES_DROPPED = re.compile(
    r"\b(?:drops?|dropped|withdraws?|withdrawn|quash(?:es|ed)|clears?|cleared|acquit(?:s|ted)?|exonerat\w+|dismiss(?:es|ed))\b"
    r"[^.;]{0,50}\b(?:charges?|cases?|probe|allegations?|complaints?|fir)\b",
    re.IGNORECASE,
)

# ---- Market-move, financial-results and promotional wording: not reputational risk ------------------------------
# A share-price move, a quarterly result or a sales video is not a reputation event, so when the title carries no
# serious term the score is capped at LOW (see noise_cap_reason). The same wording also keeps the HIGH floor away.
LOW_CAP_SCORE = 25.0            # top of the LOW band (RISK_THRESHOLDS["LOW_TO_MEDIUM"])

_MOVES = (r"(?:rise|rises|rose|gain|gains|gained|surge|surges|surged|jump|jumps|jumped|rally|rallies|rallied|fall|falls|fell|"
          r"slip|slips|slipped|drop|drops|dropped|slide|slides|tumble|tumbles|crash|crashes|crashed|plunge|plunges|plunged|"
          r"slump|slumps|slumped|decline|declines|declined|climb|climbs|up|down|gap down|gap up)")
_MARKET = re.compile(
    r"\b(?:stocks?|shares?|scrip)\b[^.;]{0,30}\b" + _MOVES + r"\b"
    r"|\bshare price\b|\bstock picks?\b|\bstocks? to (?:buy|watch|sell)\b|\banalysts? (?:recommend|suggest|advise|like)\w*"
    r"|\b(?:buy|sell|hold|accumulate)\s+(?:rating|call|recommendation)\b|\btarget price\b|\b52[- ]week (?:high|low)\b"
    r"|\bDMAs?\b|\b(?:nifty|sensex)\b|\btop (?:gainers|losers)\b|\bcrash\w*\s+(?:nearly |over |about |around )?\d+(?:\.\d+)?\s?%"
    r"|\b(?:falls?|rises?|gains?|jumps?|surges?|slips?|drops?|slides?|tumbles?|slumps?|declines?)\s+(?:over |nearly |about )?\d+(?:\.\d+)?\s?%",
    re.IGNORECASE,
)
_RESULTS = re.compile(
    r"\bQ[1-4]\b[^.;]{0,25}\b(?:results?|earnings|profit|pat|revenue|loss|sales)\b"
    r"|\b(?:net |consolidated )?(?:profit|pat|income|revenue|sales|bookings?|earnings)\b[^.;]{0,25}\b" + _MOVES + r"\b"
    r"|\bposting (?:a )?loss\b|\bposts? (?:a )?(?:net )?loss\b|\bnet loss\b|\bloss (?:narrows|widens)\b"
    r"|\bearnings calls?\b|\bdividend\b|\bboard meeting\b|\bresults? (?:today|preview|date)\b",
    re.IGNORECASE,
)
# Sales / marketing wording on video and image posts (BHK walk-throughs, payment plans, "why is X so expensive").
PROMO_DOCUMENT_TYPES = ("youtube", "instagram")
_PROMO = re.compile(
    r"\b\d\s?bhk\b|\bpayment plan\b|\bpay \d+\s?%|\bsite visit\b|\bfly ?through\b|\bwalk ?through\b|\bpre-?launch\b|\bnew launch\b"
    r"|\bbook(?:ing)? now\b|\bprice list\b|\bluxury (?:apartments?|villas?|homes?|living)\b|\bso expensive\b"
    r"|\bwhy (?:is|are)\b[^?]{0,40}\b(?:expensive|costly|worth it)\b|\btruth about\b|\bworth (?:it|the (?:money|price))\b"
    r"|\bconcept film\b|\binvest in\b|\bhandover\b|\b\d{10}\b",
    re.IGNORECASE,
)
# Wording that keeps a title scoring normally even when it also mentions a share price or a result.
_KEEP_SCORING = re.compile(
    r"\b(?:probe|investigat\w+|allegations?|alleged|raids?|arrest\w*|scandal|bribe\w*|resign\w*|default\w*|insolvency|"
    r"bankruptcy|downgrade\w*|sebi|sfio|nclt|nclat|ncdrc|rera|penalt\w+|fined|fraud|scam|lawsuit|ransomware|breach|"
    r"hack\w*|forgery|cheating)\b",
    re.IGNORECASE,
)


def noise_cap_reason(title: Optional[str], document_type: Optional[str]) -> Optional[str]:
    """'market_move' | 'financial_results' | 'promotional' when this title is not a reputational event, else None.
    Any serious or keep-scoring term in the title wins: "Shares fall after SEBI probe" still scores."""
    if not title:
        return None
    if _KEEP_SCORING.search(title) or _SERIOUS.search(title) or _SERIOUS_ABBR.search(title):
        return None
    if _RESULTS.search(title):
        return "financial_results"
    if _MARKET.search(title):
        return "market_move"
    if document_type in PROMO_DOCUMENT_TYPES and _PROMO.search(title):
        return "promotional"
    return None


def _names_entity(title: str, entity_name: Optional[str]) -> bool:
    if not entity_name:
        return False
    t, n = title.lower(), entity_name.lower().strip()
    if n in t:
        return True
    first = n.split()[0] if n.split() else ""
    return len(first) >= 4 and first in t


def floor_enabled() -> bool:
    """Off unless RISK_FLOOR_ENABLED is set to 1/true/yes/on (read per call, so a restart-free flip is possible)."""
    return os.environ.get("RISK_FLOOR_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def serious_floor_applies(title: Optional[str], document_type: Optional[str], entity_sentiment: Optional[str],
                          role: Optional[str], entity_name: Optional[str], source_text: Optional[str] = None) -> bool:
    """`source_text` = the document's Source name + url. For Google News rows it is the feed ("Google News (history)"),
    not the outlet, so the outlet is read from the title suffix; the source text is checked too for direct feeds."""
    if not floor_enabled():
        return False
    if not title or document_type not in FLOOR_DOCUMENT_TYPES:
        return False
    if entity_sentiment == "Positive" or role in ("BYSTANDER", "EXONERATED"):
        return False
    low = f"{title} {source_text or ''}".lower()
    if any(o in low for o in FLOOR_EXCLUDED_OUTLETS):
        return False
    if not _names_entity(title, entity_name):
        return False
    if _MARKET.search(title) or _RESULTS.search(title) or _CHARGES_DROPPED.search(title):
        return False          # a share-price / results headline, or charges dropped: not what the floor is for
    return bool(_SERIOUS.search(title) or _SERIOUS_ABBR.search(title)) and not _EXCLUDE.search(title)
