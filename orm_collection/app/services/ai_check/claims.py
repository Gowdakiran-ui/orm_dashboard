"""
Cross-check of what an AI says (flagged sentences, see triage.py) against what XOOP itself holds about the client.

For each flagged sentence (a serious accusation about the client or an executive, stated as plain fact) one cheap model call
(Claude Haiku 4.5, temperature 0) is given the sentence and the numbered list of the client's XOOP incidents (the flagged risk
documents grouped into incidents, incidents.py) and answers with the number of the incident that is the SAME event, or none. The
answer is stored with the flag (ai_check_flags.matched_document_id = the incident's lead document, migration 0021), so reading the
card costs nothing. The card then shows that incident's case status (allegation, probe, charged, penalty_or_order, settled ...), read
live. When the AI states as fact something XOOP labels allegation, probe or charged, a one-line note says so.
This replaces the earlier word-overlap match, which missed sentences that share only a case name with the incident (a Godrej FIR
sentence and the CBI-FIR incident share only the word "FIR").

Super admin only (the endpoint fills this for super admins and returns nothing otherwise). Reads risk events; writes only the match
columns of ai_check_flags; no score reads it. Nothing here judges whether a sentence is true.
"""
import re
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.services.intelligence.incidents import group_incidents, outlet_of
from app.services.seeding.proposer import MODEL, OPENROUTER_URL

EST_COST_PER_MATCH_CALL = 0.0011     # measured 2026-11-09: $0.00103-0.00114 per call (21 calls, $0.0226), rounded up
MATCH_CALLS_ESTIMATE = 12            # about 10-11 flagged sentences per client run
MENU_LIMIT = 30                      # incidents shown to the model (strongest first)
AS_FACT_NOTE_STATUSES = ("allegation", "probe", "charged")
_STATUS_WORD = {"allegation": "an allegation", "probe": "a probe", "charged": "charged"}

MATCH_SYSTEM = (
    "You match ONE sentence an AI wrote about a company with a numbered list of incidents a monitoring system tracks about the same "
    "company. Choose the incident only if the sentence is about the SAME event: the same case, proceeding, order or episode. The "
    "same company, the same kind of accusation or the same law is NOT enough (two different FIRs are two different events; a fine "
    "and a criminal case are different events). If no incident is the same event, answer null.\n"
    "Reply ONLY with JSON: {\"incident\": <number from the list or null>}"
)


def xoop_incidents(db, client) -> List[Dict[str, Any]]:
    """The client's flagged documents (score above LOW, not a competitor's) grouped into incidents. Each: title (the strongest
    document's), status (that document's case-status label, or None), event (its case-event phrase), documents, sources, score,
    lead_doc_id and doc_ids (every member)."""
    from app.models.document import Document
    from app.models.entity import Entity
    from app.models.risk import RiskEvent
    from app.core.risk_config import RISK_THRESHOLDS
    from sqlalchemy import or_

    best: Dict[Any, Any] = {}
    q = db.query(RiskEvent.document_id, RiskEvent.entity_id, RiskEvent.risk_score, RiskEvent.explainability,
                 Document.title, Document.published_at).join(Document, Document.id == RiskEvent.document_id).outerjoin(
        Entity, Entity.id == RiskEvent.entity_id).filter(
        RiskEvent.client_id == client.id, RiskEvent.risk_score > RISK_THRESHOLDS["LOW_TO_MEDIUM"],
        or_(Entity.entity_type != "competitor", Entity.entity_type.is_(None), RiskEvent.entity_id.is_(None)))
    for doc_id, entity_id, score, expl, title, published in q.all():
        if doc_id not in best or score > best[doc_id]["score"]:
            ex = expl or {}
            best[doc_id] = {"doc_id": doc_id, "entity_id": entity_id, "entity_name": client.name, "score": score, "title": title,
                            "published_at": published, "status": ex.get("case_status"), "event": ex.get("case_event")}
    items = sorted(best.values(), key=lambda i: str(i["doc_id"]))
    out = []
    for group in group_incidents(items):
        members = [items[i] for i in group]
        lead = max(members, key=lambda m: (m["score"], m["published_at"].timestamp() if m["published_at"] else 0.0, str(m["doc_id"])))
        out.append({
            "title": lead["title"] or "Untitled document", "status": lead["status"], "event": lead["event"], "score": lead["score"],
            "documents": len(members), "sources": len({outlet_of(m["title"]) or f"doc:{m['doc_id']}" for m in members}),
            "lead_doc_id": lead["doc_id"], "doc_ids": [m["doc_id"] for m in members],
        })
    return out


def incident_menu(incidents: Sequence[Dict[str, Any]], limit: int = MENU_LIMIT) -> List[Dict[str, Any]]:
    """The incidents the model chooses from, strongest first (score, then document count, then title: a fixed order)."""
    ranked = sorted(incidents, key=lambda i: (-(i["score"] or 0.0), -i["documents"], i["title"]))
    return ranked[:limit]


def menu_text(menu: Sequence[Dict[str, Any]]) -> str:
    lines = []
    for n, inc in enumerate(menu, 1):
        ev = f" (event: {inc['event']})" if inc.get("event") else ""
        lines.append(f"{n}. [{inc.get('status') or 'no status'}] {re.sub(chr(10), ' ', inc['title'])[:140]}{ev}")
    return "\n".join(lines)


def parse_match(text: Optional[str], size: int) -> Optional[Dict[str, Any]]:
    """Read the model's answer with a regex (it wraps JSON in code fences). {"index": 0-based or None} or None when unreadable
    (no answer, or a number outside the list)."""
    if not text:
        return None
    m = re.search(r'"?incident"?\s*:\s*"?(null|none|[0-9]+)', text, re.IGNORECASE)
    if not m:
        return None
    v = m.group(1).lower()
    if v in ("null", "none"):
        return {"index": None}
    n = int(v)
    if 1 <= n <= size:
        return {"index": n - 1}
    return None


def match_sentence(sentence: str, event: Optional[str], menu: Sequence[Dict[str, Any]], api_key: str,
                   post: Optional[Callable] = None, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
    """One model call. {"index": position in `menu` or None, "cost_usd"} or None on any failure (the flag stays unchecked)."""
    if not api_key or not sentence or not menu:
        return None
    if post is None:
        import requests
        post = requests.post
    user = "Sentence: %s\nEvent in short: %s\n\nIncidents:\n%s" % (sentence[:600], event or "unknown", menu_text(menu))
    try:
        resp = post(OPENROUTER_URL, headers={"Authorization": "Bearer " + api_key},
                    json={"model": MODEL, "messages": [{"role": "system", "content": MATCH_SYSTEM}, {"role": "user", "content": user}],
                          "temperature": 0, "max_tokens": 30, "usage": {"include": True}}, timeout=timeout)
        if getattr(resp, "status_code", 200) != 200:
            return None
        data = resp.json()
        parsed = parse_match(data["choices"][0]["message"]["content"], len(menu))
        if parsed is None:
            return None
        cost = (data.get("usage") or {}).get("cost")
        parsed["cost_usd"] = float(cost) if isinstance(cost, (int, float)) else 0.0
        return parsed
    except Exception:
        return None


def match_run_flags(db, run, client, api_key: str, post: Optional[Callable] = None, cap_usd: float = 0.60,
                    log: Optional[Callable[[str], None]] = None) -> int:
    """For every flagged sentence of the run that has not been checked yet: one model call, stored on the flag (the matched incident's
    lead document, or NULL) and added to the run's cost. A failed call leaves the flag unchecked (a later run of this function retries
    it). Stops before a call that could take the run past the cap. Returns the number of sentences matched to an incident."""
    from app.models.ai_check import AiCheckFlag
    say = log or (lambda m: None)
    todo = db.query(AiCheckFlag).filter(AiCheckFlag.run_id == run.id, AiCheckFlag.flagged.is_(True),
                                        AiCheckFlag.match_checked.is_(False)).order_by(AiCheckFlag.created_at, AiCheckFlag.id).all()
    if not todo:
        return 0
    menu = incident_menu(xoop_incidents(db, client))
    matched = 0
    for f in todo:
        if not menu:
            f.match_checked, f.matched_document_id, f.match_cost_usd = True, None, 0.0    # nothing to match against: no call needed
            db.commit()
            continue
        if (run.cost_usd or 0.0) + EST_COST_PER_MATCH_CALL > cap_usd:
            say("  claim matching stopped at the cost cap")
            break
        res = match_sentence(f.sentence, f.event, menu, api_key, post=post)
        if res is None:
            continue
        run.cost_usd = (run.cost_usd or 0.0) + res["cost_usd"]
        f.match_checked, f.match_cost_usd = True, res["cost_usd"]
        f.matched_document_id = menu[res["index"]]["lead_doc_id"] if res["index"] is not None else None
        matched += 1 if res["index"] is not None else 0
        db.commit()
    return matched


def claim_note(framing: str, matched: Optional[Dict[str, Any]]) -> str:
    if not matched:
        return "Not matched automatically."
    status = matched.get("status")
    if framing == "FACT" and status in AS_FACT_NOTE_STATUSES:
        return f"The AI states this as fact; XOOP labels the matching story {_STATUS_WORD[status]}."
    if status is None:
        return "Matching XOOP incident has no case status yet."
    return f"Matches an XOOP incident labelled {status.replace('_', ' ')}."


def build_claim_checks(db, client, flags: Sequence[Any], question_labels: Dict[str, str]) -> List[Dict[str, Any]]:
    """One entry per flagged sentence: the sentence, where the AI said it, and the matching XOOP incident (or None) with the note.
    The match is the stored one: the incident that currently contains the stored lead document (so its status is read live)."""
    flagged = [f for f in flags if f.flagged]
    if not flagged:
        return []
    incidents = xoop_incidents(db, client) if any(getattr(f, "matched_document_id", None) for f in flagged) else []
    by_doc = {d: inc for inc in incidents for d in inc["doc_ids"]}
    out = []
    for f in flagged:
        match = by_doc.get(f.matched_document_id) if getattr(f, "matched_document_id", None) else None
        occ = f.occurrences or []
        out.append({
            "sentence": f.sentence,
            "questions": [question_labels.get(o.get("prompt"), o.get("prompt")) for o in occ],
            "repeats": sorted({r for o in occ for r in (o.get("repeats") or [])}),
            "about": f.about, "event": f.event, "inline_domains": f.inline_domains or [],
            "matched": None if not match else {"status": match["status"], "title": match["title"], "documents": match["documents"], "sources": match["sources"]},
            "note": claim_note(f.framing or "FACT", match),
        })
    return out
