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

# Outlets whose coverage never gets the floor (court-restrained for defamatory articles about the client).
FLOOR_EXCLUDED_OUTLETS = ("sprouts news",)

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
    r"settle\w*|settlement|resolve[sd]?|defamat\w*)\b|rera (?:received|ii)|\balleges\b|filed by|\bheld in\b",
    re.IGNORECASE,
)


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
    return bool(_SERIOUS.search(title) or _SERIOUS_ABBR.search(title)) and not _EXCLUDE.search(title)
