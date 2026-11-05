"""
One Claude Haiku 4.5 call per client, through OpenRouter with the web plugin (native Anthropic web search).

The call returns CANDIDATES in explicit role slots, not a final list: chairperson, MD/CEO, CFO, founders and
promoter-executives, up to 8 other management, a few independent/non-executive directors, and up to 8 competitor
candidates with their country, market footprint and parent company. The final top five of each is chosen by RULE in
service.build_plan (role order first, validated news count second), so a different candidate order or an extra name from
one call to the next does not change the chosen list.

If the web call fails (no key, HTTP error, unparsable answer, or no citations came back so the answer was not
web-grounded) this raises SeedingAborted. It never falls back to the plain model.
"""
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

MODEL = "anthropic/claude-haiku-4.5"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_EXECUTIVES = 5
MAX_COMPETITORS = 5
MAX_OTHER_MANAGEMENT = 8
MAX_DIRECTORS = 4
MAX_COMPETITOR_CANDIDATES = 8

# Order in which the slots fill the final list. Directors come after all management.
SLOT_ORDER = {"chairperson": 0, "md_ceo": 1, "cfo": 2, "founder": 3, "management": 4, "director": 5}

PROMPT = """Company: "{name}"{extra}

Using web search, return the company's current leadership and its closest competitors as ONLY a JSON object:
{{
  "company": {{"website": "", "primary_market": "", "parent_company": "", "group_companies": []}},
  "executives": {{
    "chairperson": {{"name": "", "role": "", "aliases": [], "source_urls": []}},
    "md_ceo": {{"name": "", "role": "", "aliases": [], "source_urls": []}},
    "cfo": {{"name": "", "role": "", "aliases": [], "source_urls": []}},
    "founders": [{{"name": "", "role": "", "aliases": [], "source_urls": []}}],
    "other_management": [{{"name": "", "role": "", "aliases": [], "source_urls": []}}],
    "directors": [{{"name": "", "role": "", "aliases": [], "source_urls": []}}]
  }},
  "competitors": [{{"name": "", "reason": "", "aliases": [], "context_term": "", "hq_country": "", "india_operations": "primary|minor|none",
                   "parent_company": "", "subsidiaries": [], "source_urls": []}}]
}}
Rules:
- company: official website (home page URL), the market where it earns most of its revenue (primary_market, a country), its parent
  company if any, and its sister/group companies.
- executives: fill each slot with the person who CURRENTLY holds it at this company or its parent group; use null for a slot you
  cannot support. chairperson = chair of the board (or the group chairperson). md_ceo = managing director and/or CEO. cfo = chief
  financial officer. founders = founders and promoter-family members who hold an executive role. other_management = up to {max_mgmt}
  other named senior executives (not board members who are not executives). directors = up to {max_dir} independent or non-executive
  directors, listed last. Give each person at least one source URL for a page that names them (the company's own site, an
  exchange filing, or a news article). Do not invent anyone.
- competitors: up to {max_comp} closest direct competitors in the same sector at the SAME corporate level as the company
  (group-level for a group, company-level for a company); for a listed company, the listed peers analysts compare it with. Never a
  subsidiary, parent, sister or group company of "{name}". Real companies only, never products, places or media. hq_country = where it is
  headquartered; india_operations = whether its main business is in the company's primary market ("primary") or only a minor
  presence ("minor"/"none"); parent_company and subsidiaries as known; context_term = a short sector phrase of at most three
  words (for example "real estate", "online travel"); at least one source URL.
- aliases: other spellings or short forms for the same person or company; leave empty if unsure."""


class SeedingAborted(Exception):
    """The seeding call could not be completed on the web-grounded route; nothing was written."""


def build_prompt(company_name: str, domain: Optional[str] = None, industry: Optional[str] = None) -> str:
    bits = [b for b in (f"website {domain}" if domain else None, f"industry {industry}" if industry else None) if b]
    extra = f" ({', '.join(bits)})" if bits else ""
    return PROMPT.format(name=company_name, extra=extra, max_mgmt=MAX_OTHER_MANAGEMENT, max_dir=MAX_DIRECTORS,
                         max_comp=MAX_COMPETITOR_CANDIDATES)


def _parse_json(text: str) -> Dict[str, Any]:
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start < 0 or end <= start:
        raise SeedingAborted("answer contained no JSON object")
    try:
        return json.loads(t[start:end + 1])
    except ValueError as e:
        raise SeedingAborted(f"answer JSON did not parse: {e}")


def _person(p: Any, slot: str) -> Optional[Dict[str, Any]]:
    if not isinstance(p, dict) or not (p.get("name") or "").strip():
        return None
    out = dict(p)
    out["name"] = p["name"].strip()
    out["slot"] = slot
    return out


def flatten_executives(raw: Any) -> List[Dict[str, Any]]:
    """Slot dict -> flat candidate list in slot order (a flat list from an older or replayed proposal passes through; a
    person without a slot is 'management')."""
    if isinstance(raw, list):
        return [x for x in (_person(p, p.get("slot", "management") if isinstance(p, dict) else "management") for p in raw) if x]
    raw = raw or {}
    out: List[Dict[str, Any]] = []
    for key in ("chairperson", "md_ceo", "cfo"):
        p = _person(raw.get(key), key)
        if p:
            out.append(p)
    for key, slot, cap in (("founders", "founder", 4), ("other_management", "management", MAX_OTHER_MANAGEMENT),
                           ("directors", "director", MAX_DIRECTORS)):
        for p in (raw.get(key) or [])[:cap]:
            q = _person(p, slot)
            if q:
                out.append(q)
    seen, uniq = set(), []
    for p in out:                      # the same person in two slots counts once, in the earlier (more senior) slot
        k = " ".join(re.findall(r"[a-z0-9]+", p["name"].lower()))
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


# The executive slots that must not stay empty after the pooled answers.
REQUIRED_SLOTS = ("chairperson", "md_ceo", "cfo", "founder")

FOLLOW_UP_PROMPT = """Company: "{name}"

Using web search, answer ONLY with a JSON object. This is a small follow-up to an earlier answer; do ONLY what is asked below.
{asks}
Shape (leave out any key that was not asked about):
{{
  "executives": {{{exec_shape}}},
  "competitors": [{{"name": "", "reason": "", "aliases": [], "context_term": "", "hq_country": "", "india_operations": "primary|minor|none",
                   "parent_company": "", "subsidiaries": [], "source_urls": []}}],
  "ownership_evidence": [{{"candidate": "", "child": "", "parent": "", "still_owned": true, "source_urls": []}}],
  "listing": [{{"name": "", "exchange_listed": true, "ticker": ""}}]
}}
Rules: a person is {{"name": "", "role": "", "aliases": [], "source_urls": []}} with at least one source URL for a page that names them
(the company's own site, an exchange filing, or a news article); use null for a slot you cannot support; do not invent anyone.
Slot meanings: chairperson = chair of the board (or the group chairperson); md_ceo = managing director and/or CEO; cfo = chief
financial officer; founder = a founder or promoter-family member who holds an executive role."""


def missing_slots(pool: Dict[str, Any]) -> List[str]:
    have = {e.get("slot") for e in flatten_executives(pool.get("executives"))}
    return [s_ for s_ in REQUIRED_SLOTS if s_ not in have]


def build_follow_up_prompt(company_name: str, slots: List[str], tracked: List[str], claims: Optional[List[Dict[str, str]]] = None,
                           listing: Optional[List[str]] = None) -> str:
    asks = []
    if slots:
        asks.append(f'1. Fill ONLY these executive slots (leave every other slot out): {", ".join(slots)}.')
    if tracked:
        asks.append(f'2. Describe these competitors the company already tracks, one entry each (where each is headquartered, whether its main business '
                    f'is in the company\'s primary market, its parent company and subsidiaries, a short sector phrase of at most three words as '
                    f'context_term, a source URL), even if you would not rank them: {"; ".join(tracked)}.')
    if claims:
        lines = "; ".join(f'{c["child"]} is owned by {c["parent"]} (said about {c["candidate"]})' for c in claims)
        asks.append("3. For each ownership claim below give the URL of ONE fetchable HTML page (not a PDF) that states it in words such as "
                    "'subsidiary of', 'owned by', 'acquired by' or 'wholly owned'. Prefer Wikipedia, the company's own site or a news article; do NOT "
                    "give sec.gov / EDGAR links (they cannot be fetched). If the claim is not true today (for example the stake was sold, or "
                    f"it never held one) set still_owned to false. Claims: {lines}.")
    if listing:
        asks.append("4. For each of these companies say whether it is CURRENTLY listed on NSE or BSE (exchange_listed true or false) and give its "
                    f'ticker: {"; ".join(listing)}.')
    shape = ", ".join(f'"{x}": {{"name": "", "role": "", "aliases": [], "source_urls": []}}' for x in slots)
    return FOLLOW_UP_PROMPT.format(name=company_name, asks="\n".join(asks) or "Nothing is asked.", exec_shape=shape)


def follow_up(company_name: str, slots: List[str], tracked: List[str], post: Optional[Callable] = None,
              api_key: Optional[str] = None, claims: Optional[List[Dict[str, str]]] = None,
              listing: Optional[List[str]] = None) -> Dict[str, Any]:
    """ONE small web call: fills only the empty required slots, describes the client's already-tracked competitors, asks for a page that
    states each ownership claim in the pool, and for each pooled competitor's exchange-listing status."""
    out = propose(company_name, post=post, api_key=api_key, max_tokens=3500,
                  prompt=build_follow_up_prompt(company_name, slots, tracked, claims, listing))
    return out


RETRY_PROMPT = """Company: "{name}"

Using web search, answer ONLY with a JSON object {{"people": [{{"name": "", "role": "", "source_urls": []}}]}}.
These people were not verifiable from the pages given earlier: {people}.
For each, give up to 3 URLs of pages where the person's FULL NAME appears next to their role title: prefer fetchable HTML pages (the company's
own site, BSE or NSE pages), or a BSE/NSE earnings-call transcript or filing for the company. Do not give a PDF over 5 MB, an annual report
or any page that does not show the name with the role. Do not invent anyone."""


def source_retry(company_name: str, people: List[Dict[str, str]], post: Optional[Callable] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
    """ONE retry call for executives with 1-2 news items whose only citations could not be read: asks for readable pages or a BSE/NSE
    transcript. Returns a proposal whose executives carry slot "retry" (they only add source URLs to the same person)."""
    listing = "; ".join(f'{p["name"]} ({p.get("role") or "role unknown"})' for p in people)
    out = propose(company_name, post=post, api_key=api_key, max_tokens=1500, prompt=RETRY_PROMPT.format(name=company_name, people=listing))
    out["executives"] = [{**p, "slot": "retry", "name": (p.get("name") or "").strip()} for p in out.get("people", []) if (p.get("name") or "").strip()]
    return out


def merge_proposals(proposals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Union of the candidates from several answers, so one answer leaving out a person or a peer does not change the chosen list.
    Executives merge by person (the most senior slot wins, source URLs and aliases are pooled); competitors merge by company
    (validator.same_company; any parent/subsidiary/HQ detail that one answer gave is kept); the company block takes the first
    non-empty value of each field. Costs add up."""
    from app.services.seeding.validator import same_company
    if len(proposals) == 1:
        return proposals[0]
    company: Dict[str, Any] = {}
    for p in proposals:
        for k, v in (p.get("company") or {}).items():
            if v and not company.get(k):
                company[k] = v
    execs: List[Dict[str, Any]] = []
    for p in proposals:
        for e in flatten_executives(p.get("executives")):
            key = " ".join(re.findall(r"[a-z0-9]+", e["name"].lower()))
            hit = next((x for x in execs if " ".join(re.findall(r"[a-z0-9]+", x["name"].lower())) == key), None)
            if hit is None:
                execs.append({**e, "source_urls": list(e.get("source_urls") or []), "aliases": list(e.get("aliases") or [])})
                continue
            if SLOT_ORDER.get(e["slot"], 9) < SLOT_ORDER.get(hit["slot"], 9):
                hit["slot"], hit["role"] = e["slot"], e.get("role") or hit.get("role")
            hit["source_urls"] = list(dict.fromkeys(hit["source_urls"] + list(e.get("source_urls") or [])))
            hit["aliases"] = list(dict.fromkeys(hit["aliases"] + list(e.get("aliases") or [])))
    comps: List[Dict[str, Any]] = []
    for p in proposals:
        counted = set()                        # a company named twice in ONE answer (Brigade Group / Brigade Enterprises) counts once
        for pos, c in enumerate(p.get("competitors") or [], start=1):
            # agreement data: how many answers name the company and at what position (1 = first) each one lists it. An entry that
            # is itself the result of an earlier merge already carries its own counters.
            seen = c.get("seen_in") if c.get("seen_in") is not None else 1
            positions = list(c.get("positions") or [pos])
            hit = next((x for x in comps if same_company(x["name"], c["name"])), None)
            if hit is None:
                comps.append({**c, "source_urls": list(c.get("source_urls") or []), "aliases": list(c.get("aliases") or []),
                              "subsidiaries": list(c.get("subsidiaries") or []), "seen_in": seen, "positions": positions})
                counted.add(len(comps) - 1)
                continue
            idx = comps.index(hit)
            if idx not in counted or c.get("seen_in") is not None:
                hit["seen_in"] = (hit.get("seen_in") or 0) + seen
                hit["positions"] = list(hit.get("positions") or []) + positions
                counted.add(idx)
            for k in ("parent_company", "hq_country", "context_term", "india_operations", "reason"):
                if not hit.get(k) and c.get(k):
                    hit[k] = c[k]
            for k in ("source_urls", "aliases", "subsidiaries"):
                hit[k] = list(dict.fromkeys(list(hit.get(k) or []) + list(c.get(k) or [])))
    evidence = [e for p in proposals for e in (p.get("ownership_evidence") or []) if isinstance(e, dict)]
    for p in proposals:                       # exchange-listing answers apply to the pooled competitor of the same company
        for row in p.get("listing") or []:
            if not isinstance(row, dict) or "exchange_listed" not in row:
                continue
            for c in comps:
                if same_company(c["name"], row.get("name") or ""):
                    c["exchange_listed"] = bool(row["exchange_listed"])
                    c["ticker"] = row.get("ticker") or c.get("ticker")
    costs = [p.get("cost_usd") for p in proposals if p.get("cost_usd") is not None]
    return {"company": company, "executives": execs, "competitors": comps, "cost_usd": sum(costs) if costs else None,
            "citations": [u for p in proposals for u in p.get("citations", [])], "model": proposals[0].get("model"), "calls": len(proposals),
            "ownership_evidence": evidence}


def propose_multi(company_name: str, domain: Optional[str] = None, industry: Optional[str] = None, calls: int = 2,
                  post: Optional[Callable] = None, api_key: Optional[str] = None,
                  tracked_competitors: Optional[List[str]] = None) -> Dict[str, Any]:
    """`calls` independent web-grounded answers merged into one candidate pool (default 2, about $0.05 per client), then ONE small
    follow-up call (about $0.015) that: fills an empty chairperson / MD-CEO / CFO / founder slot, describes the client's already-tracked
    competitors the pool lacks, asks for a page that states each ownership claim in the pool, and asks whether each pooled competitor is
    exchange-listed. There is no third pooled call. Any failed call aborts the whole seeding (SeedingAborted); there is no fallback to
    the plain model."""
    from app.services.seeding.validator import same_company, pool_ownership_claims
    pool = merge_proposals([propose(company_name, domain, industry, post=post, api_key=api_key) for _ in range(max(1, calls))])
    tracked = [n for n in (tracked_competitors or []) if n and not any(same_company(n, c["name"]) for c in pool["competitors"])]
    slots = missing_slots(pool)
    claims = pool_ownership_claims(company_name, pool.get("company"), pool["competitors"])
    listing = [c["name"] for c in pool["competitors"] if "exchange_listed" not in c]
    if slots or tracked or claims or listing:
        fu = follow_up(company_name, slots, tracked, post=post, api_key=api_key, claims=claims, listing=listing)
        pool = merge_proposals([pool, fu])
        pool["calls"] = max(1, calls) + 1
        pool["follow_up"] = {"slots": slots, "tracked_competitors": tracked, "ownership_claims": len(claims), "listing_asked": len(listing)}
    return pool


def propose(company_name: str, domain: Optional[str] = None, industry: Optional[str] = None,
            post: Optional[Callable] = None, api_key: Optional[str] = None, prompt: Optional[str] = None,
            max_tokens: int = 4000) -> Dict[str, Any]:
    """Returns {"company": {...}, "executives": [candidates with a slot], "competitors": [candidates], "cost_usd", "citations", "model"}."""
    key = api_key or os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SeedingAborted("OPENROUTER_API_KEY is not set")
    if post is None:
        import requests
        post = requests.post
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt or build_prompt(company_name, domain, industry)}],
        "max_tokens": max_tokens,
        "temperature": 0,
        "usage": {"include": True},
        "plugins": [{"id": "web", "max_results": 5}],
    }
    try:
        resp = post(OPENROUTER_URL, headers={"Authorization": "Bearer " + key}, json=body, timeout=120)
    except Exception as e:
        raise SeedingAborted(f"web call failed: {e!r}"[:300])
    if getattr(resp, "status_code", 200) != 200:
        raise SeedingAborted(f"web call returned HTTP {resp.status_code}: {str(getattr(resp, 'text', ''))[:200]}")
    try:
        data = resp.json()
        message = data["choices"][0]["message"]
    except Exception as e:
        raise SeedingAborted(f"web call response was malformed: {e!r}"[:300])
    citations = []
    for a in message.get("annotations") or []:
        url = ((a or {}).get("url_citation") or {}).get("url") or (a or {}).get("url")
        if url:
            citations.append(url)
    if not citations:
        raise SeedingAborted("no web citations came back, so the answer was not web-grounded (not falling back to the plain model)")
    parsed = _parse_json(message.get("content") or "")
    comps = [c for c in (parsed.get("competitors") or []) if isinstance(c, dict) and (c.get("name") or "").strip()]
    cost = (data.get("usage") or {}).get("cost")
    company = parsed.get("company") if isinstance(parsed.get("company"), dict) else {}
    return {
        "company": company,
        "executives": flatten_executives(parsed.get("executives")),
        "competitors": comps[:MAX_COMPETITOR_CANDIDATES],
        "cost_usd": float(cost) if isinstance(cost, (int, float)) else None,
        "citations": citations,
        "model": MODEL,
        "ownership_evidence": [e for e in (parsed.get("ownership_evidence") or []) if isinstance(e, dict)],
        "listing": [e for e in (parsed.get("listing") or []) if isinstance(e, dict)],
        "people": [e for e in (parsed.get("people") or []) if isinstance(e, dict)],
    }
