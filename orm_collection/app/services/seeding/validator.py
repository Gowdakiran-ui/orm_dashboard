"""
Validation of proposed names. Free sources only (Google News RSS counts).

Executive: needs a source URL AND at least one Google News item over 24 months for "Name" "Company"; with 3 or more items
it is accepted, with 1 or 2 the name must also be found on a cited page that is fetched. No news item: needs_review,
whatever the sources say. (A PDF cannot be read without a PDF library, so a PDF does not verify a name.)
Competitor: must be a real peer (not the client's parent, subsidiary, sister or group company, and not a subsidiary of another
candidate), must operate mainly in the client's primary market, and must have a sector-consistent Google News count of
"Name" + context words over 24 months of at least COMP_MIN_COUNT. The final five are chosen by that count (service.build_plan).
Anything else is needs_review.
"""
import datetime as dt
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

EXEC_MIN_PAIR_COUNT = 3
EXEC_MIN_ANY_NEWS = 1
COMP_MIN_COUNT = 20
WINDOW_MONTHS = 24
SLICE_MONTHS = 6
EXCHANGE_DOMAINS = ("nseindia.com", "bseindia.com", "sebi.gov.in", "sec.gov")
# PDFs are read only from the company's own domain and NSE/BSE, with hard limits (pypdf).
PDF_HOSTS = ("nseindia.com", "bseindia.com")
PDF_MAX_BYTES = 5 * 1024 * 1024
PDF_MAX_PAGES = 10
PDF_TIMEOUT_SECONDS = 20


def _add_months(d: dt.date, months: int) -> dt.date:
    y, m = divmod(d.year * 12 + (d.month - 1) + months, 12)
    return dt.date(y, m + 1, min(d.day, 28))


def slices(today: Optional[dt.date] = None, months: int = WINDOW_MONTHS, step: int = SLICE_MONTHS):
    """Oldest-first list of (start, end) 6-month slices covering the last 24 months (Google News after:/before:)."""
    end = (today or dt.datetime.now(dt.timezone.utc).date()) + dt.timedelta(days=1)
    out = []
    for i in range(months // step, 0, -1):
        out.append((_add_months(end, -i * step), _add_months(end, -(i - 1) * step)))
    return out


def _default_fetch(query: str, start: dt.date, end: dt.date) -> List[Any]:
    from app.services.backfill.fetchers import fetch_google_news
    return fetch_google_news(query, start, end, {})


def gn_count(query: str, fetch: Optional[Callable] = None, today: Optional[dt.date] = None) -> Dict[str, Any]:
    """Google News item count for an exact-phrase query over the last 24 months, in 6-month slices.
    A slice returns at most 100 items, so `capped` marks a lower bound."""
    fetch = fetch or _default_fetch
    per, errors = [], 0
    for a, b in slices(today):
        try:
            per.append(len(fetch(query, a, b)))
        except Exception:
            per.append(0)
            errors += 1
    return {"total": sum(per), "per_slice": per, "capped": any(n >= 100 for n in per), "errors": errors}


def _q(s: str) -> str:
    return '"' + s.replace('"', " ").strip() + '"'


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().lstrip(".")
    except Exception:
        return ""


def _label(host: str) -> str:
    """Registrable name of a host: "www.godrejproperties.com" -> "godrejproperties" (last two labels, minus the TLD)."""
    parts = [p for p in host.split(".") if p]
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "net", "gov", "ac"):
        return parts[-3]
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")


def registrable_domain(host: str) -> str:
    """"news.example.co.uk" -> "example.co.uk"; "www.example.com" -> "example.com" (two pages are independent only on different ones)."""
    parts = [p for p in (host or "").split(".") if p]
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in ("co", "com", "org", "net", "gov", "ac"):
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else (host or "")


def domain_matches_company(host: str, company: Optional[str]) -> bool:
    """True when the host's registrable name IS the company's name ("godrejproperties.com" for "Godrej Properties",
    "adani.com" for "Adani Group", "easemytrip.com" for "EaseMyTrip"). Used only when no website is configured for the
    client; a configured Entity.domain / website is authoritative and is passed in as `company_domains`."""
    if not company:
        return False
    label = _label(host)
    words = _words(company)
    if not label or not words:
        return False
    return label == "".join(words) or (len(words[0]) >= 5 and label == words[0])


def is_official_source(url: str, company_domains: List[str], company: Optional[str] = None) -> bool:
    h = host_of(url)
    if not h:
        return False
    for d in list(company_domains) + list(EXCHANGE_DOMAINS):
        d = (d or "").lower().strip().lstrip(".")
        if d and (h == d or h.endswith("." + d)):
            return True
    return domain_matches_company(h, company)


def clean_urls(urls: Any) -> List[str]:
    out = []
    for u in urls or []:
        if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in out:
            out.append(u)
    return out


def is_pdf_url(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")


def pdf_allowed(url: str, company_domains: List[str], company: Optional[str] = None) -> bool:
    """A PDF is opened only when it is on the company's own domain or on NSE/BSE."""
    h = host_of(url)
    if not h:
        return False
    for d in list(company_domains) + list(PDF_HOSTS):
        d = (d or "").lower().strip().lstrip(".")
        if d and (h == d or h.endswith("." + d)):
            return True
    return domain_matches_company(h, company)


def fetch_pdf_text(url: str, get: Optional[Callable] = None, timeout: int = PDF_TIMEOUT_SECONDS,
                   max_bytes: int = PDF_MAX_BYTES, max_pages: int = PDF_MAX_PAGES) -> Optional[str]:
    """Text of the first `max_pages` pages of a PDF, or None when it cannot be read: over `max_bytes` (declared or actual),
    slow (overall `timeout`), an HTTP error, not a PDF, encrypted or unparsable. Never raises."""
    import time
    try:
        if get is None:
            import requests
            get = requests.get
        t0 = time.monotonic()
        r = get(url, timeout=timeout, stream=True, headers={"User-Agent": "Mozilla/5.0 (compatible; xoop-seeding-check)"})
        if getattr(r, "status_code", 200) >= 400:
            return None
        declared = (getattr(r, "headers", {}) or {}).get("content-length")
        if declared and str(declared).isdigit() and int(declared) > max_bytes:
            return None
        body = b""
        if hasattr(r, "iter_content"):
            for chunk in r.iter_content(65536):
                body += chunk
                if len(body) > max_bytes or time.monotonic() - t0 > timeout:
                    return None
        else:
            body = getattr(r, "content", b"") or b""
            if len(body) > max_bytes:
                return None
        if not body.startswith(b"%PDF"):
            return None
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(body))
        if getattr(reader, "is_encrypted", False):
            return None
        out = []
        for page in list(reader.pages)[:max_pages]:
            out.append(page.extract_text() or "")
            if time.monotonic() - t0 > timeout:
                break
        return " ".join(out)
    except Exception:
        return None


def fetch_page_text(url: str, get: Optional[Callable] = None, timeout: int = 15, max_chars: int = 400000,
                    allow_pdf: bool = False) -> Optional[str]:
    """Visible text of a cited page, or None when it cannot be fetched or read. A PDF is read (first 10 pages, 5 MB cap) only when
    `allow_pdf` is true, which the caller sets for the company's own domain and NSE/BSE only."""
    if is_pdf_url(url):
        return fetch_pdf_text(url, get) if allow_pdf else None
    try:
        if get is None:
            import requests
            get = requests.get
        r = get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (compatible; xoop-seeding-check)"})
        if getattr(r, "status_code", 200) >= 400:
            return None
        if "pdf" in str(getattr(r, "headers", {}).get("content-type", "")).lower():
            return fetch_pdf_text(url, get) if allow_pdf else None
        html = r.text[:max_chars * 3]
    except Exception:
        return None
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html.parser").get_text(" ")[:max_chars]
    except Exception:
        import re
        return re.sub(r"<[^>]+>", " ", html)[:max_chars]


def page_names_person(url: str, name: str, fetch_text: Optional[Callable] = None) -> bool:
    """True when the full name (case and punctuation ignored) is on the page."""
    text = (fetch_text or fetch_page_text)(url)
    if not text:
        return False
    import re
    norm = lambda t: " " + " ".join(re.findall(r"[a-z0-9]+", (t or "").lower())) + " "     # noqa: E731
    return norm(name) in norm(text)


def verification_method(url: str, company_domains: List[str], company: Optional[str]) -> str:
    """How a name was confirmed by a fetched page: PDF / exchange filing / company page / cited page."""
    h = host_of(url)
    exchange = any(h == d or h.endswith("." + d) for d in EXCHANGE_DOMAINS)
    if is_pdf_url(url):
        return "PDF (exchange filing)" if exchange else "PDF (company domain)"
    if exchange:
        return "exchange filing"
    if is_official_source(url, company_domains, company):
        return "company page"
    return "cited page"


_ROLE_SYNONYMS = {
    "chairperson": ["chairperson", "chairman", "chairwoman", "chair of the board"],
    "md_ceo": ["managing director", "chief executive officer", "ceo", "md ceo", "md and ceo"],
    "cfo": ["chief financial officer", "cfo", "finance director", "director finance"],
    "founder": ["founder", "co founder", "cofounder", "promoter"],
}
_ROLE_STOP = frozenset({"limited", "company", "group", "senior", "executive", "member", "board", "the", "and", "of", "at", "in"})


def _norm_words(t: Optional[str]) -> str:
    import re
    return " " + " ".join(re.findall(r"[a-z0-9]+", (t or "").lower())) + " "


def role_terms(slot: Optional[str], role: Optional[str]) -> List[str]:
    """Phrases that count as the person's role title on a page: the usual wordings for the slot plus the role the model gave."""
    terms = [_norm_words(x).strip() for x in _ROLE_SYNONYMS.get(slot or "", [])]
    r = _norm_words(role).strip()
    if r:
        terms.append(r)
        terms.extend(w for w in r.split() if len(w) >= 5 and w not in _ROLE_STOP)
    return [t for t in dict.fromkeys(terms) if t]


def page_has_name_and_role(text: Optional[str], name: str, terms: List[str], window: int = 300) -> bool:
    """True when the full name AND a role title appear together on the page (the title within `window` characters of the name)."""
    if not text or not terms:
        return False
    n = _norm_words(text)
    needle = _norm_words(name)
    pos = n.find(needle)
    while pos >= 0:
        seg = n[max(0, pos - window): pos + len(needle) + window]
        if any(" " + t + " " in seg for t in terms):
            return True
        pos = n.find(needle, pos + 1)
    return False


def validate_executive(item: Dict[str, Any], company: str, company_domains: List[str],
                       fetch: Optional[Callable] = None, today: Optional[dt.date] = None,
                       fetch_text: Optional[Callable] = None) -> Dict[str, Any]:
    name = item["name"].strip()
    sources = clean_urls(item.get("source_urls"))
    count = gn_count(f"{_q(name)} {_q(company)}", fetch, today)
    official = [u for u in sources if is_official_source(u, company_domains, company)]
    base = {"pair_count_24m": count["total"], "per_slice": count["per_slice"], "capped": count["capped"], "sources": sources,
            "official_sources": official, "verified_page": None, "verified_pages": [], "method": None, "needs_better_sources": False}
    if not sources:
        return {**base, "accepted": False, "reason": "no source URL"}
    if count["total"] < EXEC_MIN_ANY_NEWS:
        return {**base, "accepted": False, "reason": f"no Google News item for the name with {company} in 24 months"}
    if count["total"] >= EXEC_MIN_PAIR_COUNT:
        return {**base, "accepted": True, "method": "news count", "reason": f"pair count {count['total']} >= {EXEC_MIN_PAIR_COUNT}"}

    def default_fetch(u: str) -> Optional[str]:
        return fetch_page_text(u, allow_pdf=pdf_allowed(u, company_domains, company))

    reader = fetch_text or default_fetch
    terms = role_terms(item.get("slot"), item.get("role"))
    verified = [u for u in sources[:6] if page_has_name_and_role(reader(u), name, terms)]
    official_hit = [u for u in verified if pdf_allowed(u, company_domains, company)]
    if official_hit:
        u = official_hit[0]
        return {**base, "accepted": True, "verified_page": u, "verified_pages": verified, "method": verification_method(u, company_domains, company),
                "reason": f"pair count {count['total']} (1-2) and the name with its role title is on a fetched page on the company domain or NSE/BSE"}
    domains = {registrable_domain(host_of(u)) for u in verified}
    if len(domains) >= 2:
        return {**base, "accepted": True, "verified_page": verified[0], "verified_pages": verified, "method": "two independent domains",
                "reason": f"pair count {count['total']} (1-2) and the name with its role title is on pages of {len(domains)} independent domains"}
    return {**base, "accepted": False, "needs_better_sources": True,
            "reason": f"pair count {count['total']} < {EXEC_MIN_PAIR_COUNT} and the name with its role title was not found on a readable company-domain/NSE/BSE page or on two independent domains"}


_LEGAL_WORDS = frozenset({"limited", "ltd", "pvt", "private", "inc", "corp", "corporation", "llc", "plc", "company", "co", "public"})


def strip_legal_words(name: str) -> str:
    """Name minus trailing legal-form words ("DLF Limited" -> "DLF"). keyword_service.strip_legal_suffix is not used: it
    refuses results under 4 characters, which would leave "DLF Limited" as it was."""
    parts = name.strip().split()
    while len(parts) > 1 and parts[-1].strip(".,").lower() in _LEGAL_WORDS:
        parts.pop()
    return " ".join(parts).strip(" ,.&-")


def name_variants(name: str, aliases: Any = None) -> List[str]:
    """The company's names for a news query: the name without legal words, its core name when that has two or more words, and its
    multi-word aliases ("Macrotech Developers"). A company is reported under any of them."""
    out: List[str] = []
    core = core_name(name)
    # a one-word core ("prestige", "brigade", "lodha") is an ordinary word on its own and would inflate the count: only a core of two or
    # more words is used as a variant, next to the legal-stripped name and the multi-word aliases
    for v in [strip_legal_words(name) or name] + ([core] if len(core.split()) >= 2 else []) + [a for a in (aliases or []) if isinstance(a, str) and len(a.split()) >= 2]:
        v = (v or "").strip()
        if len(v) >= 3 and v.lower() not in {x.lower() for x in out}:
            out.append(v)
    return out


def competitor_query(name: str, context: str, aliases: Any = None) -> str:
    """Exact-phrase name variants joined with OR, plus the context words as plain terms, which Google News ANDs: the sector check
    is "about this company in this sector", not "this exact phrase appears"."""
    names = name_variants(name, aliases)
    head = _q(names[0]) if len(names) == 1 else "(" + " OR ".join(_q(n) for n in names) + ")"
    return f"{head} {context.replace(chr(34), ' ').strip()}".strip()


def _words(s: str) -> List[str]:
    import re
    return [w for w in re.split(r"[^a-z0-9]+", (s or "").lower()) if w]


def core_name(name: str) -> str:
    """Lower-cased name without corporate noise words ("DLF Limited" -> "dlf", "Prestige Estates Projects" -> "prestige estates")."""
    toks = [t for t in _words(name.replace("&", " and ")) if t not in _NOISE_WORDS]
    return " ".join(toks)


_NOISE_WORDS = frozenset({"limited", "ltd", "pvt", "private", "public", "inc", "corp", "corporation", "company", "co", "group",
                          "holdings", "projects", "developers", "com"})


_SAME_COMPANY_EXTRAS = frozenset({"estates", "projects", "online", "group", "developers", "realty", "properties", "enterprises", "limited", "ltd", "com"})


def same_company(a: str, b: str) -> bool:
    """Two spellings of one company: equal core names, or one is the other plus generic words ("Prestige" / "Prestige Estates
    Projects Limited", "Yatra.com" / "Yatra Online Limited"). Different companies of one group ("Reliance Retail") are not merged."""
    ca, cb = _words(core_name(a)), _words(core_name(b))
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    short, long_ = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    return long_[:len(short)] == short and set(long_[len(short):]) <= _SAME_COMPANY_EXTRAS


def is_same_group(competitor_name: str, company: str) -> bool:
    """True when the competitor shares the company's distinctive first word ("Godrej Consumer Products" vs "Godrej
    Properties"): a sister or parent company, not a competitor."""
    head = (_words(company) or [""])[0]
    return len(head) >= 4 and head in _words(competitor_name)


def _as_list(v: Any) -> List[str]:
    if isinstance(v, str):
        return [v] if v.strip() else []
    return [x for x in (v or []) if isinstance(x, str) and x.strip()]


_OWN_PHRASES = ("wholly owned subsidiary of", "wholly owned by", "wholly owned", "subsidiary of", "owned by", "acquired by")


def _variants_norm(name: str) -> List[str]:
    return [" " + _norm_words(v).strip() + " " for v in name_variants(name) if len(v) >= 3]


def ownership_confirmed_on_page(text: Optional[str], child: str, parent: str, window: int = 160) -> bool:
    """True when the page says the child is owned by / a subsidiary of / acquired by the parent: an ownership phrase with the child's
    name just before it and the parent's name just after it."""
    if not text:
        return False
    n = _norm_words(text)
    kids, pars = _variants_norm(child), _variants_norm(parent)
    for ph in _OWN_PHRASES:
        p = n.find(" " + ph + " ")
        while p >= 0:
            left, right = n[max(0, p - window): p + 1], n[p: p + len(ph) + window]
            if any(k in left for k in kids) and any(q in right for q in pars):
                return True
            p = n.find(" " + ph + " ", p + 1)
    return False


def verify_ownership(child: str, parent: str, urls: List[str], fetch_text: Optional[Callable] = None, max_pages: int = 5) -> Optional[str]:
    """First cited page (fetched) that confirms child is owned by parent, else None."""
    reader = fetch_text or (lambda u: fetch_page_text(u, allow_pdf=False))
    for u in clean_urls(urls)[:max_pages]:
        if ownership_confirmed_on_page(reader(u), child, parent):
            return u
    return None


def ownership_claims(item: Dict[str, Any], company: str, company_info: Optional[Dict[str, Any]] = None,
                     other_candidates: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """Every reason this candidate might not be an independent peer, as {basis, child, parent, reason}. basis "name" = it shares the
    client's distinctive first word (decided by the name alone); basis "model" = the model said so (parent / subsidiary / group data),
    which is NOT enough to reject on its own: validate_competitor needs a fetched page that confirms it."""
    info = company_info or {}
    name = item["name"].strip()
    mine = core_name(name)
    out: List[Dict[str, Any]] = []
    if is_same_group(name, company):
        return [{"basis": "name", "child": name, "parent": company, "reason": f"same group as {company} (shares its name), not a competitor"}]
    ours = {core_name(company): company}
    cp = info.get("parent_company")
    if cp:
        ours[core_name(cp)] = cp
    groups = {core_name(x): x for x in _as_list(info.get("group_companies"))}
    ours.pop("", None)
    if cp and mine == core_name(cp):
        out.append({"basis": "model", "child": company, "parent": name, "reason": "is the client's parent company"})
    elif mine in groups:
        out.append({"basis": "model", "child": name, "parent": cp or company, "reason": "is a sister/group company of the client"})
    parent = core_name(item.get("parent_company") or "")
    if parent and parent in ours:
        out.append({"basis": "model", "child": name, "parent": ours[parent], "reason": "belongs to the client's group (parent or sister company)"})
    for x in _as_list(item.get("subsidiaries")):
        if core_name(x) in ours:
            out.append({"basis": "model", "child": ours[core_name(x)], "parent": name, "reason": "is the parent of the client"})
    others = {core_name(x): x for x in (other_candidates or []) if core_name(x) != mine}
    if parent and parent in others:
        out.append({"basis": "model", "child": name, "parent": others[parent],
                    "reason": f"subsidiary of another candidate ({item.get('parent_company')}); the parent is kept instead"})
    return out


def pool_ownership_claims(company: str, company_info: Optional[Dict[str, Any]], competitors: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """The model-made claims in a candidate pool, to ask the follow-up call for a page that states each: [{candidate, child, parent}]."""
    names = [c["name"] for c in competitors]
    out = []
    for c in competitors:
        for cl in ownership_claims(c, company, company_info, names):
            if cl["basis"] == "model":
                out.append({"candidate": c["name"], "child": cl["child"], "parent": cl["parent"]})
    return out


def group_conflict(item: Dict[str, Any], company: str, company_info: Optional[Dict[str, Any]] = None,
                   other_candidates: Optional[List[str]] = None) -> Optional[str]:
    """First ownership reason found (name-based or the model's claim, UNVERIFIED), or None. validate_competitor does the verifying."""
    claims = ownership_claims(item, company, company_info, other_candidates)
    return claims[0]["reason"] if claims else None


def market_conflict(item: Dict[str, Any], primary_market: Optional[str]) -> Optional[str]:
    """None when the candidate is headquartered in the client's primary market. The model's own "mostly operates in the market"
    flag is NOT enough on its own (it marked Booking.com, Agoda and Expedia "primary" in India); it is only used when the
    headquarters country is missing."""
    pm = (primary_market or "").strip().lower()
    if not pm:
        return None
    hq = (item.get("hq_country") or "").strip().lower()
    ops = (item.get("india_operations") or item.get("market_operations") or "").strip().lower()
    if hq:
        if hq == pm or hq.startswith(pm) or pm.startswith(hq):
            return None
        return f"headquartered in {item.get('hq_country')}, not in {primary_market} (presence {ops or 'unknown'}); not a {primary_market}-market peer"
    if ops == "primary":
        return None
    return f"does not operate mainly in {primary_market} (headquarters unknown, presence {ops or 'unknown'})"


def validate_competitor(item: Dict[str, Any], fetch: Optional[Callable] = None, today: Optional[dt.date] = None,
                        company: Optional[str] = None, company_info: Optional[Dict[str, Any]] = None,
                        other_candidates: Optional[List[str]] = None, fetch_text: Optional[Callable] = None,
                        ownership_sources: Optional[Dict[str, List[str]]] = None,
                        candidate_sources: Optional[Dict[str, List[str]]] = None) -> Dict[str, Any]:
    name = item["name"].strip()
    context = (item.get("context_term") or "").strip()
    sources = clean_urls(item.get("source_urls"))
    notes: List[str] = []
    empty = {"accepted": False, "pair_count_24m": None, "per_slice": [], "capped": False, "sources": sources, "notes": notes,
             "listed": item.get("exchange_listed")}
    if company:
        claims = ownership_claims(item, company, company_info, other_candidates)
        if item.get("claim_withdrawn"):
            claims = [c for c in claims if c["basis"] == "name"]
            notes.append("ownership claim withdrawn by the model on the follow-up")
        for cl in claims:
            if cl["basis"] == "name":
                return {**empty, "reason": cl["reason"]}
            urls = list(sources) + list((ownership_sources or {}).get(core_name(name), [])) + list((candidate_sources or {}).get(core_name(cl["parent"]), []))
            url = verify_ownership(cl["child"], cl["parent"], urls, fetch_text)
            if url:
                return {**empty, "reason": f"{cl['reason']} (confirmed on {url})", "ownership_verified": url}
            notes.append(f"ownership claim unverified: {cl['reason']}")
    why = market_conflict(item, (company_info or {}).get("primary_market"))
    if why:
        return {**empty, "reason": why}
    if not context:
        return {**empty, "reason": "no context term, so no sector-consistent count is possible"}
    count = gn_count(competitor_query(name, context, item.get("aliases")), fetch, today)
    accepted = count["total"] >= COMP_MIN_COUNT
    return {"accepted": accepted, "pair_count_24m": count["total"], "per_slice": count["per_slice"], "capped": count["capped"],
            "sources": sources, "notes": notes, "listed": item.get("exchange_listed"),
            "method": "news count (sector)" if accepted else None,
            "reason": f"sector count {count['total']} {'>=' if accepted else '<'} {COMP_MIN_COUNT}"}


def rank_competitors(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Order valid peers by (a) already tracked first, (b) how many answers (the pooled answers and the follow-up) name the company,
    name variants merged, (c) the model's own position for it (the mean of the positions at which it listed it, 1 = first), then
    (d) the validated news count. The news count is only the minimum (COMP_MIN_COUNT) that makes a candidate valid. The model's
    exchange-listed flag is NOT used (it is an informational label only)."""
    def key(x: Dict[str, Any]):
        pos = x.get("positions") or []
        mean_pos = sum(pos) / len(pos) if pos else 99.0
        return (not x.get("tracked"), -(x.get("seen_in") or 0), mean_pos, -(x["validation"].get("pair_count_24m") or 0), x["name"].lower())
    return sorted(items, key=key)


def verify_website(url: Optional[str], company: str, get: Optional[Callable] = None, timeout: int = 12) -> Dict[str, Any]:
    """Does the seed call's website resolve and belong to the company? ok + the bare domain to store on the brand entity."""
    if not url or not isinstance(url, str):
        return {"ok": False, "domain": None, "reason": "no website in the seed answer"}
    if not url.startswith(("http://", "https://")):
        url = "https://" + url.strip()
    try:
        if get is None:
            import requests
            get = requests.get
        r = get(url, timeout=timeout, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (compatible; xoop-seeding-check)"})
        status = getattr(r, "status_code", 200)
        final = getattr(r, "url", url) or url
        text = (getattr(r, "text", "") or "")[:200000]
    except Exception as e:
        return {"ok": False, "domain": None, "reason": f"did not resolve: {e!r}"[:160]}
    if status >= 400:
        return {"ok": False, "domain": None, "reason": f"HTTP {status}"}
    host = host_of(final)
    domain = host[4:] if host.startswith("www.") else host
    if domain_matches_company(host, company):
        return {"ok": True, "domain": domain, "reason": "resolves; the domain is named like the company"}
    import re
    page = " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "
    words = _words(company)
    if words and " " + " ".join(words) + " " in page:
        return {"ok": True, "domain": domain, "reason": "resolves; the company name is on the page"}
    return {"ok": False, "domain": None, "reason": f"resolves ({domain}) but neither the domain nor the page matches the company name"}
