"""Source reliability of a cited web page, by its domain.

Uses the platform's own outlet list (core/reach_trust_config.TRUSTED_OUTLETS: high / medium / low) and the outlets the risk
floor already excludes (Sprouts News, Inventiva). Everything else is explained, not guessed: official bodies, user-generated
sites, the company's own site, or "unrated" (an outlet the platform has no trust decision for).

`low_reliability` is True for: low (listed low, or an excluded outlet), user_generated (forums, review and social sites) and
unrated. It is a triage flag for people to look at, not a judgement about the content.
"""
import re
from typing import Optional
from urllib.parse import urlparse

from app.core.reach_trust_config import TRUSTED_OUTLETS
from app.services.intelligence.risk_floor import FLOOR_EXCLUDED_OUTLETS

LABELS = {
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "official": "Official",
    "own": "Company",
    "user_generated": "User-generated",
    "unrated": "Unrated",
}

# PROPOSED ratings for main Indian outlets the platform's own list (TRUSTED_OUTLETS) does not cover by domain, so they stop
# showing as "Unrated". These are NOT team decisions: every result built from them carries proposed=True and is labelled
# "(proposed)" until the team reviews them and moves them into TRUSTED_OUTLETS. Domain (and its sub-domains) -> tier.
PROPOSED_RATINGS = {
    "timesofindia.indiatimes.com": "medium",
    "thehindubusinessline.com": "medium",
    "financialexpress.com": "medium",
    "cnbctv18.com": "medium",
    "theprint.in": "medium",
    "inc42.com": "medium",
    "livelaw.in": "medium",
    "livelawbiz.com": "medium",
    "barandbench.com": "medium",
    "businesstoday.in": "medium",
    "indiatoday.in": "medium",
}

_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "nic", "ac", "edu"}
_OFFICIAL_HOSTS = ("nseindia.com", "bseindia.com", "sebi.gov.in", "rbi.org.in", "mca.gov.in")
_USER_GENERATED = {
    "quora", "reddit", "youtube", "youtu", "facebook", "instagram", "twitter", "x", "linkedin", "medium", "pinterest",
    "tumblr", "blogspot", "wordpress", "substack", "consumercomplaints", "mouthshut", "trustpilot", "glassdoor",
    "ambitionbox", "complaintsboard", "pissedconsumer",
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def domain_of(url: Optional[str]) -> Optional[str]:
    """Lower-case host without a leading www., or None when the text is not a URL."""
    if not url:
        return None
    host = (urlparse(url if "//" in url else "//" + url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _label_of(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in _SECOND_LEVEL and len(parts[-1]) == 2:
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else parts[0]


def classify_domain(domain: Optional[str], client_name: Optional[str] = None) -> dict:
    """{"tier", "label", "low_reliability", "proposed"} for a host. Order: official, the company's own site, user-generated,
    the platform's outlet list, the excluded outlets, then the PROPOSED ratings above; anything else is unrated. `proposed`
    is True when the tier comes from a proposal (or from a loose company-name match) and still needs team review."""
    host = (domain or "").lower()
    if not host:
        return _result("unrated")
    base = _label_of(host)
    flat = _norm(host)
    if host.endswith((".gov.in", ".nic.in", ".gov")) or any(host == h or host.endswith("." + h) for h in _OFFICIAL_HOSTS):
        return _result("official")
    cn = _norm(client_name or "")
    if cn and len(base) >= 6 and (base == cn or cn.startswith(base) or base.startswith(cn)):
        return _result("own")
    first_word = next((w for w in re.findall(r"[a-z0-9]+", (client_name or "").lower()) if len(w) >= 5), "")
    if first_word and base.startswith(first_word):          # e.g. godrejltd.com for Godrej Properties: the group's site
        return _result("own", proposed=True)
    if base in _USER_GENERATED:
        return _result("user_generated")
    for key, tier in TRUSTED_OUTLETS.items():
        nk = _norm(key)
        if nk == base or nk == flat or (("." in key) and host.endswith("." + key)):
            return _result(tier)
    if any(_norm(x) == base or _norm(x) in flat for x in FLOOR_EXCLUDED_OUTLETS):
        return _result("low")
    for key, tier in PROPOSED_RATINGS.items():
        if host == key or host.endswith("." + key):
            return _result(tier, proposed=True)
    return _result("unrated")


def _result(tier: str, proposed: bool = False) -> dict:
    label = LABELS[tier] + (" (proposed)" if proposed else "")
    return {"tier": tier, "label": label, "low_reliability": tier in ("low", "user_generated", "unrated"), "proposed": proposed}
