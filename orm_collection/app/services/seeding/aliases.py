"""
Alias policy for seeded entities.

- Multi-word aliases (two or more words) are accepted as proposed.
- A single-word alias is a "bare" alias. Single words that are generic (sector or corporate vocabulary) are rejected
  outright. Any other bare alias for a COMPETITOR is enabled only after a measurement on up to SAMPLE_DOCS sample
  documents: of the documents whose title/summary contain the alias, the share that name neither the full name nor a
  context term must be at most MAX_FALSE_RATE. The context rule is the backfill relevance filter's
  (services/backfill/relevance.py RelevanceRules: a bare alias counts only with a context term).
- A bare alias for a PERSON is always rejected (a first or last name alone is not an identity).
"""
import datetime as dt
from typing import Any, Callable, Dict, List, Optional

from app.services.backfill.relevance import RelevanceRules, DEFAULT_ALIAS_CONTEXT_TERMS, _norm

SAMPLE_DOCS = 50
MAX_FALSE_RATE = 0.10
MIN_SAMPLE_WITH_ALIAS = 20

GENERIC_WORDS = frozenset({
    "group", "groups", "india", "indian", "limited", "ltd", "company", "corp", "corporation", "inc", "industries",
    "enterprises", "holdings", "international", "global", "national", "bank", "travel", "trip", "tour", "tours",
    "realty", "real", "estate", "estates", "properties", "property", "developers", "developer", "infra",
    "infrastructure", "energy", "power", "ports", "port", "green", "trade", "trading", "capital", "finance",
    "financial", "services", "solutions", "systems", "tech", "technologies", "digital", "online", "express",
    "prestige", "premier", "royal", "star", "sun", "new", "first", "united", "universal", "general", "one", "the",
})


def tokens(s: str) -> List[str]:
    return [t for t in _norm(s).split() if t]


def is_bare(alias: str) -> bool:
    return len(alias.split()) < 2


def split_aliases(name: str, aliases: Any, kind: str) -> Dict[str, List[Dict[str, Any]]]:
    """Sort proposed aliases into accepted-as-is, needs-measurement and rejected, with a reason each.
    Returns {"accepted": [...], "to_measure": [...], "rejected": [...]} of {"alias", "reason"}."""
    out: Dict[str, List[Dict[str, Any]]] = {"accepted": [], "to_measure": [], "rejected": []}
    seen = {" ".join(tokens(name))}
    for raw in aliases or []:
        if not isinstance(raw, str):
            continue
        a = raw.strip()
        key = " ".join(tokens(a))
        if len(key) < 3 or key in seen:
            continue
        seen.add(key)
        if not is_bare(a):
            out["accepted"].append({"alias": a, "reason": "multi-word"})
        elif kind == "executive":
            out["rejected"].append({"alias": a, "reason": "single word for a person"})
        elif key in GENERIC_WORDS:
            out["rejected"].append({"alias": a, "reason": "generic single word"})
        else:
            out["to_measure"].append({"alias": a, "reason": "bare alias: needs the 50-document false-match measurement"})
    return out


def _entry_text(entry: Any) -> (str, str):
    get = entry.get if hasattr(entry, "get") else (lambda k, d=None: getattr(entry, k, d))
    return str(get("title", "") or ""), str(get("summary", "") or get("description", "") or get("content", "") or "")


def _default_fetch(query: str, start: dt.date, end: dt.date) -> List[Any]:
    from app.services.backfill.fetchers import fetch_google_news
    return fetch_google_news(query, start, end, {})


def measure_bare_alias(alias: str, name: str, context_terms: List[str], fetch: Optional[Callable] = None,
                       today: Optional[dt.date] = None, sample: int = SAMPLE_DOCS) -> Dict[str, Any]:
    """Fetch up to `sample` recent documents for the bare alias and count how many name neither the full name nor a
    context term. Free (Google News RSS)."""
    fetch = fetch or _default_fetch
    end = (today or dt.datetime.now(dt.timezone.utc).date()) + dt.timedelta(days=1)
    start = end - dt.timedelta(days=365)
    try:
        entries = list(fetch(f'"{alias}"', start, end))[:sample]
    except Exception as e:
        return {"alias": alias, "sample": 0, "with_alias": 0, "false_matches": 0, "false_rate": None,
                "enabled": False, "reason": f"measurement failed: {e!r}"[:200]}
    ctx = [_norm(c) for c in list(context_terms) + list(DEFAULT_ALIAS_CONTEXT_TERMS) if c]
    rules = RelevanceRules(full=[_norm(name)], bare=[_norm(alias)], context=ctx, exclude=[])
    alias_n = _norm(alias)
    with_alias = false = 0
    for e in entries:
        title, body = _entry_text(e)
        text = _norm(title) + _norm(body)
        if alias_n not in text:
            continue
        with_alias += 1
        if not rules.matches(title, body):
            false += 1
    rate = (false / with_alias) if with_alias else None
    enabled = bool(with_alias >= MIN_SAMPLE_WITH_ALIAS and rate is not None and rate <= MAX_FALSE_RATE)
    if with_alias < MIN_SAMPLE_WITH_ALIAS:
        why = f"only {with_alias} of {len(entries)} sample documents contain the alias (< {MIN_SAMPLE_WITH_ALIAS}); not enough to measure, left disabled"
    elif enabled:
        why = f"false-match rate {rate:.0%} <= {MAX_FALSE_RATE:.0%}"
    else:
        why = f"false-match rate {rate:.0%} > {MAX_FALSE_RATE:.0%}"
    return {"alias": alias, "sample": len(entries), "with_alias": with_alias, "false_matches": false,
            "false_rate": rate, "enabled": enabled, "reason": why}


def resolve_aliases(name: str, aliases: Any, kind: str, context_terms: List[str], measure: bool = True,
                    fetch: Optional[Callable] = None, today: Optional[dt.date] = None) -> List[Dict[str, Any]]:
    """Final alias list for one entity: [{"alias", "enabled", "reason", ...measurement fields}]."""
    parts = split_aliases(name, aliases, kind)
    out = [{"alias": a["alias"], "enabled": True, "reason": a["reason"]} for a in parts["accepted"]]
    out += [{"alias": a["alias"], "enabled": False, "reason": a["reason"]} for a in parts["rejected"]]
    for a in parts["to_measure"]:
        if measure:
            m = measure_bare_alias(a["alias"], name, context_terms, fetch, today)
            out.append({"alias": a["alias"], "enabled": m["enabled"], "reason": m["reason"],
                        "sample": m["sample"], "with_alias": m["with_alias"], "false_rate": m["false_rate"]})
        else:
            out.append({"alias": a["alias"], "enabled": False, "reason": a["reason"]})
    return out
