"""
Small-penalty rule: a `penalty_or_order` story that is small or old does not stay HIGH.

Applies only to items the case-status label (case_status.py) calls `penalty_or_order`, and only when CASE_STATUS_ENABLED is on.
Probe, charged, allegation, settled, dismissed and unrelated items never reach this code.

What is read from the headline and stored text (the documents hold only a headline and a short summary):
  * the largest rupee amount (regex: Rs / INR / the rupee sign, with lakh, crore, L, Cr, million, thousand);
  * the authority class (regex): senior = High Court, Supreme Court, SEBI, ED, CBI, NCLT/NCLAT, CCI; small = consumer
    commission/forum/court, any RERA (MahaRERA, CGRERA ...), municipal body (MCD, BMC, municipal corporation); else other/unknown;
  * criminal wording (FIR, arrest, chargesheet, cheating, fraud, laundering, IPC/BNS ...);
  * restricting wording: the order revokes or cancels a registration or licence, bans sales, bookings or advertising, or stops or
    halts a project or its construction. Such an order hurts the business whatever the money amount, so it is never capped.
Only when NO amount is found does one small Haiku call read the headline for amount, authority and the restricting question (cached in
the risk event).

Decision (score capped at the MEDIUM / HIGH boundary, 50.0, like the other case-status caps):
  keep today's rules  if the order has criminal charges, OR comes from a senior authority, OR the amount is 25 lakh or more,
                      OR the order revokes a registration, bans sales or stops a project (even when no rupee amount is found);
  cap                 else if the story is older than 24 months;
  cap                 else if the amount is under 25 lakh and the authority is not senior (consumer commission, state RERA and
                      municipal bodies, and also an authority the headline does not name: a sub-25-lakh order is small whoever
                      issued it);
  cap                 else if no amount was found but the authority is a small one (a refund or compensation order for one buyer);
  keep                otherwise (no amount and no recognised small authority).
"""
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from app.services.intelligence.case_status import MODEL, OPENROUTER_URL

SMALL_LAKH = 25.0                 # 25 lakh rupees
OLD_DAYS = 730                    # 24 months
UNIT_LAKH = {"crore": 100.0, "crores": 100.0, "cr": 100.0, "lakh": 1.0, "lakhs": 1.0, "lac": 1.0, "lacs": 1.0, "l": 1.0,
             "million": 10.0, "mn": 10.0, "thousand": 0.01, "k": 0.01}

_AMOUNT = re.compile(
    r"(?:₹|\brs\.?|\binr)\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(crores?|cr\b|lakhs?|lacs?|l\b|million|mn\b|thousand|k\b)?", re.IGNORECASE)
_AMOUNT_BARE = re.compile(r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s*(crores?|lakhs?|lacs?)\b", re.IGNORECASE)
_SENIOR = re.compile(r"\b(high court|supreme court|sebi|enforcement directorate|nclt|nclat|competition commission|cci)\b", re.IGNORECASE)
_SENIOR_ABBR = re.compile(r"\b(ED|CBI|HC|SC)\b")          # capitals only: never the words "ed", "hc", "sc"
_SMALL = re.compile(
    r"\b(consumer (?:commission|forum|court|disputes)|ncdrc|\w*rera|real estate regulatory authority|municipal\w*|civic body|mcd|bmc|pmc)\b",
    re.IGNORECASE)
# An order that revokes/cancels/suspends a registration or licence, bans sales/bookings/advertising, or stops/halts a project. Each
# alternative needs BOTH the action and the thing acted on within a short distance, so "registration" or "ban" alone never match.
_RESTRICT = re.compile(
    r"\b(?:(?:revok\w*|cancel\w*|suspend\w*|withdr[ae]w\w*|debar\w*)\b[^.;:|]{0,40}\b(?:registration|registrations|licen[cs]es?|rera registration)\b"
    r"|(?:registration|registrations|licen[cs]es?)\b[^.;:|]{0,50}\b(?:revoked|cancell?ed|suspended|withdrawn)\b"
    r"|(?:ban|bans|banned|banning|bars|barred|barring|prohibit\w*|restrain\w*)\b[^.;:|]{0,40}\b(?:sale|sales|selling|booking|bookings|advertis\w*|launch\w*|marketing)\b"
    r"|(?:stop|stops|stopped|stopping|halt\w*|freez\w*|stay\w*)[ -]?(?:work\b|order\b)"
    r"|(?:stop|stops|stopped|stopping|halt\w*|freez\w*|stalls?|stalled)\b[^.;:|]{0,40}\b(?:project|projects|construction|sales|work on)\b)", re.IGNORECASE)
_CRIMINAL = re.compile(
    r"\b(criminal|fir|arrest\w*|charge-?sheet\w*|cheating|fraud\w*|launder\w*|ipc|bns|conspiracy|prosecution|bribe\w*|forgery)\b", re.IGNORECASE)


def _to_lakh(num: str, unit: Optional[str]) -> Optional[float]:
    try:
        v = float(num.replace(",", ""))
    except ValueError:
        return None
    if unit:
        return v * UNIT_LAKH.get(unit.lower().rstrip("."), 1.0)
    return v / 100000.0                                         # plain rupees


def parse_amount_lakh(text: Optional[str]) -> Optional[float]:
    """The largest rupee amount in the text, in lakh; None when there is none."""
    t = text or ""
    found = [a for a in (_to_lakh(m.group(1), m.group(2)) for m in _AMOUNT.finditer(t)) if a is not None]
    found += [a for a in (_to_lakh(m.group(1), m.group(2)) for m in _AMOUNT_BARE.finditer(t)) if a is not None]
    return max(found) if found else None


def parse_authority_kind(text: Optional[str]) -> str:
    """'senior' | 'small' | 'unknown'. A senior authority wins when both appear (a High Court hearing a RERA appeal)."""
    t = text or ""
    if _SENIOR.search(t) or _SENIOR_ABBR.search(t):
        return "senior"
    if _SMALL.search(t):
        return "small"
    return "unknown"


def parse_penalty(title: Optional[str], content: Optional[str] = None) -> Dict[str, Any]:
    """Regex reading of the headline and stored text. {"amount_lakh", "kind", "criminal", "source": "regex"}."""
    text = " ".join(x for x in (title, content) if x)
    return {"amount_lakh": parse_amount_lakh(text), "kind": parse_authority_kind(text), "criminal": bool(_CRIMINAL.search(text)),
            "restricts": bool(_RESTRICT.search(text)), "source": "regex"}


def with_restricts(parse: Dict[str, Any], title: Optional[str], content: Optional[str] = None) -> Dict[str, Any]:
    """A reading cached before the restricting-order question existed has no "restricts" key: add the regex answer for it, so an
    old cached reading cannot hide a revocation or a stop-work order. A reading that already has the key is returned as it is."""
    if "restricts" in parse:
        return parse
    out = dict(parse)
    out["restricts"] = bool(_RESTRICT.search(" ".join(x for x in (title, content) if x)))
    return out


_LLM_SYSTEM = (
    "You read ONE news headline about a fine, penalty or order against a company in India. Answer two things.\n"
    "amount_lakh: the rupee amount of the penalty, refund or compensation in LAKH (1 crore = 100 lakh), or null if the headline gives no amount.\n"
    "authority: who issued it: consumer_commission (any consumer commission, forum or court), state_rera (any state RERA), municipal "
    "(a municipal or civic body), senior (High Court, Supreme Court, SEBI, ED, CBI, NCLT, NCLAT, CCI), other, or unknown.\n"
    "criminal: true if criminal charges are involved (FIR, arrest, chargesheet, cheating, fraud, money laundering), else false.\n"
    "restricts: true if the order revokes, cancels or suspends a registration or licence, bans sales, bookings or advertising, or stops "
    "or halts a project or its construction, whatever the money amount; else false.\n"
    "Use only the headline. Reply ONLY with JSON: {\"amount_lakh\": <number or null>, \"authority\": \"<one of the six>\", \"criminal\": true|false, "
    "\"restricts\": true|false}"
)
_LLM_KIND = {"consumer_commission": "small", "state_rera": "small", "municipal": "small", "senior": "senior", "other": "unknown", "unknown": "unknown"}


def parse_penalty_llm_text(text: Optional[str]) -> Optional[Dict[str, Any]]:
    """Regex reading of the model's answer (it wraps JSON in code fences). None when the authority cannot be read."""
    if not text:
        return None
    a = re.search(r'"?authority"?\s*:\s*"?([a-z_]+)', text, re.IGNORECASE)
    if not a or a.group(1).lower() not in _LLM_KIND:
        return None
    amt = re.search(r'"?amount_lakh"?\s*:\s*(null|-?[0-9]+(?:\.[0-9]+)?)', text, re.IGNORECASE)
    crim = re.search(r'"?criminal"?\s*:\s*(true|false)', text, re.IGNORECASE)
    amount = float(amt.group(1)) if amt and amt.group(1).lower() != "null" else None
    restr = re.search(r'"?restricts"?\s*:\s*(true|false)', text, re.IGNORECASE)
    return {"amount_lakh": amount, "kind": _LLM_KIND[a.group(1).lower()], "criminal": bool(crim and crim.group(1).lower() == "true"),
            "restricts": bool(restr and restr.group(1).lower() == "true"), "source": "llm"}


def classify_penalty_llm(title: Optional[str], api_key: Optional[str], post: Optional[Callable] = None,
                         timeout: float = 15.0) -> Optional[Dict[str, Any]]:
    """One Haiku call, headline only, used ONLY when the regex found no amount. None on any failure (= regex result stands)."""
    if not api_key or not title:
        return None
    if post is None:
        import requests
        post = requests.post
    t0 = time.perf_counter()
    try:
        resp = post(
            OPENROUTER_URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": [{"role": "system", "content": _LLM_SYSTEM}, {"role": "user", "content": f"Headline: {title[:500]}"}],
                  "temperature": 0, "max_tokens": 70, "usage": {"include": True}},
            timeout=timeout,
        )
        if getattr(resp, "status_code", 200) != 200:
            return None
        data = resp.json()
        parsed = parse_penalty_llm_text(data["choices"][0]["message"]["content"])
        if parsed is None:
            return None
        usage = data.get("usage") or {}
        parsed.update(prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"),
                      cost=usage.get("cost"), latency_ms=(time.perf_counter() - t0) * 1000)
        return parsed
    except Exception:
        return None


def merge_with_regex(regex_parse: Dict[str, Any], llm_parse: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The model's reading fills what the regex could not (amount, and an authority the regex left unknown); criminal wording
    seen by either keeps today's rules. A failed model call leaves the regex reading as it was."""
    if not llm_parse:
        return regex_parse
    merged = dict(regex_parse)
    merged["amount_lakh"] = llm_parse["amount_lakh"] if regex_parse["amount_lakh"] is None else regex_parse["amount_lakh"]
    if regex_parse["kind"] == "unknown":
        merged["kind"] = llm_parse["kind"]
    merged["criminal"] = bool(regex_parse["criminal"] or llm_parse["criminal"])
    merged["restricts"] = bool(regex_parse.get("restricts") or llm_parse.get("restricts"))
    merged["source"] = "regex+llm"
    return merged


def _age_days(published_at: Optional[datetime], now: Optional[datetime]) -> Optional[float]:
    if not isinstance(published_at, datetime):
        return None
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    return (now - published_at).total_seconds() / 86400.0


def penalty_cap_decision(parse: Dict[str, Any], published_at: Optional[datetime], now: Optional[datetime] = None) -> Tuple[bool, str]:
    """(cap, reason). See the module docstring for the rule."""
    amount, kind = parse.get("amount_lakh"), parse.get("kind", "unknown")
    if parse.get("criminal"):
        return False, "criminal charges are involved"
    if kind == "senior":
        return False, "issued by a High Court, the Supreme Court, SEBI, ED, CBI, NCLT or CCI"
    if parse.get("restricts"):
        return False, "the order revokes a registration, bans sales or stops a project"
    if amount is not None and amount >= SMALL_LAKH:
        return False, "the amount is 25 lakh rupees or more"
    age = _age_days(published_at, now)
    if age is not None and age > OLD_DAYS:
        return True, "the story is older than 24 months"
    if amount is not None:
        return True, "a penalty under 25 lakh rupees" + (" from a consumer commission, state RERA or municipal body" if kind == "small" else "")
    if kind == "small":
        return True, "an order from a consumer commission, state RERA or municipal body with no amount stated (a single-buyer order)"
    return False, "no amount found and no recognised small authority"
