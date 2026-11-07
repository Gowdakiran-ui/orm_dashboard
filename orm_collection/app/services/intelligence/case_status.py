"""
Case-status label for legal / regulatory risk items, and the severity rule that uses it.

One cheap LLM call per (document, entity), headline only (Claude Haiku 4.5 through OpenRouter, temperature 0), cached in the
risk event's own explainability JSON (no schema change), run inside the risk stage after the SELF / BYSTANDER / EXONERATED role
gate. The same call also returns a short English `event` phrase naming who did what; incidents.py uses it to recognise the
same story across outlets and languages.

Severity rule (nothing else about the score changes): `unrelated`, `dismissed_or_closed` and `settled` never reach HIGH, i.e.
the score is capped at the MEDIUM / HIGH boundary. `allegation`, `probe`, `charged` and `penalty_or_order` keep today's score.

OFF by default: set CASE_STATUS_ENABLED=1 to turn it on, so deploying the code changes no score and makes no LLM call.
Any failure (no key, HTTP error, unparsable answer) returns None, which means "no change to today's scoring".
"""
import os
import re
import time
from typing import Any, Callable, Dict, Optional, Tuple

from app.core.risk_config import RISK_THRESHOLDS

MODEL = "anthropic/claude-haiku-4.5"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

STATUSES = ("allegation", "probe", "charged", "penalty_or_order", "settled", "dismissed_or_closed", "unrelated")
# These three never reach HIGH. The cap is the MEDIUM / HIGH boundary itself (a score of exactly 50.0 is MEDIUM).
CAPPED_STATUSES = ("unrelated", "dismissed_or_closed", "settled")
STATUS_CAP_SCORE = float(RISK_THRESHOLDS["MEDIUM_TO_HIGH"])

STATUS_LABELS = {
    "allegation": "Allegation",
    "probe": "Probe",
    "charged": "Charged",
    "penalty_or_order": "Penalty / order",
    "settled": "Settled",
    "dismissed_or_closed": "Dismissed / closed",
    "unrelated": "Unrelated",
}

SYSTEM_PROMPT = (
    "You label ONE news headline about a company for reputation-risk triage. Choose exactly one status for the "
    "legal or regulatory situation the headline reports about the named company or its people:\n"
    "allegation = a claim, complaint or accusation, no authority action yet\n"
    "probe = investigation, raid, search, FIR, notice or inquiry under way, nothing formally charged\n"
    "charged = formal charges, chargesheet, indictment or a case filed by an authority\n"
    "settled = settled or consent order with a regulator or authority, case ended by payment\n"
    "dismissed_or_closed = case dropped, dismissed, cleared, closed or exonerated\n"
    "penalty_or_order = a fine, penalty, refund or adverse court/regulator/commission order\n"
    "unrelated = no legal or regulatory event about the company (markets, business deals, brand, explainers, "
    "approvals in the company's favour)\n"
    "Also give \"event\": 3 to 7 lowercase English words saying who did what (for example \"ed chargesheet nishant pitti "
    "mahadev betting\"). Leave out outlet names, numbers of crores and filler words. The same story must get the same "
    "words whatever the language or outlet of the headline.\n"
    "Use only the headline. Reply ONLY with JSON: {\"status\": \"<one of the seven>\", \"event\": \"<words>\"}"
)

_STATUS_RE = re.compile(r'"?status"?\s*[:=]\s*"?\s*([a-z_]+)\s*"?\s*(?:[,}\n]|$)', re.IGNORECASE)
_EVENT_RE = re.compile(r'"?event"?\s*[:=]\s*"([^"\n]{0,120})"', re.IGNORECASE)


def case_status_enabled() -> bool:
    """Off unless CASE_STATUS_ENABLED is 1/true/yes/on (read per call)."""
    return os.environ.get("CASE_STATUS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def parse_case_status(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(status, event) from the model's text. Regex, not strict JSON: the model wraps its answer in code fences.
    status is None unless it is one of the seven labels; event is None when absent."""
    if not text:
        return None, None
    m = _STATUS_RE.search(text)
    status = m.group(1).strip().lower() if m else None
    if status not in STATUSES:
        status = None
    e = _EVENT_RE.search(text)
    event = re.sub(r"\s+", " ", e.group(1)).strip().lower() if e else None
    return status, (event or None)


def apply_status_cap(score: float, status: Optional[str]) -> Tuple[float, bool]:
    """(score, capped). Only a status in CAPPED_STATUSES lowers a score, and only one above the MEDIUM / HIGH boundary."""
    if status in CAPPED_STATUSES and score > STATUS_CAP_SCORE:
        return STATUS_CAP_SCORE, True
    return score, False


def cached_case_status(explainability: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The stored LLM label of an earlier run (documents never change after insert), or None."""
    expl = explainability or {}
    if expl.get("case_status_source") == "llm" and expl.get("case_status") in STATUSES:
        return {"status": expl["case_status"], "event": expl.get("case_event")}
    return None


def classify_case_status(title: Optional[str], entity_name: str, api_key: Optional[str],
                         post: Optional[Callable] = None, timeout: float = 15.0) -> Optional[Dict[str, Any]]:
    """{"status", "event", "prompt_tokens", "completion_tokens", "cost", "latency_ms"} or None on ANY failure."""
    if not api_key or not title:
        return None
    if post is None:
        import requests
        post = requests.post
    t0 = time.perf_counter()
    try:
        resp = post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Company: {entity_name}\nHeadline: {title[:500]}"},
                ],
                "temperature": 0,
                "max_tokens": 80,
                "usage": {"include": True},
            },
            timeout=timeout,
        )
        if getattr(resp, "status_code", 200) != 200:
            return None
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        status, event = parse_case_status(content)
        if status is None:
            return None
        usage = data.get("usage") or {}
        return {
            "status": status,
            "event": event,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cost": usage.get("cost"),
            "latency_ms": (time.perf_counter() - t0) * 1000,
        }
    except Exception:
        return None
